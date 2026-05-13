"""Traffic scenario helper tests."""
from __future__ import annotations

import importlib

import networkx as nx
import pytest


def _graph() -> nx.Graph:
    G = nx.Graph()
    for node, xy in {
        "A": (0.0, 0.0),
        "B": (1.0, 0.0),
        "C": (2.0, 0.0),
        "D": (1.0, 1.0),
    }.items():
        G.add_node(node, x=xy[0], y=xy[1])

    def add(u, v, distance, flow=900, capacity=1000):
        G.add_edge(
            u,
            v,
            distance_km=distance,
            capacity=capacity,
            traffic={
                "morning_peak": flow,
                "afternoon": flow,
                "evening_peak": flow,
                "night": flow,
            },
        )

    add("A", "B", 1.0)
    add("B", "C", 1.0)
    add("A", "D", 1.6)
    add("D", "C", 1.6)
    return G


@pytest.fixture(scope="module")
def project_graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-scenarios")
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
    return builder.build_graph()


def test_normal_traffic_preserves_existing_route_behavior():
    from src.scenarios.traffic_scenarios import evaluate_route_comparison

    comparison = evaluate_route_comparison(
        _graph(), "A", "C", "morning_peak", "normal"
    )

    assert comparison["scenario"]["label"] == "Normal Traffic"
    assert comparison["scenario"]["affected_edges"] == []
    assert comparison["distance_path"] == ["A", "B", "C"]
    assert comparison["traffic_path"] == ["A", "B", "C"]


def test_incident_scenario_is_in_memory_and_can_change_fastest_route():
    from src.scenarios.traffic_scenarios import (
        apply_traffic_scenario,
        evaluate_route_comparison,
    )

    G = _graph()
    original_traffic = dict(G["A"]["B"]["traffic"])
    application = apply_traffic_scenario(
        G, "incident_shortest_route", "A", "C", "morning_peak"
    )
    comparison = evaluate_route_comparison(
        G, "A", "C", "morning_peak", "incident_shortest_route"
    )

    assert application["label"] == "Incident on Shortest Route"
    assert application["affected_edges"]
    assert application["graph"] is not G
    assert G["A"]["B"]["traffic"] == original_traffic
    assert comparison["distance_path"] == ["A", "B", "C"]
    assert comparison["traffic_path"] == ["A", "D", "C"]
    assert comparison["traffic_time_winner"]["winner"] == "Traffic-aware route"


def test_scenario_evaluation_returns_both_metrics_and_fair_winners():
    from src.scenarios.traffic_scenarios import evaluate_route_comparison

    comparison = evaluate_route_comparison(
        _graph(), "A", "C", "morning_peak", "incident_shortest_route"
    )

    shortest = comparison["shortest_distance_route"]
    traffic = comparison["traffic_aware_route"]

    assert shortest["distance_label"].endswith(" km")
    assert shortest["traffic_time_label"].endswith(" min")
    assert traffic["distance_label"].endswith(" km")
    assert traffic["traffic_time_label"].endswith(" min")
    assert comparison["distance_winner"]["label"] == "Shortest Distance Winner"
    assert comparison["traffic_time_winner"]["label"] == "Fastest Traffic-Time Winner"
    assert "Distance is compared with distance" in comparison["explanation"]
    assert "traffic-time is compared with traffic-time" in comparison["explanation"]


def test_peak_congestion_is_calibrated_for_representative_demo(project_graph):
    from src.scenarios.traffic_scenarios import evaluate_route_comparison

    comparison = evaluate_route_comparison(
        project_graph, "1", "11", "morning_peak", "peak_congestion"
    )
    shortest = comparison["shortest_distance_route"]
    traffic = comparison["traffic_aware_route"]

    assert comparison["path_changed"] is True
    assert shortest["distance_km"] < traffic["distance_km"]
    assert shortest["traffic_time_min"] > traffic["traffic_time_min"]
    assert shortest["traffic_time_min"] < 120
    assert traffic["traffic_time_min"] < 90
    assert shortest["traffic_time_min"] - traffic["traffic_time_min"] >= 10


def test_incident_scenario_is_calibrated_without_absurd_minutes(project_graph):
    from src.scenarios.traffic_scenarios import evaluate_route_comparison

    comparison = evaluate_route_comparison(
        project_graph, "1", "F1", "morning_peak", "incident_shortest_route"
    )
    shortest = comparison["shortest_distance_route"]
    traffic = comparison["traffic_aware_route"]

    assert comparison["path_changed"] is True
    assert shortest["distance_km"] < traffic["distance_km"]
    assert shortest["traffic_time_min"] > traffic["traffic_time_min"]
    assert shortest["traffic_time_min"] < 120
    assert traffic["traffic_time_min"] < 90
    assert shortest["traffic_time_min"] - traffic["traffic_time_min"] >= 10


def test_representative_scenarios_do_not_explode_to_absurd_minutes(project_graph):
    from src.scenarios.traffic_scenarios import evaluate_route_comparison

    cases = [
        ("1", "11", "peak_congestion"),
        ("1", "12", "peak_congestion"),
        ("1", "F1", "incident_shortest_route"),
        ("3", "F1", "incident_shortest_route"),
        ("7", "13", "peak_congestion"),
        ("5", "14", "peak_congestion"),
    ]

    for source, target, scenario in cases:
        comparison = evaluate_route_comparison(
            project_graph, source, target, "morning_peak", scenario
        )
        for route_key in ("shortest_distance_route", "traffic_aware_route"):
            traffic_time = comparison[route_key]["traffic_time_min"]
            assert traffic_time is not None
            assert traffic_time < 10_000
