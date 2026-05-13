"""Race Lab UI presentation tests."""
from __future__ import annotations

from pathlib import Path


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


def _bundle(*, d_frames=8, a_frames=5, agree=True, paths=True):
    d_path = ["1", "3", "F1"] if paths else None
    a_path = ["1", "3", "F1"] if paths else None
    d_explored = ["1", "2", "3", "4", "5", "6", "7", "F1"][:d_frames]
    a_explored = ["1", "3", "5", "7", "F1"][:a_frames]
    return {
        "source": "1",
        "target": "F1",
        "weight_mode": "distance_km",
        "dijkstra": {
            "name": "Dijkstra",
            "path": d_path,
            "cost": 22.1 if paths else None,
            "edges_relaxed": 12,
            "runtime_ms": 0.45,
            "n_frames": d_frames,
            "explored_nodes": d_explored,
            "frames": [{"step": idx + 1, "visited": d_explored[:idx + 1]} for idx in range(len(d_explored))],
        },
        "astar": {
            "name": "A*",
            "path": a_path,
            "cost": 22.1 if paths else None,
            "edges_relaxed": 8,
            "runtime_ms": 0.31,
            "n_frames": a_frames,
            "explored_nodes": a_explored,
            "frames": [{"step": idx + 1, "visited": a_explored[:idx + 1]} for idx in range(len(a_explored))],
        },
        "agree_on_cost": agree,
        "cost_view": "objective",
        "speedup_pct_nodes": round((d_frames - a_frames) / max(1, d_frames) * 100.0, 2),
        "winner": "A*" if a_frames < d_frames else ("tie" if a_frames == d_frames else "Dijkstra"),
        "objective_comparison": {
            "source": "1",
            "target": "F1",
            "time_of_day": "morning_peak",
            "distance_path": ["1", "3", "F1"] if paths else None,
            "traffic_path": ["1", "4", "F1"] if paths else None,
            "distance_cost_km": 22.1 if paths else None,
            "traffic_cost_min": 31.4 if paths else None,
            "distance_path_travel_min": 39.2 if paths else None,
            "traffic_path_distance_km": 24.7 if paths else None,
            "path_changed": paths,
            "reachable": paths,
        },
        "panels": {
            "dijkstra": {
                "title": "DIJKSTRA",
                "subtitle": "Shortest Distance Objective",
                "path": d_path,
                "cost_label": "22.10 km" if paths else "unreachable",
                "distance_km": 22.1 if paths else None,
                "traffic_time_min": 39.2 if paths else None,
                "distance_label": "22.10 km" if paths else "unreachable",
                "traffic_time_label": "39.20 min" if paths else "unreachable",
                "unit": "km",
            },
            "astar": {
                "title": "A* SEARCH",
                "subtitle": "Traffic-Aware Heuristic Route",
                "path": a_path,
                "cost_label": "31.40 min" if paths else "unreachable",
                "distance_km": 24.7 if paths else None,
                "traffic_time_min": 31.4 if paths else None,
                "distance_label": "24.70 km" if paths else "unreachable",
                "traffic_time_label": "31.40 min" if paths else "unreachable",
                "unit": "minutes",
            },
        },
        "map_overlay": {
            "dijkstra_path": d_path,
            "astar_path": a_path,
            "dijkstra_explored_nodes": d_explored,
            "astar_explored_nodes": a_explored,
            "explored_node_style": "shared-soft-cyan-glow",
            "dijkstra_color": "cyan",
            "astar_color": "gold",
        },
    }


def test_race_summary_reports_astar_node_savings():
    from src.ui.race_view import race_summary

    summary = race_summary(_bundle(d_frames=10, a_frames=6))

    assert summary["status"] == "Optimal cost preserved"
    assert summary["node_savings"] == 4
    assert summary["dijkstra_hops"] == 2
    assert summary["astar_hops"] == 2
    assert "A* explored 4 fewer nodes" in summary["efficiency"]
    assert "admissible heuristic" in summary["heuristic"]


def test_race_summary_handles_ties():
    from src.ui.race_view import race_summary

    summary = race_summary(_bundle(d_frames=5, a_frames=5))

    assert summary["node_savings"] == 0
    assert "same number of nodes" in summary["efficiency"]
    assert summary["winner"] == "tie"


def test_race_summary_handles_disconnected_route():
    from src.ui.race_view import race_summary

    summary = race_summary(_bundle(d_frames=7, a_frames=7, agree=False, paths=False))

    assert summary["status"] == "No route found"
    assert summary["dijkstra_hops"] is None
    assert summary["astar_hops"] is None
    assert "terminated cleanly" in summary["optimality"]


def test_render_race_card_contains_lab_copy_and_preserved_ids():
    from src.ui.race_view import render_race_card

    card = render_race_card(_bundle())
    text = _text(card)
    ids = {_component_id(node) for node in _walk(card)}

    assert "Dijkstra vs A* Race Lab" in text
    assert "Objective Cost View" in text
    assert "kilometers are compared only with kilometers" in text
    assert "minutes only with minutes" in text
    assert "DIJKSTRA" in text
    assert "A* SEARCH" in text
    assert "Shortest Distance Objective" in text
    assert "Traffic-Aware Heuristic Route" in text
    assert "Dijkstra Insight" in text
    assert "A* Insight" in text
    assert "Shortest Distance Winner" in text
    assert "Fastest Traffic-Time Winner" in text
    assert "Search Efficiency Winner" in text
    assert "Dijkstra: Uniform Cost Expansion" in text
    assert "A*: Heuristic-Guided Search" in text
    assert "Distance and Traffic-Time Metrics" in text
    assert "distance in kilometers" in text
    assert "traffic-time in minutes" in text
    assert "Shortest-Distance Route" in text
    assert "Traffic-Aware Fastest Route" in text
    assert "Distance km" in text
    assert "Traffic time" in text
    assert "Why these costs differ" in text
    assert "Suggested demo route for clearer cost/path difference" in text
    assert "Both algorithms selected the same route." in text
    assert "A* explored 3 fewer nodes" in text
    assert "Explored node" in text
    assert "admissible heuristic" in text
    assert "Explored nodes" in text
    assert "Runtime" in text
    assert "Replay race" in text
    assert "22.10 km" in text
    assert "24.70 km" in text
    assert "31.40 min" in text
    assert "Both routes are evaluated using the same metrics" in text
    assert "Cost mismatch" not in text
    assert {
        "race-replay",
        "race-canvas-dijkstra",
        "race-canvas-astar",
        "race-step-readout",
    } <= ids
    assert "race-back-route" not in ids
    assert "race-map-dijkstra" in ids
    assert "race-map-astar" in ids


def test_race_card_notes_same_path_without_dramatic_difference():
    from src.ui.race_view import render_race_card

    bundle = _bundle()
    bundle["objective_comparison"]["traffic_path"] = bundle["objective_comparison"]["distance_path"]
    bundle["objective_comparison"]["path_changed"] = False

    text = _text(render_race_card(bundle))

    assert (
        "Same path here, but evaluated with different objectives. Try a "
        "congested peak-hour route to demonstrate a path change."
    ) in text


def test_cost_objective_comparison_uses_separate_units():
    from src.graph.builder import build_graph
    from src.ui.race_view import cost_objective_comparison

    comparison = cost_objective_comparison(build_graph(), "1", "F1", "morning_peak")

    assert comparison["source"] == "1"
    assert comparison["target"] == "F1"
    assert comparison["distance_cost_km"] is None or comparison["distance_cost_km"] > 0
    assert comparison["traffic_cost_min"] is None or comparison["traffic_cost_min"] > 0
    assert "distance_path" in comparison
    assert "traffic_path" in comparison


def test_config_exposes_race_lab_mode_after_transit():
    from src.config import MODES

    assert [mode["label"] for mode in MODES] == [
        "Network",
        "Route",
        "Emergency",
        "Maintain",
        "Transit",
        "Race Lab",
        "Signals",
    ]


def test_layout_contains_dedicated_main_workspace_not_wide_overlay():
    from src.ui.layout import render_layout

    layout = render_layout()
    ids = [_component_id(node) for node in _walk(layout)]

    assert "main-workspace" in ids
    assert "race-lab-view" in ids
    assert "route-race-wide-slot" not in ids


def test_race_lab_sidebar_has_independent_controls():
    from src.ui.race_view import render_race_panel

    panel = render_race_panel()
    components = [node for component in panel for node in _walk(component)]
    ids = [_component_id(node) for node in components]
    text = " ".join(_text(component) for component in panel)

    assert "Choose source and target, then run the Dijkstra vs A* Race Lab." in text
    assert "race-from" in ids
    assert "race-to" in ids
    assert "race-cost-view" in ids
    assert "race-tod" in ids
    assert "race-scenario" in ids
    assert "race-run" in ids


def test_race_run_callback_uses_race_lab_controls_and_map_payload():
    import app

    callback = next(
        value for value in app.app.callback_map.values()
        if any(
            item["id"] == "race-run" and item["property"] == "n_clicks"
            for item in value.get("inputs", [])
        )
    )

    outputs = callback.get("output")
    output_ids = {out.component_id for out in outputs}
    assert {"race-run-status", "race-data"} <= output_ids

    status, bundle = app._run_race_lab(
        1, "1", "F1", "objective", "Morning"
    )
    assert "Race Lab active." in _text(status)
    assert bundle["source"] == "1"
    assert bundle["target"] == "F1"
    assert bundle["cost_view"] == "objective"
    assert bundle["scenario"]["label"] == "Normal Traffic"
    assert bundle["map_overlay"]["dijkstra_path"] == bundle["dijkstra"]["path"]
    assert bundle["map_overlay"]["astar_path"] == bundle["astar"]["path"]
    assert bundle["dijkstra"]["explored_nodes"]
    assert bundle["astar"]["explored_nodes"]
    assert bundle["map_overlay"]["dijkstra_explored_nodes"] == bundle["dijkstra"]["explored_nodes"]
    assert bundle["map_overlay"]["astar_explored_nodes"] == bundle["astar"]["explored_nodes"]
    assert bundle["map_overlay"]["explored_node_style"] == "shared-soft-cyan-glow"
    assert bundle["map_overlay"]["dijkstra_color"] == "cyan"
    assert bundle["map_overlay"]["astar_color"] == "gold"
    assert bundle["panels"]["dijkstra"]["unit"] == "km"
    assert bundle["panels"]["astar"]["unit"] == "minutes"
    assert bundle["panels"]["dijkstra"]["distance_label"].endswith(" km")
    assert bundle["panels"]["dijkstra"]["traffic_time_label"].endswith(" min")
    assert bundle["panels"]["astar"]["distance_label"].endswith(" km")
    assert bundle["panels"]["astar"]["traffic_time_label"].endswith(" min")


def test_main_workspace_renders_two_real_map_panels_when_race_lab_is_active():
    import app

    class_name, race_view = app._render_main_workspace("race_lab", _bundle())
    text = _text(race_view)

    assert class_name == "cf-main-workspace is-race-lab"
    assert "Dijkstra vs A* Race Lab" in text
    ids = [_component_id(node) for node in _walk(race_view)]
    assert "race-map-dijkstra" in ids
    assert "race-map-astar" in ids

    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".cf-race-map-grid" in css
    assert ".cf-main-workspace.is-race-lab .cf-map-wrap" in css
    assert "display: none;" in css
    assert ".cf-race-legacy-canvases" in css
    assert "overflow-y: auto" in css


def test_maplibre_bridge_supports_two_race_lab_map_panels():
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    assert "racePanelKind" in bridge
    assert "cairoflow-race-panel-state" in bridge
    assert "cairoflow-race-panel-replay" in bridge
    assert "updateRacePanelMap" in bridge
    assert "drawRacePanelRoute" in bridge
    assert "animateRacePanelRoute" in bridge
    assert "exploredIdsFromResult" in bridge
    assert "raceExploredFeatures" in bridge
    assert '"cf-race-explored"' in bridge
    assert '"cf-race-explored-glow"' in bridge
    assert '"cf-race-explored-dot"' in bridge
    assert "#9eefff" in bridge
    assert "fitPathBounds" in bridge
    assert "fitRacePanelBounds" in bridge
    assert "exploreDuration = 3500" in bridge
    assert "routeDuration = 3500" in bridge
    assert '"cf-race-dijkstra-line"' in bridge
    assert '"cf-race-astar-line"' in bridge
    assert '"Dijkstra - cyan"' in bridge
    assert '"A* - gold"' in bridge


def test_clientside_bridge_posts_payload_to_both_race_maps():
    root = Path(__file__).resolve().parents[1]
    clientside = (root / "assets" / "clientside.js").read_text(encoding="utf-8")
    race_js = (root / "assets" / "race.js").read_text(encoding="utf-8")

    assert "race-map-" in clientside
    assert "cairoflow-race-panel-state" in clientside
    assert "cairoflow-race-panel-replay" in race_js


def test_map_state_payload_uses_race_lab_time_context():
    import app

    payload = app._map_state_payload(
        "race_lab",
        "Morning",
        None,
        {**_bundle(), "time_context": "Evening"},
        None,
        None,
        None,
        None,
        None,
    )

    assert payload["active_mode"] == "race_lab"
    assert payload["time_of_day"] == "Evening"
    assert payload["race"]["dijkstra"]["path"]


def test_existing_modes_still_render():
    from src.ui.sidebar import placeholder_for

    for mode in ("network", "route", "emergency", "maintain", "transit", "race_lab", "signals"):
        assert placeholder_for(mode)


def test_major_mode_panels_surface_feature_and_algorithm_labels():
    from src.ui.emergency_mode import render_emergency_panel
    from src.ui.maintain_mode import render_maintain_panel
    from src.ui.network_mode import render_network_panel
    from src.ui.route_mode import render_route_panel
    from src.ui.transit_mode import render_transit_panel

    panels = (
        render_route_panel(),
        render_network_panel(),
        render_emergency_panel(),
        render_maintain_panel(),
        render_transit_panel(),
    )
    text = " ".join(_text(item) for panel in panels for item in panel)

    assert "Route Planning" in text
    assert "Dijkstra, A*, Time-Dependent Dijkstra + BPR" in text
    assert "Infrastructure Network Design" in text
    assert "Kruskal MST / Prim MST" in text
    assert "Emergency Dispatch" in text
    assert "A* Emergency Routing" in text
    assert "Road Maintenance Planning" in text
    assert "0/1 Knapsack Dynamic Programming" in text
    assert "Public Transit Optimization" in text
    assert "Dynamic Programming + Multimodal Shortest Path" in text


def test_route_mode_no_longer_contains_main_race_lab_button():
    from src.ui.route_mode import render_route_panel

    panel = render_route_panel()
    components = [node for component in panel for node in _walk(component)]

    assert not any(_component_id(node) == "route-race" for node in components)
    assert any(_component_id(node) == "route-ml" for node in components)
    assert any(_component_id(node) == "route-scenario" for node in components)


def test_route_mode_scenario_comparison_card_renders_for_incident():
    import app

    result = app._compute_route(
        1,
        "time_aware",
        "1",
        "F1",
        [],
        [],
        "Morning",
        "incident_shortest_route",
    )
    side_slot = result[5]
    text = _text(side_slot)

    assert "Traffic Scenario Comparison" in text
    assert "Time-Dependent Dijkstra + In-Memory Scenario Simulation" in text
    assert "Incident on Shortest Route" in text
    assert "Scenario is applied in memory only." in text
    assert "Shortest-distance route" in text
    assert "Traffic-aware route" in text
    assert "Shortest Distance Winner" in text
    assert "Fastest Traffic-Time Winner" in text
    assert "Distance is compared with distance; traffic-time is compared with traffic-time." in text


def test_race_lab_scrollable_cards_and_no_visible_canvas_styles():
    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")

    assert ".cf-race-map-details" in css
    assert ".cf-race-insight-region" in css
    assert "overscroll-behavior: contain" in css
    assert ".cf-race-legacy-canvases" in css
    assert "position: absolute" in css


def test_race_lab_workspace_has_bounded_scroll_and_map_heights():
    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")

    assert ".cf-main-workspace.is-race-lab .cf-race-view-shell" in css
    assert "height: 100%" in css
    assert "max-height: 100%" in css
    assert "overflow-y: auto" in css
    assert "padding: 14px 14px 64px" in css
    assert "scrollbar-gutter: stable" in css
    assert "clamp(300px, 34vh, 380px)" in css
    assert "clamp(280px, 42vh, 340px)" in css


def test_race_lab_difference_callout_and_winner_are_visually_strong():
    from src.ui.race_view import render_race_card

    bundle = _bundle(d_frames=10, a_frames=6)
    bundle["cost_view"] = "algorithm"
    text = _text(render_race_card(bundle))

    assert "Both algorithms selected the same route." in text
    assert "A* explored 4 fewer nodes" in text
    assert "A* is more search-efficient because it explored 4 fewer nodes" in text
    assert "Explored node" in text
    assert "Suggested demo route for clearer cost/path difference" in text

    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".cf-race-difference-callout" in css
    assert ".cf-race-bar-track" in css
    assert ".cf-race-insight.is-winner" in css


def test_race_js_still_references_required_ids():
    root = Path(__file__).resolve().parents[1]
    race_js = (root / "assets" / "race.js").read_text(encoding="utf-8")

    for required_id in (
        "race-canvas-dijkstra",
        "race-canvas-astar",
        "race-step-readout",
        "race-replay",
    ):
        assert required_id in race_js


def test_race_panel_uses_flat_camera_and_no_blur_on_explored_glow():
    """Perf guard: race panels must not pay for 3D pitch + circle-blur."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    # Race-panel iframes ditch pitch/globe/antialias for smooth pan/zoom.
    assert "flatPanel ? 0 : 43" in bridge
    assert "flatPanel ? 0 : 62" in bridge
    assert "fadeDuration: flatPanel ? 0 : 300" in bridge
    assert "if (!flatPanel) {" in bridge

    # The explored-node glow must not use circle-blur (very expensive
    # on the small panels). A solid translucent ring + a crisp dot
    # gives the same visual without the GPU cost.
    explored_glow_block = bridge.split('id: "cf-race-explored-glow"', 1)[1]
    explored_glow_block = explored_glow_block.split('addLayer({', 1)[0]
    assert "circle-blur" not in explored_glow_block

    # Path-glow blur must be reduced from the old 1.9 to a cheap value.
    assert '"line-blur": 0.6' in bridge


def test_race_panel_map_dedup_and_ready_handshake():
    """Perf guard: state ingestion is deduped, and ready-handshake is
    posted back to the parent so the parent can stop spamming retries."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")
    clientside = (root / "assets" / "clientside.js").read_text(encoding="utf-8")

    assert "lastRacePanelBaseKey" in bridge
    assert "lastRacePanelOverlayKey" in bridge
    assert 'type: "cairoflow-map-ready"' in bridge

    assert "__cairoFlowMapReady" in clientside
    assert "'cairoflow-map-ready'" in clientside
    # The old 4-shot retry storm (0/250/900/1800) must be gone.
    assert "setTimeout(post, 1800)" not in clientside
    assert "setTimeout(post, 900)" not in clientside


def test_race_panel_animation_throttles_setsource():
    """Perf guard: the explored/path animation must batch setSource calls
    by integer step changes, not call setData on every animation frame."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    assert "lastExploredCount" in bridge
    assert "lastRouteStep" in bridge
    assert "ROUTE_STEPS" in bridge


def test_race_js_skips_main_map_when_panels_mounted():
    """When the Race Lab is the active workspace, race.js must not also
    post a heavy `cairoflow-race-visual` to the hidden main map."""
    root = Path(__file__).resolve().parents[1]
    race_js = (root / "assets" / "race.js").read_text(encoding="utf-8")

    assert "race-map-dijkstra" in race_js
    assert "race-map-astar" in race_js
    # The hasPanels guard avoids posting to the hidden main iframe.
    assert "if (!hasPanels)" in race_js


def test_race_panel_renders_explored_edges_from_real_road_graph():
    """Race Lab must render edges between visited nodes so the search-
    tree shape is visible. The edges come from `data.roads` filtered by
    the visited set — REAL road-graph edges, never fakes."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    # Dedicated source + layer for explored edges.
    assert '"cf-race-explored-edges"' in bridge
    assert '"cf-race-explored-edges-line"' in bridge

    # Edge geometries come from real `data.roads`, filtered by the
    # visited set. There must be a helper that builds those features.
    assert "computeExploredEdges" in bridge
    assert "raceExploredEdgeFeatures" in bridge
    # Helper reads from `latestState.roads` (real graph data, no fakes).
    assert "latestState && latestState.roads" in bridge

    # Animation must reveal explored edges in lockstep with the
    # explored-node count and stay throttled.
    assert "exploredEdges" in bridge
    assert "stepEdges" in bridge


def test_race_panel_final_path_has_dark_casing_and_thicker_line():
    """Final path must dominate visually: a dark casing layer under
    each algorithm line, and the bright line must be wider than the
    explored-edge line."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    assert '"cf-race-dijkstra-casing"' in bridge
    assert '"cf-race-astar-casing"' in bridge

    # Casings come from the same source as the line (so they animate
    # together with the slice during route-draw).
    casing_dijkstra = bridge.split('"cf-race-dijkstra-casing"', 1)[1].split("});", 1)[0]
    assert 'source: "cf-race-dijkstra"' in casing_dijkstra
    casing_astar = bridge.split('"cf-race-astar-casing"', 1)[1].split("});", 1)[0]
    assert 'source: "cf-race-astar"' in casing_astar

    # Final-path casings are extra thick (12-16 px) to dominate.
    assert "8, 12.0" in casing_dijkstra
    assert "8, 12.0" in casing_astar

    # The bright Dijkstra/A* lines sit at 7-10 px, well above the
    # explored-edge line (~3.8 px at low zoom).
    dijkstra_line = bridge.split('"cf-race-dijkstra-line"', 1)[1].split("});", 1)[0]
    astar_line = bridge.split('"cf-race-astar-line"', 1)[1].split("});", 1)[0]
    explored_edge_line = bridge.split('"cf-race-explored-edges-line"', 1)[1].split("});", 1)[0]
    assert "8, 7.0" in dijkstra_line
    assert "8, 7.0" in astar_line
    assert "8, 3.8" in explored_edge_line


def test_race_panel_explored_edge_in_legend():
    """The map legend must call out the new 'Explored edge' style so
    the viewer understands the dashed cyan lines are search expansion,
    not the final path."""
    from src.ui.race_view import render_race_card

    bundle = _bundle()
    text = _text(render_race_card(bundle))
    assert "Explored edge" in text

    root = Path(__file__).resolve().parents[1]
    css = (root / "assets" / "style.css").read_text(encoding="utf-8")
    assert ".cf-race-legend-swatch.is-explored-edge" in css


def test_race_panel_explored_edges_have_dark_casing():
    """Explored-edge lines must have a dark casing layer underneath so
    the bright cyan line stands out on any basemap."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    assert '"cf-race-explored-edges-casing"' in bridge
    casing = bridge.split('"cf-race-explored-edges-casing"', 1)[1].split("});", 1)[0]
    assert 'source: "cf-race-explored-edges"' in casing
    # Casing width 6-8 px at zoom 8-12.
    assert "8, 6.0" in casing
    assert "12, 8.0" in casing
    # Casing included in visibility toggle.
    assert '"cf-race-explored-edges-casing"' in bridge.split("setLayerVisibility", 2)[-1]


def test_race_animation_duration_at_least_6_seconds():
    """The race animation must take 6-8 seconds total so the professor
    can see the drawing process in a screen recording."""
    root = Path(__file__).resolve().parents[1]
    bridge = (root / "assets" / "maplibre_view.js").read_text(encoding="utf-8")

    import re
    explore_match = re.search(r"const\s+exploreDuration\s*=\s*(\d+)", bridge)
    route_match = re.search(r"const\s+routeDuration\s*=\s*(\d+)", bridge)
    assert explore_match and route_match
    total = int(explore_match.group(1)) + int(route_match.group(1))
    assert total >= 6000, f"Total animation {total} ms < 6000 ms"
    assert total <= 9000, f"Total animation {total} ms > 9000 ms"
