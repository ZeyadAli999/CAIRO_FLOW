"""Backward-compatible data enrichment for CairoFlow source records.

All functions in this module return copied dictionaries. The original CSV
records and SQLAlchemy model objects remain untouched.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any


TIME_PERIOD_TO_FLOW_KEY: dict[str, str] = {
    "morning": "morning_peak",
    "afternoon": "afternoon",
    "evening": "evening_peak",
    "night": "night",
}

FLOW_KEY_TO_TIME_PERIOD: dict[str, str] = {
    flow_key: period for period, flow_key in TIME_PERIOD_TO_FLOW_KEY.items()
}

CONNECTOR_REASON = (
    "Medical facility was isolated in the original dataset and was connected "
    "for emergency routing."
)


def as_record(obj: Any) -> dict:
    """Return a plain dict for either a dict-like record or model object."""
    if isinstance(obj, dict):
        return dict(obj)
    out: dict[str, Any] = {}
    for name in (
        "id", "from_id", "to_id", "name", "type", "population", "x", "y",
        "distance_km", "capacity", "condition", "cost_million_egp",
        "morning_peak", "afternoon", "evening_peak", "night",
        "line_id", "route_id", "stations", "stops", "buses_assigned",
        "daily_passengers",
    ):
        if hasattr(obj, name):
            out[name] = getattr(obj, name)
    return out


def normalized_pair(a: Any, b: Any) -> tuple[str, str]:
    return tuple(sorted((str(a), str(b))))


def coordinate_distance_km(a: dict, b: dict) -> float:
    """Approximate coordinate distance using the project's A* convention."""
    ax, ay = float(a.get("x", 0) or 0), float(a.get("y", 0) or 0)
    bx, by = float(b.get("x", 0) or 0), float(b.get("y", 0) or 0)
    lat_km = (ay - by) * 111.0
    lon_km = (ax - bx) * 111.0 * math.cos(math.radians(by))
    return math.sqrt(lat_km * lat_km + lon_km * lon_km)


def estimated_speed_kmh_for_condition(condition: Any) -> float:
    """Conservative urban speed estimate used only by enriched views."""
    try:
        cond = float(condition)
    except (TypeError, ValueError):
        cond = 7.0
    return max(20.0, min(65.0, 20.0 + cond * 4.5))


def traffic_lookup(traffic_rows: Iterable[Any]) -> dict[tuple[str, str], dict[str, float]]:
    lookup: dict[tuple[str, str], dict[str, float]] = {}
    for row in traffic_rows:
        rec = as_record(row)
        if "from_id" not in rec or "to_id" not in rec:
            continue
        lookup[normalized_pair(rec["from_id"], rec["to_id"])] = {
            "morning_peak": float(rec.get("morning_peak", 0) or 0),
            "afternoon": float(rec.get("afternoon", 0) or 0),
            "evening_peak": float(rec.get("evening_peak", 0) or 0),
            "night": float(rec.get("night", 0) or 0),
        }
    return lookup


def enrich_road(record: Any, traffic: dict[str, float] | None = None) -> dict:
    """Return a copied existing-road record with calculated fields."""
    road = as_record(record)
    distance = float(road.get("distance_km", 0) or 0)
    capacity = float(road.get("capacity", 0) or 0)
    condition = road.get("condition", 7)
    speed = estimated_speed_kmh_for_condition(condition)
    base_time = (distance / speed * 60.0) if speed > 0 else 0.0
    traffic = traffic or {}

    utilization: dict[str, float] = {}
    time_cost: dict[str, float] = {}
    for period, flow_key in TIME_PERIOD_TO_FLOW_KEY.items():
        flow = float(traffic.get(flow_key, 0) or 0)
        util = flow / capacity if capacity > 0 else 0.0
        utilization[period] = util
        time_cost[period] = base_time * (1.0 + util)

    average_utilization = (
        sum(utilization.values()) / len(utilization) if utilization else 0.0
    )
    congestion_score = max(utilization.values(), default=0.0)
    try:
        cond_float = float(condition)
    except (TypeError, ValueError):
        cond_float = 7.0

    road.update({
        "estimated_speed_kmh": speed,
        "base_travel_time_min": base_time,
        "utilization": utilization,
        "time_dependent_cost": time_cost,
        "congestion_score": congestion_score,
        "maintenance_priority_score": (
            (10.0 - cond_float) * distance * (1.0 + average_utilization)
        ),
        "emergency_priority_score": congestion_score + max(0.0, 10.0 - cond_float) / 10.0,
        "average_utilization": average_utilization,
        "is_original": True,
        "is_inferred": False,
        "traffic": {
            "morning_peak": float(traffic.get("morning_peak", 0) or 0),
            "afternoon": float(traffic.get("afternoon", 0) or 0),
            "evening_peak": float(traffic.get("evening_peak", 0) or 0),
            "night": float(traffic.get("night", 0) or 0),
        },
    })
    return road


def enrich_existing_roads(existing_roads: Iterable[Any], traffic_rows: Iterable[Any]) -> list[dict]:
    lookup = traffic_lookup(traffic_rows)
    enriched: list[dict] = []
    for road in existing_roads:
        rec = as_record(road)
        key = normalized_pair(rec["from_id"], rec["to_id"])
        enriched.append(enrich_road(rec, lookup.get(key)))
    return enriched


def node_lookup(neighborhoods: Iterable[Any], facilities: Iterable[Any]) -> dict[str, dict]:
    nodes: dict[str, dict] = {}
    for n in neighborhoods:
        rec = as_record(n)
        rec["id"] = str(rec["id"])
        rec["kind"] = "neighborhood"
        nodes[rec["id"]] = rec
    for f in facilities:
        rec = as_record(f)
        rec["id"] = str(rec["id"])
        rec["kind"] = "facility"
        nodes[rec["id"]] = rec
    return nodes


def isolated_medical_facility_ids(
    neighborhoods: Iterable[Any],
    facilities: Iterable[Any],
    existing_roads: Iterable[Any],
) -> list[str]:
    nodes = node_lookup(neighborhoods, facilities)
    incident: set[str] = set()
    for road in existing_roads:
        rec = as_record(road)
        incident.add(str(rec.get("from_id")))
        incident.add(str(rec.get("to_id")))
    return sorted(
        fid for fid, data in nodes.items()
        if data.get("kind") == "facility"
        and data.get("type") == "Medical"
        and fid not in incident
    )


def generate_medical_connectors(
    neighborhoods: Iterable[Any],
    facilities: Iterable[Any],
    existing_roads: Iterable[Any],
) -> list[dict]:
    """Create inferred emergency connectors for isolated Medical facilities."""
    nodes = node_lookup(neighborhoods, facilities)
    incident: set[str] = set()
    for road in existing_roads:
        rec = as_record(road)
        incident.add(str(rec.get("from_id")))
        incident.add(str(rec.get("to_id")))

    connected_nodes = {
        nid: data for nid, data in nodes.items()
        if nid in incident and "x" in data and "y" in data
    }
    connectors: list[dict] = []

    for fid in isolated_medical_facility_ids(neighborhoods, facilities, existing_roads):
        facility = nodes[fid]
        nearest_id = None
        nearest_distance = math.inf
        for nid, candidate in connected_nodes.items():
            if nid == fid:
                continue
            distance = coordinate_distance_km(facility, candidate)
            if distance < nearest_distance:
                nearest_id = nid
                nearest_distance = distance
        if nearest_id is None:
            continue

        capacity = 1800
        condition = 8
        speed = 45.0
        base_time = nearest_distance / speed * 60.0
        connectors.append({
            "id": f"INFERRED_MEDICAL_{fid}_TO_{nearest_id}",
            "from_id": fid,
            "to_id": nearest_id,
            "distance_km": nearest_distance,
            "capacity": capacity,
            "condition": condition,
            "estimated_speed_kmh": speed,
            "base_travel_time_min": base_time,
            "utilization": {period: 0.0 for period in TIME_PERIOD_TO_FLOW_KEY},
            "time_dependent_cost": {period: base_time for period in TIME_PERIOD_TO_FLOW_KEY},
            "congestion_score": 0.0,
            "maintenance_priority_score": 0.0,
            "emergency_priority_score": 1.0,
            "traffic": {
                "morning_peak": 0.0,
                "afternoon": 0.0,
                "evening_peak": 0.0,
                "night": 0.0,
            },
            "cost_million_egp": 0.0,
            "road_type": "inferred",
            "is_original": False,
            "is_inferred": True,
            "connector_type": "medical_emergency_connector",
            "reason": CONNECTOR_REASON,
            "confidence": 0.72,
            "connected_to_nearest_node": True,
        })
    return connectors

