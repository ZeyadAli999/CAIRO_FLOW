"""ML forecast UI integration tests."""
from __future__ import annotations

from pathlib import Path

from dash import dcc, html


def _children(component):
    children = getattr(component, "children", None)
    if children is None:
        return []
    if isinstance(children, (list, tuple)):
        return list(children)
    return [children]


def _walk(component):
    yield component
    for child in _children(component):
        yield from _walk(child)


def _component_id(component):
    return getattr(component, "id", None)


def test_route_panel_contains_ml_button_and_visible_slot():
    from src.ui.route_mode import render_route_panel

    panel = render_route_panel()
    all_components = [node for component in panel for node in _walk(component)]

    assert any(_component_id(node) == "route-ml" for node in all_components)
    assert any(_component_id(node) == "route-ml-slot" for node in all_components)

    bonus_index = next(
        i for i, component in enumerate(panel)
        if getattr(component, "className", None) == "cf-route-bonus-row"
    )
    loading = panel[bonus_index + 1]
    assert isinstance(loading, dcc.Loading)
    assert _component_id(loading) == "route-ml-loading"
    assert any(_component_id(node) == "route-ml-slot" for node in _walk(loading))


def test_ml_forecast_callback_is_registered():
    import app

    callback = next(
        value for value in app.app.callback_map.values()
        if any(
            item["id"] == "route-ml" and item["property"] == "n_clicks"
            for item in value.get("inputs", [])
        )
    )

    outputs = callback.get("output")
    output_ids = {out.component_id for out in outputs}
    assert {"route-ml-slot", "ml-result"} <= output_ids


def test_ml_forecast_callback_returns_card_and_result_dict():
    import app

    card, result = app._ml_forecast(1, "1", "F1", "Morning")

    assert isinstance(card, html.Div)
    assert isinstance(result, dict)
    assert result["source"] == "1"
    assert result["target"] == "F1"
    assert result["tod"] == "morning_peak"
    assert "metrics" in result
    assert "sample" in result
    assert isinstance(result["sample"], list)


def test_clientside_feedback_includes_ml_forecast_button():
    root = Path(__file__).resolve().parents[1]
    clientside = (root / "assets" / "clientside.js").read_text(encoding="utf-8")

    assert "'route-ml'" in clientside or '"route-ml"' in clientside
