"""Network mode sidebar — MST controls + stats + algorithm details."""
from __future__ import annotations

from typing import Any

from dash import dcc, html

from src.algorithms.trace import AlgorithmTrace
from src.ui.components import (
    algorithm_context,
    cf_button,
    cf_icon,
    empty_state,
    info_card,
    programmer_panel,
)


def _algo_pill(label: str, algo: str, active: bool = False) -> html.Button:
    cls = "cf-pill cf-pill-wide"
    if active:
        cls += " active"
    return html.Button(
        label,
        id={"type": "mst-algo", "algo": algo},
        n_clicks=0,
        className=cls,
    )


def render_algo_pills(active: str = "kruskal") -> html.Div:
    return html.Div(
        [
            _algo_pill("Kruskal", "kruskal", active=(active == "kruskal")),
            _algo_pill("Prim", "prim", active=(active == "prim")),
        ],
        className="cf-pills cf-pills-2",
        id="mst-algo-pills",
    )


def render_network_panel(active_algo: str = "kruskal") -> list:
    """The Network mode body. Plugged into `mode-content` by the
    sidebar dispatcher."""
    return [
        info_card(
            title="Infrastructure Network Design",
            body=html.Div(
                [
                    algorithm_context(
                        "Infrastructure Network Design",
                        "Kruskal MST / Prim MST",
                        "Builds a low-cost connection network using minimum spanning tree algorithms.",
                    ),
                    render_algo_pills(active_algo),
                    dcc.Checklist(
                        id="mst-options",
                        options=[
                            {"label": " Population-weighted",
                             "value": "weighted"},
                            {"label": " Prioritize critical facility connectivity",
                             "value": "must_include"},
                        ],
                        value=["must_include"],
                        className="cf-checklist",
                        labelStyle={"display": "block", "marginTop": "6px"},
                    ),
                ]
            ),
        ),
        cf_button(
            "Compute Network", btn_id="mst-compute",
            variant="accent", icon="lucide:zap",
        ),
        # Slots for the compute callback. Wrapped in dcc.Loading so a
        # spinner appears in the result area while the graph runs.
        dcc.Loading(
            id="mst-stats-loading",
            type="circle",
            color="var(--accent)",
            children=html.Div(empty_state(), id="mst-stats-slot"),
        ),
        html.Div(id="mst-prog-slot"),
    ]


# ---- Stats and algo-details cards ----

def _row(label: str, value: Any, *, accent: bool = False, icon: str | None = None) -> html.Div:
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
            html.Span(
                value,
                className="cf-stat-value" + (" cf-stat-accent" if accent else ""),
            ),
        ],
        className="cf-stat-row",
    )


def _format_cost_display(cost: float, all_potential_cost: float) -> Any:
    """Per spec:
    - if total_cost == 0: 'EGP 0M — all existing roads, no new construction'
    - else: 'EGP {cost:.1f}M  (saves {savings_pct}% vs. building all)'
    """
    if cost == 0:
        return html.Span(
            ["EGP 0M  ",
             html.Span("— all existing roads, no new construction",
                       style={"color": "var(--text-secondary)",
                              "fontWeight": "400",
                              "fontSize": "11px"})],
        )
    if all_potential_cost > 0:
        savings_pct = max(0.0, (all_potential_cost - cost) / all_potential_cost * 100.0)
        return html.Span(
            [f"EGP {cost:,.1f}M  ",
             html.Span(
                 f"(saves {savings_pct:.0f}% vs. EGP {all_potential_cost:,.0f}M "
                 "to build all potential roads)",
                 style={"color": "var(--text-secondary)",
                        "fontWeight": "400",
                        "fontSize": "11px"},
             )],
        )
    return f"EGP {cost:,.1f}M"


def render_stats_card(stats: dict[str, Any]) -> html.Div:
    isolated = stats.get("isolated_before", [])
    isolated_text = ", ".join(isolated) if isolated else "None"
    connected_after = stats.get("all_connected_after", False)
    cost = stats.get("total_cost_million_egp", 0)
    all_potential_cost = stats.get("all_potential_cost_million_egp", 0)
    cost_display = _format_cost_display(cost, all_potential_cost)
    covered = stats.get("covered_nodes", 0) or 1
    cost_per_node = cost / covered if covered else 0.0
    return info_card(
        title="Infrastructure Network Design Result",
        body=html.Div(
            [
                algorithm_context(
                    "Infrastructure Network Design",
                    "Minimum Spanning Tree",
                    "Connects the reachable city network with the lowest available construction cost.",
                ),
                _row("Total MST cost", cost_display, accent=True, icon="lucide:wallet"),
                _row("Cost-effectiveness",
                     f"EGP {cost_per_node:,.2f}M per connected node",
                     icon="lucide:trending-up"),
                _row("Roads included",
                     f"{stats.get('roads_included', 0)} edges",
                     icon="lucide:milestone"),
                _row("New roads needed",
                     f"{stats.get('new_roads_needed', 0)} edges",
                     icon="lucide:hammer"),
                _row("Existing roads used",
                     f"{stats.get('existing_roads_used', 0)} edges",
                     icon="lucide:check-check"),
                _row(
                    "Covered nodes",
                    f"{stats.get('covered_nodes', 0)} / {stats.get('total_nodes', 0)} nodes",
                    icon="lucide:circle-dot",
                ),
                _row("Isolated before MST", isolated_text,
                     icon="lucide:circle-off"),
                _row(
                    "Reachable network spanned",
                    html.Span("✓",
                              style={"color": "#22c55e", "fontWeight": "600"}) if connected_after
                    else html.Span("✕",
                                   style={"color": "#ef4444", "fontWeight": "600"}),
                    icon="lucide:link",
                ),
            ]
        ),
    )


def render_algo_details_card(trace: AlgorithmTrace) -> html.Div:
    p = trace.parameters
    return info_card(
        title="Network Algorithm Details",
        body=html.Div(
            [
                algorithm_context(
                    "MST Computation",
                    trace.name,
                    "Shows the graph strategy, data structure, and runtime used for network design.",
                ),
                _row("Algorithm", trace.name, icon="lucide:cpu"),
                _row("Time complexity", trace.complexity_time, icon="lucide:clock"),
                _row("Space complexity", trace.complexity_space, icon="lucide:database"),
                _row("Data structure", p.get("data_structure", "—"),
                     icon="lucide:layers"),
                _row("Edges considered", trace.edges_relaxed,
                     icon="lucide:git-branch"),
                _row("MST edges selected", len(list(trace.nodes_explored)),
                     icon="lucide:check"),
                _row("Runtime", f"{trace.runtime_ms:.2f} ms",
                     accent=True, icon="lucide:timer"),
            ]
        ),
    )


def render_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    """Renders the programmer panel only when Programmer Mode is on."""
    if not programmer_on:
        return None
    return programmer_panel(trace)
