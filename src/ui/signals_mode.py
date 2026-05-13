"""Signals mode sidebar and result cards for Greedy traffic control."""
from __future__ import annotations

from typing import Any

from dash import dcc, html

from src.algorithms.greedy import CYCLE_SECONDS, MAX_GREEN_S, MIN_GREEN_S
from src.algorithms.trace import AlgorithmTrace
from src.config import TIMES_OF_DAY
from src.db.queries import node_lookup
from src.graph.builder import build_graph
from src.ui.components import (
    algorithm_context,
    cf_button,
    cf_icon,
    empty_state,
    info_card,
    programmer_panel,
)


AUTO_INTERSECTION = "__all__"


def _sort_node_id(node_id: Any) -> tuple[int, str]:
    text = str(node_id)
    return (0, f"{int(text):04d}") if text.isdigit() else (1, text)


def signal_intersection_options() -> list[dict[str, str]]:
    """Return intersections with enough degree for a signal audit."""
    graph = build_graph()
    names = node_lookup()
    options = [
        {
            "label": "Auto / All intersections",
            "value": AUTO_INTERSECTION,
        }
    ]
    for node in sorted(graph.nodes(), key=_sort_node_id):
        if graph.degree(node) < 3:
            continue
        label = names.get(str(node), {}).get("name", str(node))
        options.append({
            "label": f"{label} ({node})",
            "value": str(node),
        })
    return options


def render_signals_panel() -> list:
    return [
        info_card(
            title="Traffic Signal Command Center",
            body=html.Div([
                algorithm_context(
                    "Real-time local optimization",
                    "Greedy Signal Timing",
                    "Allocates green-light time using local traffic demand while respecting minimum and maximum timing constraints.",
                    icon="lucide:traffic-cone",
                ),
                html.Div(
                    "Greedy is suitable for traffic signals because each intersection needs a fast local decision based on current demand, without recomputing a global city-wide optimization every second.",
                    className="cf-signals-note",
                ),
            ]),
        ),
        info_card(
            title="Signal Audit Controls",
            body=html.Div([
                html.Label("Time of Day", className="cf-field-label"),
                dcc.Dropdown(
                    id="signals-tod",
                    options=[{"label": t, "value": t} for t in TIMES_OF_DAY],
                    value=TIMES_OF_DAY[0],
                    clearable=False,
                    className="cf-dd",
                ),
                html.Label("Intersection", className="cf-field-label"),
                dcc.Dropdown(
                    id="signals-intersection",
                    options=signal_intersection_options(),
                    value=AUTO_INTERSECTION,
                    clearable=False,
                    className="cf-dd",
                ),
            ]),
        ),
        cf_button(
            "Run Greedy Signal Audit",
            btn_id="signals-run",
            variant="accent",
            icon="lucide:traffic-cone",
        ),
        dcc.Loading(
            id="signals-result-loading",
            type="circle",
            color="var(--accent-warm)",
            children=html.Div(
                empty_state("Run a Greedy signal audit to see intersection timing"),
                id="signals-result-slot",
            ),
        ),
        html.Div(id="signals-preemption-slot"),
        html.Div(id="signals-prog-slot"),
    ]


def render_signal_result_card(
    *,
    report: dict[str, Any],
    allocation: dict[str, Any],
    selected_intersection: str,
    time_label: str,
    names: dict[str, str],
    flows: dict[str, int],
) -> html.Div:
    trace = allocation.get("trace")
    total_flow = int((trace.parameters or {}).get("total_flow", 0)) if trace else 0
    display_name = names.get(str(selected_intersection), str(selected_intersection))
    optimal = len(report.get("optimal_cases") or [])
    suboptimal = len(report.get("suboptimal_cases") or [])
    audited = int(report.get("intersections_audited") or 0)

    return info_card(
        title="Greedy Decision Panel",
        body=html.Div([
            algorithm_context(
                "Greedy Local Decision Rule",
                "Greedy Signal Timing",
                "Greedy chooses the highest local demand direction first while respecting timing constraints.",
                icon="lucide:traffic-cone",
            ),
            html.Div(
                "Decision rule: sort connected approaches by demand, allocate green time greedily, then clamp to min/max safety limits.",
                className="cf-signals-rule",
            ),
            _signal_stat("Selected intersection", f"{display_name} ({selected_intersection})", "lucide:map-pin", True),
            _signal_stat("Demand score", f"{total_flow:,} veh/h", "lucide:gauge"),
            _signal_stat("Signal limits", f"{MIN_GREEN_S}s min / {MAX_GREEN_S}s max / {CYCLE_SECONDS}s cycle", "lucide:timer"),
            _signal_stat("Intersections audited", str(audited), "lucide:scan-line"),
            _signal_stat("Optimal signal count", str(optimal), "lucide:check-circle"),
            _signal_stat("Suboptimal signal count", str(suboptimal), "lucide:alert-triangle"),
            _signal_stat("Fairness / Gini score", str(report.get("gini_overall", "0.0")), "lucide:scale", True),
            _signals_map_legend(),
            _allocation_bars(allocation.get("allocations") or {}, flows, names),
            render_signal_audit_board(report, names),
            html.Div(
                f"Audit time: {time_label}. Green time is allocated from local edge demand, then clamped to the signal safety limits.",
                className="cf-comparison-strip",
            ),
        ]),
    )


def _signals_map_legend() -> html.Div:
    return html.Div(
        [
            html.Div("Map Overlay Legend", className="cf-signals-subtitle"),
            html.Div([
                _legend_item("Optimal signal", "is-optimal"),
                _legend_item("Watch / near limit", "is-watch"),
                _legend_item("Suboptimal", "is-risk"),
                _legend_item("Selected intersection", "is-selected"),
                _legend_item("Connected approach", "is-approach"),
            ], className="cf-signals-legend-grid"),
        ],
        className="cf-signals-map-legend",
    )


def _legend_item(label: str, cls: str) -> html.Div:
    return html.Div(
        [html.Span(className=f"cf-signals-legend-swatch {cls}"), html.Span(label)],
        className="cf-signals-legend-item",
    )


def render_signal_audit_board(report: dict[str, Any], names: dict[str, str]) -> html.Div:
    optimal = report.get("optimal_cases") or []
    suboptimal = report.get("suboptimal_cases") or []
    cards = []
    for case in optimal[:2]:
        node = str(case.get("intersection"))
        cards.append(_audit_chip(
            "Optimal signal",
            names.get(node, node),
            f"max/min {case.get('max_min_ratio')} | Greedy spread matches demand.",
            "is-optimal",
        ))
    for case in suboptimal[:3]:
        node = str(case.get("intersection"))
        direction = str(case.get("starved_direction"))
        route_label = f"{names.get(node, node)} \u2192 {names.get(direction, direction)}"
        cards.append(_audit_chip(
            "Approach Watch",
            route_label,
            f"Connected approach warning: {route_label} received {case.get('green_s')}s green.",
            "is-watch",
        ))
    if not cards:
        cards.append(_audit_chip(
            "Stable",
            "All audited signals",
            "No high-risk greedy cases surfaced for this time period.",
            "is-optimal",
        ))
    return html.Div(
        [
            html.Div("Audited Intersection Summary", className="cf-signals-subtitle"),
            html.Div(cards, className="cf-signals-audit-grid"),
        ],
        className="cf-signals-board",
    )


def render_emergency_preemption_card(schedule: list[dict[str, Any]], names: dict[str, str]) -> html.Div:
    grouped = _group_preemption_schedule(schedule, names)
    if not grouped:
        body: list[Any] = [
            html.Div("No eligible signalized intersection found for the sample emergency route.", className="cf-placeholder")
        ]
    else:
        body = [
            _signal_stat(
                f"{item['vehicle']} - Priority {item['priority']}",
                f"Route sequence: {item['sequence']}",
                "lucide:siren",
                idx == 0,
            )
            for idx, item in enumerate(grouped[:4])
        ]
    return info_card(
        title="Emergency Preemption",
        body=html.Div([
            algorithm_context(
                "Priority dispatch rule",
                "Greedy Priority Scheduling",
                "Prioritizes emergency vehicles by urgency and route order using a fast local priority rule.",
                icon="lucide:siren",
            ),
            *body,
        ]),
        )


def _group_preemption_schedule(schedule: list[dict[str, Any]], names: dict[str, str]) -> list[dict[str, str]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in schedule:
        vehicle = str(row.get("emergency_id") or "Emergency")
        item = grouped.setdefault(vehicle, {
            "vehicle": vehicle,
            "priority": int(row.get("priority") or 9),
            "steps": [],
        })
        item["priority"] = min(item["priority"], int(row.get("priority") or item["priority"]))
        item["steps"].append(row)

    output = []
    for item in sorted(grouped.values(), key=lambda entry: (entry["priority"], entry["vehicle"])):
        steps = sorted(item["steps"], key=lambda row: int(row.get("arrival_index") or 0))
        sequence = " \u2192 ".join(
            names.get(str(row.get("intersection")), str(row.get("intersection")))
            for row in steps
        )
        output.append({
            "vehicle": item["vehicle"],
            "priority": str(item["priority"]),
            "sequence": sequence,
        })
    return output


def render_signals_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    if not programmer_on or trace is None:
        return None
    return programmer_panel(trace)


def _signal_stat(label: str, value: Any, icon: str, accent: bool = False) -> html.Div:
    return html.Div(
        [
            html.Span(
                [cf_icon(icon, size=14, style={"marginRight": "6px"}), label],
                className="cf-stat-label",
            ),
            html.Span(str(value), className="cf-stat-value" + (" cf-stat-accent" if accent else "")),
        ],
        className="cf-stat-row",
    )


def _allocation_bars(allocations: dict[Any, int], flows: dict[str, int], names: dict[str, str]) -> html.Div:
    if not allocations:
        return html.Div("No allocation data available.", className="cf-placeholder")
    rows = []
    for node, seconds in sorted(allocations.items(), key=lambda item: (-int(item[1]), str(item[0]))):
        key = str(node)
        pct = max(6, min(100, int(seconds) / max(1, CYCLE_SECONDS) * 100))
        rows.append(html.Div(
            [
                html.Div(
                    [
                        html.Span(names.get(key, key)),
                        html.Strong(f"Greedy: {int(seconds)}s green"),
                    ],
                    className="cf-signals-bar-label",
                ),
                html.Div(
                    html.Span(style={"width": f"{pct:.1f}%"}),
                    className="cf-signals-bar-track",
                ),
                html.Div(f"Demand: {int(flows.get(key, 0)):,} veh/h", className="cf-signals-bar-meta"),
            ],
            className="cf-signals-bar",
        ))
    return html.Div(
        [
            html.Div("Recommended Green-Time Allocation for Connected Approaches", className="cf-signals-subtitle"),
            html.Div(
                "Each row represents a connected approach receiving green time from the selected intersection.",
                className="cf-signals-note",
            ),
            *rows,
        ],
        className="cf-signals-bars",
    )


def _audit_chip(status: str, title: str, body: str, cls: str) -> html.Div:
    return html.Div(
        [
            html.Span(status, className=f"cf-signals-status {cls}"),
            html.Strong(title),
            html.Span(body),
        ],
        className="cf-signals-audit-chip",
    )
