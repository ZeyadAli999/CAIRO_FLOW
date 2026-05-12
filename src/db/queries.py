"""Read helpers used by the UI and graph builder."""
from __future__ import annotations

from sqlalchemy import select

from src.db.models import (
    ExistingRoad,
    Facility,
    Neighborhood,
    PotentialRoad,
    SessionLocal,
    TrafficFlow,
    TransitDemand,
)


def all_neighborhoods() -> list[Neighborhood]:
    with SessionLocal() as s:
        return list(s.scalars(select(Neighborhood)).all())


def all_facilities() -> list[Facility]:
    with SessionLocal() as s:
        return list(s.scalars(select(Facility)).all())


def all_existing_roads() -> list[ExistingRoad]:
    with SessionLocal() as s:
        return list(s.scalars(select(ExistingRoad)).all())


def all_potential_roads() -> list[PotentialRoad]:
    with SessionLocal() as s:
        return list(s.scalars(select(PotentialRoad)).all())


def all_traffic_flow() -> list[TrafficFlow]:
    with SessionLocal() as s:
        return list(s.scalars(select(TrafficFlow)).all())


def all_transit_demand() -> list[TransitDemand]:
    with SessionLocal() as s:
        return list(s.scalars(select(TransitDemand)).all())


def node_lookup() -> dict[str, dict]:
    """Unified id -> {name, x, y, type, kind, population?} map for neighborhoods + facilities."""
    out: dict[str, dict] = {}
    for n in all_neighborhoods():
        out[n.id] = {
            "id": n.id,
            "name": n.name,
            "x": n.x,
            "y": n.y,
            "type": n.type,
            "kind": "neighborhood",
            "population": n.population,
        }
    for f in all_facilities():
        out[f.id] = {
            "id": f.id,
            "name": f.name,
            "x": f.x,
            "y": f.y,
            "type": f.type,
            "kind": "facility",
            "population": None,
        }
    return out
