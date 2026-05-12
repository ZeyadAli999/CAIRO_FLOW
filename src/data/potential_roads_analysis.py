"""Heuristic recommendations for potential road construction.

This module ranks copied potential-road records only. It does not modify raw
CSV files, database rows, graph builders, or MST behavior.
"""
from __future__ import annotations

import math
from typing import Any

from src.data.data_enrichment import as_record
from src.data.optimized_loader import load_source_data


CRITICAL_TYPES = {"Government", "Medical", "Transit Hub", "Airport"}


def recommend_potential_roads(limit: int = 5) -> list[dict[str, Any]]:
    """Return heuristic potential-road recommendations sorted by score.

    The score is intentionally simple and explainable:

    - higher capacity helps,
    - lower construction cost helps,
    - shorter distance helps,
    - high-population neighborhood endpoints get a bonus,
    - Government/Medical/Transit/Airport endpoints get a bonus,
    - endpoints with low existing-road degree get a small connectivity bonus.

    This is a planning heuristic, not a claim of real-world optimality.
    """
    source_data = load_source_data()
    potential_roads = [as_record(r) for r in source_data.get("potential_roads", [])]
    nodes = _node_lookup(source_data)
    degrees = _existing_degrees(source_data)

    recommendations = [
        _score_potential_road(road, nodes, degrees)
        for road in potential_roads
    ]
    recommendations.sort(key=lambda row: (-row["score"], row["from_id"], row["to_id"]))
    if limit is None:
        return recommendations
    return recommendations[:max(0, int(limit))]


def _node_lookup(source_data: dict[str, list[Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in source_data.get("neighborhoods", []):
        rec = as_record(row)
        rec["kind"] = "neighborhood"
        out[str(rec["id"])] = rec
    for row in source_data.get("facilities", []):
        rec = as_record(row)
        rec["kind"] = "facility"
        rec["population"] = 0
        out[str(rec["id"])] = rec
    return out


def _existing_degrees(source_data: dict[str, list[Any]]) -> dict[str, int]:
    degrees: dict[str, int] = {}
    for road in source_data.get("existing_roads", []):
        rec = as_record(road)
        u, v = str(rec.get("from_id")), str(rec.get("to_id"))
        degrees[u] = degrees.get(u, 0) + 1
        degrees[v] = degrees.get(v, 0) + 1
    return degrees


def _score_potential_road(
    road: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    degrees: dict[str, int],
) -> dict[str, Any]:
    from_id = str(road["from_id"])
    to_id = str(road["to_id"])
    distance = float(road["distance_km"])
    capacity = float(road["capacity"])
    construction_cost = float(road["cost_million_egp"])
    cost_per_km = construction_cost / distance

    a = nodes.get(from_id, {})
    b = nodes.get(to_id, {})
    population_sum = int(a.get("population") or 0) + int(b.get("population") or 0)
    population_bonus = min(1.0, math.log1p(population_sum) / 15.0) if population_sum > 0 else 0.0

    critical_hits = sum(
        1 for node in (a, b)
        if node.get("type") in CRITICAL_TYPES
    )
    critical_bonus = 0.25 * critical_hits

    low_degree_hits = sum(
        1 for node_id in (from_id, to_id)
        if degrees.get(node_id, 0) <= 1
    )
    connectivity_bonus = 0.15 * low_degree_hits

    base_score = capacity / max(construction_cost * distance, 0.1) * 1000.0
    multiplier = 1.0 + population_bonus + critical_bonus + connectivity_bonus
    score = base_score * multiplier

    reasons = [
        f"capacity {int(capacity)}",
        f"cost/km {cost_per_km:.2f} M EGP",
        f"distance {distance:.1f} km",
    ]
    if population_sum:
        reasons.append(f"population bonus from {population_sum:,} residents")
    if critical_hits:
        reasons.append("critical endpoint bonus")
    if low_degree_hits:
        reasons.append("low-connectivity endpoint bonus")

    return {
        "from_id": from_id,
        "to_id": to_id,
        "distance_km": distance,
        "capacity": int(capacity),
        "construction_cost": construction_cost,
        "cost_per_km": cost_per_km,
        "score": round(score, 4),
        "explanation": (
            "Heuristic recommendation based on "
            + ", ".join(reasons)
            + ". This is a planning heuristic, not ground-truth construction priority."
        ),
    }

