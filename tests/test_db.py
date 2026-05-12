"""DB tests: every CSV loads, and row counts match the source files."""
from __future__ import annotations

import importlib
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def fresh_db(tmp_path_factory):
    """Reload config, models, seed against an isolated SQLite file."""
    tmp = tmp_path_factory.mktemp("cf-db")
    from src import config
    importlib.reload(config)
    config.DB_PATH = tmp / "test.db"
    config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"

    from src.db import models
    importlib.reload(models)
    from src.db import seed
    importlib.reload(seed)
    seed.ensure_seeded()
    return models


def _csv_rows(name: str) -> int:
    from src.config import RAW_DIR
    return len(pd.read_csv(Path(RAW_DIR) / name))


def test_neighborhoods_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.Neighborhood).count()
    assert count == _csv_rows("neighborhoods.csv") == 15


def test_facilities_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.Facility).count()
    assert count == _csv_rows("facilities.csv") == 10


def test_existing_roads_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.ExistingRoad).count()
    assert count == _csv_rows("existing_roads.csv") == 28


def test_potential_roads_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.PotentialRoad).count()
    assert count == _csv_rows("potential_roads.csv") == 15


def test_traffic_flow_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.TrafficFlow).count()
    assert count == _csv_rows("traffic_flow.csv") == 28


def test_metro_lines_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.MetroLine).count()
    assert count == _csv_rows("metro_lines.csv") == 3


def test_bus_routes_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.BusRoute).count()
    assert count == _csv_rows("bus_routes.csv") == 10


def test_transit_demand_loaded(fresh_db):
    with fresh_db.SessionLocal() as s:
        count = s.query(fresh_db.TransitDemand).count()
    assert count == _csv_rows("transit_demand.csv") == 17


def test_node_lookup_unifies_namespace(fresh_db):
    from src.db import queries
    importlib.reload(queries)
    nodes = queries.node_lookup()
    assert "1" in nodes
    assert "F1" in nodes
    assert nodes["1"]["kind"] == "neighborhood"
    assert nodes["F1"]["kind"] == "facility"
