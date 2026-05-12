"""Safe data optimization layer tests."""
from __future__ import annotations

import importlib
import math
import sys

import networkx as nx
import pytest


@pytest.fixture(scope="module")
def opt_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-data-opt")
    from src import config
    importlib.reload(config)
    config.DB_PATH = tmp / "test.db"
    config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"

    from src.db import models
    importlib.reload(models)
    from src.db import seed
    importlib.reload(seed)
    seed.ensure_seeded()
    from src.db import queries
    importlib.reload(queries)
    from src.graph import builder
    importlib.reload(builder)
    from src.algorithms import shortest_path as sp
    importlib.reload(sp)
    from src.algorithms import mst as mst_mod
    importlib.reload(mst_mod)
    from src.data import (
        data_enrichment,
        data_validator,
        emergency_explanation,
        graph_views,
        optimized_loader,
    )
    importlib.reload(data_enrichment)
    importlib.reload(data_validator)
    importlib.reload(emergency_explanation)
    importlib.reload(graph_views)
    importlib.reload(optimized_loader)

    source = optimized_loader.load_source_data()
    optimized = optimized_loader.load_optimized_transport_data(source)
    return {
        "source": source,
        "optimized": optimized,
        "builder": builder,
        "sp": sp,
        "mst": mst_mod,
        "graph_views": graph_views,
        "emergency_explanation": emergency_explanation,
    }


def _ids(rows):
    return {str(getattr(r, "id", r["id"] if isinstance(r, dict) else None)) for r in rows}


def test_original_counts_and_ids_remain_unchanged(opt_env):
    source = opt_env["source"]
    optimized = opt_env["optimized"]

    assert optimized.original_node_count == 25
    assert optimized.original_road_count == 28
    assert len(source["existing_roads"]) == 28
    assert _ids(source["neighborhoods"]) == {str(i) for i in range(1, 16)}
    assert {"F9", "F10"}.issubset(_ids(source["facilities"]))


def test_validation_detects_known_medical_isolation_and_duplicate(opt_env):
    report = opt_env["optimized"].validation_report

    assert report.ok
    assert {"F9", "F10"}.issubset(set(report.isolated_medical_facilities))
    assert {"F3", "F4", "F5", "F6", "F9", "F10"}.issubset(set(report.isolated_nodes))
    assert any(item["pair"] == ("15", "7") for item in report.duplicate_bidirectional_roads)


def test_f9_f10_are_isolated_before_connector_generation(opt_env):
    base = opt_env["builder"].build_graph()

    assert base.degree("F9") == 0
    assert base.degree("F10") == 0
    assert base.has_node("F9")
    assert base.has_node("F10")


def test_inferred_connectors_generated_and_marked(opt_env):
    connectors = opt_env["optimized"].inferred_medical_connectors
    by_facility = {c["from_id"]: c for c in connectors}

    assert {"F9", "F10"}.issubset(by_facility)
    for connector in by_facility.values():
        assert connector["is_inferred"] is True
        assert connector["is_original"] is False
        assert connector["connector_type"] == "medical_emergency_connector"
        assert connector["connected_to_nearest_node"] is True
        assert connector["confidence"] > 0
        assert connector["distance_km"] > 0
        assert connector["base_travel_time_min"] > 0


def test_connectors_are_excluded_from_base_and_included_in_emergency(opt_env):
    views = opt_env["graph_views"]
    source = opt_env["source"]
    base = views.build_base_graph(source)
    emergency = views.build_emergency_graph(source)

    assert views.inferred_connector_edges(base) == []
    inferred = views.inferred_connector_edges(emergency)
    assert len(inferred) == 2
    assert emergency.degree("F9") == 1
    assert emergency.degree("F10") == 1


def test_astar_emergency_reaches_f9_and_f10_with_optimized_view(opt_env):
    sp = opt_env["sp"]
    emergency = opt_env["graph_views"].build_emergency_graph(opt_env["source"])

    for target in ("F9", "F10"):
        path, eta_h, trace = sp.astar_emergency(emergency, "1", target, "morning_peak")
        assert path is not None
        assert path[0] == "1"
        assert path[-1] == target
        assert eta_h > 0
        assert trace.parameters["weight_mode"] == "BPR travel time (hours)"


def test_base_graph_preserves_original_no_path_behavior(opt_env):
    sp = opt_env["sp"]
    base = opt_env["graph_views"].build_base_graph(opt_env["source"])

    path, cost, trace = sp.dijkstra(base, "1", "F9", weight="distance_km")
    assert path is None
    assert cost == math.inf
    assert trace.parameters["result"] == "no_path"


def test_dijkstra_and_astar_still_work_on_normal_route(opt_env):
    sp = opt_env["sp"]
    base = opt_env["graph_views"].build_base_graph(opt_env["source"])

    d_path, d_cost, _ = sp.dijkstra(base, "1", "F1", weight="distance_km")
    a_path, a_cost, _ = sp.astar(base, "1", "F1", weight="distance_km")
    assert d_path is not None
    assert a_path is not None
    assert a_cost == pytest.approx(d_cost)


def test_mst_largest_component_remains_spanning_tree(opt_env):
    G = opt_env["graph_views"].build_mst_graph(opt_env["source"])
    mst, _ = opt_env["mst"].kruskal_mst(G, weight="cost_million_egp")
    largest_cc = max(nx.connected_components(G), key=len)
    sub = mst.subgraph(largest_cc)

    assert nx.is_connected(sub)
    assert sub.number_of_edges() == sub.number_of_nodes() - 1


def test_traffic_weights_and_maintenance_scores_are_computed(opt_env):
    views = opt_env["graph_views"]
    source = opt_env["source"]

    for period in ("morning", "afternoon", "evening", "night"):
        graph = views.build_traffic_graph(period, source)
        assert all(data["time_weight_min"] > 0 for _, _, data in graph.edges(data=True))

    roads = opt_env["optimized"].enriched_existing_roads
    assert all("maintenance_priority_score" in road for road in roads)
    assert any(road["maintenance_priority_score"] > 0 for road in roads)


def test_ui_module_imports_still_work():
    for module in (
        "src.ui.route_mode",
        "src.ui.emergency_mode",
        "src.ui.network_mode",
        "src.ui.maintain_mode",
        "src.ui.transit_mode",
    ):
        assert importlib.import_module(module)


def test_app_emergency_dispatch_uses_optimized_medical_graph(opt_env):
    sys.modules.pop("app", None)
    app_mod = importlib.import_module("app")

    result = app_mod._dispatch_emergency(1, "11", "Medical", "current", "Morning")
    summary = result[7]

    assert summary["selected"] in {"F9", "F10"}
    assert summary["path"] is not None
    assert summary["path"][0] == "11"
    assert summary["path"][-1] == summary["selected"]
    assert summary["eta_minutes"] > 0
    assert summary["choice_explanation"]["selected"] == summary["selected"]
    assert summary["choice_explanation"]["reason"]


def test_emergency_choice_explanation_for_f9_selection(opt_env):
    sp = opt_env["sp"]
    helper = opt_env["emergency_explanation"].explain_emergency_facility_choice
    emergency = opt_env["graph_views"].build_emergency_graph(opt_env["source"])
    facilities = opt_env["source"]["facilities"]

    selected, path, eta_h, _ = sp.find_nearest_facility(
        emergency, "11", "Medical", facilities=facilities,
        time_of_day="morning_peak",
    )
    explanation = helper(emergency, "11", selected, "Medical", "morning_peak")

    assert selected == "F9"
    assert path[-1] == selected
    assert explanation["selected"] == selected
    assert explanation["alternative"] == "F10"
    assert explanation["selected_eta"] == pytest.approx(round(eta_h * 60.0, 2))
    assert explanation["alternative_eta"] > explanation["selected_eta"]
    assert explanation["eta_saved"] > 0
    assert explanation["extra_nodes_if_alternative"] is not None
    assert "F10 would take" in explanation["reason"]


def test_emergency_choice_explanation_for_f10_selection(opt_env):
    sp = opt_env["sp"]
    helper = opt_env["emergency_explanation"].explain_emergency_facility_choice
    emergency = opt_env["graph_views"].build_emergency_graph(opt_env["source"])
    facilities = opt_env["source"]["facilities"]

    selected, path, eta_h, _ = sp.find_nearest_facility(
        emergency, "1", "Medical", facilities=facilities,
        time_of_day="morning_peak",
    )
    explanation = helper(emergency, "1", selected, "Medical", "morning_peak")

    assert selected == "F10"
    assert path[-1] == selected
    assert explanation["selected"] == selected
    assert explanation["alternative"] == "F9"
    assert explanation["selected_eta"] == pytest.approx(round(eta_h * 60.0, 2))
    assert explanation["alternative_eta"] > explanation["selected_eta"]
    assert explanation["eta_saved"] > 0
    assert explanation["extra_nodes_if_alternative"] is not None
    assert "F9 would take" in explanation["reason"]


def test_all_neighborhoods_have_emergency_medical_coverage(opt_env):
    sp = opt_env["sp"]
    views = opt_env["graph_views"]
    source_data = opt_env["source"]
    facilities = source_data["facilities"]
    neighborhood_ids = [str(i) for i in range(1, 16)]

    before_failures = []
    base = views.build_base_graph(source_data)
    for source in neighborhood_ids:
        fid, path, eta_h, _ = sp.find_nearest_facility(
            base, source, "Medical", facilities=facilities,
            time_of_day="morning_peak",
        )
        if fid is None or path is None or not math.isfinite(eta_h):
            before_failures.append(source)

    route_report = []
    for source in neighborhood_ids:
        emergency = views.build_emergency_graph(source_data)
        fid, path, eta_h, _ = sp.find_nearest_facility(
            emergency, source, "Medical", facilities=facilities,
            time_of_day="morning_peak",
        )

        assert fid in {"F9", "F10"}
        assert path is not None
        assert path[0] == source
        assert path[-1] in {"F9", "F10"}
        assert eta_h > 0

        route_report.append({
            "source": source,
            "hospital": fid,
            "path": path,
            "eta_minutes": round(eta_h * 60.0, 2),
        })

    assert before_failures
    assert len(route_report) == 15
    print("Before emergency_graph medical failures:", before_failures)
    for row in route_report:
        print(
            f"{row['source']} -> {row['hospital']} "
            f"({row['eta_minutes']} min): {' -> '.join(row['path'])}"
        )
