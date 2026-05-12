"""The top-level Dash layout."""
from __future__ import annotations

from dash import dcc, html

from src.config import DEFAULT_MODE, DEFAULT_TIME_OF_DAY, TIMES_OF_DAY
from src.ui.components import cf_icon
from src.ui.map_view import render_map
from src.ui.sidebar import render_sidebar


# ---------------------------------------------------------------------------
# Topbar — Phase 3 polish: custom SVG mark + mixed-weight wordmark
# ---------------------------------------------------------------------------

def _logo_mark() -> html.Button:
    """The user-supplied CairoFlow mark, served from /assets/NEW_LOGO.png."""
    return html.Button(
        html.Img(
            src="/assets/NEW_LOGO.png",
            className="cf-logo-mark",
            alt="CairoFlow",
        ),
        id="cf-logo-button",
        className="cf-logo-button",
        n_clicks=0,
        title="CairoFlow home. Long press to preview logo.",
    )


def _wordmark() -> html.Div:
    return html.Div(
        [
            html.Span("Cairo", className="cf-wordmark-1"),
            html.Span("Flow", className="cf-wordmark-2"),
        ],
        className="cf-wordmark",
    )


def _programmer_toggle() -> html.Div:
    return html.Div(
        [
            cf_icon("lucide:eye", size=14, className="cf-toggle-icon-off",
                    color="var(--text-muted)"),
            html.Span(
                [
                    html.Span(
                        id="programmer-mode-thumb-shadow",
                        className="cf-toggle-thumb",
                    )
                ],
                id="programmer-mode-track",
                className="cf-toggle-track",
            ),
            cf_icon("lucide:code-2", size=14, className="cf-toggle-icon-on",
                    color="var(--text-muted)"),
            html.Span("Trace Mode", className="cf-toggle-label"),
        ],
        className="cf-toggle",
        id="programmer-mode-toggle",
        n_clicks=0,
    )


def _topbar() -> html.Header:
    return html.Header(
        [
            html.Div(
                [
                    _logo_mark(),
                    html.Div(
                        [
                            _wordmark(),
                            html.Span(
                                "Greater Cairo Smart Mobility",
                                className="cf-brand-subtitle",
                            ),
                        ],
                        className="cf-brand-lockup",
                    ),
                ],
                className="cf-brand",
            ),
            html.Div(
                [
                    html.Span("Graph Intelligence for Urban Mobility",
                              className="cf-phase-label"),
                    html.Button(
                        [
                            cf_icon("lucide:sun", size=13,
                                    className="cf-theme-icon cf-theme-sun",
                                    color="currentColor"),
                            html.Span("Light", className="cf-theme-label-light"),
                            html.Span("Dark", className="cf-theme-label-dark"),
                            cf_icon("lucide:moon", size=13,
                                    className="cf-theme-icon cf-theme-moon",
                                    color="currentColor"),
                        ],
                        id="cf-theme-toggle",
                        className="cf-theme-toggle",
                        n_clicks=0,
                        title="Toggle Light / Dark appearance",
                    ),
                    _programmer_toggle(),
                ],
                className="cf-topbar-right",
            ),
        ],
        className="cf-topbar",
    )


# ---------------------------------------------------------------------------
# Control strip
# ---------------------------------------------------------------------------

def _time_marks() -> dict[int, str]:
    return {i: t for i, t in enumerate(TIMES_OF_DAY)}


def _control_strip() -> html.Div:
    return html.Div(
        [
            html.Span("Time of day", className="cf-controls-label"),
            html.Div(
                dcc.Slider(
                    id="time-of-day-slider",
                    min=0,
                    max=len(TIMES_OF_DAY) - 1,
                    step=1,
                    value=TIMES_OF_DAY.index(DEFAULT_TIME_OF_DAY),
                    marks=_time_marks(),
                    included=False,
                ),
                className="cf-slider-wrap",
            ),
            html.Button(
                [cf_icon("lucide:play", size=14,
                         style={"marginRight": "6px"}, color="currentColor"),
                 html.Span("Play 24h")],
                id="play-24h", className="cf-btn", n_clicks=0,
            ),
            html.Span(
                "Time locked - Morning",
                id="day-cycle-readout",
                className="cf-daycycle-readout",
            ),
            html.Button(
                [cf_icon("lucide:zap", size=14,
                         style={"marginRight": "6px"}, color="currentColor"),
                 html.Span("What If?")],
                id="what-if", className="cf-btn cf-btn-accent", n_clicks=0,
            ),
        ],
        className="cf-controls",
    )


# ---------------------------------------------------------------------------
# Scenario panel
# ---------------------------------------------------------------------------

_SCENARIO_BUTTONS = [
    ("road_closure", "Road closure", "Close a strategic corridor"),
    ("accident", "Accident", "Slow a key road segment"),
    ("heavy_congestion", "Heavy congestion", "Increase pressure downtown"),
    ("weather", "Weather impact", "Apply wet-road delays"),
    ("airport_spike", "Airport spike", "Push demand toward Cairo airport"),
    ("hospital_surge", "Hospital surge", "Prioritize medical access"),
    ("stadium_event", "Stadium event", "Create event traffic near Nasr City"),
    ("transit_disruption", "Transit disruption", "Stress multimodal corridors"),
    ("maintenance_closure", "Maintenance", "Close a repair corridor"),
]


def _what_if_panel() -> html.Div:
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span("Scenario engine", className="cf-panel-eyebrow"),
                            html.H3("What If?", className="cf-panel-title"),
                        ]
                    ),
                    cf_icon("lucide:activity", size=18, color="currentColor"),
                ],
                className="cf-whatif-head",
            ),
            html.Div(
                [
                    html.Button(
                        "Reset Scenario",
                        id="reset-what-if",
                        className="cf-scenario-reset",
                        n_clicks=0,
                    ),
                ] + [
                    html.Button(
                        [
                            html.Span(label, className="cf-scenario-name"),
                            html.Span(desc, className="cf-scenario-desc"),
                        ],
                        id={"type": "what-if-scenario", "scenario": sid},
                        className="cf-scenario-btn",
                        n_clicks=0,
                    )
                    for sid, label, desc in _SCENARIO_BUTTONS
                ],
                className="cf-scenario-grid",
            ),
            html.Div(
                "Pick a scenario to recalculate the current route with temporary, non-destructive road conditions.",
                id="what-if-result",
                className="cf-whatif-result",
            ),
        ],
        id="what-if-panel",
        className="cf-whatif-panel",
    )


# ---------------------------------------------------------------------------
# Root layout
# ---------------------------------------------------------------------------

def _hero_overlay() -> html.Div:
    """The CTOS launch hero — a self-contained iframe rendering the
    Three.js Hyperspeed scene + branding. The Dash app sits behind it;
    a clientside listener dismisses the iframe when the user clicks
    Start Simulation or Explore Algorithms inside the frame."""
    return html.Div(
        html.Iframe(
            id="cf-hero-iframe",
            src="/assets/hero.html",
            className="cf-hero-iframe",
        ),
        id="cf-hero-shell",
        className="cf-hero-shell",
    )


def render_layout() -> html.Div:
    return html.Div(
        [
            # Cross-cutting state stores
            dcc.Store(id="programmer-mode", data=False),
            dcc.Store(id="active-mode", data=DEFAULT_MODE),
            dcc.Store(id="time-of-day", data=DEFAULT_TIME_OF_DAY),
            dcc.Store(id="play-24h-running", data=False),
            dcc.Store(id="what-if-open", data=False),
            dcc.Store(id="what-if-scenario", data=None),
            dcc.Store(id="map-state", data=None),
            # Hero overlay state — flipped by a clientside listener
            # when the user clicks Start Simulation / Explore Algorithms.
            dcc.Store(id="hero-dismissed", data=False),
            dcc.Store(id="hero-action", data=None),
            # MST state.
            dcc.Store(id="mst-algo", data="kruskal"),
            dcc.Store(id="mst-result", data=None),
            dcc.Store(id="mst-trace", data=None),
            # Route mode state.
            dcc.Store(id="route-algo", data="time_aware"),
            dcc.Store(id="route-result", data=None),
            dcc.Store(id="route-trace", data=None),
            # Emergency mode state.
            dcc.Store(id="em-result", data=None),
            dcc.Store(id="em-trace", data=None),
            # Maintain mode state.
            dcc.Store(id="maintain-result", data=None),
            dcc.Store(id="maintain-trace", data=None),
            # Transit mode state.
            dcc.Store(id="transit-tab", data="bus"),
            dcc.Store(id="transit-result", data=None),
            dcc.Store(id="transit-trace", data=None),
            # Pulse-effect targets — written only by clientside callbacks.
            dcc.Store(id="mst-pulse-effect", data=None),
            dcc.Store(id="route-pulse-effect", data=None),
            dcc.Store(id="em-pulse-effect", data=None),
            dcc.Store(id="maintain-pulse-effect", data=None),
            dcc.Store(id="transit-pulse-effect", data=None),
            dcc.Store(id="map-pulse-effect", data=None),
            dcc.Interval(
                id="play-24h-timer",
                interval=1200,
                n_intervals=0,
                disabled=True,
            ),

            # BONUS — race + ML data stores. Server callbacks fill these,
            # clientside animator (`assets/race.js`) reads them and paints
            # the side-by-side race canvases.
            dcc.Store(id="race-data", data=None),
            dcc.Store(id="race-effect", data=None),
            dcc.Store(id="ml-result", data=None),

            _topbar(),
            html.Div(
                [
                    render_sidebar(DEFAULT_MODE),
                    html.Section(
                        [
                            _control_strip(),
                            html.Div(
                                [render_map(), _what_if_panel()],
                                className="cf-map-wrap",
                            ),
                        ],
                        className="cf-main",
                    ),
                ],
                className="cf-shell",
            ),

            # Hero overlay — mounted last so it stacks on top via z-index.
            _hero_overlay(),
            html.Div(
                [
                    html.Button(
                        cf_icon("lucide:x", size=18, color="currentColor"),
                        id="cf-logo-preview-close",
                        className="cf-logo-preview-close",
                        n_clicks=0,
                        title="Close",
                    ),
                    html.Div(
                        [
                            html.Img(
                                src="/assets/NEW_LOGO.png",
                                className="cf-logo-preview-image",
                                alt="CairoFlow logo preview",
                            ),
                            html.Div("CairoFlow", className="cf-logo-preview-title"),
                            html.Div(
                                "Greater Cairo Smart Mobility",
                                className="cf-logo-preview-subtitle",
                            ),
                        ],
                        className="cf-logo-preview-card",
                    ),
                ],
                id="cf-logo-preview",
                className="cf-logo-preview",
            ),
        ],
        id="cf-root",
    )
