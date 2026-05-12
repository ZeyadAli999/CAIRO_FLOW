"""Bonus — Side-by-side Dijkstra vs A* race UI.

Renders two synchronized canvas mini-graphs (one per algorithm) plus a
header card with metrics and a winner badge. The actual frame-by-frame
animation is driven clientside by `assets/race.js` reading the
`race-data` Store the server callback writes into.
"""
from __future__ import annotations

from typing import Any

from dash import dcc, html

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


def render_race_card(bundle: dict[str, Any]) -> html.Div:
    """The metrics + winner card. The actual race animation lives in
    the side-by-side SVG canvases below this component."""
    d = bundle["dijkstra"]
    a = bundle["astar"]
    winner = bundle["winner"]
    speedup = bundle["speedup_pct_nodes"]

    winner_chip = html.Span(
        [cf_icon("lucide:trophy", size=14, color="var(--accent)",
                 style={"marginRight": "6px"}),
         winner],
        className="cf-stat-value cf-stat-accent",
    )

    return html.Div([
        info_card(
            title=html.Span([
                cf_icon("lucide:swords", size=14, color="var(--accent)",
                        style={"marginRight": "6px"}),
                "Dijkstra vs A* — race result",
            ]),
            body=html.Div([
                _stat("Source → Target",
                      f"{bundle['source']}  →  {bundle['target']}"),
                _stat("Weight mode", bundle["weight_mode"]),
                _stat("Both algorithms agreed on optimal cost",
                      "✓ yes" if bundle["agree_on_cost"] else "✕ no"),
                _stat("Winner (fewer nodes explored)",
                      winner_chip, accent=True),
                _stat("Speed-up by node count",
                      f"{speedup:+.1f}%" + (" (A* faster)" if speedup > 0 else
                                            (" (tie)" if speedup == 0 else " (Dijkstra faster)"))),
            ]),
        ),
        # Per-algorithm columns
        html.Div(
            [
                _algo_column("Dijkstra", d, accent="var(--accent)",
                             canvas_id="race-canvas-dijkstra"),
                _algo_column("A*",       a, accent="var(--accent-warm)",
                             canvas_id="race-canvas-astar"),
            ],
            className="cf-race-grid",
        ),
        # The clientside animator binds here.
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
    ])


def _algo_column(label: str, payload: dict, accent: str, canvas_id: str) -> html.Div:
    nodes = payload["n_frames"]
    edges = payload["edges_relaxed"]
    runtime = payload["runtime_ms"]
    cost = payload["cost"]
    cost_str = f"{cost:.2f}" if cost is not None else "—"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(label, className="cf-race-col-title"),
                    html.Span(f"{nodes} nodes · {edges} edges · {runtime:.2f} ms",
                              className="cf-race-col-meta"),
                ],
                className="cf-race-col-header",
                style={"borderColor": accent},
            ),
            html.Div(
                # The canvas the clientside animator paints into.
                # It's a regular <canvas> wrapped so we can size it.
                html.Canvas(id=canvas_id, className="cf-race-canvas",
                            width="320", height="220"),
                className="cf-race-canvas-wrap",
            ),
            html.Div(
                [
                    _stat("Cost", cost_str),
                    _stat("Nodes explored", str(nodes)),
                    _stat("Edges relaxed", str(edges)),
                    _stat("Runtime", f"{runtime:.2f} ms"),
                ],
                className="cf-race-col-stats",
            ),
        ],
        className="cf-race-col",
    )


# ---------------------------------------------------------------------------
# ML forecast card — shown alongside Route results
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
            _stat("Model", metrics.get("model", "—")),
            _stat("Samples", str(metrics.get("n_samples", "—"))),
            _stat("Train / Test", f"{metrics.get('n_train','—')} / {metrics.get('n_test','—')}"),
            _stat("R² (held-out)",
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
                            html.Span(f"{r['from']} → {r['to']} ({r['tod']})",
                                      className="cf-stat-label"),
                            html.Span(
                                f"pred {r['predicted_vc']*100:.0f}%  ·  actual {r['actual_vc']*100:.0f}%"
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
