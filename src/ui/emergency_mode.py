"""Emergency mode sidebar — incident → nearest hospital with A*."""
from __future__ import annotations

from typing import Any

from dash import dcc, html

from src.algorithms.trace import AlgorithmTrace
from src.ui.components import (
    cf_button,
    cf_icon,
    empty_state,
    info_card,
    programmer_panel,
)
from src.ui.route_mode import node_options


def render_emergency_panel() -> list:
    return [
        info_card(
            title="Incident location",
            body=dcc.Dropdown(
                id="em-incident",
                options=node_options(),
                value="11",
                clearable=False,
                className="cf-dd",
            ),
        ),
        info_card(
            title="Facility type",
            body=dcc.RadioItems(
                id="em-facility-type",
                options=[
                    {"label": " Medical", "value": "Medical"},
                    {"label": " Any", "value": "Any"},
                ],
                value="Any",  # Phase 4: Medical defaults to no path on
                              # the shipped data (F9/F10 isolated); "Any"
                              # gives a useful first-time result.
                className="cf-radio",
                labelStyle={"display": "inline-block", "marginRight": "16px"},
            ),
        ),
        info_card(
            title="Traffic conditions",
            body=dcc.RadioItems(
                id="em-traffic-mode",
                options=[
                    {"label": " Use current time", "value": "current"},
                    {"label": " Ignore traffic — emergency", "value": "ignore"},
                ],
                value="current",
                className="cf-radio",
                labelStyle={"display": "block", "marginTop": "4px"},
            ),
        ),
        cf_button(
            "Dispatch", btn_id="em-dispatch",
            variant="danger", icon="lucide:siren",
        ),
        dcc.Loading(
            id="em-result-loading",
            type="circle",
            color="var(--danger)",
            children=html.Div(empty_state("Dispatch a vehicle to see results"),
                              id="em-result-slot"),
        ),
        html.Div(id="em-perf-slot"),
        html.Div(id="em-traffic-slot"),
        html.Div(id="em-prog-slot"),
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


def render_emergency_result_card(
    *,
    facility_id: str | None,
    facility_name: str | None,
    eta_min: float | None,
    distance_km: float | None,
    path: list,
    names: dict[str, str],
    choice_explanation: str | None = None,
) -> html.Div:
    if facility_id is None or path is None:
        return info_card(
            title="Dispatch failed",
            body=html.Div(
                "No reachable facility from this incident location.",
                className="cf-placeholder",
            ),
        )
    via = "  →  ".join(names.get(p, str(p)) for p in path)
    return info_card(
        title=html.Span([
            cf_icon("lucide:siren", size=16, color="var(--danger)",
                    style={"marginRight": "6px"}),
            "Dispatch result",
        ]),
        body=html.Div([
            _stat_row("Nearest facility",
                      f"{facility_name or facility_id} ({facility_id})",
                      accent=True, icon="lucide:hospital"),
            _stat_row("ETA",
                      f"{eta_min:.1f} min" if eta_min is not None else "—",
                      icon="lucide:clock"),
            _stat_row("Distance",
                      f"{distance_km:.1f} km" if distance_km is not None else "—",
                      icon="lucide:ruler"),
            _stat_row("Route", via, icon="lucide:route"),
            html.Div(choice_explanation, className="cf-placeholder")
            if choice_explanation else None,
        ]),
    )


def render_emergency_performance_card(
    astar_nodes: int, dijkstra_nodes: int,
    astar_runtime_ms: float, dijkstra_runtime_ms: float,
) -> html.Div:
    if dijkstra_nodes:
        speedup = max(0.0, (dijkstra_nodes - astar_nodes) / dijkstra_nodes * 100.0)
    else:
        speedup = 0.0
    return info_card(
        title="A* vs Dijkstra",
        body=html.Div([
            _stat_row("A* explored", f"{astar_nodes} nodes",
                      icon="lucide:circle-dot"),
            _stat_row("Dijkstra would explore", f"{dijkstra_nodes} nodes",
                      icon="lucide:circle-dashed"),
            _stat_row("Speed-up (nodes)", f"{speedup:.1f}% fewer",
                      accent=True, icon="lucide:zap"),
            _stat_row("A* runtime", f"{astar_runtime_ms:.2f} ms",
                      icon="lucide:timer"),
            _stat_row("Dijkstra runtime", f"{dijkstra_runtime_ms:.2f} ms",
                      icon="lucide:timer"),
        ]),
    )


def render_emergency_traffic_card(
    naive_min: float | None, aware_min: float | None,
) -> html.Div:
    if naive_min is None or aware_min is None:
        return info_card(
            title="Traffic-awareness",
            body=html.Div("Comparison unavailable (no reachable path).",
                          className="cf-placeholder"),
        )
    saved = naive_min - aware_min
    pct = (saved / naive_min * 100.0) if naive_min > 0 else 0.0
    return info_card(
        title="Traffic-awareness impact",
        body=html.Div([
            _stat_row("Naive routing ETA", f"{naive_min:.1f} min",
                      icon="lucide:clock"),
            _stat_row("Traffic-aware ETA", f"{aware_min:.1f} min",
                      accent=True, icon="lucide:activity"),
            _stat_row("Time saved",
                      f"{saved:+.1f} min  ({pct:+.1f}%)",
                      icon="lucide:trending-down"),
        ]),
    )


def render_emergency_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    if not programmer_on:
        return None
    return programmer_panel(trace)
