"""Full-project feature verification.

This file intentionally exercises existing public APIs and opt-in graph views
without modifying production behavior or the original dataset.
"""
from __future__ import annotations

import importlib
import inspect
import math
import sys

import networkx as nx
import pytest


@pytest.fixture(scope="module")
def full_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-full-project")
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
    from src.data import (
        optimized_loader,
        graph_views,
        data_validator,
        potential_roads_analysis,
    )
    importlib.reload(optimized_loader)
    importlib.reload(graph_views)
    importlib.reload(data_validator)
    importlib.reload(potential_roads_analysis)
    from src.algorithms import dp, greedy, mst, multimodal, shortest_path as sp
    for module in (dp, greedy, mst, multimodal, sp):
        importlib.reload(module)
    from src.simulation import framework
    importlib.reload(framework)

    source_data = optimized_loader.load_source_data()
    optimized = optimized_loader.load_optimized_transport_data(source_data)
    base_graph = builder.build_graph()
    return {
        "models": models,
        "queries": queries,
        "builder": builder,
        "source_data": source_data,
        "optimized": optimized,
        "graph_views": graph_views,
        "potential_roads_analysis": potential_roads_analysis,
        "base_graph": base_graph,
        "dp": dp,
        "greedy": greedy,
        "mst": mst,
        "multimodal": multimodal,
        "sp": sp,
        "framework": framework,
    }


def _path_is_valid(graph, path):
    return (
        path is not None
        and all(node in graph for node in path)
        and all(graph.has_edge(u, v) for u, v in zip(path[:-1], path[1:]))
    )


def _session_rows(env, model):
    with env["models"].SessionLocal() as session:
        return list(session.query(model).all())


def test_data_loading_validation_and_graph_views(full_env):
    source = full_env["source_data"]
    views = full_env["graph_views"]
    report = full_env["optimized"].validation_report

    assert len(source["neighborhoods"]) == 15
    assert len(source["facilities"]) == 10
    assert len(source["existing_roads"]) == 28
    assert report.ok

    graphs = views.build_all_graph_views(source)
    expected = {
        "base_graph", "routing_graph", "emergency_graph", "mst_graph",
        "traffic_graph_morning", "traffic_graph_afternoon",
        "traffic_graph_evening", "traffic_graph_night", "transit_graph",
    }
    assert expected.issubset(graphs)
    assert views.inferred_connector_edges(graphs["base_graph"]) == []
    connectors = views.inferred_connector_edges(graphs["emergency_graph"])
    assert len(connectors) == 2
    assert all(data["is_inferred"] is True and data["is_original"] is False
               for _, _, data in connectors)

    for name, graph in graphs.items():
        assert graph.number_of_nodes() > 0, name
        for u, v, data in graph.edges(data=True):
            assert u in graph and v in graph
            if "distance_km" in data:
                assert float(data["distance_km"]) > 0


def test_emergency_medical_coverage_from_all_neighborhoods(full_env):
    source = full_env["source_data"]
    sp = full_env["sp"]
    emergency = full_env["graph_views"].build_emergency_graph(source)
    facilities = source["facilities"]
    rows = []

    for source_id in [str(i) for i in range(1, 16)]:
        fid, path, eta_h, _ = sp.find_nearest_facility(
            emergency, source_id, "Medical", facilities=facilities,
            time_of_day="morning_peak",
        )
        assert fid in {"F9", "F10"}
        assert _path_is_valid(emergency, path)
        assert path[0] == source_id
        assert path[-1] in {"F9", "F10"}
        assert eta_h > 0
        rows.append((source_id, fid, path, round(eta_h * 60.0, 2)))

    assert len(rows) == 15
    for source_id, fid, path, eta_min in rows:
        print(f"{source_id}|{fid}|{eta_min}|{' -> '.join(path)}")


@pytest.mark.parametrize("source,target", [
    ("1", "3"),
    ("1", "F1"),
    ("7", "13"),
    ("12", "5"),
    ("15", "3"),
])
def test_dijkstra_required_routes_on_base_graph(full_env, source, target):
    graph = full_env["base_graph"]
    path, cost, _ = full_env["sp"].dijkstra(graph, source, target, weight="distance_km")

    assert _path_is_valid(graph, path)
    assert path[0] == source
    assert path[-1] == target
    assert cost > 0


@pytest.mark.parametrize("source,target", [
    ("1", "F1"),
    ("1", "13"),
    ("7", "3"),
    ("12", "F2"),
    ("14", "8"),
])
def test_astar_matches_dijkstra_on_required_routes(full_env, source, target):
    graph = full_env["base_graph"]
    d_path, d_cost, _ = full_env["sp"].dijkstra(graph, source, target, weight="distance_km")
    a_path, a_cost, _ = full_env["sp"].astar(graph, source, target, weight="distance_km")

    assert _path_is_valid(graph, d_path)
    assert _path_is_valid(graph, a_path)
    assert a_path[0] == source and a_path[-1] == target
    assert a_cost == pytest.approx(d_cost, rel=1e-9)


@pytest.mark.parametrize("source,target", [
    ("1", "13"),
    ("7", "3"),
    ("F1", "3"),
])
def test_time_dependent_routing_all_periods(full_env, source, target):
    graph = full_env["base_graph"]
    sp = full_env["sp"]
    costs = {}
    for tod in sp.VALID_TIMES_OF_DAY:
        path, hours, _ = sp.dijkstra_time_dependent(graph, source, target, tod)
        assert _path_is_valid(graph, path)
        assert hours > 0
        costs[tod] = hours

    assert costs["morning_peak"] >= costs["night"]
    print(source, target, {k: round(v * 60.0, 2) for k, v in costs.items()})


def test_mst_largest_component_duplicate_safety_and_positive_distance(full_env):
    graph = full_env["graph_views"].build_mst_graph(full_env["source_data"])
    mst_graph, trace = full_env["mst"].kruskal_mst(graph, weight="cost_million_egp")
    largest_cc = max(nx.connected_components(graph), key=len)
    sub = mst_graph.subgraph(largest_cc)

    assert nx.is_tree(sub)
    assert sub.number_of_edges() == sub.number_of_nodes() - 1
    assert sum(float(d.get("distance_km", 0) or 0) for _, _, d in sub.edges(data=True)) > 0
    assert graph.number_of_edges() == 42
    assert graph.has_edge("7", "15")
    assert trace.extra["edge_breakdown"][0] >= 1


def test_potential_roads_load_positive_and_are_available_for_network_design(full_env):
    potential = full_env["source_data"]["potential_roads"]
    assert len(potential) == 15
    for road in potential:
        assert float(road.distance_km) > 0
        assert int(road.capacity) > 0
        assert float(road.cost_million_egp) > 0

    graph = full_env["graph_views"].build_mst_graph(full_env["source_data"])
    potential_edges = [
        (u, v, data) for u, v, data in graph.edges(data=True)
        if data.get("road_type") == "potential"
    ]
    assert potential_edges
    ranked = sorted(
        potential_edges,
        key=lambda e: float(e[2].get("cost_million_egp", 0)) / float(e[2].get("capacity", 1)),
    )
    assert ranked[0][2]["cost_million_egp"] > 0

    original_count = len(potential)
    recommendations = full_env["potential_roads_analysis"].recommend_potential_roads(limit=5)
    assert recommendations
    assert len(recommendations) == 5
    assert len(full_env["source_data"]["potential_roads"]) == original_count
    scores = [row["score"] for row in recommendations]
    assert all(score > 0 for score in scores)
    assert scores == sorted(scores, reverse=True)
    for row in recommendations:
        assert {
            "from_id", "to_id", "distance_km", "capacity", "construction_cost",
            "cost_per_km", "score", "explanation",
        }.issubset(row)
        assert row["explanation"]


def test_dynamic_programming_public_apis_with_deterministic_inputs(full_env):
    dp = full_env["dp"]
    graph = full_env["base_graph"]

    bus_result = dp.transit_scheduling([
        {"route_id": "A", "daily_passengers": 1000},
        {"route_id": "B", "daily_passengers": 500},
    ], total_buses=6, per_route_cap=6)
    assert sum(bus_result["allocations"].values()) <= 6
    assert bus_result["total_benefit"] > 0

    metro_result = dp.metro_scheduling([
        {"line_id": "M-A", "daily_passengers": 10000},
        {"line_id": "M-B", "daily_passengers": 8000},
    ], total_train_hours=12, per_line_cap=12)
    assert sum(metro_result["allocations"].values()) <= 12
    assert metro_result["total_benefit"] > 0

    maintenance = dp.road_maintenance_knapsack([
        {"from": "A", "to": "B", "distance_km": 3.0, "condition": 5, "pop_a": 1000, "pop_b": 2000},
        {"from": "B", "to": "C", "distance_km": 5.0, "condition": 9, "pop_a": 1000, "pop_b": 2000},
    ], budget_million_egp=20.0)
    assert maintenance["total_cost"] <= 20.0
    assert maintenance["total_value"] > 0

    dp.cache_clear()
    first = dp.memoized_route_query(graph, "1", "F1", "morning_peak")
    second = dp.memoized_route_query(graph, "1", "F1", "morning_peak")
    assert first["path"] == second["path"]
    assert second["trace"].parameters["cache_hit"] is True
    assert dp.cache_stats()["hits"] >= 1


def test_greedy_signal_preemption_and_audit(full_env):
    greedy = full_env["greedy"]
    graph = full_env["base_graph"]

    allocation = greedy.traffic_signal_allocation("3", graph, "morning_peak")
    assert allocation["total_cycle"] == greedy.CYCLE_SECONDS
    assert all(greedy.MIN_GREEN_S <= seconds <= greedy.MAX_GREEN_S
               for seconds in allocation["allocations"].values())

    schedule = greedy.emergency_preemption_priority([
        {"id": "low", "priority": 4, "path": ["1", "3", "5"]},
        {"id": "high", "priority": 1, "path": ["11", "F2", "3", "5"]},
    ], intersections=graph.nodes(), graph=graph)
    assert schedule
    assert schedule[0]["emergency_id"] == "high"
    assert [row["priority"] for row in schedule] == sorted(row["priority"] for row in schedule)

    audit = greedy.signal_audit_report(graph, "morning_peak")
    assert audit["intersections_audited"] > 0
    assert 0 <= audit["gini_overall"] <= 1


def test_public_transport_multimodal_and_demand_features(full_env):
    models = full_env["models"]
    multimodal = full_env["multimodal"]
    graph = full_env["base_graph"]
    metros = _session_rows(full_env, models.MetroLine)
    buses = _session_rows(full_env, models.BusRoute)
    demands = _session_rows(full_env, models.TransitDemand)

    assert metros and buses and demands
    for metro in metros:
        for station in str(metro.stations).split(","):
            assert station in graph
    for bus in buses:
        for stop in str(bus.stops).split(","):
            assert stop in graph
    for demand in demands:
        assert demand.from_id in graph and demand.to_id in graph

    mm_graph = multimodal.build_multimodal_graph(graph, metros, buses)
    path, total_min, breakdown, _ = multimodal.multimodal_shortest_path(mm_graph, "12", "F1")
    assert path is not None
    assert total_min > 0
    assert len(breakdown) == len(path) - 1

    ranking = multimodal.analyze_transfer_points(mm_graph, demands)
    assert ranking
    assert all("node_id" in row and "weighted_demand" in row for row in ranking)
    assert ranking == sorted(
        ranking,
        key=lambda row: (-row["weighted_demand"], -row["transfer_count"], str(row["node_id"])),
    )


def test_simulation_framework_scenarios_and_non_mutation(full_env):
    framework = full_env["framework"]
    graph = full_env["base_graph"]
    before_edges = set(map(frozenset, graph.edges()))
    sim = framework.TransportSimulator(graph, facilities_df=full_env["source_data"]["facilities"])

    peak = sim.run_scenario("peak_rush", source="1", target="F1")
    assert peak.summary["morning_peak_min"] > 0
    closure = sim.run_scenario("road_closure", source="1", target="3", closed=[("1", "3")])
    assert closure.summary["alternatives_found"] >= 0
    transit = sim.run_scenario("transit_optimization", total_buses=30)
    assert transit.summary["dp_benefit"] > 0
    maintain = sim.run_scenario("maintenance_budget")
    assert maintain.summary["best_total_value"] >= 0
    signal = sim.run_scenario("signal_audit")
    assert signal.summary["intersections_audited"] > 0
    mm = sim.run_scenario("multimodal_demand")
    assert mm.summary["n_transfer_hubs"] > 0

    emergency_sim = framework.TransportSimulator(
        full_env["graph_views"].build_emergency_graph(full_env["source_data"]),
        facilities_df=full_env["source_data"]["facilities"],
    )
    emergency = emergency_sim.run_scenario("emergency_dispatch", source="11", facility_type="Medical")
    assert emergency.summary["selected_facility"] in {"F9", "F10"}

    assert set(map(frozenset, graph.edges())) == before_edges


def test_ui_callback_safety_and_graph_builder_use(full_env):
    for module_name in (
        "src.ui.route_mode", "src.ui.emergency_mode", "src.ui.network_mode",
        "src.ui.maintain_mode", "src.ui.transit_mode", "src.ui.layout",
    ):
        assert importlib.import_module(module_name)

    sys.modules.pop("app", None)
    app_mod = importlib.import_module("app")
    assert "build_emergency_graph()" in inspect.getsource(app_mod._dispatch_emergency)
    assert "build_graph()" in inspect.getsource(app_mod._compute_route)
    assert "build_mst_graph()" in inspect.getsource(app_mod._compute_mst)
