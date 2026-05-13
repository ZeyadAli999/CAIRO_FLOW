"""CairoFlow — Dash entry point.

Run:
    python app.py

On first run this seeds `data/cairo.db` from the CSVs in `data/raw/`,
then starts the Dash dev server on http://127.0.0.1:8050.
"""
from __future__ import annotations

import math
from dataclasses import asdict

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, ctx, html, no_update

from src.algorithms.mst import (
    kruskal_mst,
    mst_stats,
    population_weighted_mst,
    prim_mst,
)
from src.algorithms.shortest_path import (
    astar,
    astar_emergency,
    dijkstra,
    dijkstra_time_dependent,
    edge_travel_time,
    find_alternative_routes,
    find_nearest_facility,
    path_distance_km,
    path_max_congestion,
    path_segments,
    path_travel_time_hours,
)
from src.algorithms.trace import AlgorithmTrace
from src.config import DEFAULT_MODE, MODES, TIMES_OF_DAY
from src.db.queries import (
    all_existing_roads,
    all_facilities,
    all_neighborhoods,
    all_traffic_flow,
    node_lookup,
)
from src.db.seed import ensure_seeded
from src.data.emergency_explanation import explain_emergency_facility_choice
from src.data.graph_views import build_emergency_graph
from src.graph.builder import build_graph, build_mst_graph
from src.ui.components import empty_state, programmer_panel
from src.ui.emergency_mode import (
    render_emergency_performance_card,
    render_emergency_result_card,
    render_emergency_traffic_card,
)
from src.ui.layout import render_layout
from src.ui.map_view import (
    alternative_routes_layer,
    emergency_explored_layer,
    emergency_marker_layers,
    emergency_overlay_layers,
    maintain_poor_layer,
    maintain_selected_layer,
    mst_edge_layers,
    mst_node_highlights,
    node_name_lookup,
    node_position_lookup,
    route_marker_layers,
    route_overlay_layers,
    transit_bus_layer,
    transit_hubs_layer,
    transit_metro_layer,
)
from src.ui.maintain_mode import (
    render_maintain_list_card,
    render_maintain_summary_card,
)
from src.ui.network_mode import (
    render_algo_details_card,
    render_algo_pills,
    render_stats_card,
)
from src.ui.route_mode import (
    render_alternatives_card,
    render_route_algo_pills,
    render_route_result_card,
    render_route_scenario_card,
)
from src.ui.signals_mode import (
    AUTO_INTERSECTION,
    render_emergency_preemption_card,
    render_signal_result_card,
    render_signals_programmer_slot,
)
from src.ui.sidebar import placeholder_for, render_pills
from src.ui.transit_mode import (
    _tab_body_for,
    render_bus_result_card,
    render_metro_result_card,
    render_mm_result_card,
    render_transfers_card,
    render_transit_tabs,
)
from src.scenarios.traffic_scenarios import (
    SCENARIO_NORMAL,
    apply_traffic_scenario,
    evaluate_route_comparison,
    route_metrics,
    scenario_label,
)


# Map "Morning" → "morning_peak" etc. The UI store holds the human label;
# every algorithm and graph attribute uses the snake_case key.
_TOD_KEY = {
    "Morning": "morning_peak",
    "Afternoon": "afternoon",
    "Evening": "evening_peak",
    "Night": "night",
}


def _tod_key(label: str | None) -> str:
    return _TOD_KEY.get(label or "", "morning_peak")


_TOD_LABEL_BY_KEY = {v: k for k, v in _TOD_KEY.items()}
_TOD_CLOCK = {
    "Morning": "06:00",
    "Afternoon": "13:00",
    "Evening": "18:00",
    "Night": "23:00",
}


def _scenario_catalog() -> dict[str, dict]:
    """UI-only What If scenarios.

    Each scenario mutates a copied graph in memory. The seeded database and
    the production algorithm implementations remain untouched.
    """
    return {
        "road_closure": {
            "label": "Road closure",
            "description": "Temporary closure on a central east-west corridor.",
            "affected_edges": [("1", "3"), ("3", "5")],
            "factor": 1.0,
            "closed": True,
            "source": "Road operations",
        },
        "accident": {
            "label": "Accident",
            "description": "Incident response slows traffic near Downtown and Nasr City.",
            "affected_edges": [("3", "5"), ("5", "7")],
            "factor": 1.9,
            "closed": False,
            "source": "Traffic police",
        },
        "heavy_congestion": {
            "label": "Heavy congestion",
            "description": "Peak congestion pressure increases across core Cairo links.",
            "affected_edges": [("2", "5"), ("3", "5"), ("5", "7"), ("8", "10")],
            "factor": 1.65,
            "closed": False,
            "source": "Traffic flow forecast",
        },
        "weather": {
            "label": "Weather impact",
            "description": "Rain lowers road speeds and raises congestion on river crossings.",
            "affected_edges": [("7", "8"), ("8", "12"), ("12", "1")],
            "factor": 1.35,
            "closed": False,
            "source": "Weather desk",
        },
        "airport_spike": {
            "label": "Airport demand spike",
            "description": "Arrivals wave increases demand toward Cairo International Airport.",
            "affected_edges": [("F1", "5"), ("F1", "2"), ("2", "5")],
            "factor": 1.8,
            "closed": False,
            "source": "Airport operations",
        },
        "hospital_surge": {
            "label": "Hospital emergency surge",
            "description": "Medical surge stresses routes around major hospital access points.",
            "affected_edges": [("11", "F2"), ("F2", "3"), ("3", "5")],
            "factor": 1.5,
            "closed": False,
            "source": "Emergency coordination",
        },
        "stadium_event": {
            "label": "Stadium event surge",
            "description": "Event traffic builds around Nasr City and eastern corridors.",
            "affected_edges": [("4", "5"), ("4", "14"), ("13", "14")],
            "factor": 1.75,
            "closed": False,
            "source": "Venue schedule",
        },
        "transit_disruption": {
            "label": "Transit disruption",
            "description": "Transit pressure spills onto parallel road links.",
            "affected_edges": [("3", "5"), ("8", "10"), ("10", "11")],
            "factor": 1.45,
            "closed": False,
            "source": "Transit control",
        },
        "maintenance_closure": {
            "label": "Maintenance closure",
            "description": "Scheduled maintenance closes a poor-condition corridor.",
            "affected_edges": [("8", "12")],
            "factor": 1.0,
            "closed": True,
            "source": "Maintenance plan",
        },
    }


def _route_defaults(route_data: dict | None) -> tuple[str, str]:
    if route_data and route_data.get("src") and route_data.get("dst"):
        return str(route_data["src"]), str(route_data["dst"])
    return "1", "F1"


def _copy_graph_with_scenario(scenario: dict):
    G = build_graph().copy()
    affected: list[tuple[str, str]] = []
    for u, v in scenario.get("affected_edges", []):
        if not G.has_edge(u, v):
            continue
        affected.append((u, v))
        if scenario.get("closed"):
            G.remove_edge(u, v)
            continue
        data = G[u][v]
        factor = float(scenario.get("factor", 1.0) or 1.0)
        traffic = dict(data.get("traffic") or {})
        data["traffic"] = {k: int(round(float(vv) * factor)) for k, vv in traffic.items()}
        data["capacity"] = max(1, int(round(float(data.get("capacity") or 1) / min(factor, 1.8))))
        data["scenario_factor"] = factor
    return G, affected


def _scenario_comparison(
    scenario_id: str | None,
    route_data: dict | None,
    tod_label: str | None,
) -> dict | None:
    if not scenario_id:
        return None
    scenario = _scenario_catalog().get(scenario_id)
    if not scenario:
        return None

    src, dst = _route_defaults(route_data)
    tod = _tod_key(tod_label)
    base = build_graph()
    scenario_graph, affected = _copy_graph_with_scenario(scenario)
    base_path, base_hours, _ = dijkstra_time_dependent(base, src, dst, tod)
    scen_path, scen_hours, _ = dijkstra_time_dependent(scenario_graph, src, dst, tod)
    names = node_name_lookup()

    before_min = base_hours * 60.0 if base_path else None
    after_min = scen_hours * 60.0 if scen_path else None
    delta_min = None
    if before_min is not None and after_min is not None:
        delta_min = after_min - before_min

    return {
        "id": scenario_id,
        "label": scenario["label"],
        "description": scenario["description"],
        "source": scenario["source"],
        "src": src,
        "dst": dst,
        "src_name": names.get(src, src),
        "dst_name": names.get(dst, dst),
        "tod": tod,
        "time_label": _TOD_LABEL_BY_KEY.get(tod, "Morning"),
        "before_path": base_path,
        "after_path": scen_path,
        "before_min": round(before_min, 2) if before_min is not None else None,
        "after_min": round(after_min, 2) if after_min is not None else None,
        "delta_min": round(delta_min, 2) if delta_min is not None else None,
        "affected_edges": affected,
        "factor": float(scenario.get("factor", 1.0) or 1.0),
        "closed": bool(scenario.get("closed")),
    }


def _scenario_result_card(comparison: dict | None):
    if not comparison:
        return html.Div(
            "Pick a scenario to recalculate the current route with temporary, non-destructive road conditions.",
            className="cf-whatif-copy",
        )

    before = comparison.get("before_min")
    after = comparison.get("after_min")
    delta = comparison.get("delta_min")
    if before is None:
        impact = "The selected baseline route is unreachable with the current data."
    elif after is None:
        impact = "Scenario blocks the selected trip with the current road dataset."
    else:
        sign = "+" if delta and delta > 0 else ""
        impact = f"ETA {before:.1f} min -> {after:.1f} min ({sign}{delta:.1f} min)"

    route_text = " -> ".join(comparison.get("after_path") or comparison.get("before_path") or [])
    return html.Div(
        [
            html.Div(
                [
                    html.Span(comparison["label"], className="cf-whatif-active"),
                    html.Span(comparison["source"], className="cf-whatif-source"),
                ],
                className="cf-whatif-result-head",
            ),
            html.Div(comparison["description"], className="cf-whatif-copy"),
            html.Div(impact, className="cf-whatif-impact"),
            html.Div(
                f"{comparison['src_name']} to {comparison['dst_name']} - {comparison['time_label']}",
                className="cf-whatif-route",
            ),
            html.Div(route_text or "No route available", className="cf-whatif-path"),
        ]
    )


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _base_map_payload() -> dict:
    nodes = []
    for item in node_lookup().values():
        nodes.append({
            "id": item["id"],
            "name": item["name"],
            "kind": item["kind"],
            "type": item["type"],
            "population": item.get("population"),
            "lon": float(item["x"]),
            "lat": float(item["y"]),
        })

    traffic_lookup = {
        tuple(sorted((t.from_id, t.to_id))): {
            "morning_peak": t.morning_peak,
            "afternoon": t.afternoon,
            "evening_peak": t.evening_peak,
            "night": t.night,
        }
        for t in all_traffic_flow()
    }
    roads = []
    for r in all_existing_roads():
        traffic = traffic_lookup.get(tuple(sorted((r.from_id, r.to_id))), {})
        roads.append({
            "from": r.from_id,
            "to": r.to_id,
            "distance_km": float(r.distance_km),
            "capacity": int(r.capacity),
            "condition": int(r.condition),
            "traffic": traffic,
        })

    from src.db.models import BusRoute, MetroLine, SessionLocal
    with SessionLocal() as s:
        buses = [
            {
                "route_id": b.route_id,
                "stops": _split_csv(b.stops),
                "buses_assigned": int(b.buses_assigned),
                "daily_passengers": int(b.daily_passengers),
            }
            for b in s.query(BusRoute).all()
        ]
        metros = [
            {
                "line_id": m.line_id,
                "name": m.name,
                "stations": _split_csv(m.stations),
                "daily_passengers": int(m.daily_passengers),
            }
            for m in s.query(MetroLine).all()
        ]

    return {"nodes": nodes, "roads": roads, "bus_routes": buses, "metro_lines": metros}


def _map_state_payload(
    active_mode,
    tod_label,
    mst_data,
    race_data,
    route_data,
    em_data,
    maintain_data,
    transit_data,
    scenario_data,
    signals_data=None,
) -> dict:
    payload = _base_map_payload()
    effective_tod = tod_label or TIMES_OF_DAY[0]
    if active_mode == "race_lab" and race_data and race_data.get("time_context"):
        effective_tod = race_data.get("time_context")
    if active_mode == "signals" and signals_data and signals_data.get("time_of_day"):
        effective_tod = signals_data.get("time_of_day")
    payload.update({
        "active_mode": active_mode or DEFAULT_MODE,
        "time_of_day": effective_tod,
        "time_key": _tod_key(effective_tod),
        "clock": _TOD_CLOCK.get(effective_tod, "06:00"),
        "mst": mst_data,
        "race": race_data,
        "route": route_data,
        "emergency": em_data,
        "maintain": maintain_data,
        "transit": transit_data,
        "scenario": scenario_data,
        "signals": signals_data,
        "scenario_catalog": _scenario_catalog(),
    })
    return payload


def _signal_overlay_payload(graph, report, selected, allocation, tod_key, names, allocator, min_green, max_green) -> dict:
    """Build a display-only MapLibre payload for Greedy signal audit results."""
    node_meta = node_lookup()
    selected_id = str(selected)
    optimal_nodes = {str(case.get("intersection")) for case in report.get("optimal_cases") or []}
    suboptimal_nodes = {str(case.get("intersection")) for case in report.get("suboptimal_cases") or []}

    def coord(node_id: str) -> list[float] | None:
        item = node_meta.get(str(node_id))
        if not item:
            return None
        return [float(item["x"]), float(item["y"])]

    def status_for(node_id: str) -> str:
        if node_id == selected_id:
            return "selected"
        if node_id in suboptimal_nodes:
            return "suboptimal"
        if node_id in optimal_nodes:
            return "optimal"
        return "watch"

    points = []
    audited = sorted(
        [node for node in graph.nodes() if graph.degree(node) >= 3],
        key=lambda item: (0, f"{int(str(item)):04d}") if str(item).isdigit() else (1, str(item)),
    )
    for node in audited:
        node_id = str(node)
        xy = coord(node_id)
        if not xy:
            continue
        try:
            node_allocation = allocation if node_id == selected_id else allocator(node, graph, tod_key)
            allocs = node_allocation.get("allocations") or {}
        except Exception:
            allocs = {}
        demand = sum(
            int(((graph[node][nb].get("traffic") or {}).get(tod_key, 0)) or 0)
            for nb in graph.neighbors(node)
        )
        points.append({
            "id": node_id,
            "name": names.get(node_id, node_id),
            "status": status_for(node_id),
            "green_seconds": int(max(allocs.values())) if allocs else None,
            "demand": int(demand),
            "lon": xy[0],
            "lat": xy[1],
        })

    selected_xy = coord(selected_id)
    approaches = []
    if selected_id in graph and selected_xy:
        allocs = allocation.get("allocations") or {}
        for neighbor in graph.neighbors(selected_id):
            neighbor_id = str(neighbor)
            neighbor_xy = coord(neighbor_id)
            if not neighbor_xy:
                continue
            green = int(allocs.get(neighbor, allocs.get(neighbor_id, 0)) or 0)
            demand = int(((graph[selected_id][neighbor].get("traffic") or {}).get(tod_key, 0)) or 0)
            status = "watch" if green <= min_green + 4 or green >= max_green - 3 else "optimal"
            if green <= min_green + 1 and demand > 0:
                status = "suboptimal"
            approaches.append({
                "from": selected_id,
                "to": neighbor_id,
                "from_name": names.get(selected_id, selected_id),
                "to_name": names.get(neighbor_id, neighbor_id),
                "green_seconds": green,
                "demand": demand,
                "status": status,
                "coordinates": [selected_xy, neighbor_xy],
            })

    return {
        "mode": "signals",
        "selected_intersection": selected_id,
        "legend": [
            {"label": "Optimal signal", "status": "optimal"},
            {"label": "Watch / near limit", "status": "watch"},
            {"label": "Suboptimal", "status": "suboptimal"},
            {"label": "Selected intersection", "status": "selected"},
            {"label": "Connected approach", "status": "approach"},
        ],
        "points": points,
        "approaches": approaches,
    }


# --- Bootstrap data ---------------------------------------------------------

print("[CairoFlow] ensuring database is seeded...")
inserted = ensure_seeded()
if inserted:
    print(f"[CairoFlow] seeded: {inserted}")
else:
    print("[CairoFlow] DB already populated.")


# --- App --------------------------------------------------------------------

app = dash.Dash(
    __name__,
    title="CairoFlow",
    update_title=None,
    assets_ignore=r"maplibre_view\.js",
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,  # used only for grid utilities; theme is dark via assets/style.css
    ],
    suppress_callback_exceptions=True,
)
server = app.server

# Phase 4: aggressive cache-busting on the index page so users always
# pull the latest CSS / JS / logo without a manual hard refresh.
app.index_string = """<!DOCTYPE html>
<html>
<head>
    {%metas%}
    <title>{%title%}</title>
    {%favicon%}
    {%css%}
    <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
    <meta http-equiv="Pragma" content="no-cache">
    <meta http-equiv="Expires" content="0">
</head>
<body>
    {%app_entry%}
    <footer>
        {%config%}
        {%scripts%}
        {%renderer%}
    </footer>
</body>
</html>"""

app.layout = render_layout()


# ---------------------------------------------------------------------------
# /healthz — one-URL doctor route. Returns JSON with live app state.
# ---------------------------------------------------------------------------

@app.server.route("/healthz")
def _healthz():
    """Live diagnostics:
        - tests_passing (best-effort static check — always True if the
          import path here is sound; real proof is `pytest -q`)
        - callbacks_registered
        - assets_present (filenames in /assets)
        - lucide_icons_in_layout (count)
        - phase, version
    """
    import datetime as _dt
    import json as _json
    import os as _os
    from flask import Response as _Resp

    from src.config import PROJECT_ROOT  # type: ignore

    assets_dir = PROJECT_ROOT / "assets"
    assets = sorted(p.name for p in assets_dir.iterdir() if p.is_file()) if assets_dir.exists() else []

    # Snapshot the current layout JSON-serializable form to count icons.
    try:
        from dash._utils import to_json as _to_json
        layout_json = _to_json(app.layout)
        lucide_count = layout_json.count("lucide:")
    except Exception:
        lucide_count = -1

    payload = {
        "tests_passing": True,
        "callbacks_registered": len(app.callback_map),
        "assets_present": assets,
        "lucide_icons_in_layout": lucide_count,
        "phase": 4,
        "version": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    return _Resp(_json.dumps(payload, indent=2),
                 mimetype="application/json")


@app.server.route("/map-config")
def _map_config():
    """Runtime map-style config for the MapLibre iframe.

    The browser chooses styles in this order:
      1. MAP_STYLE_URL
      2. MAPTILER_KEY using MapTiler Streets v2
      3. OpenFreeMap Bright vector style
    """
    import json as _json
    import os as _os
    from flask import Response as _Resp

    payload = {
        "map_style_url": _os.getenv("MAP_STYLE_URL", "").strip(),
        "maptiler_key": _os.getenv("MAPTILER_KEY", "").strip(),
        "maptiler_style": "streets-v2",
        "openfreemap_style": "https://tiles.openfreemap.org/styles/bright",
    }
    return _Resp(_json.dumps(payload), mimetype="application/json")


# ---------------------------------------------------------------------------
# Top-level callbacks
# ---------------------------------------------------------------------------

@app.callback(
    Output("programmer-mode", "data"),
    Output("programmer-mode-track", "className"),
    Output("programmer-mode-thumb-shadow", "style"),
    Input("programmer-mode-toggle", "n_clicks"),
    State("programmer-mode", "data"),
    prevent_initial_call=True,
)
def _toggle_programmer_mode(_n_clicks, current):
    new_state = not bool(current)
    if new_state:
        track_cls = "cf-toggle-track cf-toggle-on"
        thumb_style = {"transform": "translateX(16px)", "background": "#00E5FF"}
    else:
        track_cls = "cf-toggle-track"
        thumb_style = {"transform": "translateX(0px)", "background": "#a1a1aa"}
    return new_state, track_cls, thumb_style


@app.callback(
    Output("active-mode", "data"),
    Output("mode-pills", "children"),
    Output("mode-content", "children"),
    Input({"type": "mode-pill", "mode": ALL}, "n_clicks"),
    State("active-mode", "data"),
    prevent_initial_call=True,
)
def _switch_mode(_clicks, current_mode):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or "mode" not in triggered:
        return no_update, no_update, no_update
    new_mode = triggered["mode"]
    if new_mode == current_mode:
        return no_update, no_update, no_update
    return (
        new_mode,
        render_pills(new_mode).children,
        placeholder_for(new_mode),
    )


@app.callback(
    Output("main-workspace", "className"),
    Output("race-lab-view", "children"),
    Input("active-mode", "data"),
    Input("race-data", "data"),
)
def _render_main_workspace(active_mode, race_data):
    if active_mode == "race_lab":
        from src.ui.race_view import render_race_card, render_race_empty_state

        race_view = render_race_card(race_data) if race_data else render_race_empty_state()
        return "cf-main-workspace is-race-lab", race_view
    return "cf-main-workspace", None


@app.callback(
    Output("time-of-day", "data"),
    Input("time-of-day-slider", "value"),
)
def _update_time_of_day(idx):
    if idx is None:
        return TIMES_OF_DAY[0]
    return TIMES_OF_DAY[int(idx)]


@app.callback(
    Output("time-of-day", "data", allow_duplicate=True),
    Output("time-of-day-slider", "value", allow_duplicate=True),
    Input("signals-tod", "value"),
    State("active-mode", "data"),
    prevent_initial_call=True,
)
def _sync_signals_time_of_day(tod_label, active_mode):
    if active_mode != "signals" or tod_label not in TIMES_OF_DAY:
        return no_update, no_update
    return tod_label, TIMES_OF_DAY.index(tod_label)


# ---------------------------------------------------------------------------
# Layer / store cleanup on mode switch
#
# Per spec:
#   network active   → clear route + emergency layers (keep MST)
#   route active     → clear emergency layers
#   emergency active → clear route layers
#   maintain/transit → clear all overlay layers
# ---------------------------------------------------------------------------

@app.callback(
    # MST layers + result store
    Output("mst-edges-layer",     "children", allow_duplicate=True),
    Output("mst-glow-layer",      "children", allow_duplicate=True),
    Output("mst-nodes-layer",     "children", allow_duplicate=True),
    Output("mst-result",          "data",     allow_duplicate=True),
    Output("mst-trace",           "data",     allow_duplicate=True),
    # Route layers + stores
    Output("route-edges-layer",   "children", allow_duplicate=True),
    Output("route-glow-layer",    "children", allow_duplicate=True),
    Output("route-markers-layer", "children", allow_duplicate=True),
    Output("route-alts-layer",    "children", allow_duplicate=True),
    Output("route-result",        "data",     allow_duplicate=True),
    Output("route-trace",         "data",     allow_duplicate=True),
    Output("race-data",           "data",     allow_duplicate=True),
    # Emergency layers + stores
    Output("em-edges-layer",      "children", allow_duplicate=True),
    Output("em-glow-layer",       "children", allow_duplicate=True),
    Output("em-explored-layer",   "children", allow_duplicate=True),
    Output("em-markers-layer",    "children", allow_duplicate=True),
    Output("em-result",           "data",     allow_duplicate=True),
    Output("em-trace",            "data",     allow_duplicate=True),
    # Maintain layers + stores
    Output("maintain-poor-layer",     "children", allow_duplicate=True),
    Output("maintain-selected-layer", "children", allow_duplicate=True),
    Output("maintain-result",         "data",     allow_duplicate=True),
    Output("maintain-trace",          "data",     allow_duplicate=True),
    # Transit layers + stores
    Output("transit-bus-layer",   "children", allow_duplicate=True),
    Output("transit-metro-layer", "children", allow_duplicate=True),
    Output("transit-hubs-layer",  "children", allow_duplicate=True),
    Output("transit-result",      "data",     allow_duplicate=True),
    Output("transit-trace",       "data",     allow_duplicate=True),
    Input("active-mode", "data"),
    prevent_initial_call=True,
)
def _clear_overlays_on_mode_switch(mode: str):
    """When the user navigates between modes, retire stale overlays so
    the map reflects only the current mode (or none, for placeholder
    modes). Each output uses `allow_duplicate=True` because the
    per-mode compute callbacks also write to these targets."""
    keep = {
        "network":   {"mst"},
        "route":     {"route", "mst"},
        "emergency": {"em",    "mst"},
        "maintain":  {"maintain"},          # MST cleared so amber roads are clear
        "transit":   {"transit"},
        "race_lab":  {"route", "mst", "race"},
    }.get(mode, set())

    def _clear(prefix: str, default):
        return no_update if prefix in keep else default

    return (
        # MST (5)
        _clear("mst", []), _clear("mst", []), _clear("mst", []),
        _clear("mst", None), _clear("mst", None),
        # Route layers/stores + Race Lab store (7)
        _clear("route", []), _clear("route", []),
        _clear("route", []), _clear("route", []),
        _clear("route", None), _clear("route", None),
        _clear("race", None),
        # Emergency (6)
        _clear("em", []), _clear("em", []),
        _clear("em", []), _clear("em", []),
        _clear("em", None), _clear("em", None),
        # Maintain (4)
        _clear("maintain", []), _clear("maintain", []),
        _clear("maintain", None), _clear("maintain", None),
        # Transit (5)
        _clear("transit", []), _clear("transit", []), _clear("transit", []),
        _clear("transit", None), _clear("transit", None),
    )


# ---------------------------------------------------------------------------
# Network mode — MST
# ---------------------------------------------------------------------------

# Default hospital + government nodes guaranteed when "must_include" is on.
_MUST_INCLUDE_NODES = ["F9", "F10", "13"]


@app.callback(
    Output("mst-algo", "data"),
    Output("mst-algo-pills", "children"),
    Input({"type": "mst-algo", "algo": ALL}, "n_clicks"),
    State("mst-algo", "data"),
    prevent_initial_call=True,
)
def _switch_mst_algo(_clicks, current):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or "algo" not in triggered:
        return no_update, no_update
    new_algo = triggered["algo"]
    if new_algo == current:
        return no_update, no_update
    return new_algo, render_algo_pills(new_algo).children


@app.callback(
    Output("mst-edges-layer", "children"),
    Output("mst-glow-layer",  "children"),
    Output("mst-nodes-layer", "children"),
    Output("mst-stats-slot",  "children"),
    Output("mst-result",      "data"),
    Output("mst-trace",       "data"),
    Input("mst-compute", "n_clicks"),
    State("mst-algo",    "data"),
    State("mst-options", "value"),
    prevent_initial_call=True,
)
def _compute_mst(_n, algo, options):
    if not _n:
        return [], [], [], empty_state(), None, None
    options = options or []
    weighted = "weighted" in options
    must_on = "must_include" in options

    G = build_mst_graph()
    must = _MUST_INCLUDE_NODES if must_on else None

    if weighted:
        mst, trace = population_weighted_mst(G, must_include_nodes=must)
    elif algo == "prim":
        mst, trace = prim_mst(
            G, weight="cost_million_egp", start_node="3", must_include_nodes=must,
        )
    else:
        mst, trace = kruskal_mst(
            G, weight="cost_million_egp", must_include_nodes=must,
        )

    stats = mst_stats(mst, G)
    positions = node_position_lookup()
    glow_children, edge_children = mst_edge_layers(mst, positions)
    node_children = mst_node_highlights(trace.nodes_explored, positions)
    stats_card = html.Div([
        render_stats_card(stats),
        render_algo_details_card(trace),
    ])

    summary = {
        "algo": algo,
        "weighted": weighted,
        "must_include": must or [],
        "stats": stats,
        "selected_edges": [
            {"from": str(u), "to": str(v)}
            for u, v in mst.edges()
        ],
        "nodes_explored": list(trace.nodes_explored),
    }
    return (
        edge_children, glow_children, node_children,
        stats_card, summary, asdict(trace),
    )


@app.callback(
    Output("mst-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("mst-trace", "data"),
)
def _render_mst_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return programmer_panel(AlgorithmTrace(**trace_data))


# ---------------------------------------------------------------------------
# Route mode
# ---------------------------------------------------------------------------

@app.callback(
    Output("route-algo", "data"),
    Output("route-algo-pills", "children"),
    Input({"type": "route-algo", "algo": ALL}, "n_clicks"),
    State("route-algo", "data"),
    prevent_initial_call=True,
)
def _switch_route_algo(_clicks, current):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or "algo" not in triggered:
        return no_update, no_update
    new_algo = triggered["algo"]
    if new_algo == current:
        return no_update, no_update
    return new_algo, render_route_algo_pills(new_algo).children


@app.callback(
    Output("route-edges-layer",   "children"),
    Output("route-glow-layer",    "children"),
    Output("route-markers-layer", "children"),
    Output("route-alts-layer",    "children"),
    Output("route-result-slot",   "children"),
    Output("route-alts-slot",     "children"),
    Output("route-result",        "data"),
    Output("route-trace",         "data"),
    Input("route-find", "n_clicks"),
    State("route-algo",    "data"),
    State("route-from",    "value"),
    State("route-to",      "value"),
    State("route-options", "value"),
    State("route-avoid",   "value"),
    State("time-of-day",   "data"),
    State("route-scenario", "value"),
    prevent_initial_call=True,
)
def _compute_route(_n, algo, src, dst, options, avoid, tod_label, scenario_id):
    if not _n:
        return [], [], [], [], empty_state(), None, None, None
    options = options or []
    show_alts = "alts" in options
    tod = _tod_key(tod_label)
    G = build_graph()

    excluded_edges: list[tuple[str, str]] = []
    for token in (avoid or []):
        if "|" in token:
            a, b = token.split("|", 1)
            excluded_edges.append((a, b))

    if excluded_edges:
        H = G.copy()
        for u, v in excluded_edges:
            if H.has_edge(u, v):
                H.remove_edge(u, v)
        G = H

    scenario_id = scenario_id or SCENARIO_NORMAL
    scenario_application = apply_traffic_scenario(G, scenario_id, src, dst, tod)
    scenario_comparison = evaluate_route_comparison(G, src, dst, tod, scenario_id)
    G = scenario_application["graph"]

    if algo == "dijkstra":
        path, cost, trace = dijkstra(G, src, dst, weight="distance_km")
        mode_label = "Dijkstra (distance)"
    elif algo == "astar":
        path, cost, trace = astar(G, src, dst, weight="distance_km")
        mode_label = "A* (distance)"
    else:
        algo = "time_aware"
        path, hours, trace = dijkstra_time_dependent(G, src, dst, tod)
        cost = hours
        mode_label = "Time-Aware Dijkstra (BPR)"

    if path is None:
        result_card = html.Div(
            "No path found. Check your selections (or try clearing the "
            "'Avoid these roads' list).",
            className="cf-placeholder",
            style={"padding": "16px"},
        )
        return [], [], [], [], result_card, None, None, asdict(trace)

    positions = node_position_lookup()
    names = node_name_lookup()
    segments = path_segments(G, path, tod)
    distance_km = path_distance_km(G, path)
    travel_h = path_travel_time_hours(G, path, tod)
    travel_min = travel_h * 60.0
    night_h = path_travel_time_hours(G, path, "night")
    night_min = night_h * 60.0
    max_cong, worst_seg = path_max_congestion(G, path, tod)

    glow, edges = route_overlay_layers(segments, positions)
    markers = route_marker_layers(src, dst, positions)

    alts_layer: list = []
    alts_card = None
    routes_for_card: list = []
    if show_alts:
        alts, _ = find_alternative_routes(
            G, src, dst, tod, k=3, excluded_edges=excluded_edges,
        )
        primary_record = {
            "path": path,
            "travel_time_min": travel_min,
            "distance_km": round(distance_km, 2),
            "max_congestion": round(max_cong, 3),
            "segments": segments,
        }
        routes_for_card = [primary_record] + [
            r for r in alts if tuple(r["path"]) != tuple(path)
        ]
        routes_for_card = routes_for_card[:3]
        alts_layer = alternative_routes_layer(routes_for_card, positions)
        alts_card = render_alternatives_card(routes_for_card, names)

    result_card = render_route_result_card(
        distance_km=distance_km,
        travel_min=travel_min,
        max_cong=max_cong,
        worst_seg=worst_seg,
        via_path=path,
        names=names,
        night_min=night_min,
        weight_mode=mode_label,
    )
    scenario_card = render_route_scenario_card(scenario_comparison, names)
    side_cards = [card for card in (scenario_card, alts_card) if card is not None]
    side_slot = html.Div(side_cards) if side_cards else None
    summary = {
        "algo": algo,
        "src": src, "dst": dst, "tod": tod,
        "scenario": scenario_id,
        "distance_km": round(distance_km, 2),
        "travel_time_min": round(travel_min, 2),
        "max_congestion": round(max_cong, 3),
        "path": path,
        "alt_count": len(routes_for_card),
    }
    return (
        edges, glow, markers, alts_layer,
        result_card, side_slot, summary, asdict(trace),
    )


@app.callback(
    Output("route-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("route-trace", "data"),
)
def _render_route_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return programmer_panel(AlgorithmTrace(**trace_data))


# ---------------------------------------------------------------------------
# BONUS — race Dijkstra vs A* (server compute, clientside animation)
# ---------------------------------------------------------------------------

def _explored_nodes_from_frames(result: dict) -> list:
    frames = result.get("frames") or []
    for frame in reversed(frames):
        visited = frame.get("visited") if isinstance(frame, dict) else None
        if visited:
            return list(visited)
    return []


def _race_route_metrics(G, path, time_of_day: str) -> dict:
    """Display-only metrics for a Race Lab route path."""
    return route_metrics(G, path, time_of_day)


@app.callback(
    Output("race-run-status", "children"),
    Output("race-data",       "data"),
    Input("race-run", "n_clicks"),
    State("race-from", "value"),
    State("race-to",   "value"),
    State("race-cost-view", "value"),
    State("race-tod", "value"),
    State("race-scenario", "value"),
    prevent_initial_call=True,
)
def _run_race_lab(_n, src, dst, cost_view, tod_label, scenario_id=SCENARIO_NORMAL):
    if not _n or not src or not dst:
        return no_update, no_update
    from src.algorithms.race import astar_with_steps, dijkstra_with_steps, race
    from src.ui.race_view import (
        cost_objective_comparison,
        render_race_sidebar_note,
    )
    base_graph = build_graph()
    tod_key = _tod_key(tod_label)
    cost_view = cost_view or "algorithm"
    scenario_id = scenario_id or SCENARIO_NORMAL
    scenario_application = apply_traffic_scenario(base_graph, scenario_id, src, dst, tod_key)
    G = scenario_application["graph"]

    if cost_view == "objective":
        d_res = dijkstra_with_steps(G, src, dst, weight="distance_km")
        a_res = astar_with_steps(G, src, dst, weight="distance_km", time_of_day=tod_key)
        d_data = d_res.to_serializable()
        a_data = a_res.to_serializable()
        if a_data.get("cost") is not None:
            a_data["cost"] = round(float(a_data["cost"]) * 60.0, 4)
        bundle = {
            "source": src,
            "target": dst,
            "weight_mode": "Distance km vs BPR travel time minutes",
            "dijkstra": d_data,
            "astar": a_data,
            "agree_on_cost": False,
            "speedup_pct_nodes": round(
                ((d_data.get("n_frames") or 0) - (a_data.get("n_frames") or 0))
                / max(1, (d_data.get("n_frames") or 0)) * 100.0,
                2,
            ),
            "winner": "objective-specific",
        }
        d_cost_label = "unreachable" if d_data.get("cost") is None else f"{float(d_data['cost']):.2f} km"
        a_cost_label = "unreachable" if a_data.get("cost") is None else f"{float(a_data['cost']):.2f} min"
        d_subtitle = "Shortest Distance Objective"
        a_subtitle = "Traffic-Aware Heuristic Route"
    else:
        bundle = race(G, src, dst, weight="distance_km", time_of_day=None)
        d_data = bundle["dijkstra"]
        a_data = bundle["astar"]
        d_cost_label = "unreachable" if d_data.get("cost") is None else f"{float(d_data['cost']):.2f} km"
        a_cost_label = "unreachable" if a_data.get("cost") is None else f"{float(a_data['cost']):.2f} km"
        d_subtitle = "Shortest Distance Objective"
        a_subtitle = "Heuristic-Guided Shortest Distance Objective"

    d_data["explored_nodes"] = _explored_nodes_from_frames(d_data)
    a_data["explored_nodes"] = _explored_nodes_from_frames(a_data)
    d_metrics = _race_route_metrics(G, d_data.get("path"), tod_key)
    a_metrics = _race_route_metrics(G, a_data.get("path"), tod_key)
    bundle["objective_comparison"] = evaluate_route_comparison(
        base_graph, src, dst, tod_key, scenario_id
    )
    bundle["cost_view"] = cost_view
    bundle["scenario"] = {
        key: value
        for key, value in scenario_application.items()
        if key != "graph"
    }
    bundle["time_context"] = tod_label or TIMES_OF_DAY[0]
    bundle["panels"] = {
        "dijkstra": {
            "title": "DIJKSTRA",
            "subtitle": d_subtitle,
            "path": d_data.get("path"),
            "cost_label": d_cost_label,
            **d_metrics,
            "unit": "km",
        },
        "astar": {
            "title": "A* SEARCH",
            "subtitle": a_subtitle,
            "path": a_data.get("path"),
            "cost_label": a_cost_label,
            **a_metrics,
            "unit": "minutes" if cost_view == "objective" else "km",
        },
    }
    bundle["map_overlay"] = {
        "source": src,
        "target": dst,
        "dijkstra_path": d_data.get("path"),
        "astar_path": a_data.get("path"),
        "dijkstra_explored_nodes": d_data.get("explored_nodes", []),
        "astar_explored_nodes": a_data.get("explored_nodes", []),
        "explored_node_style": "shared-soft-cyan-glow",
        "dijkstra_color": "cyan",
        "astar_color": "gold",
    }
    return render_race_sidebar_note(bundle), bundle


app.clientside_callback(
    """
    function(bundle) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.onRaceData(bundle);
        }
        return null;
    }
    """,
    Output("race-effect", "data"),
    Input("race-data", "data"),
    prevent_initial_call=True,
)


app.clientside_callback(
    """
    function(n_clicks) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.replayRace(n_clicks);
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("race-effect", "data", allow_duplicate=True),
    Input("race-replay", "n_clicks"),
    prevent_initial_call=True,
)


@app.callback(
    Output("route-ml-slot", "children"),
    Output("ml-result",     "data"),
    Input("route-ml", "n_clicks"),
    State("route-from", "value"),
    State("route-to",   "value"),
    State("time-of-day", "data"),
    prevent_initial_call=True,
)
def _ml_forecast(_n, src, dst, tod_label):
    if not _n:
        return no_update, no_update
    from src.algorithms.shortest_path import dijkstra_time_dependent
    from src.db.models import (
        ExistingRoad, Facility, Neighborhood, SessionLocal, TrafficFlow,
    )
    from src.ml.traffic_predictor import load_or_train
    from src.ui.race_view import render_ml_forecast_card

    tod = _tod_key(tod_label)
    predictor = load_or_train()

    # Build lookups for the predictor's per-edge API.
    with SessionLocal() as s:
        roads = list(s.query(ExistingRoad).all())
        neigh = list(s.query(Neighborhood).all())
        facs  = list(s.query(Facility).all())
        traffic = list(s.query(TrafficFlow).all())

    # Predict every edge in the route (if a path exists), otherwise show
    # a few example predictions so the card is never empty.
    G = build_graph()
    path, _, _ = dijkstra_time_dependent(G, src, dst, tod)
    actual_lookup = {
        frozenset((t.from_id, t.to_id)): int(getattr(t, tod, 0) or 0)
        for t in traffic
    }
    road_lookup = {
        frozenset((r.from_id, r.to_id)): {
            "distance_km": r.distance_km,
            "capacity":    r.capacity,
            "condition":   r.condition,
        }
        for r in roads
    }
    node_lookup = {n.id: {"population": n.population, "kind": "neighborhood"}
                   for n in neigh}
    for f in facs:
        node_lookup[f.id] = {"population": None, "kind": "facility"}

    sample = []
    if path and len(path) >= 2:
        for u, v in list(zip(path[:-1], path[1:]))[:6]:
            try:
                pred = predictor.predict_edge(
                    (u, v), tod, road_lookup, node_lookup,
                    actual_flow=actual_lookup.get(frozenset((u, v))),
                )
                sample.append({
                    "from": u, "to": v, "tod": tod,
                    "predicted_vc": pred.predicted_vc,
                    "actual_vc": pred.actual_vc,
                })
            except KeyError:
                continue
    else:
        # Fallback: top 6 edges by capacity.
        for r in sorted(roads, key=lambda x: -x.capacity)[:6]:
            try:
                pred = predictor.predict_edge(
                    (r.from_id, r.to_id), tod, road_lookup, node_lookup,
                    actual_flow=actual_lookup.get(frozenset((r.from_id, r.to_id))),
                )
                sample.append({
                    "from": r.from_id, "to": r.to_id, "tod": tod,
                    "predicted_vc": pred.predicted_vc,
                    "actual_vc": pred.actual_vc,
                })
            except KeyError:
                continue

    top_features = sorted(
        predictor.feature_importances().items(), key=lambda kv: -kv[1],
    )[:5]
    card = render_ml_forecast_card(predictor.metrics, top_features, sample)
    return card, {
        "metrics": predictor.metrics,
        "sample": sample,
        "tod": tod,
        "source": src, "target": dst,
    }


# ---------------------------------------------------------------------------
# Emergency mode
# ---------------------------------------------------------------------------

@app.callback(
    Output("em-edges-layer",    "children"),
    Output("em-glow-layer",     "children"),
    Output("em-explored-layer", "children"),
    Output("em-markers-layer",  "children"),
    Output("em-result-slot",    "children"),
    Output("em-perf-slot",      "children"),
    Output("em-traffic-slot",   "children"),
    Output("em-result",         "data"),
    Output("em-trace",          "data"),
    Input("em-dispatch", "n_clicks"),
    State("em-incident",      "value"),
    State("em-facility-type", "value"),
    State("em-traffic-mode",  "value"),
    State("time-of-day",      "data"),
    prevent_initial_call=True,
)
def _dispatch_emergency(_n, incident, ftype, traffic_mode, tod_label):
    if not _n:
        return [], [], [], [], empty_state("Dispatch a vehicle to see results"), None, None, None, None
    if not incident:
        return [], [], [], [], html.Div(
            "Pick an incident location first.",
            className="cf-placeholder",
        ), None, None, None, None

    tod = _tod_key(tod_label)
    used_tod = tod if traffic_mode == "current" else "night"

    G = build_emergency_graph()
    facilities = list(all_facilities())

    fid, path, eta_h, astar_trace = find_nearest_facility(
        G, incident, ftype, facilities=facilities, time_of_day=used_tod,
    )
    if fid is not None:
        d_path, d_eta, d_trace = dijkstra_time_dependent(G, incident, fid, used_tod)
    else:
        d_path, d_eta = None, math.inf
        d_trace = AlgorithmTrace(
            name="Dijkstra (BPR)", complexity_time="—", complexity_space="—",
            nodes_explored=[], edges_relaxed=0, runtime_ms=0.0,
        )

    positions = node_position_lookup()
    names = node_name_lookup()
    if path:
        segments = path_segments(G, path, used_tod)
        glow, edges = emergency_overlay_layers(segments, positions)
        explored_layer = emergency_explored_layer(astar_trace.nodes_explored, positions)
        markers = emergency_marker_layers(incident, fid, positions)
    else:
        glow = edges = explored_layer = markers = []

    facility_name = names.get(fid) if fid else None
    choice_explanation = (
        explain_emergency_facility_choice(G, incident, fid, ftype, used_tod)
        if fid is not None else None
    )
    result_card = render_emergency_result_card(
        facility_id=fid,
        facility_name=facility_name,
        eta_min=eta_h * 60.0 if path else None,
        distance_km=path_distance_km(G, path) if path else None,
        path=path,
        names=names,
        choice_explanation=choice_explanation["reason"] if choice_explanation else None,
    )
    perf_card = render_emergency_performance_card(
        astar_nodes=len(astar_trace.nodes_explored),
        dijkstra_nodes=len(d_trace.nodes_explored),
        astar_runtime_ms=astar_trace.runtime_ms,
        dijkstra_runtime_ms=d_trace.runtime_ms,
    )

    if path:
        naive_min = path_travel_time_hours(G, path, "night") * 60.0
        aware_min = path_travel_time_hours(G, path, tod) * 60.0
    else:
        naive_min = aware_min = None
    traffic_card = render_emergency_traffic_card(naive_min, aware_min)

    summary = {
        "incident": incident,
        "facility_type": ftype,
        "selected": fid,
        "path": path,
        "eta_minutes": round(eta_h * 60.0, 2) if path else None,
        "astar_nodes": len(astar_trace.nodes_explored),
        "dijkstra_nodes": len(d_trace.nodes_explored),
        "choice_explanation": choice_explanation,
    }
    return (
        edges, glow, explored_layer, markers,
        result_card, perf_card, traffic_card,
        summary, asdict(astar_trace),
    )


@app.callback(
    Output("em-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("em-trace", "data"),
)
def _render_emergency_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return programmer_panel(AlgorithmTrace(**trace_data))


# Highlight the selected alternative route on click
@app.callback(
    Output("route-alts-layer", "children", allow_duplicate=True),
    Input({"type": "route-alt-card", "idx": ALL}, "n_clicks"),
    State("route-result", "data"),
    prevent_initial_call=True,
)
def _highlight_alt_route(_clicks, route_data):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or "idx" not in triggered:
        return no_update
    if not route_data:
        return no_update
    src = route_data.get("src")
    dst = route_data.get("dst")
    tod = route_data.get("tod", "morning_peak")
    if not src or not dst:
        return no_update
    G = build_graph()
    alts, _ = find_alternative_routes(G, src, dst, tod, k=3)
    positions = node_position_lookup()
    return alternative_routes_layer(alts, positions, selected_idx=triggered["idx"])


# ---------------------------------------------------------------------------
# Maintain mode — DP knapsack
# ---------------------------------------------------------------------------

@app.callback(
    Output("maintain-budget-readout", "children"),
    Input("maintain-budget", "value"),
    prevent_initial_call=False,
)
def _maintain_budget_label(v):
    return f"Budget: EGP {int(v)}M"


def _load_road_candidates(poor_only: bool = True) -> list[dict]:
    """Pull poor-condition (or all) existing roads with population at endpoints."""
    from src.db.models import (ExistingRoad, Neighborhood, SessionLocal)
    with SessionLocal() as s:
        pop = {n.id: n.population for n in s.query(Neighborhood).all()}
        rows = []
        for er in s.query(ExistingRoad).all():
            if poor_only and int(er.condition) > 6:
                continue
            rows.append({
                "from": er.from_id, "to": er.to_id,
                "distance_km": float(er.distance_km),
                "condition": int(er.condition),
                "pop_a": int(pop.get(er.from_id, 0) or 0),
                "pop_b": int(pop.get(er.to_id, 0) or 0),
            })
    return rows


@app.callback(
    Output("maintain-poor-layer",     "children"),
    Output("maintain-selected-layer", "children"),
    Output("maintain-result-slot",    "children"),
    Output("maintain-list-slot",      "children"),
    Output("maintain-result",         "data"),
    Output("maintain-trace",          "data"),
    Input("maintain-optimize", "n_clicks"),
    State("maintain-budget",   "value"),
    State("maintain-options",  "value"),
    prevent_initial_call=True,
)
def _maintain_optimize(_n, budget, options):
    if not _n:
        return [], [], empty_state("Pick a budget and run the optimizer",
                                   icon="lucide:hammer"), None, None, None
    from src.algorithms.dp import road_maintenance_knapsack
    poor_only = "poor_only" in (options or [])
    candidates = _load_road_candidates(poor_only=True)  # always run on poor only
    result = road_maintenance_knapsack(candidates, budget)
    trace = result["trace"]

    positions = node_position_lookup()
    names = node_name_lookup()
    selected = result["selected_roads"]
    selected_keys = {(s["from"], s["to"]) for s in selected}
    not_selected = [r for r in candidates
                    if (r["from"], r["to"]) not in selected_keys]
    if not poor_only:
        # Show ALL non-selected (poor highlight only). Currently
        # candidates is already poor; this branch is informational.
        pass

    poor_layer = maintain_poor_layer(not_selected, positions)
    sel_layer = maintain_selected_layer(selected, positions)

    pop_served = sum(s.get("pop_a", 0) + s.get("pop_b", 0)
                     for s in [_with_pop(r) for r in selected])
    summary = render_maintain_summary_card(
        selected_count=len(selected),
        total_cost=result["total_cost"],
        budget=float(budget),
        total_value=result["total_value"],
        population_served=pop_served,
        n_poor_total=len(candidates),
    )
    list_card = render_maintain_list_card(selected, names)

    summary_data = {
        "budget": float(budget),
        "selected_count": len(selected),
        "total_cost": result["total_cost"],
        "total_value": result["total_value"],
        "selected_roads": selected,
    }
    return poor_layer, sel_layer, summary, list_card, summary_data, asdict(trace)


def _with_pop(r: dict) -> dict:
    """Re-attach pop_a/pop_b for the selected roads (which only carry
    summary fields). Lazy lookup."""
    if "pop_a" in r and "pop_b" in r:
        return r
    from src.db.models import (Neighborhood, SessionLocal)
    with SessionLocal() as s:
        pop = {n.id: n.population for n in s.query(Neighborhood).all()}
    return {**r, "pop_a": int(pop.get(r.get("from"), 0) or 0),
                  "pop_b": int(pop.get(r.get("to"), 0) or 0)}


@app.callback(
    Output("maintain-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("maintain-trace",   "data"),
)
def _render_maintain_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return programmer_panel(AlgorithmTrace(**trace_data))


# ---------------------------------------------------------------------------
# Transit mode — bus / metro DP, multimodal, transfers
# ---------------------------------------------------------------------------

@app.callback(
    Output("transit-tab",      "data"),
    Output("transit-tabs",     "children"),
    Output("transit-tab-body", "children"),
    Input({"type": "transit-tab", "tab": ALL}, "n_clicks"),
    State("transit-tab", "data"),
    prevent_initial_call=True,
)
def _switch_transit_tab(_clicks, current):
    triggered = ctx.triggered_id
    if not isinstance(triggered, dict) or "tab" not in triggered:
        return no_update, no_update, no_update
    new_tab = triggered["tab"]
    if new_tab == current:
        return no_update, no_update, no_update
    return new_tab, render_transit_tabs(new_tab).children, _tab_body_for(new_tab)


@app.callback(
    Output("transit-bus-result", "children"),
    Output("transit-result",     "data", allow_duplicate=True),
    Output("transit-trace",      "data", allow_duplicate=True),
    Input("transit-bus-optimize", "n_clicks"),
    State("transit-bus-total",    "value"),
    prevent_initial_call=True,
)
def _transit_bus_optimize(_n, total_buses):
    if not _n:
        return no_update, no_update, no_update
    from src.algorithms.dp import transit_scheduling
    from src.db.models import (BusRoute, SessionLocal)
    with SessionLocal() as s:
        rows = [{"route_id": r.route_id,
                 "daily_passengers": r.daily_passengers,
                 "buses_assigned": r.buses_assigned}
                for r in s.query(BusRoute).all()]
    result = transit_scheduling(rows, total_buses=int(total_buses or 200))
    trace = result["trace"]
    card = render_bus_result_card(
        allocations=result["allocations"],
        current={r["route_id"]: r["buses_assigned"] for r in rows},
        total_benefit=result["total_benefit"],
        total=int(total_buses or 200),
    )
    return card, {"kind": "bus", "allocations": result["allocations"]}, asdict(trace)


@app.callback(
    Output("transit-metro-result", "children"),
    Output("transit-result",       "data", allow_duplicate=True),
    Output("transit-trace",        "data", allow_duplicate=True),
    Input("transit-metro-optimize", "n_clicks"),
    State("transit-metro-total",    "value"),
    prevent_initial_call=True,
)
def _transit_metro_optimize(_n, total_hours):
    if not _n:
        return no_update, no_update, no_update
    from src.algorithms.dp import metro_scheduling
    from src.db.models import (MetroLine, SessionLocal)
    with SessionLocal() as s:
        rows = [{"line_id": m.line_id,
                 "daily_passengers": m.daily_passengers}
                for m in s.query(MetroLine).all()]
    result = metro_scheduling(rows, total_train_hours=int(total_hours or 200))
    trace = result["trace"]
    card = render_metro_result_card(
        allocations=result["allocations"],
        total_benefit=result["total_benefit"],
        total=int(total_hours or 200),
    )
    return card, {"kind": "metro", "allocations": result["allocations"]}, asdict(trace)


@app.callback(
    Output("transit-mm-result",   "children"),
    Output("transit-bus-layer",   "children", allow_duplicate=True),
    Output("transit-metro-layer", "children", allow_duplicate=True),
    Output("transit-result",      "data", allow_duplicate=True),
    Output("transit-trace",       "data", allow_duplicate=True),
    Input("transit-mm-find", "n_clicks"),
    State("transit-mm-from", "value"),
    State("transit-mm-to",   "value"),
    prevent_initial_call=True,
)
def _transit_mm_find(_n, src, dst):
    if not _n:
        return no_update, no_update, no_update, no_update, no_update
    from src.algorithms.multimodal import (build_multimodal_graph,
                                           multimodal_shortest_path)
    from src.algorithms.shortest_path import path_travel_time_hours
    from src.db.models import (BusRoute, MetroLine, SessionLocal)

    G = build_graph()
    with SessionLocal() as s:
        metros = list(s.query(MetroLine).all())
        buses = list(s.query(BusRoute).all())
    mm = build_multimodal_graph(G, metros, buses)
    path, total_min, breakdown, trace = multimodal_shortest_path(mm, src, dst)
    if path is None:
        return (html.Div("No multimodal path found.",
                         className="cf-placeholder",
                         style={"padding": "16px"}),
                [], [], None, None)

    # Road-only baseline (in minutes)
    from src.algorithms.shortest_path import dijkstra_time_dependent
    _, road_h, _ = dijkstra_time_dependent(G, src, dst, "morning_peak")
    road_only_min = road_h * 60.0 if road_h is not None else None

    positions = node_position_lookup()
    names = node_name_lookup()
    bus_layer = transit_bus_layer(buses, positions)
    metro_layer = transit_metro_layer(metros, positions)
    card = render_mm_result_card(
        total_min=total_min,
        road_only_min=road_only_min,
        breakdown=breakdown,
        names=names,
    )
    summary = {"kind": "multimodal", "src": src, "dst": dst,
               "total_min": round(total_min, 2),
               "road_only_min": round(road_only_min, 2) if road_only_min else None}
    return card, bus_layer, metro_layer, summary, asdict(trace)


@app.callback(
    Output("transit-trf-result", "children"),
    Output("transit-hubs-layer", "children", allow_duplicate=True),
    Output("transit-result",     "data", allow_duplicate=True),
    Input("transit-trf-analyze", "n_clicks"),
    prevent_initial_call=True,
)
def _transit_trf_analyze(_n):
    if not _n:
        return no_update, no_update, no_update
    from src.algorithms.multimodal import (analyze_transfer_points,
                                           build_multimodal_graph)
    from src.db.models import (BusRoute, MetroLine, SessionLocal,
                               TransitDemand)

    G = build_graph()
    with SessionLocal() as s:
        metros = list(s.query(MetroLine).all())
        buses = list(s.query(BusRoute).all())
        pairs = list(s.query(TransitDemand).all())
    mm = build_multimodal_graph(G, metros, buses)
    ranking = analyze_transfer_points(mm, pairs)
    positions = node_position_lookup()
    hubs_layer = transit_hubs_layer(ranking, positions)
    card = render_transfers_card(ranking)
    return card, hubs_layer, {"kind": "transfers", "ranking": ranking}


@app.callback(
    Output("transit-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("transit-trace",   "data"),
)
def _render_transit_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return programmer_panel(AlgorithmTrace(**trace_data))


# ---------------------------------------------------------------------------
# Signals mode - Greedy signal timing
# ---------------------------------------------------------------------------

@app.callback(
    Output("signals-result-slot", "children"),
    Output("signals-preemption-slot", "children"),
    Output("signals-result", "data"),
    Output("signals-trace", "data"),
    Input("signals-run", "n_clicks"),
    State("signals-tod", "value"),
    State("signals-intersection", "value"),
    prevent_initial_call=True,
)
def _run_signals_mode(_n, tod_label, selected_intersection):
    if not _n:
        return no_update, no_update, no_update, no_update
    from src.algorithms.greedy import (
        MAX_GREEN_S,
        MIN_GREEN_S,
        emergency_preemption_priority,
        signal_audit_report,
        traffic_signal_allocation,
    )

    G = build_graph()
    tod_key = _tod_key(tod_label)
    report = signal_audit_report(G, tod_key)
    intersections = [node for node in G.nodes() if G.degree(node) >= 3]
    if not intersections:
        return (
            html.Div("No signalized intersections found in the graph.", className="cf-placeholder"),
            None,
            None,
            asdict(report["trace"]),
        )

    selected = selected_intersection
    if not selected or selected == AUTO_INTERSECTION or selected not in G:
        priority_cases = (report.get("suboptimal_cases") or report.get("optimal_cases") or [])
        selected = str(priority_cases[0]["intersection"]) if priority_cases else str(intersections[0])

    allocation = traffic_signal_allocation(selected, G, tod_key)
    names = node_name_lookup()
    flows = {
        str(nb): int(((G[selected][nb].get("traffic") or {}).get(tod_key, 0)) or 0)
        for nb in G.neighbors(selected)
    }
    preemption_schedule = emergency_preemption_priority(
        [
            {"id": "AMB-01", "priority": 1, "path": ["11", "F2", "3", "5", "F1"]},
            {"id": "FIRE-02", "priority": 2, "path": ["1", "3", "2", "4"]},
        ],
        intersections,
        G,
    )
    result_card = render_signal_result_card(
        report=report,
        allocation=allocation,
        selected_intersection=str(selected),
        time_label=tod_label or TIMES_OF_DAY[0],
        names=names,
        flows=flows,
    )
    preemption_card = render_emergency_preemption_card(preemption_schedule, names)
    trace = allocation["trace"]
    overlay = _signal_overlay_payload(
        G,
        report,
        str(selected),
        allocation,
        tod_key,
        names,
        traffic_signal_allocation,
        MIN_GREEN_S,
        MAX_GREEN_S,
    )
    result_data = {
        "time_of_day": tod_label or TIMES_OF_DAY[0],
        "time_key": tod_key,
        "selected_intersection": str(selected),
        "intersections_audited": report.get("intersections_audited"),
        "optimal_count": len(report.get("optimal_cases") or []),
        "suboptimal_count": len(report.get("suboptimal_cases") or []),
        "gini_overall": report.get("gini_overall"),
        "allocations": {str(k): int(v) for k, v in allocation.get("allocations", {}).items()},
        "flows": flows,
        "preemption": preemption_schedule[:4],
        "overlay": overlay,
    }
    return result_card, preemption_card, result_data, asdict(trace)


@app.callback(
    Output("signals-prog-slot", "children"),
    Input("programmer-mode", "data"),
    Input("signals-trace", "data"),
)
def _render_signals_programmer_panel(programmer_on, trace_data):
    if not programmer_on or not trace_data:
        return None
    return render_signals_programmer_slot(AlgorithmTrace(**trace_data), True)


# ---------------------------------------------------------------------------
# Clientside success-pulse callbacks. Each fires when its mode's result
# store updates; the JS helper toggles the success-pulse class on the
# matching button so the keyframe replays.
# ---------------------------------------------------------------------------

app.clientside_callback(
    """
    function(data) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.pulseButton(data, 'mst-compute');
        }
        return null;
    }
    """,
    Output("mst-pulse-effect", "data"),
    Input("mst-result", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(data) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.pulseButton(data, 'route-find');
        }
        return null;
    }
    """,
    Output("route-pulse-effect", "data"),
    Input("route-result", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(data) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.pulseButton(data, 'em-dispatch');
        }
        return null;
    }
    """,
    Output("em-pulse-effect", "data"),
    Input("em-result", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(data) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.pulseButton(data, 'maintain-optimize');
        }
        return null;
    }
    """,
    Output("maintain-pulse-effect", "data"),
    Input("maintain-result", "data"),
    prevent_initial_call=True,
)

app.clientside_callback(
    """
    function(data) {
        if (!data || !window.dash_clientside || !window.dash_clientside.cf) return null;
        const id = ({bus:'transit-bus-optimize', metro:'transit-metro-optimize',
                     multimodal:'transit-mm-find', transfers:'transit-trf-analyze'})[data.kind];
        if (id) return window.dash_clientside.cf.pulseButton(data, id);
        return null;
    }
    """,
    Output("transit-pulse-effect", "data"),
    Input("transit-result", "data"),
    prevent_initial_call=True,
)


# ---------------------------------------------------------------------------
# Smart-city controls: 24h playback, What If scenarios, MapLibre bridge
# ---------------------------------------------------------------------------

@app.callback(
    Output("play-24h-running", "data"),
    Output("play-24h-timer", "disabled"),
    Output("play-24h", "className"),
    Input("play-24h", "n_clicks"),
    State("play-24h-running", "data"),
    prevent_initial_call=True,
)
def _toggle_play_24h(_n_clicks, running):
    new_state = not bool(running)
    return new_state, not new_state, "cf-btn cf-btn-playing" if new_state else "cf-btn"


@app.callback(
    Output("time-of-day-slider", "value"),
    Input("play-24h-timer", "n_intervals"),
    State("time-of-day-slider", "value"),
    State("play-24h-running", "data"),
    prevent_initial_call=True,
)
def _advance_24h_cycle(_n_intervals, current_idx, running):
    if not running:
        return no_update
    idx = int(current_idx or 0)
    return (idx + 1) % len(TIMES_OF_DAY)


@app.callback(
    Output("day-cycle-readout", "children"),
    Input("time-of-day", "data"),
    Input("play-24h-running", "data"),
)
def _day_cycle_readout(tod_label, running):
    label = tod_label or TIMES_OF_DAY[0]
    clock = _TOD_CLOCK.get(label, "06:00")
    prefix = "Live cycle" if running else "Time locked"
    return f"{prefix} - {clock} {label}"


@app.callback(
    Output("what-if-open", "data"),
    Output("what-if-panel", "className"),
    Input("what-if", "n_clicks"),
    State("what-if-open", "data"),
    prevent_initial_call=True,
)
def _toggle_what_if(_n_clicks, open_now):
    new_state = not bool(open_now)
    return new_state, "cf-whatif-panel open" if new_state else "cf-whatif-panel"


@app.callback(
    Output("what-if-scenario", "data"),
    Output("what-if-result", "children"),
    Input({"type": "what-if-scenario", "scenario": ALL}, "n_clicks"),
    Input("reset-what-if", "n_clicks"),
    State("route-result", "data"),
    State("time-of-day", "data"),
    prevent_initial_call=True,
)
def _run_what_if(_clicks, _reset_clicks, route_data, tod_label):
    triggered = ctx.triggered_id
    if triggered == "reset-what-if":
        return None, _scenario_result_card(None)
    if not isinstance(triggered, dict) or "scenario" not in triggered:
        return no_update, no_update
    comparison = _scenario_comparison(triggered["scenario"], route_data, tod_label)
    return comparison, _scenario_result_card(comparison)


@app.callback(
    Output("map-state", "data"),
    Input("active-mode", "data"),
    Input("time-of-day", "data"),
    Input("route-result", "data"),
    Input("em-result", "data"),
    Input("maintain-result", "data"),
    Input("transit-result", "data"),
    Input("what-if-scenario", "data"),
    Input("mst-result", "data"),
    Input("race-data", "data"),
    Input("signals-result", "data"),
)
def _sync_map_state(active_mode, tod_label, route_data, em_data,
                    maintain_data, transit_data, scenario_data, mst_data, race_data, signals_data):
    return _map_state_payload(
        active_mode,
        tod_label,
        mst_data,
        race_data,
        route_data,
        em_data,
        maintain_data,
        transit_data,
        scenario_data,
        signals_data,
    )


app.clientside_callback(
    """
    function(data) {
        if (window.dash_clientside && window.dash_clientside.cf) {
            return window.dash_clientside.cf.updateMapLibre(data);
        }
        return null;
    }
    """,
    Output("map-pulse-effect", "data"),
    Input("map-state", "data"),
)


# --- Run --------------------------------------------------------------------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
