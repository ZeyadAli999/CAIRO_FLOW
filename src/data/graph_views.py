"""Graph views for optimized, non-destructive routing analysis."""
from __future__ import annotations

from typing import Any

import networkx as nx

from src.data.data_enrichment import (
    FLOW_KEY_TO_TIME_PERIOD,
    TIME_PERIOD_TO_FLOW_KEY,
    enrich_existing_roads,
    generate_medical_connectors,
)


def _load_source_data() -> dict[str, list[Any]]:
    from src.db.queries import (
        all_existing_roads,
        all_facilities,
        all_neighborhoods,
        all_potential_roads,
        all_traffic_flow,
        all_transit_demand,
    )
    from src.db.models import BusRoute, MetroLine, SessionLocal
    from sqlalchemy import select

    with SessionLocal() as session:
        metros = list(session.scalars(select(MetroLine)).all())
        buses = list(session.scalars(select(BusRoute)).all())

    return {
        "neighborhoods": all_neighborhoods(),
        "facilities": all_facilities(),
        "existing_roads": all_existing_roads(),
        "potential_roads": all_potential_roads(),
        "traffic_flow": all_traffic_flow(),
        "metro_lines": metros,
        "bus_routes": buses,
        "transit_demand": all_transit_demand(),
    }


def _copy_with_enriched_original_edges(g: nx.Graph, source_data: dict[str, list[Any]]) -> nx.Graph:
    out = g.copy()
    enriched = enrich_existing_roads(
        source_data.get("existing_roads", []),
        source_data.get("traffic_flow", []),
    )
    for road in enriched:
        u, v = str(road["from_id"]), str(road["to_id"])
        if not out.has_edge(u, v):
            continue
        out[u][v].update(road)
        out[u][v]["road_type"] = "existing"
        out[u][v]["cost_million_egp"] = out[u][v].get("cost_million_egp", 0.0)
    return out


def _add_connectors(g: nx.Graph, source_data: dict[str, list[Any]]) -> list[dict]:
    connectors = generate_medical_connectors(
        source_data.get("neighborhoods", []),
        source_data.get("facilities", []),
        source_data.get("existing_roads", []),
    )
    for connector in connectors:
        u, v = str(connector["from_id"]), str(connector["to_id"])
        if u not in g or v not in g:
            continue
        if not g.has_edge(u, v):
            g.add_edge(u, v, **connector)
    return connectors


def build_base_graph(source_data: dict[str, list[Any]] | None = None) -> nx.Graph:
    """Original existing roads only, enriched with copied metadata."""
    from src.graph.builder import build_graph

    source_data = source_data or _load_source_data()
    return _copy_with_enriched_original_edges(build_graph(), source_data)


def build_routing_graph(source_data: dict[str, list[Any]] | None = None) -> nx.Graph:
    """Original roads plus safe inferred connectors for opt-in routing."""
    source_data = source_data or _load_source_data()
    graph = build_base_graph(source_data)
    _add_connectors(graph, source_data)
    graph.graph["view"] = "routing_graph"
    graph.graph["uses_inferred_connectors"] = True
    return graph


def build_emergency_graph(source_data: dict[str, list[Any]] | None = None) -> nx.Graph:
    """Emergency routing graph with inferred medical connectors."""
    source_data = source_data or _load_source_data()
    graph = build_base_graph(source_data)
    connectors = _add_connectors(graph, source_data)
    graph.graph["view"] = "emergency_graph"
    graph.graph["uses_inferred_connectors"] = bool(connectors)
    graph.graph["inferred_connector_count"] = len(connectors)
    return graph


def build_mst_graph(source_data: dict[str, list[Any]] | None = None) -> nx.Graph:
    """Undirected MST view that preserves original records elsewhere."""
    from src.graph.builder import build_mst_graph as legacy_build_mst_graph

    source_data = source_data or _load_source_data()
    graph = legacy_build_mst_graph()
    enriched_base = _copy_with_enriched_original_edges(graph, source_data)
    enriched_base.graph["view"] = "mst_graph"
    enriched_base.graph["normalized_duplicate_bidirectional_roads"] = True
    return enriched_base


def build_traffic_graph(
    time_period: str,
    source_data: dict[str, list[Any]] | None = None,
    *,
    include_connectors: bool = True,
) -> nx.Graph:
    """Return a graph weighted by enriched time-dependent minutes."""
    period = _normalize_time_period(time_period)
    source_data = source_data or _load_source_data()
    graph = build_routing_graph(source_data) if include_connectors else build_base_graph(source_data)

    for _, _, data in graph.edges(data=True):
        costs = data.get("time_dependent_cost") or {}
        weight = float(costs.get(period, data.get("base_travel_time_min", 0)) or 0)
        data["time_weight_min"] = max(weight, 0.0001)
        data[f"time_weight_{period}_min"] = data["time_weight_min"]

    graph.graph["view"] = f"traffic_graph_{period}"
    graph.graph["time_period"] = period
    return graph


def build_transit_graph(source_data: dict[str, list[Any]] | None = None) -> nx.MultiGraph:
    """Build the existing multimodal graph from the optimized base view."""
    from src.algorithms.multimodal import build_multimodal_graph

    source_data = source_data or _load_source_data()
    return build_multimodal_graph(
        build_base_graph(source_data),
        source_data.get("metro_lines", []),
        source_data.get("bus_routes", []),
    )


def build_all_graph_views(source_data: dict[str, list[Any]] | None = None) -> dict[str, nx.Graph]:
    source_data = source_data or _load_source_data()
    return {
        "base_graph": build_base_graph(source_data),
        "routing_graph": build_routing_graph(source_data),
        "emergency_graph": build_emergency_graph(source_data),
        "mst_graph": build_mst_graph(source_data),
        "traffic_graph_morning": build_traffic_graph("morning", source_data),
        "traffic_graph_afternoon": build_traffic_graph("afternoon", source_data),
        "traffic_graph_evening": build_traffic_graph("evening", source_data),
        "traffic_graph_night": build_traffic_graph("night", source_data),
        "transit_graph": build_transit_graph(source_data),
    }


def inferred_connector_edges(graph: nx.Graph) -> list[tuple[Any, Any, dict]]:
    return [
        (u, v, data) for u, v, data in graph.edges(data=True)
        if data.get("is_inferred") is True
    ]


def _normalize_time_period(value: str) -> str:
    normalized = str(value).strip().lower()
    if normalized in TIME_PERIOD_TO_FLOW_KEY:
        return normalized
    if normalized in FLOW_KEY_TO_TIME_PERIOD:
        return FLOW_KEY_TO_TIME_PERIOD[normalized]
    raise ValueError(
        "time_period must be one of morning, afternoon, evening, night "
        "or the matching flow key."
    )

