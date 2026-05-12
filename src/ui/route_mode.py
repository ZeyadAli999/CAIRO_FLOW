"""Route mode sidebar — input controls + result/alternatives cards."""
from __future__ import annotations

from typing import Any

from dash import dcc, html

from src.algorithms.trace import AlgorithmTrace
from src.config import DEFAULT_TIME_OF_DAY
from src.db.queries import (
    all_existing_roads,
    all_facilities,
    all_neighborhoods,
    node_lookup,
)
from src.ui.components import (
    cf_button,
    cf_icon,
    empty_state,
    info_card,
    programmer_panel,
)


# ---------------------------------------------------------------------------
# Dropdown option builders
# ---------------------------------------------------------------------------

def node_options() -> list[dict]:
    """Grouped (via category prefix) node options for FROM/TO selectors."""
    options: list[dict] = []
    # Neighborhoods first
    for n in sorted(all_neighborhoods(), key=lambda x: int(x.id)):
        options.append({
            "label": f"●  {n.name}  ({n.id})",
            "value": n.id,
            "search": f"{n.name} {n.id} neighborhood",
        })
    for f in sorted(all_facilities(), key=lambda x: x.id):
        options.append({
            "label": f"◆  {f.name}  ({f.id})",
            "value": f.id,
            "search": f"{f.name} {f.id} facility",
        })
    return options


def edge_options() -> list[dict]:
    """Edge options for the 'Avoid these roads' multi-select.

    Value is encoded as `"u|v"` so we can split it back inside the
    callback into a tuple."""
    nodes = node_lookup()
    out: list[dict] = []
    for r in all_existing_roads():
        a = nodes.get(r.from_id, {}).get("name", r.from_id)
        b = nodes.get(r.to_id, {}).get("name", r.to_id)
        out.append({
            "label": f"{a}  ↔  {b}",
            "value": f"{r.from_id}|{r.to_id}",
        })
    return sorted(out, key=lambda o: o["label"])


# ---------------------------------------------------------------------------
# Algorithm pills
# ---------------------------------------------------------------------------

ROUTE_ALGOS = [
    ("dijkstra", "Dijkstra"),
    ("time_aware", "Time-Aware"),
    ("astar", "A*"),
]


def render_route_algo_pills(active: str = "time_aware") -> html.Div:
    pills = []
    for algo_id, label in ROUTE_ALGOS:
        cls = "cf-pill cf-pill-wide"
        if algo_id == active:
            cls += " active"
        pills.append(
            html.Button(
                label,
                id={"type": "route-algo", "algo": algo_id},
                n_clicks=0,
                className=cls,
            )
        )
    return html.Div(pills, className="cf-pills cf-pills-3", id="route-algo-pills")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------

def render_route_panel(
    active_algo: str = "time_aware",
    *,
    source: str = "1",
    target: str = "F1",
) -> list:
    return [
        info_card(
            title="From",
            body=dcc.Dropdown(
                id="route-from",
                options=node_options(),
                value=source,
                clearable=False,
                className="cf-dd",
            ),
        ),
        info_card(
            title="To",
            body=dcc.Dropdown(
                id="route-to",
                options=node_options(),
                value=target,
                clearable=False,
                className="cf-dd",
            ),
        ),
        info_card(
            title="Algorithm",
            body=html.Div(
                [
                    render_route_algo_pills(active_algo),
                    dcc.Checklist(
                        id="route-options",
                        options=[
                            {"label": " Show alternative routes (top 3)",
                             "value": "alts"},
                        ],
                        value=[],
                        className="cf-checklist",
                        labelStyle={"display": "block", "marginTop": "6px"},
                    ),
                ]
            ),
        ),
        info_card(
            title="Avoid these roads",
            body=dcc.Dropdown(
                id="route-avoid",
                options=edge_options(),
                value=[],
                multi=True,
                placeholder="Select roads to exclude…",
                className="cf-dd",
            ),
        ),
        cf_button(
            "Find Route", btn_id="route-find",
            variant="primary", icon="lucide:navigation",
        ),
        # Bonus ML forecast trigger. Race Lab now owns its separate mode.
        html.Div(
            [
                html.Button(
                    [cf_icon("lucide:brain", size=14,
                             style={"marginRight": "6px"}, color="currentColor"),
                     html.Span("ML forecast")],
                    id="route-ml",
                    className="cf-btn",
                    n_clicks=0,
                ),
            ],
            className="cf-route-bonus-row",
        ),
        dcc.Loading(
            id="route-ml-loading",
            type="circle",
            color="var(--accent)",
            children=html.Div(id="route-ml-slot"),
        ),
        dcc.Loading(
            id="route-result-loading",
            type="circle",
            color="var(--accent)",
            children=html.Div(empty_state(), id="route-result-slot"),
        ),
        html.Div(id="route-alts-slot"),
        html.Div(id="route-prog-slot"),
    ]


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------

def _stat_row(label: str, value: Any, *, accent: bool = False, icon: str | None = None) -> html.Div:
    label_node: Any = label
    if icon:
        label_node = html.Span(
            [cf_icon(icon, size=14, color="var(--text-muted)",
                     style={"marginRight": "6px"}),
             label],
            style={"display": "inline-flex", "alignItems": "center"},
        )
    return html.Div(
        [
            html.Span(label_node, className="cf-stat-label"),
            html.Span(value, className="cf-stat-value"
                                  + (" cf-stat-accent" if accent else "")),
        ],
        className="cf-stat-row",
    )


def _format_path(path: list, names: dict[str, str]) -> str:
    return "  →  ".join(names.get(p, str(p)) for p in path)


def render_route_result_card(
    *,
    distance_km: float,
    travel_min: float,
    max_cong: float,
    worst_seg: tuple | None,
    via_path: list,
    names: dict[str, str],
    night_min: float | None = None,
    weight_mode: str = "Time-Aware",
) -> html.Div:
    cong_str = f"{int(max_cong * 100)}%"
    if worst_seg:
        u, v = worst_seg
        cong_str += f"  ({names.get(u, u)} → {names.get(v, v)})"
    via_str = _format_path(via_path, names)
    children = [
        _stat_row("Distance", f"{distance_km:.1f} km", icon="lucide:ruler"),
        _stat_row("Travel time", f"{travel_min:.1f} min",
                  accent=True, icon="lucide:clock"),
        _stat_row("Max congestion", cong_str, icon="lucide:gauge"),
        _stat_row("Via", via_str, icon="lucide:route"),
        _stat_row("Weight mode", weight_mode, icon="lucide:cpu"),
    ]
    if night_min is not None and travel_min is not None:
        diff = travel_min - night_min
        if diff >= 1:
            note = f"vs night: {diff:.1f} min faster off-peak  —  travel at night to save time"
        elif diff <= -1:
            note = f"vs night: {abs(diff):.1f} min slower off-peak  —  current time is the better window"
        else:
            note = "vs night: no significant difference"
        children.append(html.Div(note, className="cf-comparison-strip"))
    return info_card(title="Route Result", body=html.Div(children))


def render_alternatives_card(
    routes: list[dict], names: dict[str, str]
) -> html.Div:
    if not routes:
        return info_card(
            title="Alternative routes",
            body=html.Div("No alternative routes found.", className="cf-placeholder"),
        )
    labels = ["Fastest", "Shortest", "Cleanest"]
    # Heuristic ranking just for the labels — actual order is whatever
    # the K-alternatives algorithm produced.
    sorted_by_dist = sorted(range(len(routes)), key=lambda i: routes[i]["distance_km"])
    sorted_by_cong = sorted(range(len(routes)), key=lambda i: routes[i]["max_congestion"])
    label_for: dict[int, str] = {}
    label_for[0] = "Fastest"
    if sorted_by_dist:
        label_for[sorted_by_dist[0]] = "Shortest" if sorted_by_dist[0] != 0 else label_for.get(0, "Shortest")
    if sorted_by_cong:
        idx = sorted_by_cong[0]
        if idx not in label_for:
            label_for[idx] = "Cleanest"
    cards = []
    for i, r in enumerate(routes):
        tag = label_for.get(i, labels[i] if i < len(labels) else f"Route {i+1}")
        cards.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"Route {i+1}: ", className="cf-stat-label"),
                            html.Span(tag, className="cf-stat-value cf-stat-accent"),
                        ],
                        className="cf-stat-row",
                    ),
                    _stat_row("Travel time", f"{r['travel_time_min']:.1f} min"),
                    _stat_row("Distance", f"{r['distance_km']:.1f} km"),
                    _stat_row("Max congestion", f"{int(r['max_congestion'] * 100)}%"),
                    _stat_row("Via", _format_path(r["path"], names)),
                ],
                id={"type": "route-alt-card", "idx": i},
                className="cf-card cf-alt-card",
                n_clicks=0,
            )
        )
    return html.Div(
        [html.Div("Alternative routes", className="cf-section-title")] + cards
    )


def render_route_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    if not programmer_on:
        return None
    return programmer_panel(trace)
