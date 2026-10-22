"""Phase 3 tests — TransportSimulator scenarios + measurement helpers."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def sim_env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-sim")
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
    from src.simulation import framework
    importlib.reload(framework)

    G = builder.build_graph()
    sim = framework.TransportSimulator(G)
    return {"G": G, "sim": sim, "framework": framework}


# ---------------------------------------------------------------------------
# run_scenario
# ---------------------------------------------------------------------------

def test_peak_rush_returns_dict(sim_env):
    sim = sim_env["sim"]
    result = sim.run_scenario("peak_rush", source="1", target="F1")
    d = result.to_dict()
    assert d["scenario"] == "peak_rush"
    assert "summary" in d
    assert "morning_peak_min" in d["summary"]
    assert "night_min" in d["summary"]
    # Detail breaks down per time-of-day.
    assert "morning_peak" in d["detail"]
    assert "night" in d["detail"]
    assert d["detail"]["morning_peak"]["found"] is True


def test_road_closure_finds_alternatives(sim_env):
    sim = sim_env["sim"]
    result = sim.run_scenario(
        "road_closure", source="1", target="2",
        closed=[("1", "3")], time_of_day="morning_peak", k=3,
    )
    d = result.to_dict()
    assert d["scenario"] == "road_closure"
    assert d["summary"]["alternatives_found"] >= 1
    # Every returned alternative must avoid the closed edge.
    for alt in d["detail"]["alternatives"]:
        for u, v in zip(alt["path"][:-1], alt["path"][1:]):
            assert {u, v} != {"1", "3"}


def test_emergency_dispatch_compares_algorithms(sim_env):
    """Emergency dispatch from Shubra (11) to a connected facility type
    so that both A* and Dijkstra actually find a path. (Medical
    facilities are isolated in the Phase 1 dataset — see docs/history/PHASE3_NOTES.md.)"""
    sim = sim_env["sim"]
    result = sim.run_scenario(
        "emergency_dispatch", source="11",
        facility_type="Transit Hub", time_of_day="morning_peak",
    )
    d = result.to_dict()
    assert d["summary"]["selected_facility"] == "F2"
    assert d["summary"]["eta_minutes"] is not None
    assert d["summary"]["eta_minutes"] > 0
    # A* should never explore more nodes than Dijkstra here.
    assert d["summary"]["astar_nodes"] <= d["summary"]["dijkstra_nodes"]


def test_all_pairs_baseline_runs(sim_env):
    sim = sim_env["sim"]
    result = sim.run_scenario("all_pairs_baseline", time_of_day="morning_peak")
    d = result.to_dict()
    assert d["summary"]["pairs_evaluated"] > 0
    # Connected component size 19, so reachable directed pairs = 19*18 = 342.
    assert d["summary"]["pairs_evaluated"] == 19 * 18
    assert d["summary"]["mean_travel_minutes"] > 0


def test_unknown_scenario_raises(sim_env):
    sim = sim_env["sim"]
    with pytest.raises(ValueError):
        sim.run_scenario("not_a_scenario")


# ---------------------------------------------------------------------------
# Measurement helpers
# ---------------------------------------------------------------------------

def test_measure_response_time_positive_eta(sim_env):
    sim = sim_env["sim"]
    out = sim.measure_response_time(
        "11", "Transit Hub", time_of_day="morning_peak", algorithm="astar",
    )
    assert out["selected_facility"] == "F2"
    assert out["eta_minutes"] is not None
    assert out["eta_minutes"] > 0
    assert out["nodes_explored"] > 0
    assert out["runtime_ms"] >= 0


def test_measure_response_time_dijkstra_path(sim_env):
    sim = sim_env["sim"]
    out = sim.measure_response_time(
        "11", "Transit Hub", time_of_day="morning_peak", algorithm="dijkstra",
    )
    assert out["algorithm"] == "dijkstra"
    assert out["selected_facility"] == "F2"


def test_compare_algorithms_returns_three_entries(sim_env):
    sim = sim_env["sim"]
    out = sim.compare_algorithms("1", "F1", time_of_day="morning_peak")
    assert "dijkstra_distance" in out
    assert "dijkstra_time" in out
    assert "astar" in out
    assert "speedup_pct_nodes" in out
    for key in ("dijkstra_distance", "dijkstra_time", "astar"):
        assert out[key]["nodes_explored"] > 0
        assert out[key]["runtime_ms"] >= 0


def test_measure_congestion_reduction_nonneg(sim_env):
    sim = sim_env["sim"]
    out = sim.measure_congestion_reduction("1", "F1", time_of_day="morning_peak")
    assert out["peak_minutes"] is not None
    assert out["offpeak_minutes"] is not None
    assert out["reduction_pct"] >= 0.0
    assert isinstance(out["segments_peak"], list)
    assert isinstance(out["segments_off"], list)


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

def test_cli_main_callable(sim_env):
    """Exercising main() directly forces a real DB seed + scenario run.
    Good as a smoke check that the CLI wiring still imports correctly."""
    fw = sim_env["framework"]
    rc = fw.main(["--scenario", "peak_rush", "--from", "1", "--to", "F1"])
    assert rc == 0
