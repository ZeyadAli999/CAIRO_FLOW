"""Maintain mode sidebar — DP knapsack road-repair optimizer."""
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


# ---------------------------------------------------------------------------
# Sidebar panel
# ---------------------------------------------------------------------------

def render_maintain_panel() -> list:
    return [
        info_card(
            title="Budget",
            body=html.Div(
                [
                    dcc.Slider(
                        id="maintain-budget",
                        min=200, max=2000, step=50, value=500,
                        marks={i: f"{i}M" for i in (200, 500, 1000, 1500, 2000)},
                        tooltip={"placement": "bottom", "always_visible": False},
                    ),
                    html.Div(id="maintain-budget-readout",
                             style={"marginTop": "8px",
                                    "fontFamily": "JetBrains Mono, monospace",
                                    "fontSize": "12px",
                                    "color": "var(--text-secondary)"}),
                ]
            ),
        ),
        info_card(
            title="Filters",
            body=dcc.Checklist(
                id="maintain-options",
                options=[{"label": " Show only poor roads (condition ≤ 6)",
                          "value": "poor_only"}],
                value=["poor_only"],
                className="cf-checklist",
                labelStyle={"display": "block", "marginTop": "6px"},
            ),
        ),
        cf_button(
            "Optimize Repairs", btn_id="maintain-optimize",
            variant="primary", icon="lucide:hammer",
        ),
        dcc.Loading(
            id="maintain-result-loading",
            type="circle",
            color="var(--accent-warm)",
            children=html.Div(empty_state(
                "Pick a budget and run the optimizer",
                icon="lucide:hammer",
            ), id="maintain-result-slot"),
        ),
        html.Div(id="maintain-list-slot"),
        html.Div(id="maintain-prog-slot"),
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


def render_maintain_summary_card(
    *, selected_count: int, total_cost: float, budget: float,
    total_value: float, population_served: int,
    n_poor_total: int,
) -> html.Div:
    cost_str = f"EGP {total_cost:,.1f}M / {budget:,.0f}M"
    return info_card(
        title=html.Span([
            cf_icon("lucide:wrench", size=16, color="var(--accent-warm)",
                    style={"marginRight": "6px"}),
            "Repair plan",
        ]),
        body=html.Div([
            _stat_row("Selected roads",
                      f"{selected_count} / {n_poor_total} poor",
                      accent=True, icon="lucide:check"),
            _stat_row("Total cost", cost_str, icon="lucide:wallet"),
            _stat_row("Total value score", f"{total_value:.2f}",
                      icon="lucide:trending-up"),
            _stat_row("Population served", f"{population_served:,}",
                      icon="lucide:users"),
        ]),
    )


def render_maintain_list_card(selected_roads: list[dict],
                              names: dict[str, str]) -> html.Div:
    if not selected_roads:
        return info_card(
            title="Selected roads",
            body=html.Div(
                "No roads selected at this budget.",
                className="cf-placeholder",
            ),
        )
    rows = []
    for r in selected_roads:
        a = names.get(str(r["from"]), str(r["from"]))
        b = names.get(str(r["to"]), str(r["to"]))
        rows.append(
            html.Div(
                [
                    html.Span(f"{a}  →  {b}", className="cf-stat-label"),
                    html.Span(
                        f"EGP {r['cost_million_egp']:.0f}M  ·  "
                        f"v={r['value']:.2f}  ·  cond={r['condition']}",
                        className="cf-stat-value",
                    ),
                ],
                className="cf-stat-row",
            )
        )
    return info_card(title="Per-road detail", body=html.Div(rows))


def render_maintain_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    if not programmer_on:
        return None
    return programmer_panel(trace)
