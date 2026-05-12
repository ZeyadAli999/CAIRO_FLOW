"""Race Lab UI.

Renders an evaluator-friendly side-by-side comparison of the captured
Dijkstra and A* race bundle. The primary visualization is the shared
MapLibre Cairo map; hidden legacy canvas IDs remain for compatibility
with the existing replay/readout callback.
"""
from __future__ import annotations

from typing import Any

from dash import dcc, html

from src.config import TIMES_OF_DAY
from src.ui.components import cf_icon, info_card


def _stat(label: str, value: Any, accent: bool = False) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="cf-stat-label"),
            html.Span(value, className="cf-stat-value"
                                  + (" cf-stat-accent" if accent else "")),
        ],
        className="cf-stat-row",
    )


def _path_hops(payload: dict[str, Any]) -> int | None:
    path = payload.get("path")
    if not path:
        return None
    return max(0, len(path) - 1)


def _fmt_cost(cost: Any) -> str:
    if cost is None:
        return "unreachable"
    try:
        return f"{float(cost):.2f}"
    except (TypeError, ValueError):
        return str(cost)


def _fmt_path(path: list[Any] | None) -> str:
    if not path:
        return "unreachable"
    return " -> ".join(str(node) for node in path)


def render_race_panel() -> list:
    """Sidebar controls for Race Lab mode."""
    from src.ui.route_mode import node_options

    return [
        info_card(
            title="Race Lab",
            body="Choose source and target, then run the Dijkstra vs A* Race Lab.",
        ),
        info_card(
            title="From",
            body=dcc.Dropdown(
                id="race-from",
                options=node_options(),
                value="1",
                clearable=False,
                className="cf-dd",
            ),
        ),
        info_card(
            title="To",
            body=dcc.Dropdown(
                id="race-to",
                options=node_options(),
                value="F1",
                clearable=False,
                className="cf-dd",
            ),
        ),
        info_card(
            title="Cost View",
            body=dcc.RadioItems(
                id="race-cost-view",
                options=[
                    {"label": " Algorithm Cost View", "value": "algorithm"},
                    {"label": " Objective Cost View", "value": "objective"},
                ],
                value="algorithm",
                className="cf-checklist",
                labelStyle={"display": "block", "marginTop": "6px"},
            ),
        ),
        info_card(
            title="Time of day",
            body=dcc.Dropdown(
                id="race-tod",
                options=[{"label": t, "value": t} for t in TIMES_OF_DAY],
                value=TIMES_OF_DAY[0],
                clearable=False,
                className="cf-dd",
            ),
            footer="Used when the objective is Traffic-aware / BPR.",
        ),
        html.Button(
            [
                cf_icon("lucide:swords", size=14,
                        style={"marginRight": "6px"}, color="currentColor"),
                html.Span("Run Race"),
            ],
            id="race-run",
            className="cf-btn cf-btn-accent",
            n_clicks=0,
        ),
        dcc.Loading(
            id="race-run-loading",
            type="circle",
            color="var(--accent)",
            children=html.Div(id="race-run-status"),
        ),
    ]


def cost_objective_comparison(G, source: Any, target: Any, time_of_day: str) -> dict[str, Any]:
    """Build display-only distance-vs-traffic objective facts.

    This does not modify routing algorithms or graph data. It runs the
    existing shortest-path helpers with two different objectives so the
    Race Lab can show why equal Dijkstra/A* cost is correct while
    traffic-aware routing may legitimately report a different score.
    """
    from src.algorithms.shortest_path import (
        dijkstra,
        dijkstra_time_dependent,
        path_distance_km,
        path_travel_time_hours,
    )

    distance_path, distance_cost, _ = dijkstra(G, source, target, weight="distance_km")
    traffic_path, traffic_hours, _ = dijkstra_time_dependent(G, source, target, time_of_day)

    distance_reachable = distance_path is not None
    traffic_reachable = traffic_path is not None
    return {
        "source": source,
        "target": target,
        "time_of_day": time_of_day,
        "distance_path": distance_path,
        "traffic_path": traffic_path,
        "distance_cost_km": round(distance_cost, 2) if distance_reachable else None,
        "traffic_cost_min": round(traffic_hours * 60.0, 2) if traffic_reachable else None,
        "distance_path_travel_min": (
            round(path_travel_time_hours(G, distance_path, time_of_day) * 60.0, 2)
            if distance_reachable else None
        ),
        "traffic_path_distance_km": (
            round(path_distance_km(G, traffic_path), 2) if traffic_reachable else None
        ),
        "path_changed": (
            bool(distance_reachable and traffic_reachable and distance_path != traffic_path)
        ),
        "reachable": bool(distance_reachable and traffic_reachable),
    }


def race_summary(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return display-only facts derived from a race bundle.

    This helper does not alter race computation. It only translates the
    existing race payload into professor-friendly explanation text and
    metric values.
    """
    d = bundle.get("dijkstra", {})
    a = bundle.get("astar", {})
    d_nodes = int(d.get("n_frames") or 0)
    a_nodes = int(a.get("n_frames") or 0)
    d_runtime = float(d.get("runtime_ms") or 0.0)
    a_runtime = float(a.get("runtime_ms") or 0.0)
    node_savings = d_nodes - a_nodes
    speedup = float(bundle.get("speedup_pct_nodes") or 0.0)
    agree = bool(bundle.get("agree_on_cost"))
    disconnected = not d.get("path") and not a.get("path")

    if disconnected:
        status = "No route found"
        optimality = (
            "Both algorithms terminated cleanly because the target is not "
            "reachable in the current graph view."
        )
        efficiency = "No efficiency winner is reported for an unreachable route."
    elif agree:
        status = "Optimal cost preserved"
        optimality = (
            "Both algorithms agree on the same optimal cost, so the heuristic "
            "did not compromise correctness."
        )
        if node_savings > 0:
            efficiency = (
                f"A* explored {node_savings} fewer nodes than Dijkstra "
                f"({speedup:.1f}% fewer), focusing the search toward the target. "
                f"Runtime: A* {a_runtime:.2f} ms vs Dijkstra {d_runtime:.2f} ms."
            )
        elif node_savings == 0:
            efficiency = (
                "A* and Dijkstra explored the same number of nodes on this route; "
                f"A* still preserved optimality. Runtime: A* {a_runtime:.2f} ms "
                f"vs Dijkstra {d_runtime:.2f} ms."
            )
        else:
            efficiency = (
                f"Dijkstra explored {abs(node_savings)} fewer nodes on this route. "
                f"A* still preserved the same optimal cost. Runtime: A* "
                f"{a_runtime:.2f} ms vs Dijkstra {d_runtime:.2f} ms."
            )
    else:
        status = "Cost mismatch"
        optimality = (
            "The algorithms did not agree on cost for this bundle; inspect the "
            "graph view, weight mode, and heuristic assumptions."
        )
        efficiency = "Efficiency comparison is secondary until cost agreement is restored."

    heuristic = (
        "A* uses h(n) = straight-line distance to the target. Because this "
        "admissible heuristic never overestimates the remaining road cost, "
        "A* can explore fewer nodes while preserving optimality."
    )

    return {
        "status": status,
        "optimality": optimality,
        "efficiency": efficiency,
        "heuristic": heuristic,
        "node_savings": node_savings,
        "node_savings_pct": speedup,
        "dijkstra_nodes": d_nodes,
        "astar_nodes": a_nodes,
        "dijkstra_hops": _path_hops(d),
        "astar_hops": _path_hops(a),
        "dijkstra_cost": d.get("cost"),
        "astar_cost": a.get("cost"),
        "agree_on_cost": agree,
        "winner": bundle.get("winner", "tie"),
    }


def render_race_card(bundle: dict[str, Any]) -> html.Div:
    """Render the Dijkstra vs A* Race Lab.

    The MapLibre map is mounted beside this panel by the main layout.
    Hidden legacy canvas IDs are preserved so older clientside callbacks
    and tests remain safe, but they are no longer the primary visual.
    """
    d = bundle["dijkstra"]
    a = bundle["astar"]
    summary = race_summary(bundle)
    objective = bundle.get("objective_comparison")
    panels = _panel_models(bundle)

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("CSE112 algorithm comparison",
                                      className="cf-race-eyebrow"),
                            html.H3(
                                [
                                    cf_icon("lucide:swords", size=18,
                                            color="var(--accent)",
                                            style={"marginRight": "8px"}),
                                    "Dijkstra vs A* Race Lab",
                                ],
                                className="cf-race-title",
                            ),
                            html.P(
                                "Same-objective race: both algorithms optimize "
                                "the same edge cost. Same cost is expected and "
                                "confirms optimality; the real comparison is "
                                "explored nodes and runtime.",
                                className="cf-race-subtitle",
                            ),
                        ],
                        className="cf-race-heading",
                    ),
                    html.Div(
                        [
                            _meta_chip("Source", bundle["source"]),
                            _meta_chip("Target", bundle["target"]),
                            _meta_chip("Weight", bundle["weight_mode"]),
                            _meta_chip("Result", summary["status"]),
                        ],
                        className="cf-race-meta-grid",
                    ),
                ],
                className="cf-race-hero",
            ),
            html.Div(
                [
                    _difference_callout(bundle, summary),
                    _map_legend(),
                ],
                className="cf-race-visual-strip",
            ),
            html.Div(
                [
                    _map_algorithm_panel(panels["dijkstra"]),
                    _map_algorithm_panel(panels["astar"]),
                ],
                className="cf-race-map-grid",
            ),
            html.Div(
                [
                    html.Button(
                        [cf_icon("lucide:play", size=12,
                                 style={"marginRight": "6px"}, color="currentColor"),
                         "Replay race"],
                        id="race-replay",
                        className="cf-btn cf-btn-accent",
                        n_clicks=0,
                    ),
                    html.Span(id="race-step-readout", className="cf-race-readout"),
                ],
                className="cf-race-controls",
            ),
            _legacy_canvas_mount(),
            _section_title(
                "Dijkstra vs A* — Same Cost Objective",
                "Both algorithms optimize the same edge objective, so the same optimal cost is expected. A* is judged by efficiency: fewer explored nodes and runtime, not a lower cost.",
            ),
            html.Div(
                [
                    _comparison_insight_cards(bundle, panels, summary),
                ],
                className="cf-race-insight-region",
            ),
            _objective_section(objective),
        ],
        className="cf-race-lab",
    )


def render_race_sidebar_note(bundle: dict[str, Any]) -> html.Div:
    """Small sidebar confirmation for the dedicated Race Lab mode."""
    summary = race_summary(bundle)
    return html.Div(
        [
            html.Div("Race Lab active.", className="cf-race-side-title"),
            html.Div(
                (
                    "Dijkstra and A* use the same objective here, so matching "
                    "cost is correct. Use the main Race Lab view for the distance-vs-traffic "
                    "cost comparison."
                ),
                className="cf-race-side-copy",
            ),
            html.Div(summary["status"], className="cf-race-side-status"),
        ],
        className="cf-race-side-note",
    )


def _meta_chip(label: str, value: Any) -> html.Div:
    return html.Div(
        [
            html.Span(label, className="cf-race-meta-label"),
            html.Span(str(value), className="cf-race-meta-value"),
        ],
        className="cf-race-meta-chip",
    )


def _section_title(title: str, subtitle: str) -> html.Div:
    return html.Div(
        [
            html.H4(title, className="cf-race-section-title"),
            html.Div(subtitle, className="cf-race-section-copy"),
        ],
        className="cf-race-section-head",
    )


def _metric(label: str, value: Any, icon: str, accent: bool = False) -> html.Div:
    return html.Div(
        [
            cf_icon(icon, size=14, color="var(--accent)" if accent else "var(--text-muted)"),
            html.Div(
                [
                    html.Span(label, className="cf-race-metric-label"),
                    html.Span(str(value), className="cf-race-metric-value"),
                ],
                className="cf-race-metric-copy",
            ),
        ],
        className="cf-race-metric" + (" is-accent" if accent else ""),
    )


def _difference_callout(bundle: dict[str, Any], summary: dict[str, Any]) -> html.Div:
    d_nodes = int(summary.get("dijkstra_nodes") or 0)
    a_nodes = int(summary.get("astar_nodes") or 0)
    node_savings = int(summary.get("node_savings") or 0)
    pct = float(summary.get("node_savings_pct") or 0.0)
    same_route = (
        bundle.get("dijkstra", {}).get("path")
        and bundle.get("dijkstra", {}).get("path") == bundle.get("astar", {}).get("path")
    )
    title = (
        "Same final route. Different search effort."
        if same_route else "Different final route. Different search effort."
    )
    if node_savings > 0:
        body = f"A* explored {node_savings} fewer nodes than Dijkstra ({pct:.1f}% less search)."
    elif node_savings == 0:
        body = (
            "Both algorithms explored a similar number of nodes on this route. "
            "Try a longer cross-city route for a clearer race difference."
        )
    else:
        body = (
            f"Dijkstra explored {abs(node_savings)} fewer nodes on this route; "
            "the maps still show the real explored-node sets without forcing a winner."
        )
    total = max(1, d_nodes, a_nodes)
    return html.Div(
        [
            html.Div(
                [
                    html.Div(title, className="cf-race-callout-title"),
                    html.Div(body, className="cf-race-callout-copy"),
                ],
                className="cf-race-callout-copywrap",
            ),
            html.Div(
                [
                    _explored_bar("Dijkstra", d_nodes, total, "is-dijkstra"),
                    _explored_bar("A*", a_nodes, total, "is-astar"),
                ],
                className="cf-race-bars",
            ),
        ],
        className="cf-race-difference-callout",
    )


def _explored_bar(label: str, value: int, total: int, cls: str) -> html.Div:
    width = max(4.0, min(100.0, value / max(1, total) * 100.0))
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label),
                    html.Strong(f"{value} explored"),
                ],
                className="cf-race-bar-label",
            ),
            html.Div(
                html.Span(style={"width": f"{width:.1f}%"}),
                className=f"cf-race-bar-track {cls}",
            ),
        ],
        className="cf-race-bar",
    )


def _panel_models(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    panels = bundle.get("panels") or {}
    d = bundle.get("dijkstra", {})
    a = bundle.get("astar", {})
    cost_view = bundle.get("cost_view", "algorithm")
    d_hops = _path_hops(d)
    a_hops = _path_hops(a)

    return {
        "dijkstra": {
            "kind": "dijkstra",
            "iframe_id": "race-map-dijkstra",
            "title": "DIJKSTRA",
            "algorithm_label": "Dijkstra: Uniform Cost Expansion",
            "subtitle": panels.get("dijkstra", {}).get("subtitle", "Shortest Distance Objective"),
            "cost": panels.get("dijkstra", {}).get("cost_label", _fmt_cost(d.get("cost"))),
            "path": panels.get("dijkstra", {}).get("path", d.get("path")),
            "explored": d.get("n_frames", 0),
            "edges": d.get("edges_relaxed", 0),
            "runtime": d.get("runtime_ms", 0.0),
            "hops": d_hops,
            "color_label": "Cyan",
            "accent": "var(--accent)",
            "cost_view": cost_view,
        },
        "astar": {
            "kind": "astar",
            "iframe_id": "race-map-astar",
            "title": "A* SEARCH",
            "algorithm_label": "A*: Heuristic-Guided Search",
            "subtitle": panels.get("astar", {}).get("subtitle", "Traffic-Aware Heuristic Route"),
            "cost": panels.get("astar", {}).get("cost_label", _fmt_cost(a.get("cost"))),
            "path": panels.get("astar", {}).get("path", a.get("path")),
            "explored": a.get("n_frames", 0),
            "edges": a.get("edges_relaxed", 0),
            "runtime": a.get("runtime_ms", 0.0),
            "hops": a_hops,
            "heuristic": "straight-line distance to target",
            "color_label": "Gold",
            "accent": "var(--accent-warm)",
            "cost_view": cost_view,
        },
    }


def _map_algorithm_panel(panel: dict[str, Any]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(panel["title"], className="cf-race-algo-title"),
                            html.Div(panel["subtitle"], className="cf-race-algo-subtitle"),
                            html.Div(panel["algorithm_label"], className="cf-race-algo-caption"),
                        ],
                        className="cf-race-algo-name",
                    ),
                    html.Div(
                        [
                            html.Span("Cost", className="cf-race-cost-label"),
                            html.Strong(panel["cost"], className="cf-race-cost-value"),
                        ],
                        className="cf-race-cost-chip",
                    ),
                ],
                className="cf-race-map-head",
            ),
            html.Div(
                [
                    _metric("Path", _fmt_path(panel["path"]), "lucide:route", accent=True),
                    _metric("Explored nodes", str(panel["explored"]), "lucide:circle-dot"),
                    _metric("Edges relaxed", str(panel["edges"]), "lucide:git-branch"),
                    _metric("Runtime", f"{float(panel['runtime']):.2f} ms", "lucide:timer"),
                    _metric("Hops", "unreachable" if panel["hops"] is None else str(panel["hops"]), "lucide:milestone"),
                    _metric("Heuristic", panel.get("heuristic", "none"), "lucide:compass")
                    if panel["kind"] == "astar" else None,
                ],
                className="cf-race-map-details",
            ),
            html.Div(
                [
                    html.Iframe(
                        id=panel["iframe_id"],
                        src=f"/assets/maplibre_view.html?race_panel={panel['kind']}",
                        className="cf-race-map-frame",
                        title=f"Race Lab {panel['title']} Cairo map",
                    ),
                ],
                className=f"cf-race-map-shell is-{panel['kind']}",
            ),
        ],
        className=f"cf-race-map-panel is-{panel['kind']}",
    )


def _comparison_insight_cards(
    bundle: dict[str, Any],
    panels: dict[str, dict[str, Any]],
    summary: dict[str, Any],
) -> html.Div:
    d = panels["dijkstra"]
    a = panels["astar"]
    cost_view = bundle.get("cost_view", "algorithm")
    node_savings = int(summary.get("node_savings") or 0)

    if cost_view == "objective":
        winner = (
            "Best for shortest distance: Dijkstra, because its score is measured in kilometers. "
            "Best for traffic-aware travel time: A* / traffic-aware route, because its score is "
            "measured in BPR minutes. These are different objective scores, so the raw numbers "
            "are not compared as the same unit."
        )
    elif node_savings > 0 and summary.get("agree_on_cost"):
        winner = (
            f"A* is more search-efficient because it explored {node_savings} fewer nodes while "
            "preserving the same optimal cost. Dijkstra remains the pure uniform-cost baseline."
        )
    elif node_savings < 0 and summary.get("agree_on_cost"):
        winner = (
            f"Dijkstra explored {abs(node_savings)} fewer nodes on this selected run while both "
            "algorithms preserved the same optimal cost."
        )
    elif summary.get("agree_on_cost"):
        winner = (
            "Both algorithms preserved the same optimal cost and explored the same number of nodes. "
            "For this run the best choice is a tie on search effort."
        )
    else:
        winner = (
            "The selected cost view uses different objective scores. Use the objective labels and "
            "units to decide what is better for the question being asked."
        )

    return html.Div(
        [
            _insight_card(
                "Dijkstra Insight",
                (
                    f"Dijkstra used {d['subtitle']} with cost {d['cost']}. It explored "
                    f"{d['explored']} nodes and relaxed {d['edges']} edges because uniform-cost "
                    "search expands broadly from the source before committing to the target."
                ),
                icon="lucide:radar",
                accent=True,
            ),
            _insight_card(
                "A* Insight",
                (
                    f"A* used {a['subtitle']} with cost {a['cost']}. It explored "
                    f"{a['explored']} nodes and relaxed {a['edges']} edges. Its admissible "
                    "heuristic uses straight-line distance to point the search toward the target, often "
                    "reducing exploration."
                ),
                icon="lucide:compass",
                accent=True,
            ),
            _insight_card(
                "Winner / Best Choice",
                winner,
                icon="lucide:trophy",
                accent=True,
            ),
            _insight_card(
                "Objective Explanation",
                (
                    "Algorithm Cost View compares search behavior under a shared objective. "
                    "Objective Cost View intentionally separates kilometers from BPR minutes so "
                    "the professor can see a real cost-objective difference without fake costs."
                ),
                icon="lucide:split",
                accent=False,
            ),
        ],
        className="cf-race-insights",
    )


def _map_legend() -> html.Div:
    return html.Div(
        [
            _legend_item("Cyan", "Dijkstra path", "is-dijkstra"),
            _legend_item("Gold", "A* path", "is-astar"),
            _legend_item("Glow", "Explored node", "is-explored"),
            _legend_item("Edge", "Explored edge", "is-explored-edge"),
            _legend_item("Source", "Source", "is-source"),
            _legend_item("Target", "Target", "is-target"),
        ],
        className="cf-race-map-legend",
    )


def _legend_item(label: str, value: str, cls: str) -> html.Div:
    return html.Div(
        [
            html.Span(label, className=f"cf-race-legend-swatch {cls}"),
            html.Span(value),
        ],
        className="cf-race-legend-item",
    )


def _legacy_canvas_mount() -> html.Div:
    return html.Div(
        [
            html.Canvas(id="race-canvas-dijkstra", width="320", height="220"),
            html.Canvas(id="race-canvas-astar", width="320", height="220"),
        ],
        className="cf-race-legacy-canvases",
        **{"aria-hidden": "true"},
    )


def _algo_metric_column(
    label: str,
    description: str,
    payload: dict,
    accent: str,
    hops: int | None,
) -> html.Div:
    nodes = payload["n_frames"]
    edges = payload["edges_relaxed"]
    runtime = payload["runtime_ms"]
    cost = payload["cost"]
    cost_str = _fmt_cost(cost)
    hops_str = "unreachable" if hops is None else str(hops)
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label, className="cf-race-col-title"),
                    html.Span(description, className="cf-race-col-meta"),
                ],
                className="cf-race-col-header",
                style={"borderColor": accent},
            ),
            html.Div(
                [
                    _metric("Optimal cost", cost_str, "lucide:sigma", accent=True),
                    _metric("Hops", hops_str, "lucide:milestone"),
                    _metric("Explored nodes", str(nodes), "lucide:circle-dot"),
                    _metric("Edges relaxed", str(edges), "lucide:git-branch"),
                    _metric("Runtime", f"{runtime:.2f} ms", "lucide:timer"),
                ],
                className="cf-race-metrics",
            ),
        ],
        className="cf-race-col",
    )


def _objective_section(objective: dict[str, Any] | None) -> html.Div:
    if not objective:
        body = html.Div(
            "Run Race Lab from the Race Lab controls to compare shortest distance in km "
            "against fastest traffic-aware travel time in minutes.",
            className="cf-race-insight-body",
        )
        return html.Div(
            [
                _section_title(
                    "Distance Cost vs Traffic-Time Cost",
                    "Two different routing objectives shown with separate units.",
                ),
                html.Div(body, className="cf-race-objective-empty"),
            ],
            className="cf-race-objective",
        )

    path_changed = "Changed" if objective.get("path_changed") else "Same path"
    distance_cost = objective.get("distance_cost_km")
    traffic_cost = objective.get("traffic_cost_min")
    distance_cost_text = (
        "unreachable" if distance_cost is None else f"{distance_cost:.2f} km"
    )
    traffic_cost_text = (
        "unreachable" if traffic_cost is None else f"{traffic_cost:.2f} minutes"
    )
    if objective.get("path_changed"):
        path_note = (
            "The selected path changed because fastest travel time can avoid "
            "congested segments even when distance increases."
        )
    else:
        path_note = (
            "Same path here, but evaluated with different objectives. Try a "
            "congested peak-hour route to demonstrate a path change."
        )

    return html.Div(
        [
            _section_title(
                "Distance Cost vs Traffic-Time Cost",
                "This is an objective comparison, not a Dijkstra vs A* race. Distance uses kilometers; traffic-aware routing uses BPR travel time in minutes.",
            ),
            html.Div(
                [
                    _objective_card(
                        "Shortest-Distance Route",
                        "Optimizes road distance only.",
                        [
                            _metric("Distance score", distance_cost_text,
                                    "lucide:ruler", accent=True),
                            _metric("Distance km", distance_cost_text,
                                    "lucide:ruler"),
                            _metric(
                                "Travel time minutes",
                                _fmt_minutes(objective.get("distance_path_travel_min")),
                                "lucide:clock",
                            ),
                            _metric("Path", _fmt_path(objective.get("distance_path")),
                                    "lucide:route"),
                        ],
                    ),
                    _objective_card(
                        "Traffic-Aware Fastest Route",
                        f"Optimizes BPR travel time for {objective.get('time_of_day')}.",
                        [
                            _metric("Traffic-time score", traffic_cost_text,
                                    "lucide:clock", accent=True),
                            _metric(
                                "Distance km",
                                _fmt_km(objective.get("traffic_path_distance_km")),
                                "lucide:ruler",
                            ),
                            _metric("Travel time minutes", traffic_cost_text,
                                    "lucide:clock"),
                            _metric("Path", _fmt_path(objective.get("traffic_path")),
                                    "lucide:route"),
                        ],
                    ),
                ],
                className="cf-race-objective-grid",
            ),
            html.Div(
                [
                    _insight_card(
                        "Why these costs differ",
                        "These costs differ because the objectives differ: shortest "
                        "distance in kilometers vs fastest traffic-aware travel time "
                        "in minutes. The values are separate objective scores, not "
                        "the same unit.",
                        icon="lucide:split",
                        accent=True,
                    ),
                    _insight_card(
                        "Path comparison",
                        f"{path_changed}. {path_note}",
                        icon="lucide:git-compare",
                        accent=bool(objective.get("path_changed")),
                    ),
                    _insight_card(
                        "Suggested demo route for clearer cost/path difference",
                        "Use Morning/Evening peak and a longer cross-city route to make congestion effects clearer.",
                        icon="lucide:map",
                        accent=False,
                    ),
                ],
                className="cf-race-insights",
            ),
        ],
        className="cf-race-objective",
    )


def render_race_empty_state() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("CSE112 algorithm comparison",
                                      className="cf-race-eyebrow"),
                            html.H3("Dijkstra vs A* Race Lab",
                                    className="cf-race-title"),
                            html.P(
                                "Choose source and target, then run the Dijkstra vs A* Race Lab.",
                                className="cf-race-subtitle",
                            ),
                        ],
                        className="cf-race-heading",
                    ),
                ],
                className="cf-race-hero",
            ),
            _map_legend(),
            html.Div(
                "Choose source and target, then run the Dijkstra vs A* Race Lab.",
                className="cf-race-objective-empty",
            ),
            _legacy_canvas_mount(),
        ],
        className="cf-race-lab",
    )


def _objective_card(title: str, subtitle: str, metrics: list[html.Div]) -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Span(title, className="cf-race-col-title"),
                    html.Span(subtitle, className="cf-race-col-meta"),
                ],
                className="cf-race-col-header",
            ),
            html.Div(metrics, className="cf-race-metrics"),
        ],
        className="cf-race-col cf-race-objective-card",
    )


def _fmt_minutes(value: Any) -> str:
    if value is None:
        return "unreachable"
    return f"{float(value):.2f} minutes"


def _fmt_km(value: Any) -> str:
    if value is None:
        return "unreachable"
    return f"{float(value):.2f} km"


def _insight_card(title: str, body: str, icon: str, accent: bool = False) -> html.Div:
    class_name = "cf-race-insight" + (" is-accent" if accent else "")
    if title == "Winner / Best Choice":
        class_name += " is-winner"
    return html.Div(
        [
            html.Div(
                [
                    cf_icon(icon, size=15,
                            color="var(--accent)" if accent else "var(--text-muted)",
                            style={"marginRight": "7px"}),
                    html.Span(title),
                ],
                className="cf-race-insight-title",
            ),
            html.Div(body, className="cf-race-insight-body"),
        ],
        className=class_name,
    )


# ---------------------------------------------------------------------------
# ML forecast card - shown alongside Route results
# ---------------------------------------------------------------------------

def render_ml_forecast_card(metrics: dict, top_features: list[tuple[str, float]],
                            sample: list[dict]) -> html.Div:
    """Compact ML model card: training metrics + top-5 feature importances
    + a few sample predictions vs actuals."""
    return info_card(
        title=html.Span([
            cf_icon("lucide:brain", size=14, color="var(--accent)",
                    style={"marginRight": "6px"}),
            "ML traffic predictor (scikit-learn)",
        ]),
        body=html.Div([
            _stat("Model", metrics.get("model", "-")),
            _stat("Samples", str(metrics.get("n_samples", "-"))),
            _stat("Train / Test", f"{metrics.get('n_train','-')} / {metrics.get('n_test','-')}"),
            _stat("R2 (held-out)",
                  f"{metrics.get('r2', 0.0):.3f}", accent=True),
            _stat("MAE (v/c)",
                  f"{metrics.get('mae', 0.0):.4f}"),
            _stat("vs. mean baseline",
                  f"{metrics.get('improvement_pct', 0.0):+.1f}% better"),
            html.Div("Top features", className="cf-race-section-label"),
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(name.replace("_", " "),
                                      className="cf-stat-label"),
                            html.Span(f"{imp:.3f}",
                                      className="cf-stat-value cf-stat-accent"),
                        ],
                        className="cf-stat-row",
                    )
                    for name, imp in top_features
                ]
            ),
            html.Div("Sample predictions", className="cf-race-section-label")
                if sample else None,
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(f"{r['from']} -> {r['to']} ({r['tod']})",
                                      className="cf-stat-label"),
                            html.Span(
                                f"pred {r['predicted_vc']*100:.0f}%  /  actual {r['actual_vc']*100:.0f}%"
                                if r.get("actual_vc") is not None
                                else f"pred {r['predicted_vc']*100:.0f}%",
                                className="cf-stat-value",
                            ),
                        ],
                        className="cf-stat-row",
                    )
                    for r in sample
                ]
            ) if sample else None,
        ]),
    )
