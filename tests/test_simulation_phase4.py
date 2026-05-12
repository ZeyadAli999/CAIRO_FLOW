"""Phase 4 simulation scenario tests."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def sim_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-sim4")
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
    from src.algorithms import dp, greedy, multimodal
    importlib.reload(dp)
    importlib.reload(greedy)
    importlib.reload(multimodal)
    from src.simulation import framework
    importlib.reload(framework)

    G = builder.build_graph()
    sim = framework.TransportSimulator(G)
    return {"G": G, "sim": sim, "framework": framework}


def test_transit_optimization_runs(sim_env):
    res = sim_env["sim"].run_scenario("transit_optimization", total_buses=180)
    d = res.to_dict()
    assert d["scenario"] == "transit_optimization"
    assert d["summary"]["dp_benefit"] >= d["summary"]["even_split_benefit"] - 1e-6


def test_maintenance_budget_returns_three(sim_env):
    res = sim_env["sim"].run_scenario("maintenance_budget")
    d = res.to_dict()
    comps = d["detail"]["comparisons"]
    assert len(comps) == 3
    # Increasing budgets → non-decreasing total value (monotone)
    values = [c["total_value"] for c in comps]
    assert values[0] <= values[1] <= values[2] + 1e-6


def test_signal_audit_returns_audit_dict(sim_env):
    res = sim_env["sim"].run_scenario("signal_audit", time_of_day="morning_peak")
    d = res.to_dict()
    assert "intersections_audited" in d["summary"]
    assert d["summary"]["intersections_audited"] >= 1


def test_multimodal_demand_returns_ranking(sim_env):
    res = sim_env["sim"].run_scenario("multimodal_demand")
    d = res.to_dict()
    assert d["summary"]["mm_nodes"] == 25
    assert "ranking" in d["detail"]
    # We can't pin a specific top hub on the data, but ranking should be a list.
    assert isinstance(d["detail"]["ranking"], list)


def test_unknown_phase4_scenario_raises(sim_env):
    with pytest.raises(ValueError):
        sim_env["sim"].run_scenario("phase42_invented")
