"""Display-only traffic scenarios for route-cost comparison.

The helpers in this module never edit raw data and never mutate the
caller-provided graph. Scenario effects are applied to a copied graph so
Race Lab and Route Mode can evaluate the same temporary traffic story.
"""
from __future__ import annotations

from typing import Any

import networkx as nx

from src.algorithms.shortest_path import (
    dijkstra,
    dijkstra_time_dependent,
    edge_congestion_ratio,
    path_distance_km,
    path_travel_time_hours,
)


SCENARIO_NORMAL = "normal"
SCENARIO_PEAK = "peak_congestion"
SCENARIO_INCIDENT = "incident_shortest_route"


TRAFFIC_SCENARIOS: dict[str, dict[str, Any]] = {
    SCENARIO_NORMAL: {
        "id": SCENARIO_NORMAL,
        "label": "Normal Traffic",
        "short_label": "Normal Traffic",
        "description": "Uses the existing graph and traffic data.",
        "factor": 1.0,
    },
    SCENARIO_PEAK: {
        "id": SCENARIO_PEAK,
        "label": "Peak Congestion",
        "short_label": "Peak Congestion",
        "description": (
            "Applies temporary in-memory congestion to high-pressure and "
            "route-relevant links."
        ),
        "factor": 2.1,
        "max_vc_ratio": 2.0,
    },
    SCENARIO_INCIDENT: {
        "id": SCENARIO_INCIDENT,
        "label": "Incident on Shortest Route",
        "short_label": "Incident on Shortest Route",
        "description": (
            "Computes the shortest-distance route first, then applies an "
            "in-memory incident penalty to one or more edges on that route."
        ),
        "factor": 3.0,
        "max_vc_ratio": 2.2,
    },
}


def scenario_options() -> list[dict[str, str]]:
    """Return Dash-friendly selector options."""
    return [
        {"label": data["label"], "value": sid}
        for sid, data in TRAFFIC_SCENARIOS.items()
    ]


def normalize_scenario_id(scenario_id: str | None) -> str:
    if scenario_id in TRAFFIC_SCENARIOS:
        return str(scenario_id)
    return SCENARIO_NORMAL


def scenario_label(scenario_id: str | None) -> str:
    return TRAFFIC_SCENARIOS[normalize_scenario_id(scenario_id)]["label"]


def route_metrics(G: nx.Graph, path: list[Any] | None, time_of_day: str) -> dict[str, Any]:
    """Evaluate one route with both fair display metrics."""
    if not path:
        return {
            "path": path,
            "distance_km": None,
            "traffic_time_min": None,
            "distance_label": "unreachable",
            "traffic_time_label": "unreachable",
        }
    distance = round(path_distance_km(G, path), 2)
    traffic_min = round(path_travel_time_hours(G, path, time_of_day) * 60.0, 2)
    return {
        "path": path,
        "distance_km": distance,
        "traffic_time_min": traffic_min,
        "distance_label": f"{distance:.2f} km",
        "traffic_time_label": f"{traffic_min:.2f} min",
    }


def compare_lower(
    label: str,
    first_name: str,
    first_value: float | None,
    second_name: str,
    second_value: float | None,
    unit: str,
    tie_text: str,
) -> dict[str, Any]:
    """Compare same-unit values; lower wins."""
    if first_value is None or second_value is None:
        return {
            "label": label,
            "winner": None,
            "text": f"{label}: winner unavailable because one route is unreachable.",
        }
    if abs(float(first_value) - float(second_value)) < 1e-9:
        return {"label": label, "winner": "tie", "text": tie_text}
    if float(first_value) < float(second_value):
        winner, win_value, lose_value = first_name, first_value, second_value
    else:
        winner, win_value, lose_value = second_name, second_value, first_value
    return {
        "label": label,
        "winner": winner,
        "text": (
            f"{label}: {winner} wins with {float(win_value):.2f} {unit} "
            f"vs {float(lose_value):.2f} {unit}."
        ),
    }


def apply_traffic_scenario(
    G: nx.Graph,
    scenario_id: str | None,
    source: Any,
    target: Any,
    time_of_day: str,
) -> dict[str, Any]:
    """Return a copied graph with temporary scenario traffic effects."""
    sid = normalize_scenario_id(scenario_id)
    scenario = TRAFFIC_SCENARIOS[sid]
    H = G.copy()
    affected_edges: list[tuple[Any, Any]] = []
    shortest_path, _, _ = dijkstra(G, source, target, weight="distance_km")

    if sid == SCENARIO_NORMAL:
        return {
            "id": sid,
            "label": scenario["label"],
            "description": scenario["description"],
            "graph": H,
            "affected_edges": affected_edges,
            "shortest_path": shortest_path,
            "factor": 1.0,
            "applied": False,
            "note": "Normal Traffic uses existing graph behavior.",
        }

    if sid == SCENARIO_PEAK:
        affected_edges = _peak_edges(G, source, target, time_of_day, shortest_path)
    else:
        affected_edges = _incident_edges(shortest_path)

    factor = float(scenario["factor"])
    max_vc_ratio = float(scenario.get("max_vc_ratio") or factor)
    for u, v in affected_edges:
        if H.has_edge(u, v):
            _apply_edge_penalty(H[u][v], factor, max_vc_ratio=max_vc_ratio)

    return {
        "id": sid,
        "label": scenario["label"],
        "description": scenario["description"],
        "graph": H,
        "affected_edges": affected_edges,
        "shortest_path": shortest_path,
        "factor": factor,
        "max_vc_ratio": max_vc_ratio,
        "applied": bool(affected_edges),
        "note": "Scenario is applied in memory only.",
    }


def evaluate_route_comparison(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
    scenario_id: str | None = SCENARIO_NORMAL,
) -> dict[str, Any]:
    """Compare shortest-distance and traffic-aware routes under a scenario."""
    application = apply_traffic_scenario(G, scenario_id, source, target, time_of_day)
    scenario_graph = application["graph"]

    distance_path, _, distance_trace = dijkstra(
        scenario_graph, source, target, weight="distance_km"
    )
    traffic_path, _, traffic_trace = dijkstra_time_dependent(
        scenario_graph, source, target, time_of_day
    )
    distance_metrics = route_metrics(scenario_graph, distance_path, time_of_day)
    traffic_metrics = route_metrics(scenario_graph, traffic_path, time_of_day)
    same_route = bool(
        distance_path and traffic_path and tuple(distance_path) == tuple(traffic_path)
    )

    distance_winner = compare_lower(
        "Shortest Distance Winner",
        "Shortest-distance route",
        distance_metrics["distance_km"],
        "Traffic-aware route",
        traffic_metrics["distance_km"],
        "km",
        "Both routes have the same distance.",
    )
    traffic_winner = compare_lower(
        "Fastest Traffic-Time Winner",
        "Shortest-distance route",
        distance_metrics["traffic_time_min"],
        "Traffic-aware route",
        traffic_metrics["traffic_time_min"],
        "min",
        "Both routes have the same estimated traffic time.",
    )
    no_alternative_note = (
        "No alternative route exists in this graph for this scenario; "
        "comparison focuses on search efficiency."
        if application["id"] != SCENARIO_NORMAL and same_route
        else None
    )

    return {
        "scenario": {
            key: value
            for key, value in application.items()
            if key != "graph"
        },
        "source": source,
        "target": target,
        "time_of_day": time_of_day,
        "distance_path": distance_path,
        "traffic_path": traffic_path,
        "distance_cost_km": distance_metrics["distance_km"],
        "traffic_cost_min": traffic_metrics["traffic_time_min"],
        "distance_path_travel_min": distance_metrics["traffic_time_min"],
        "traffic_path_distance_km": traffic_metrics["distance_km"],
        "path_changed": bool(distance_path and traffic_path and not same_route),
        "reachable": bool(distance_path and traffic_path),
        "shortest_distance_route": distance_metrics,
        "traffic_aware_route": traffic_metrics,
        "distance_winner": distance_winner,
        "traffic_time_winner": traffic_winner,
        "same_route": same_route,
        "no_alternative_note": no_alternative_note,
        "distance_trace_nodes": len(distance_trace.nodes_explored or []),
        "traffic_trace_nodes": len(traffic_trace.nodes_explored or []),
        "explanation": (
            "Shortest route is not always the fastest under congestion. "
            "Distance is compared with distance; traffic-time is compared "
            "with traffic-time."
        ),
    }


def _peak_edges(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
    shortest_path: list[Any] | None,
) -> list[tuple[Any, Any]]:
    selected: list[tuple[Any, Any]] = []
    if shortest_path:
        route_edges = list(zip(shortest_path[:-1], shortest_path[1:]))
        route_edges.sort(
            key=lambda edge: edge_congestion_ratio(G[edge[0]][edge[1]], time_of_day),
            reverse=True,
        )
        selected.extend(route_edges[:3])

    ranked = sorted(
        G.edges(data=True),
        key=lambda item: edge_congestion_ratio(item[2], time_of_day),
        reverse=True,
    )
    for u, v, _ in ranked:
        selected.append((u, v))

    return _unique_existing_edges(G, selected, limit=5)


def _incident_edges(shortest_path: list[Any] | None) -> list[tuple[Any, Any]]:
    if not shortest_path or len(shortest_path) < 2:
        return []
    edges = list(zip(shortest_path[:-1], shortest_path[1:]))
    if len(edges) <= 2:
        return edges
    middle = len(edges) // 2
    return edges[max(0, middle - 1): middle + 1]


def _unique_existing_edges(
    G: nx.Graph,
    edges: list[tuple[Any, Any]],
    *,
    limit: int,
) -> list[tuple[Any, Any]]:
    seen: set[frozenset[Any]] = set()
    out: list[tuple[Any, Any]] = []
    for u, v in edges:
        key = frozenset((u, v))
        if key in seen or not G.has_edge(u, v):
            continue
        seen.add(key)
        out.append((u, v))
        if len(out) >= limit:
            break
    return out


def _apply_edge_penalty(
    data: dict[str, Any],
    factor: float,
    *,
    max_vc_ratio: float,
) -> None:
    traffic = dict(data.get("traffic") or {})
    capacity = float(data.get("capacity") or 1)
    data["traffic"] = {
        key: int(round(min(float(value or 0) * factor, capacity * max_vc_ratio)))
        for key, value in traffic.items()
    }
    data["scenario_factor"] = factor
    data["scenario_max_vc_ratio"] = max_vc_ratio
