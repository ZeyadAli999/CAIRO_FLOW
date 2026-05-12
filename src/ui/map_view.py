"""The Cairo map. Pure presentation — every layer is rebuilt from DB on
each call to `render_map()`, which is fine at 25 nodes / 28 edges.

Phase 3 adds polished node rendering (halo rings, sqrt(pop) radii),
route overlays with per-segment congestion coloring, and emergency
overlays with A* exploration markers.
"""
from __future__ import annotations

import math

from dash import html
import dash_leaflet as dl

from src.config import (
    DARK_TILE_ATTRIBUTION,
    DARK_TILE_URL,
    MAP_CENTER,
    MAP_ZOOM,
)
from src.db.queries import (
    all_existing_roads,
    all_facilities,
    all_neighborhoods,
    node_lookup,
)
from src.ui.theme import COLORS


# ---------------------------------------------------------------------------
# Node sizing — Phase 3 polish formula
# ---------------------------------------------------------------------------

_RADIUS_FLOOR = 4.0
_RADIUS_CAP = 14.0
_POP_DIVISOR = 50_000


def _node_radius(population: int | None) -> float:
    if not population or population <= 0:
        return _RADIUS_FLOOR
    r = _RADIUS_FLOOR + math.sqrt(population / _POP_DIVISOR) * 1.2
    return min(r, _RADIUS_CAP)


# ---------------------------------------------------------------------------
# Base layers
# ---------------------------------------------------------------------------

def _neighborhood_layer() -> dl.LayerGroup:
    children = []
    for n in all_neighborhoods():
        radius = _node_radius(n.population)
        tooltip = f"{n.name}  —  {n.type}  ·  pop {n.population:,}"
        # Halo ring (slightly larger, 30% opacity).
        children.append(
            dl.CircleMarker(
                center=(n.y, n.x),
                radius=radius + 4,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 1,
                    "opacity": 0.30,
                    "fillOpacity": 0,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(n.y, n.x),
                radius=radius,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 1.5,
                    "opacity": 0.9,
                    "fillColor": COLORS["accent"],
                    "fillOpacity": 0.18,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(tooltip, sticky=True),
            )
        )
    return dl.LayerGroup(children, id="neighborhoods-layer")


def _facility_layer() -> dl.LayerGroup:
    children = []
    for f in all_facilities():
        tooltip = f"{f.name}  —  {f.type}"
        # Halo
        children.append(
            dl.CircleMarker(
                center=(f.y, f.x),
                radius=10,
                pathOptions={
                    "color": COLORS["accent_warm"],
                    "weight": 1,
                    "opacity": 0.30,
                    "fillOpacity": 0,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(f.y, f.x),
                radius=6,
                pathOptions={
                    "color": COLORS["accent_warm"],
                    "weight": 2,
                    "opacity": 0.95,
                    "fillColor": COLORS["bg_primary"],
                    "fillOpacity": 1.0,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(tooltip, sticky=True),
            )
        )
    return dl.LayerGroup(children, id="facilities-layer")


def _road_layer() -> dl.LayerGroup:
    nodes = node_lookup()
    children = []
    for r in all_existing_roads():
        a = nodes.get(r.from_id)
        b = nodes.get(r.to_id)
        if not a or not b:
            continue
        children.append(
            dl.Polyline(
                positions=[(a["y"], a["x"]), (b["y"], b["x"])],
                pathOptions={
                    "color": COLORS["road"],
                    "weight": 1.5,
                    "opacity": 0.85,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
    return dl.LayerGroup(children, id="roads-layer")


def _legacy_leaflet_map() -> dl.Map:
    """Hidden compatibility map.

    Existing Dash callbacks still target these Leaflet layer IDs. The
    premium MapLibre view is the visible map, while this map preserves the
    established callback contract without touching algorithm code.
    """
    return dl.Map(
        id="cairo-map",
        center=MAP_CENTER,
        zoom=MAP_ZOOM,
        zoomControl=True,
        scrollWheelZoom=True,
        style={"width": "1px", "height": "1px", "opacity": 0, "pointerEvents": "none"},
        children=[
            dl.TileLayer(url=DARK_TILE_URL, attribution=DARK_TILE_ATTRIBUTION),
            _road_layer(),
            # MST overlays
            dl.LayerGroup(id="mst-glow-layer", children=[]),
            dl.LayerGroup(id="mst-edges-layer", children=[]),
            # Route overlays — alternates beneath, primary on top
            dl.LayerGroup(id="route-alts-layer", children=[]),
            dl.LayerGroup(id="route-glow-layer", children=[]),
            dl.LayerGroup(id="route-edges-layer", children=[]),
            # Emergency overlays
            dl.LayerGroup(id="em-explored-layer", children=[]),
            dl.LayerGroup(id="em-glow-layer", children=[]),
            dl.LayerGroup(id="em-edges-layer", children=[]),
            # Base markers
            _neighborhood_layer(),
            _facility_layer(),
            # Marker overlays drawn on top
            dl.LayerGroup(id="mst-nodes-layer", children=[]),
            dl.LayerGroup(id="route-markers-layer", children=[]),
            dl.LayerGroup(id="em-markers-layer", children=[]),
            # Maintain (Phase 4) — beneath the markers but above MST.
            dl.LayerGroup(id="maintain-poor-layer", children=[]),
            dl.LayerGroup(id="maintain-selected-layer", children=[]),
            # Transit (Phase 4)
            dl.LayerGroup(id="transit-bus-layer", children=[]),
            dl.LayerGroup(id="transit-metro-layer", children=[]),
            dl.LayerGroup(id="transit-hubs-layer", children=[]),
        ],
    )


def render_map() -> html.Div:
    return html.Div(
        [
            html.Iframe(
                id="cairo-maplibre",
                src="/assets/maplibre_view.html",
                className="cf-maplibre-frame",
                title="CairoFlow Egypt Smart City Map",
            ),
            _legacy_leaflet_map(),
        ],
        className="cf-map-stage",
    )


# ---------------------------------------------------------------------------
# MST overlay rendering (Phase 2 — kept here for cohesion)
# ---------------------------------------------------------------------------

def mst_edge_layers(mst_graph, node_positions: dict[str, tuple[float, float]]):
    glow: list = []
    edges: list = []
    for u, v, data in mst_graph.edges(data=True):
        if u not in node_positions or v not in node_positions:
            continue
        a = node_positions[u]
        b = node_positions[v]
        positions = [(a[1], a[0]), (b[1], b[0])]
        is_potential = data.get("road_type") == "potential"
        glow.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 8,
                    "opacity": 0.18,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
        edges.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 3,
                    "opacity": 0.95,
                    "dashArray": "6 6" if is_potential else None,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(
                    f"{'New road' if is_potential else 'Existing road'}  ·  "
                    f"{data.get('distance_km', 0):.1f} km"
                    + (f"  ·  EGP {data.get('cost_million_egp', 0):.0f}M"
                       if is_potential else ""),
                    sticky=True,
                ),
            )
        )
    return glow, edges


def mst_node_highlights(nodes_explored, node_positions):
    out = []
    for n in nodes_explored:
        if n not in node_positions:
            continue
        x, y = node_positions[n]
        out.append(
            dl.CircleMarker(
                center=(y, x),
                radius=10,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 2,
                    "opacity": 0.85,
                    "fillOpacity": 0,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
    return out


# ---------------------------------------------------------------------------
# Phase 3 — Route + Emergency overlays
# ---------------------------------------------------------------------------

# Congestion thresholds → color
def congestion_color(ratio: float) -> str:
    if ratio < 0.6:
        return COLORS["success"]   # green
    if ratio < 0.85:
        return "#eab308"           # amber
    return COLORS["danger"]        # red


def route_overlay_layers(segments, node_positions):
    """Returns (glow_children, edge_children) for the primary route.

    `segments` is the list returned by
    `shortest_path.path_segments(G, path, time_of_day)`.
    """
    glow: list = []
    edges: list = []
    for seg in segments:
        u, v = seg["from"], seg["to"]
        if u not in node_positions or v not in node_positions:
            continue
        ax, ay = node_positions[u]
        bx, by = node_positions[v]
        positions = [(ay, ax), (by, bx)]
        color = congestion_color(seg["congestion"])
        # Outer glow
        glow.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 11,
                    "opacity": 0.18,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
        edges.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": color,
                    "weight": 5,
                    "opacity": 0.95,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(
                    f"{u} → {v}  ·  {seg['distance_km']:.1f} km  ·  "
                    f"v/c {int(seg['congestion'] * 100)}%  ·  "
                    f"{seg['travel_time_h'] * 60.0:.1f} min",
                    sticky=True,
                ),
            )
        )
    return glow, edges


def route_marker_layers(source: str, target: str, node_positions):
    children: list = []
    if source in node_positions:
        sx, sy = node_positions[source]
        # Pulsing source halo
        children.append(
            dl.CircleMarker(
                center=(sy, sx),
                radius=14,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 2,
                    "opacity": 0.4,
                    "fillOpacity": 0,
                    "className": "cf-pulse",
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(sy, sx),
                radius=7,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 2,
                    "opacity": 1.0,
                    "fillColor": COLORS["accent"],
                    "fillOpacity": 0.9,
                },
                children=dl.Tooltip(f"FROM  {source}", sticky=True),
            )
        )
    if target in node_positions:
        tx, ty = node_positions[target]
        # Target ring + dot (a simple "pin" stand-in)
        children.append(
            dl.CircleMarker(
                center=(ty, tx),
                radius=12,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 2.5,
                    "opacity": 1.0,
                    "fillOpacity": 0,
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(ty, tx),
                radius=4,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 1,
                    "opacity": 1.0,
                    "fillColor": COLORS["accent"],
                    "fillOpacity": 1.0,
                },
                children=dl.Tooltip(f"TO  {target}", sticky=True),
            )
        )
    return children


def alternative_routes_layer(routes: list[dict], node_positions, selected_idx: int | None = None):
    """Renders the alternative routes (excluding the primary, which is
    drawn separately by `route_overlay_layers`). The first route is
    treated as primary and is omitted here."""
    if not routes:
        return []
    children: list = []
    styles = [
        {"weight": 5, "opacity": 0.95, "dashArray": None},   # primary (drawn elsewhere too — emphasized when selected)
        {"weight": 3, "opacity": 0.60, "dashArray": "10 6"},
        {"weight": 3, "opacity": 0.40, "dashArray": "2 6"},
    ]
    for i, r in enumerate(routes[1:], start=1):
        positions = []
        for u, v in zip(r["path"][:-1], r["path"][1:]):
            if u not in node_positions or v not in node_positions:
                continue
            ax, ay = node_positions[u]
            bx, by = node_positions[v]
            positions.append((ay, ax))
            positions.append((by, bx))
        if not positions:
            continue
        style = styles[min(i, len(styles) - 1)]
        # Boost selected
        weight = style["weight"] + (3 if selected_idx == i else 0)
        opacity = min(1.0, style["opacity"] + (0.35 if selected_idx == i else 0))
        # Draw as one polyline per segment for cleaner caps
        for u, v in zip(r["path"][:-1], r["path"][1:]):
            if u not in node_positions or v not in node_positions:
                continue
            ax, ay = node_positions[u]
            bx, by = node_positions[v]
            children.append(
                dl.Polyline(
                    positions=[(ay, ax), (by, bx)],
                    pathOptions={
                        "color": COLORS["accent"],
                        "weight": weight,
                        "opacity": opacity,
                        "dashArray": style["dashArray"],
                        "lineCap": "round",
                        "lineJoin": "round",
                    },
                    children=dl.Tooltip(
                        f"Alt {i+1}  ·  {r['travel_time_min']:.1f} min  ·  "
                        f"{r['distance_km']:.1f} km",
                        sticky=True,
                    ),
                )
            )
    return children


def emergency_overlay_layers(segments, node_positions):
    glow: list = []
    edges: list = []
    for seg in segments:
        u, v = seg["from"], seg["to"]
        if u not in node_positions or v not in node_positions:
            continue
        ax, ay = node_positions[u]
        bx, by = node_positions[v]
        positions = [(ay, ax), (by, bx)]
        glow.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 14,
                    "opacity": 0.20,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
            )
        )
        edges.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 6,
                    "opacity": 0.95,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(
                    f"{u} → {v}  ·  {seg['distance_km']:.1f} km  ·  "
                    f"{seg['travel_time_h'] * 60.0:.1f} min",
                    sticky=True,
                ),
            )
        )
    return glow, edges


def emergency_explored_layer(nodes_explored: list, node_positions):
    """Faded red dots at every node A* visited — visualizes the
    'searched but not selected' frontier."""
    out = []
    for n in nodes_explored:
        if n not in node_positions:
            continue
        x, y = node_positions[n]
        out.append(
            dl.CircleMarker(
                center=(y, x),
                radius=4,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 1,
                    "opacity": 0.35,
                    "fillColor": COLORS["danger"],
                    "fillOpacity": 0.30,
                },
            )
        )
    return out


def emergency_marker_layers(source: str, target: str | None, node_positions):
    children: list = []
    if source in node_positions:
        sx, sy = node_positions[source]
        children.append(
            dl.CircleMarker(
                center=(sy, sx),
                radius=14,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 2,
                    "opacity": 0.45,
                    "fillOpacity": 0,
                    "className": "cf-pulse-danger",
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(sy, sx),
                radius=7,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 2,
                    "opacity": 1.0,
                    "fillColor": COLORS["danger"],
                    "fillOpacity": 0.9,
                },
                children=dl.Tooltip(f"INCIDENT  {source}", sticky=True),
            )
        )
    if target and target in node_positions:
        tx, ty = node_positions[target]
        # Cross marker: two short Polylines forming a +
        children.append(
            dl.Polyline(
                positions=[(ty - 0.004, tx), (ty + 0.004, tx)],
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 3,
                    "opacity": 1.0,
                    "lineCap": "round",
                },
            )
        )
        children.append(
            dl.Polyline(
                positions=[(ty, tx - 0.004), (ty, tx + 0.004)],
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 3,
                    "opacity": 1.0,
                    "lineCap": "round",
                },
            )
        )
        children.append(
            dl.CircleMarker(
                center=(ty, tx),
                radius=12,
                pathOptions={
                    "color": COLORS["danger"],
                    "weight": 2,
                    "opacity": 0.7,
                    "fillOpacity": 0,
                },
                children=dl.Tooltip(f"FACILITY  {target}", sticky=True),
            )
        )
    return children


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def node_position_lookup() -> dict[str, tuple[float, float]]:
    """Single source of truth for `(x, y)` per node ID."""
    out: dict[str, tuple[float, float]] = {}
    for n in all_neighborhoods():
        out[n.id] = (n.x, n.y)
    for f in all_facilities():
        out[f.id] = (f.x, f.y)
    return out


def node_name_lookup() -> dict[str, str]:
    out: dict[str, str] = {}
    for n in all_neighborhoods():
        out[n.id] = n.name
    for f in all_facilities():
        out[f.id] = f.name
    return out


# ---------------------------------------------------------------------------
# Phase 4 — Maintain & Transit overlays
# ---------------------------------------------------------------------------

_AMBER = "#f59e0b"
_AMBER_DIM = "#92400e"


def maintain_poor_layer(poor_roads: list[dict], node_positions):
    """Dim amber lines for every poor-condition road that's not selected."""
    out = []
    for r in poor_roads:
        u, v = str(r["from"]), str(r["to"])
        if u not in node_positions or v not in node_positions:
            continue
        ax, ay = node_positions[u]
        bx, by = node_positions[v]
        out.append(
            dl.Polyline(
                positions=[(ay, ax), (by, bx)],
                pathOptions={
                    "color": _AMBER,
                    "weight": 2,
                    "opacity": 0.30,
                    "lineCap": "round",
                    "lineJoin": "round",
                    "dashArray": "4 4",
                },
                children=dl.Tooltip(
                    f"Poor — condition {r['condition']}, "
                    f"{r['distance_km']:.1f} km",
                    sticky=True,
                ),
            )
        )
    return out


def maintain_selected_layer(selected_roads: list[dict], node_positions):
    """Bright amber selected roads + outer pulsing glow."""
    out = []
    for r in selected_roads:
        u, v = str(r["from"]), str(r["to"])
        if u not in node_positions or v not in node_positions:
            continue
        ax, ay = node_positions[u]
        bx, by = node_positions[v]
        positions = [(ay, ax), (by, bx)]
        # Glow
        out.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": _AMBER,
                    "weight": 10,
                    "opacity": 0.20,
                    "lineCap": "round",
                    "lineJoin": "round",
                    "className": "cf-pulse-amber",
                },
            )
        )
        # Stroke
        out.append(
            dl.Polyline(
                positions=positions,
                pathOptions={
                    "color": _AMBER,
                    "weight": 4,
                    "opacity": 0.95,
                    "lineCap": "round",
                    "lineJoin": "round",
                },
                children=dl.Tooltip(
                    f"Selected — EGP {r['cost_million_egp']:.0f}M  ·  "
                    f"value {r['value']:.2f}  ·  cond {r['condition']}",
                    sticky=True,
                ),
            )
        )
    return out


# Transit ----------------------------------------------------------

_METRO_PALETTE = ["#ef4444", "#f59e0b", "#a855f7", "#22c55e", "#06b6d4"]


def transit_metro_layer(metro_lines: list, node_positions):
    """Solid bold lines for each metro line — one color per line."""
    out = []
    for i, ml in enumerate(metro_lines or []):
        stations = _split_csv(_get(ml, "stations"))
        line_id = _get(ml, "line_id") or f"M{i+1}"
        color = _METRO_PALETTE[i % len(_METRO_PALETTE)]
        for u, v in zip(stations[:-1], stations[1:]):
            if u not in node_positions or v not in node_positions:
                continue
            ax, ay = node_positions[u]
            bx, by = node_positions[v]
            out.append(
                dl.Polyline(
                    positions=[(ay, ax), (by, bx)],
                    pathOptions={
                        "color": color,
                        "weight": 4,
                        "opacity": 0.85,
                        "lineCap": "round",
                        "lineJoin": "round",
                    },
                    children=dl.Tooltip(f"{line_id}", sticky=True),
                )
            )
    return out


def transit_bus_layer(bus_routes: list, node_positions):
    """Dashed soft-yellow lines for every bus route."""
    out = []
    for br in bus_routes or []:
        stops = _split_csv(_get(br, "stops"))
        rid = _get(br, "route_id")
        for u, v in zip(stops[:-1], stops[1:]):
            if u not in node_positions or v not in node_positions:
                continue
            ax, ay = node_positions[u]
            bx, by = node_positions[v]
            out.append(
                dl.Polyline(
                    positions=[(ay, ax), (by, bx)],
                    pathOptions={
                        "color": "#fde047",
                        "weight": 2,
                        "opacity": 0.55,
                        "dashArray": "6 4",
                        "lineCap": "round",
                        "lineJoin": "round",
                    },
                    children=dl.Tooltip(f"Bus {rid}", sticky=True),
                )
            )
    return out


def transit_hubs_layer(transfer_ranking: list[dict], node_positions):
    """Bigger cyan rings around top transfer hubs, sized by usage."""
    out = []
    if not transfer_ranking:
        return out
    max_count = max(r["transfer_count"] for r in transfer_ranking) or 1
    for r in transfer_ranking[:10]:
        nid = str(r["node_id"])
        if nid not in node_positions:
            continue
        x, y = node_positions[nid]
        radius = 10 + 14 * (r["transfer_count"] / max_count)
        out.append(
            dl.CircleMarker(
                center=(y, x),
                radius=radius,
                pathOptions={
                    "color": COLORS["accent"],
                    "weight": 2,
                    "opacity": 0.85,
                    "fillColor": COLORS["accent"],
                    "fillOpacity": 0.15,
                    "lineCap": "round",
                },
                children=dl.Tooltip(
                    f"{r['name']}  ·  {r['transfer_count']} transfers  ·  "
                    f"{r['weighted_demand']:.0f} pax/day",
                    sticky=True,
                ),
            )
        )
    return out


def _get(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _split_csv(s):
    if not s:
        return []
    return [tok.strip() for tok in str(s).split(",") if tok.strip()]
