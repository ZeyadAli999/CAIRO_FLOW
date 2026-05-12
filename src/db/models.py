"""SQLAlchemy 2.x declarative models for CairoFlow.

Node identifiers are stored as strings throughout so that neighborhood IDs
("1", "2", ...) and facility IDs ("F1", "F2", ...) share a unified namespace.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.config import DB_URL


class Base(DeclarativeBase):
    pass


# ---------- Static (seeded from CSV) ----------

class Neighborhood(Base):
    __tablename__ = "neighborhoods"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    population: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)


class Facility(Base):
    __tablename__ = "facilities"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)


class ExistingRoad(Base):
    __tablename__ = "existing_roads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String, nullable=False)
    to_id: Mapped[str] = mapped_column(String, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    condition: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_existing_roads_endpoints", "from_id", "to_id"),
    )


class PotentialRoad(Base):
    __tablename__ = "potential_roads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String, nullable=False)
    to_id: Mapped[str] = mapped_column(String, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_million_egp: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_potential_roads_endpoints", "from_id", "to_id"),
    )


class TrafficFlow(Base):
    __tablename__ = "traffic_flow"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String, nullable=False)
    to_id: Mapped[str] = mapped_column(String, nullable=False)
    morning_peak: Mapped[int] = mapped_column(Integer, nullable=False)
    afternoon: Mapped[int] = mapped_column(Integer, nullable=False)
    evening_peak: Mapped[int] = mapped_column(Integer, nullable=False)
    night: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_traffic_flow_endpoints", "from_id", "to_id"),
    )


class MetroLine(Base):
    __tablename__ = "metro_lines"
    line_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    stations: Mapped[str] = mapped_column(String, nullable=False)  # comma-separated node IDs
    daily_passengers: Mapped[int] = mapped_column(Integer, nullable=False)


class BusRoute(Base):
    __tablename__ = "bus_routes"
    route_id: Mapped[str] = mapped_column(String, primary_key=True)
    stops: Mapped[str] = mapped_column(String, nullable=False)  # comma-separated node IDs
    buses_assigned: Mapped[int] = mapped_column(Integer, nullable=False)
    daily_passengers: Mapped[int] = mapped_column(Integer, nullable=False)


class TransitDemand(Base):
    __tablename__ = "transit_demand"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_id: Mapped[str] = mapped_column(String, nullable=False)
    to_id: Mapped[str] = mapped_column(String, nullable=False)
    daily_passengers: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_transit_demand_endpoints", "from_id", "to_id"),
    )


# ---------- Live (populated as the app runs) ----------

class RouteQuery(Base):
    __tablename__ = "route_queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    from_id: Mapped[str] = mapped_column(String, nullable=False)
    to_id: Mapped[str] = mapped_column(String, nullable=False)
    time_of_day: Mapped[str] = mapped_column(String, nullable=False)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)
    distance_km: Mapped[float] = mapped_column(Float, nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    runtime_ms: Mapped[float] = mapped_column(Float, nullable=False)


class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    closed_roads: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    results_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string


class EmergencyLog(Base):
    __tablename__ = "emergency_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    incident_location: Mapped[str] = mapped_column(String, nullable=False)
    dispatched_to: Mapped[str] = mapped_column(String, nullable=False)
    eta_minutes: Mapped[float] = mapped_column(Float, nullable=False)
    algorithm: Mapped[str] = mapped_column(String, nullable=False)


class ResultCache(Base):
    __tablename__ = "result_cache"
    cache_key: Mapped[str] = mapped_column(String, primary_key=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


# ---------- Engine / session factory ----------

engine = create_engine(DB_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_schema() -> None:
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(engine)
