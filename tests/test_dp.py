"""Phase 4 — DP module tests."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-dp")
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
    from src.algorithms import shortest_path as sp
    importlib.reload(sp)
    from src.algorithms import dp
    importlib.reload(dp)
    G = builder.build_graph()
    return {"G": G, "dp": dp, "models": models}


# ---------------------------------------------------------------------------
# transit_scheduling
# ---------------------------------------------------------------------------

def test_transit_scheduling_respects_total_buses(env):
    routes = [
        {"route_id": "B1", "daily_passengers": 35000},
        {"route_id": "B2", "daily_passengers": 42000},
        {"route_id": "B3", "daily_passengers": 28000},
    ]
    res = env["dp"].transit_scheduling(routes, total_buses=80)
    total = sum(res["allocations"].values())
    assert total <= 80
    assert res["total_benefit"] > 0


def test_transit_scheduling_beats_or_ties_equal_split(env):
    routes = [
        {"route_id": "B1", "daily_passengers": 35000},
        {"route_id": "B2", "daily_passengers": 42000},
        {"route_id": "B3", "daily_passengers": 28000},
    ]
    total = 90
    res = env["dp"].transit_scheduling(routes, total_buses=total)
    # Equal-split benchmark
    from src.algorithms.dp import _bus_benefit  # type: ignore
    even = total // 3
    even_benefit = sum(_bus_benefit(r["daily_passengers"], even) for r in routes)
    assert res["total_benefit"] >= even_benefit - 1e-6


def test_metro_scheduling_non_negative(env):
    lines = [
        {"line_id": "M1", "daily_passengers": 1500000},
        {"line_id": "M2", "daily_passengers": 1200000},
        {"line_id": "M3", "daily_passengers": 800000},
    ]
    res = env["dp"].metro_scheduling(lines, total_train_hours=120)
    assert all(v >= 0 for v in res["allocations"].values())
    assert sum(res["allocations"].values()) <= 120


# ---------------------------------------------------------------------------
# road_maintenance_knapsack
# ---------------------------------------------------------------------------

def _load_road_candidates(env):
    from src.db.models import (ExistingRoad, Neighborhood)
    models = env["models"]
    with models.SessionLocal() as s:
        pop = {n.id: n.population for n in s.query(Neighborhood).all()}
        out = []
        for er in s.query(ExistingRoad).all():
            out.append({
                "from": er.from_id, "to": er.to_id,
                "distance_km": er.distance_km,
                "condition": er.condition,
                "pop_a": pop.get(er.from_id, 0),
                "pop_b": pop.get(er.to_id, 0),
            })
    return out


def test_knapsack_respects_budget(env):
    roads = _load_road_candidates(env)
    for budget in (200.0, 500.0, 1000.0):
        r = env["dp"].road_maintenance_knapsack(roads, budget)
        assert r["total_cost"] <= budget + 0.01


def test_knapsack_finds_something_at_500m(env):
    roads = _load_road_candidates(env)
    r = env["dp"].road_maintenance_knapsack(roads, 500.0)
    assert len(r["selected_roads"]) >= 1


def test_knapsack_zero_budget_returns_nothing(env):
    roads = _load_road_candidates(env)
    r = env["dp"].road_maintenance_knapsack(roads, 0.0)
    assert r["selected_roads"] == []
    assert r["total_cost"] == 0.0


# ---------------------------------------------------------------------------
# memoized_route_query
# ---------------------------------------------------------------------------

def test_memoization_cache_hit_is_faster(env):
    dp = env["dp"]
    G = env["G"]
    dp.cache_clear()
    miss = dp.memoized_route_query(G, "1", "F1", "morning_peak")
    hit = dp.memoized_route_query(G, "1", "F1", "morning_peak")
    assert hit["trace"].parameters["cache_hit"] is True
    assert miss["trace"].parameters["cache_hit"] is False
    # Hit must be at least 5x faster than miss (typically 100x+).
    assert hit["trace"].runtime_ms <= max(0.0, miss["trace"].runtime_ms / 5.0) + 0.001


def test_memoization_cache_clear_resets_stats(env):
    dp = env["dp"]
    G = env["G"]
    dp.cache_clear()
    dp.memoized_route_query(G, "1", "F1", "morning_peak")
    dp.memoized_route_query(G, "1", "F1", "morning_peak")
    stats = dp.cache_stats()
    assert stats["hits"] == 1 and stats["misses"] == 1
    dp.cache_clear()
    assert dp.cache_stats() == {"size": 0, "hits": 0, "misses": 0}


# ---------------------------------------------------------------------------
# Trace contracts
# ---------------------------------------------------------------------------

def test_dp_traces_populated(env):
    dp = env["dp"]
    res = dp.transit_scheduling(
        [{"route_id": "B1", "daily_passengers": 1000}], total_buses=10,
    )
    t = res["trace"]
    assert t.name and t.complexity_time and t.formula and t.code_snippet
    # Knapsack
    res2 = dp.road_maintenance_knapsack(
        [{"from": "1", "to": "3", "distance_km": 8.5,
          "condition": 5, "pop_a": 1, "pop_b": 1}], 100.0,
    )
    t2 = res2["trace"]
    assert "Knapsack" in t2.name
    assert t2.complexity_time and t2.formula
