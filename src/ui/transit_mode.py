"""Transit mode sidebar — bus / metro DP, multimodal routing, transfers."""
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


# ---------------------------------------------------------------------------
# Sub-tab pills
# ---------------------------------------------------------------------------

TRANSIT_TABS = [
    ("bus",        "Bus Schedule"),
    ("metro",      "Metro Schedule"),
    ("multimodal", "Multi-Modal"),
    ("transfers",  "Transfers"),
]


def render_transit_tabs(active: str = "bus") -> html.Div:
    pills = []
    for tab_id, label in TRANSIT_TABS:
        cls = "cf-pill cf-pill-wide"
        if tab_id == active:
            cls += " active"
        pills.append(html.Button(
            label,
            id={"type": "transit-tab", "tab": tab_id},
            n_clicks=0,
            className=cls,
        ))
    return html.Div(pills, className="cf-pills cf-pills-4", id="transit-tabs")


# ---------------------------------------------------------------------------
# Tab bodies
# ---------------------------------------------------------------------------

def _bus_tab_body() -> html.Div:
    return html.Div([
        info_card(
            title="Total buses available",
            body=html.Div([
                dcc.Slider(id="transit-bus-total", min=50, max=250,
                           step=10, value=200,
                           marks={i: str(i) for i in (50, 100, 150, 200, 250)},
                           tooltip={"placement": "bottom",
                                    "always_visible": False}),
            ]),
        ),
        cf_button("Optimize Allocation", btn_id="transit-bus-optimize",
                  variant="primary", icon="lucide:bus"),
        dcc.Loading(
            id="transit-bus-loading", type="circle", color="var(--accent)",
            children=html.Div(empty_state("Set a fleet size and optimize",
                                          icon="lucide:bus"),
                              id="transit-bus-result"),
        ),
    ])


def _metro_tab_body() -> html.Div:
    return html.Div([
        info_card(
            title="Train-hours per day",
            body=html.Div([
                dcc.Slider(id="transit-metro-total", min=50, max=500,
                           step=10, value=200,
                           marks={i: str(i) for i in (50, 150, 250, 350, 500)},
                           tooltip={"placement": "bottom"}),
            ]),
        ),
        cf_button("Optimize Allocation", btn_id="transit-metro-optimize",
                  variant="primary", icon="lucide:train-front"),
        dcc.Loading(
            id="transit-metro-loading", type="circle", color="var(--accent)",
            children=html.Div(empty_state("Set train-hours and optimize",
                                          icon="lucide:train-front"),
                              id="transit-metro-result"),
        ),
    ])


def _multimodal_tab_body() -> html.Div:
    return html.Div([
        info_card(
            title="From",
            body=dcc.Dropdown(id="transit-mm-from",
                              options=node_options(), value="11",
                              clearable=False, className="cf-dd"),
        ),
        info_card(
            title="To",
            body=dcc.Dropdown(id="transit-mm-to",
                              options=node_options(), value="F1",
                              clearable=False, className="cf-dd"),
        ),
        cf_button("Find Best Route", btn_id="transit-mm-find",
                  variant="primary", icon="lucide:navigation"),
        dcc.Loading(
            id="transit-mm-loading", type="circle", color="var(--accent)",
            children=html.Div(empty_state("Pick endpoints to see legs",
                                          icon="lucide:navigation"),
                              id="transit-mm-result"),
        ),
    ])


def _transfers_tab_body() -> html.Div:
    return html.Div([
        info_card(
            title="Transfer hub analysis",
            body=html.Div([
                "Multimodal Dijkstra is run for every transit-demand pair "
                "in the dataset. Hubs are ranked by usage × demand.",
            ], style={"fontSize": "12px",
                      "color": "var(--text-secondary)",
                      "lineHeight": "1.5"}),
        ),
        cf_button("Analyze Transfer Points", btn_id="transit-trf-analyze",
                  variant="primary", icon="lucide:replace"),
        dcc.Loading(
            id="transit-trf-loading", type="circle", color="var(--accent)",
            children=html.Div(empty_state("Run analysis to rank hubs",
                                          icon="lucide:replace"),
                              id="transit-trf-result"),
        ),
    ])


def _tab_body_for(tab: str) -> Any:
    return {
        "bus":        _bus_tab_body,
        "metro":      _metro_tab_body,
        "multimodal": _multimodal_tab_body,
        "transfers":  _transfers_tab_body,
    }.get(tab, _bus_tab_body)()


# ---------------------------------------------------------------------------
# Top-level panel
# ---------------------------------------------------------------------------

def render_transit_panel(active_tab: str = "bus") -> list:
    return [
        render_transit_tabs(active_tab),
        html.Div(_tab_body_for(active_tab), id="transit-tab-body"),
        html.Div(id="transit-prog-slot"),
    ]


# ---------------------------------------------------------------------------
# Result-card builders
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


def render_bus_result_card(allocations: dict, current: dict,
                           total_benefit: float, total: int) -> html.Div:
    rows = []
    for rid, opt in allocations.items():
        cur = current.get(rid, "—")
        delta = opt - cur if isinstance(cur, int) else 0
        delta_str = (f" ({delta:+d})" if isinstance(cur, int) and delta else "")
        rows.append(_stat_row(
            f"Route {rid}",
            f"{cur} → {opt}{delta_str}",
            icon="lucide:bus",
        ))
    return info_card(
        title=html.Span([
            cf_icon("lucide:bus", size=16, color="var(--accent)",
                    style={"marginRight": "6px"}),
            "Optimized bus allocation",
        ]),
        body=html.Div([
            _stat_row("Total buses", str(total), accent=True,
                      icon="lucide:hash"),
            _stat_row("DP benefit", f"{total_benefit:,.0f} pax/day",
                      accent=True, icon="lucide:trending-up"),
            *rows,
        ]),
    )


def render_metro_result_card(allocations: dict, total_benefit: float,
                             total: int) -> html.Div:
    return info_card(
        title=html.Span([
            cf_icon("lucide:train-front", size=16, color="var(--accent)",
                    style={"marginRight": "6px"}),
            "Optimized metro hours",
        ]),
        body=html.Div([
            _stat_row("Total train-hours", str(total), accent=True,
                      icon="lucide:hash"),
            _stat_row("DP benefit", f"{total_benefit:,.0f} pax-mins",
                      accent=True, icon="lucide:trending-up"),
            *[
                _stat_row(f"Line {lid}", f"{hours} hours",
                          icon="lucide:train-front")
                for lid, hours in allocations.items()
            ],
        ]),
    )


_MODE_BADGE = {
    "road":  ("lucide:car",     "Road",  "var(--text-secondary)"),
    "metro": ("lucide:train-front", "Metro", "#06b6d4"),
    "bus":   ("lucide:bus",     "Bus",   "#fde047"),
}


def render_mm_result_card(*, total_min: float, road_only_min: float | None,
                          breakdown: list[dict],
                          names: dict[str, str]) -> html.Div:
    legs = []
    for leg in breakdown:
        ico, name, color = _MODE_BADGE.get(leg["mode"], ("lucide:circle", leg["mode"], "var(--text-secondary)"))
        legs.append(html.Div(
            [
                cf_icon(ico, size=14, color=color,
                        style={"marginRight": "6px", "flexShrink": 0}),
                html.Span(
                    f"{name}  {names.get(str(leg['from']), str(leg['from']))}"
                    f"  →  {names.get(str(leg['to']), str(leg['to']))}",
                    style={"flex": 1},
                ),
                html.Span(f"{leg['time_min']:.1f} min",
                          className="cf-stat-value"),
            ],
            className="cf-stat-row",
            style={"display": "flex", "alignItems": "center"},
        ))
    delta_node = ""
    if road_only_min is not None:
        save = road_only_min - total_min
        if save > 0:
            delta_node = (
                f"Saved {save:.1f} min vs road-only {road_only_min:.1f} min"
            )
        elif save < 0:
            delta_node = (
                f"+{abs(save):.1f} min vs road-only {road_only_min:.1f} min"
            )
    return info_card(
        title=html.Span([
            cf_icon("lucide:navigation", size=16, color="var(--accent)",
                    style={"marginRight": "6px"}),
            "Multimodal route",
        ]),
        body=html.Div([
            _stat_row("Total time", f"{total_min:.1f} min",
                      accent=True, icon="lucide:clock"),
            *legs,
            html.Div(delta_node, className="cf-comparison-strip") if delta_node else None,
        ]),
    )


def render_transfers_card(ranking: list[dict]) -> html.Div:
    if not ranking:
        return info_card(
            title="Transfer hubs",
            body=html.Div("No transfer hubs found in current demand graph.",
                          className="cf-placeholder"),
        )
    return info_card(
        title=html.Span([
            cf_icon("lucide:replace", size=16, color="var(--accent)",
                    style={"marginRight": "6px"}),
            "Top transfer hubs",
        ]),
        body=html.Div([
            _stat_row(
                f"{r['name']} ({r['node_id']})",
                f"{r['transfer_count']} transfers · {r['weighted_demand']:,.0f} pax",
                icon="lucide:replace",
            )
            for r in ranking[:5]
        ]),
    )


def render_transit_programmer_slot(trace: AlgorithmTrace, programmer_on: bool):
    if not programmer_on or trace is None:
        return None
    return programmer_panel(trace)
