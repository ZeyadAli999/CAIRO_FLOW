"""Phase 4 — greedy module tests."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-greedy")
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
    from src.algorithms import greedy
    importlib.reload(greedy)
    from src.algorithms import shortest_path as sp
    importlib.reload(sp)
    G = builder.build_graph()
    return {"G": G, "greedy": greedy, "sp": sp}


# ---------------------------------------------------------------------------
# traffic_signal_allocation
# ---------------------------------------------------------------------------

def test_signal_allocation_sums_to_cycle(env):
    res = env["greedy"].traffic_signal_allocation("3", env["G"], "morning_peak")
    cycle = res["total_cycle"]
    assert cycle == 120  # CYCLE_SECONDS default
    assert sum(res["allocations"].values()) == cycle


def test_signal_allocation_min_max_bounds(env):
    res = env["greedy"].traffic_signal_allocation("3", env["G"], "morning_peak")
    for sec in res["allocations"].values():
        assert 10 <= sec <= 60


def test_signal_allocation_higher_flow_gets_more_green(env):
    res = env["greedy"].traffic_signal_allocation("3", env["G"], "morning_peak")
    flows = {
        nb: (env["G"]["3"][nb].get("traffic") or {}).get("morning_peak", 0)
        for nb in res["allocations"]
    }
    # The neighbour with the most flow should get at least the median green.
    most = max(flows, key=lambda k: flows[k])
    median = sorted(res["allocations"].values())[len(res["allocations"]) // 2]
    assert res["allocations"][most] >= median


# ---------------------------------------------------------------------------
# emergency_preemption_priority
# ---------------------------------------------------------------------------

def test_preemption_returns_priority_ordered(env):
    intersections = [n for n in env["G"].nodes() if env["G"].degree(n) >= 3]
    emergencies = [
        {"id": "E1", "priority": 3, "path": ["11", "F2", "3", "5"]},
        {"id": "E2", "priority": 1, "path": ["1", "3", "9"]},
        {"id": "E3", "priority": 2, "path": ["8", "10", "3"]},
    ]
    sched = env["greedy"].emergency_preemption_priority(
        emergencies, intersections, env["G"],
    )
    # Highest-priority first
    priorities = [r["priority"] for r in sched]
    assert priorities == sorted(priorities)


# ---------------------------------------------------------------------------
# signal_audit_report
# ---------------------------------------------------------------------------

def test_audit_returns_optimal_and_suboptimal_cases(env):
    rep = env["greedy"].signal_audit_report(env["G"], "morning_peak")
    assert rep["intersections_audited"] >= 1
    assert len(rep["optimal_cases"]) >= 1
    assert len(rep["suboptimal_cases"]) >= 1


def test_audit_gini_in_unit_interval(env):
    rep = env["greedy"].signal_audit_report(env["G"], "morning_peak")
    g = rep["gini_overall"]
    assert 0.0 <= g <= 1.0
