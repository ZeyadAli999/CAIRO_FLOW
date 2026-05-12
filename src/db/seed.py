"""One-shot CSV seeding for the SQLite store.

`ensure_seeded()` is idempotent: it creates the schema, and only loads CSV
data if the static tables are empty.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from src.config import CSV_FILES, RAW_DIR
from src.db.models import (
    BusRoute,
    ExistingRoad,
    Facility,
    MetroLine,
    Neighborhood,
    PotentialRoad,
    SessionLocal,
    TrafficFlow,
    TransitDemand,
    init_schema,
)


def _read_csv(name: str) -> pd.DataFrame:
    path = RAW_DIR / CSV_FILES[name]
    return pd.read_csv(path)


def _str_id(df: pd.DataFrame, *cols: str) -> pd.DataFrame:
    for c in cols:
        df[c] = df[c].astype(str)
    return df


def _table_empty(session, model) -> bool:
    return session.scalar(select(model).limit(1)) is None


def seed_all(force: bool = False) -> dict[str, int]:
    """Load every CSV into the database.

    If `force` is False, only loads tables that are currently empty.
    Returns the number of rows inserted per table.
    """
    init_schema()
    inserted: dict[str, int] = {}

    with SessionLocal() as session:
        # --- Neighborhoods ---
        if force or _table_empty(session, Neighborhood):
            df = _str_id(_read_csv("neighborhoods"), "id")
            session.bulk_save_objects([
                Neighborhood(
                    id=r.id, name=r.name, population=int(r.population),
                    type=r.type, x=float(r.x), y=float(r.y),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["neighborhoods"] = len(df)

        # --- Facilities ---
        if force or _table_empty(session, Facility):
            df = _str_id(_read_csv("facilities"), "id")
            session.bulk_save_objects([
                Facility(id=r.id, name=r.name, type=r.type, x=float(r.x), y=float(r.y))
                for r in df.itertuples(index=False)
            ])
            inserted["facilities"] = len(df)

        # --- Existing roads ---
        if force or _table_empty(session, ExistingRoad):
            df = _str_id(_read_csv("existing_roads"), "from_id", "to_id")
            session.bulk_save_objects([
                ExistingRoad(
                    from_id=r.from_id, to_id=r.to_id,
                    distance_km=float(r.distance_km),
                    capacity=int(r.capacity),
                    condition=int(r.condition),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["existing_roads"] = len(df)

        # --- Potential roads ---
        if force or _table_empty(session, PotentialRoad):
            df = _str_id(_read_csv("potential_roads"), "from_id", "to_id")
            session.bulk_save_objects([
                PotentialRoad(
                    from_id=r.from_id, to_id=r.to_id,
                    distance_km=float(r.distance_km),
                    capacity=int(r.capacity),
                    cost_million_egp=float(r.cost_million_egp),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["potential_roads"] = len(df)

        # --- Traffic flow ---
        if force or _table_empty(session, TrafficFlow):
            df = _str_id(_read_csv("traffic_flow"), "from_id", "to_id")
            session.bulk_save_objects([
                TrafficFlow(
                    from_id=r.from_id, to_id=r.to_id,
                    morning_peak=int(r.morning_peak),
                    afternoon=int(r.afternoon),
                    evening_peak=int(r.evening_peak),
                    night=int(r.night),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["traffic_flow"] = len(df)

        # --- Metro lines ---
        if force or _table_empty(session, MetroLine):
            df = _read_csv("metro_lines")
            session.bulk_save_objects([
                MetroLine(
                    line_id=r.line_id, name=r.name,
                    stations=r.stations,
                    daily_passengers=int(r.daily_passengers),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["metro_lines"] = len(df)

        # --- Bus routes ---
        if force or _table_empty(session, BusRoute):
            df = _read_csv("bus_routes")
            session.bulk_save_objects([
                BusRoute(
                    route_id=r.route_id, stops=r.stops,
                    buses_assigned=int(r.buses_assigned),
                    daily_passengers=int(r.daily_passengers),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["bus_routes"] = len(df)

        # --- Transit demand ---
        if force or _table_empty(session, TransitDemand):
            df = _str_id(_read_csv("transit_demand"), "from_id", "to_id")
            session.bulk_save_objects([
                TransitDemand(
                    from_id=r.from_id, to_id=r.to_id,
                    daily_passengers=int(r.daily_passengers),
                )
                for r in df.itertuples(index=False)
            ])
            inserted["transit_demand"] = len(df)

        session.commit()

    return inserted


def ensure_seeded() -> dict[str, int]:
    """Public entrypoint used by `app.py` and tests."""
    return seed_all(force=False)
