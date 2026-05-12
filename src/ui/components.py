"""Reusable UI components.

These helpers are small and composable so later phases can drop them into
mode-specific panels without re-styling. Phase 3 polish: `cf_icon` for
Lucide icons via dash-iconify (with a graceful fallback if the package
isn't installed yet) and `empty_state` for the "no result yet"
placeholders that fill result slots before any compute click.
"""
from __future__ import annotations

from typing import Any

from dash import html

from src.algorithms.trace import AlgorithmTrace


# ---------------------------------------------------------------------------
# Iconify wrapper — defensive against dash-iconify not yet being installed.
# ---------------------------------------------------------------------------

try:  # pragma: no cover — runtime dependency check
    from dash_iconify import DashIconify
    _HAS_ICONIFY = True
except Exception:  # ModuleNotFoundError, or any incompatible install
    DashIconify = None  # type: ignore[assignment]
    _HAS_ICONIFY = False


def cf_icon(name: str, size: int = 16, color: str | None = None,
            className: str | None = None, style: dict | None = None) -> Any:
    """Render a Lucide (or any Iconify) icon.

    If dash-iconify isn't installed, fall back to a simple span dot so
    the layout still renders without crashing — the icon just won't be
    visible. CI / linters won't break on the missing package.
    """
    base_style = {"verticalAlign": "middle", "flexShrink": 0}
    if color:
        base_style["color"] = color
    if style:
        base_style.update(style)
    if _HAS_ICONIFY:
        return DashIconify(
            icon=name, width=size, height=size,
            style=base_style,
            className=className or "",
        )
    return html.Span(
        "",
        className=(className or "") + " cf-icon-fallback",
        style={**base_style, "display": "inline-block",
               "width": f"{size}px", "height": f"{size}px",
               "borderRadius": "50%",
               "background": color or "var(--text-muted)",
               "opacity": 0.4},
    )


# ---------------------------------------------------------------------------
# Mode pills — Lucide-driven (Phase 3 polish)
# ---------------------------------------------------------------------------

def mode_pill(label: str, icon: str, mode_id: str, active: bool = False) -> html.Button:
    """A mode selector pill.

    `icon` may be either a Lucide-style identifier (`lucide:network`) or
    a Font Awesome class string (`fa-solid fa-route`). The pill picks
    the correct renderer automatically — Phase 1 used Font Awesome,
    Phase 3 standardizes on Lucide.
    """
    cls = "cf-pill active" if active else "cf-pill"
    if ":" in icon:
        # Iconify-style id, e.g. "lucide:network"
        icon_node = cf_icon(
            icon, size=18,
            className="cf-pill-icon",
            color="var(--accent)" if active else "var(--text-secondary)",
        )
    else:
        icon_node = html.Span(className=f"cf-pill-icon {icon}")
    return html.Button(
        [icon_node, html.Span(label)],
        id={"type": "mode-pill", "mode": mode_id},
        n_clicks=0,
        className=cls,
    )


# ---------------------------------------------------------------------------
# Cards / chips
# ---------------------------------------------------------------------------

def info_card(title: Any, body: Any, footer: Any | None = None) -> html.Div:
    """A titled card. `body` and `footer` may be strings or Dash components."""
    children: list[Any] = [
        html.Div(title, className="cf-card-title"),
        html.Div(body, className="cf-card-body"),
    ]
    if footer is not None:
        children.append(html.Div(footer, className="cf-card-footer"))
    return html.Div(children, className="cf-card")


def algorithm_badge(trace: AlgorithmTrace) -> html.Span:
    """A small chip identifying which algorithm produced the active result."""
    return html.Span(
        [
            cf_icon("lucide:cpu", size=12,
                    style={"marginRight": "4px"}),
            trace.name,
        ],
        className="cf-algo-chip",
    )


# ---------------------------------------------------------------------------
# Programmer panel
# ---------------------------------------------------------------------------

def programmer_panel(trace: AlgorithmTrace) -> html.Div:
    """The expandable technical card. Caller decides whether to render it
    by checking the `programmer-mode` store."""
    total_nodes = trace.parameters.get("total_nodes_in_graph") if trace.parameters else None
    explored = len(trace.nodes_explored)
    explored_str = f"{explored} / {total_nodes}" if total_nodes else str(explored)
    rows = [
        ("Algorithm", trace.name),
        ("Time complexity", trace.complexity_time),
        ("Space complexity", trace.complexity_space),
        ("Nodes explored", explored_str),
        ("Edges relaxed", str(trace.edges_relaxed)),
        ("Runtime", f"{trace.runtime_ms:.2f} ms"),
    ]
    body: list[Any] = [
        html.Div(
            [html.Span(label), html.Code(value)],
            className="cf-prog-row",
        )
        for label, value in rows
    ]
    if trace.parameters:
        # Render selected fields prominently before the catch-all dump.
        for key in ("data_structure", "heuristic", "weight_mode",
                    "time_of_day", "alpha", "beta", "free_flow_kmh"):
            if key in trace.parameters:
                body.append(
                    html.Div(
                        [html.Span(key.replace("_", " ").title()),
                         html.Code(str(trace.parameters[key]))],
                        className="cf-prog-row",
                    )
                )
    if trace.formula:
        body.append(
            html.Div(
                [html.Span("Formula"), html.Code(trace.formula)],
                className="cf-prog-row",
            )
        )
    if trace.explanation:
        body.append(html.Div(trace.explanation, style={"marginTop": "10px"}))
    if trace.code_snippet:
        body.append(html.Pre(trace.code_snippet, className="cf-prog-snippet"))
    return html.Div(body, className="cf-prog-panel")


# ---------------------------------------------------------------------------
# Empty states (Phase 3 polish)
# ---------------------------------------------------------------------------

def empty_state(message: str = "Run a query to see results",
                icon: str = "lucide:sparkles") -> html.Div:
    """An elegant placeholder shown in result slots before the user
    runs anything. Used by every mode."""
    return html.Div(
        [
            cf_icon(icon, size=32, color="var(--text-muted)",
                    style={"opacity": 0.4, "marginBottom": "8px"}),
            html.Div(message, className="cf-empty-text"),
        ],
        className="cf-empty-state",
    )


def empty_panel(message: str) -> html.Div:
    """Legacy alias — kept for back-compat with earlier phases."""
    return info_card(
        title="Empty",
        body=html.Div(message, className="cf-placeholder"),
    )


# ---------------------------------------------------------------------------
# Premium button helper — Phase 3 polish
# ---------------------------------------------------------------------------

def cf_button(label: str, btn_id: str, *,
              variant: str = "primary", icon: str | None = None,
              extra_class: str = "") -> html.Button:
    """Premium button factory used by every action button.

    `variant` ∈ {"primary", "danger", "accent"} maps to the matching
    CSS class. Loading + success-pulse classes are toggled at runtime
    by clientside callbacks.
    """
    base = "cf-btn cf-btn-large"
    if variant == "primary":
        base += " cf-btn-primary"
    elif variant == "danger":
        base += " cf-btn-danger"
    elif variant == "accent":
        base += " cf-btn-accent"
    cls = f"{base} {extra_class}".strip()
    children: list[Any] = []
    if icon:
        children.append(cf_icon(icon, size=16,
                                style={"marginRight": "8px"},
                                color="currentColor"))
    children.append(html.Span(label, className="cf-btn-label"))
    return html.Button(children, id=btn_id, n_clicks=0, className=cls)
