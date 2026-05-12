"""Opt-in optimized data loader for CairoFlow.

This loader preserves the original database and CSV data as the source of
truth, then returns enriched copies plus graph views for algorithms that want
the safer dataset.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.data.data_enrichment import enrich_existing_roads, generate_medical_connectors
from src.data.data_validator import ValidationReport, validate_source_data


@dataclass
class OptimizedTransportData:
    source_data: dict[str, list[Any]]
    validation_report: ValidationReport
    enriched_existing_roads: list[dict]
    inferred_medical_connectors: list[dict]

    @property
    def original_node_count(self) -> int:
        return len(self.source_data.get("neighborhoods", [])) + len(self.source_data.get("facilities", []))

    @property
    def original_road_count(self) -> int:
        return len(self.source_data.get("existing_roads", []))


def load_source_data() -> dict[str, list[Any]]:
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
        metro_lines = list(session.scalars(select(MetroLine)).all())
        bus_routes = list(session.scalars(select(BusRoute)).all())

    return {
        "neighborhoods": all_neighborhoods(),
        "facilities": all_facilities(),
        "existing_roads": all_existing_roads(),
        "potential_roads": all_potential_roads(),
        "traffic_flow": all_traffic_flow(),
        "metro_lines": metro_lines,
        "bus_routes": bus_routes,
        "transit_demand": all_transit_demand(),
    }


def load_optimized_transport_data(
    source_data: dict[str, list[Any]] | None = None,
) -> OptimizedTransportData:
    source_data = source_data or load_source_data()
    report = validate_source_data(source_data)
    enriched_roads = enrich_existing_roads(
        source_data.get("existing_roads", []),
        source_data.get("traffic_flow", []),
    )
    connectors = generate_medical_connectors(
        source_data.get("neighborhoods", []),
        source_data.get("facilities", []),
        source_data.get("existing_roads", []),
    )
    return OptimizedTransportData(
        source_data=source_data,
        validation_report=report,
        enriched_existing_roads=enriched_roads,
        inferred_medical_connectors=connectors,
    )


def build_optimized_graph_views(
    optimized: OptimizedTransportData | None = None,
) -> dict[str, Any]:
    from src.data.graph_views import build_all_graph_views

    optimized = optimized or load_optimized_transport_data()
    return build_all_graph_views(optimized.source_data)

