"""Signals mode UI and Greedy integration tests."""
from __future__ import annotations

from dash import html


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


def _text(component) -> str:
    parts: list[str] = []
    for node in _walk(component):
        if isinstance(node, str):
            parts.append(node)
    return " ".join(parts)


def test_signals_mode_exists_in_modes_and_sidebar():
    from src.config import MODES
    from src.ui.sidebar import placeholder_for, render_pills

    assert any(mode["id"] == "signals" and mode["label"] == "Signals" for mode in MODES)
    pills_text = _text(render_pills("signals"))
    assert "Signals" in pills_text
    assert placeholder_for("signals")


def test_signals_mode_renders_required_controls_and_explanation():
    from src.ui.signals_mode import render_signals_panel

    panel = render_signals_panel()
    text = " ".join(_text(item) for item in panel)
    components = [node for item in panel for node in _walk(item)]

    assert "Traffic Signal Command Center" in text
    assert text.count("Traffic Signal Command Center") == 1
    assert "Algorithm: Greedy Signal Timing" in text
    assert "Run Greedy Signal Audit" in text
    assert "fast local decision based on current demand" in text
    assert any(_component_id(node) == "signals-tod" for node in components)
    assert any(_component_id(node) == "signals-intersection" for node in components)
    assert any(_component_id(node) == "signals-run" for node in components)


def test_signals_callback_returns_real_greedy_results():
    import app

    result_card, preemption_card, data, trace = app._run_signals_mode(
        1,
        "Night",
        "3",
    )
    text = _text(result_card) + " " + _text(preemption_card)

    assert isinstance(result_card, html.Div)
    assert "Greedy Decision Panel" in text
    assert text.count("Greedy Decision Panel") == 1
    assert "Greedy Local Decision Rule" in text
    assert "Connected approach decision" not in text
    assert "Algorithm: Greedy Signal Timing" in text
    assert "Decision rule: sort connected approaches by demand" in text
    assert "Recommended Green-Time Allocation for Connected Approaches" in text
    assert "Each row represents a connected approach receiving green time from the selected intersection." in text
    assert "Audited Intersection Summary" in text
    assert "Emergency Preemption" in text
    assert text.count("Emergency Preemption") == 1
    assert "Greedy Priority Scheduling" in text
    assert "Route sequence:" in text
    assert "Approach Watch" in text
    assert "Connected approach warning:" in text
    assert "Audit time: Night" in text
    assert "\u2192" in text
    assert "->" not in text
    assert data["time_of_day"] == "Night"
    assert data["time_key"] == "night"
    assert data["selected_intersection"] == "3"
    assert data["intersections_audited"] > 0
    assert data["allocations"]
    assert data["overlay"]["mode"] == "signals"
    assert data["overlay"]["selected_intersection"] == "3"
    assert data["overlay"]["points"]
    assert data["overlay"]["approaches"]
    assert {point["status"] for point in data["overlay"]["points"]} & {"selected", "optimal", "watch", "suboptimal"}
    assert all("green_seconds" in point and "demand" in point for point in data["overlay"]["points"])
    assert all("coordinates" in approach for approach in data["overlay"]["approaches"])
    assert trace["name"] == "Greedy Signal Allocation"


def test_signals_time_of_day_drives_map_state():
    import app

    _, _, data, _ = app._run_signals_mode(1, "Night", "3")
    payload = app._map_state_payload(
        "signals",
        "Morning",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        data,
    )

    assert payload["active_mode"] == "signals"
    assert payload["time_of_day"] == "Night"
    assert payload["time_key"] == "night"
    assert payload["signals"]["time_of_day"] == "Night"

    synced_tod, synced_idx = app._sync_signals_time_of_day("Evening", "signals")
    assert synced_tod == "Evening"
    assert synced_idx >= 0


def test_signals_preemption_groups_route_steps_by_vehicle():
    import app

    _, preemption_card, _, _ = app._run_signals_mode(1, "Morning", "3")
    text = _text(preemption_card)

    assert text.count("AMB-01") == 1
    assert "AMB-01 - Priority 1" in text
    assert "FIRE-02 - Priority 2" in text
    assert "Route sequence:" in text
    assert "\u2192" in text
    assert "->" not in text


def test_maplibre_contains_scoped_signal_overlay_layers():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    js = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    assert "cf-signals-points" in js
    assert "cf-signals-approaches" in js
    assert "cf-signals-approaches-casing" in js
    assert "cf-signals-points-fill" in js
    assert "cf-signals-selected-casing" in js
    assert "cf-signals-selected-ring" in js
    assert "Selected: " in js
    assert "Signal points: audited intersections" in js
    assert "Connected approaches highlighted - bright dashed lines" in js
    assert 'data.active_mode === "signals"' in js
    assert 'mode === "signals"' in js
    assert "inSignals && hasSignals" in js
    assert 'setTimeMode(data.time_of_day || "Morning", true)' in js
    assert "? \"signal audit\"" in js

    signal_layers = js[js.index('id: "cf-signals-approaches-casing"'):js.index('id: "cf-signals-points-circle"')]
    assert "#d7a448" not in signal_layers
    assert "#c99633" not in signal_layers
    assert "#e0a13f" not in signal_layers
    assert "#020711" in signal_layers
    assert "#54faff" in signal_layers
    assert "#ff68d8" in signal_layers
    assert '"line-opacity": 0.98' in signal_layers
    assert '"line-width": ["interpolate", ["linear"], ["zoom"], 8, 3.2, 12, 4.8]' in signal_layers

    point_layers = js[js.index('id: "cf-signals-points-circle"'):js.index('id: "cf-signals-labels"')]
    assert "#020711" in point_layers
    assert "#39ff88" in point_layers
    assert "#ffd43b" in point_layers
    assert "#ff3b6b" in point_layers
    assert "#54faff" in point_layers
    assert "#fff0a3" in point_layers
    assert '"circle-opacity": 1.0' in point_layers
    assert '"circle-stroke-width": 2.2' in point_layers
    assert '"circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 17, 12, 31]' in point_layers


def test_existing_modes_still_render_and_route_has_no_race_button():
    from src.ui.route_mode import render_route_panel
    from src.ui.sidebar import placeholder_for

    for mode in ("network", "route", "emergency", "maintain", "transit", "race_lab", "signals"):
        assert placeholder_for(mode)

    components = [node for item in render_route_panel() for node in _walk(item)]
    assert not any(_component_id(node) == "route-race" for node in components)
