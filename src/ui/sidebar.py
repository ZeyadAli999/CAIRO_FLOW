"""Sidebar: mode pills + per-mode placeholder content area.

Phase 1 only renders placeholder panels; later phases will plug real
controls into the same `mode-content` Output target.
"""
from __future__ import annotations

from dash import html

from src.config import DEFAULT_MODE, MODES
from src.ui.components import info_card, mode_pill
from src.ui.emergency_mode import render_emergency_panel
from src.ui.maintain_mode import render_maintain_panel
from src.ui.network_mode import render_network_panel
from src.ui.race_view import render_race_panel
from src.ui.route_mode import render_route_panel
from src.ui.transit_mode import render_transit_panel


def render_pills(active_mode: str = DEFAULT_MODE) -> html.Div:
    return html.Div(
        [
            mode_pill(m["label"], m["icon"], m["id"], active=(m["id"] == active_mode))
            for m in MODES
        ],
        className="cf-pills",
        id="mode-pills",
    )


def placeholder_for(mode: str) -> list:
    """Return the body shown in the sidebar for a given mode."""
    if mode == "network":
        return render_network_panel()
    if mode == "route":
        return render_route_panel()
    if mode == "emergency":
        return render_emergency_panel()
    if mode == "maintain":
        return render_maintain_panel()
    if mode == "transit":
        return render_transit_panel()
    if mode == "race_lab":
        return render_race_panel()
    return [
        info_card(
            title="Mode",
            body="Coming soon.",
            footer="Phase 4.",
        ),
    ]


def render_sidebar(active_mode: str = DEFAULT_MODE) -> html.Aside:
    return html.Aside(
        [
            html.Div(
                [
                    html.Span("Control Panel", className="cf-sidebar-chrome-label"),
                    html.Button(
                        "<",
                        id="cf-sidebar-toggle",
                        className="cf-sidebar-toggle",
                        type="button",
                        title="Collapse sidebar",
                        **{
                            "aria-label": "Collapse controls sidebar",
                            "aria-expanded": "true",
                        },
                    ),
                ],
                className="cf-sidebar-chrome",
                **{"aria-label": "Sidebar controls"},
            ),
            render_pills(active_mode),
            html.Div(placeholder_for(active_mode), id="mode-content"),
            html.Div(
                id="cf-sidebar-resize-handle",
                className="cf-sidebar-resize-handle",
                role="separator",
                **{
                    "aria-orientation": "vertical",
                    "aria-label": "Resize sidebar",
                },
            ),
        ],
        className="cf-sidebar",
    )
