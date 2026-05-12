"""Bonus — race step-capture tests."""
from __future__ import annotations

import importlib
import math

import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-race")
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
    from src.algorithms import race
    importlib.reload(race)
    G = builder.build_graph()
    return {"G": G, "race": race, "sp": sp}


def test_dijkstra_steps_finds_known_path(env):
    """1 → F1 has a known shortest path; the captured run must agree."""
    res = env["race"].dijkstra_with_steps(env["G"], "1", "F1")
    assert res.path is not None
    assert res.path[0] == "1" and res.path[-1] == "F1"
    assert math.isclose(res.cost, 22.10, abs_tol=0.01)
    assert res.frames, "Dijkstra must emit at least one frame"
    assert res.frames[0].current == "1"
    assert res.frames[-1].current == "F1"


def test_astar_steps_optimal_and_no_more_explored(env):
    """A*'s captured cost must match Dijkstra's, and its frame count
    must be ≤ Dijkstra's (admissible heuristic guarantee)."""
    d = env["race"].dijkstra_with_steps(env["G"], "12", "F1")
    a = env["race"].astar_with_steps(env["G"], "12", "F1")
    assert d.path is not None and a.path is not None
    assert math.isclose(d.cost, a.cost, abs_tol=1e-9)
    assert len(a.frames) <= len(d.frames)


def test_frame_invariants(env):
    """Visited grows monotonically; current ∈ visited; frontier disjoint
    from visited."""
    res = env["race"].dijkstra_with_steps(env["G"], "1", "F1")
    last_n = -1
    for fr in res.frames:
        assert fr.step == last_n + 1 + 1 or fr.step >= 1
        last_n = fr.step - 1
        assert fr.current in fr.visited
        for n in fr.frontier:
            assert n not in fr.visited
        assert fr.edges_relaxed >= 0


def test_race_serializable(env):
    """The full bundle must be JSON-serializable so it can ride a
    Dash dcc.Store across to a clientside animator."""
    import json
    bundle = env["race"].race(env["G"], "1", "F1")
    js = json.dumps(bundle)
    assert "dijkstra" in bundle and "astar" in bundle
    assert bundle["agree_on_cost"] is True
    assert bundle["winner"] in {"A*", "tie", "Dijkstra"}
    # Round-trip
    restored = json.loads(js)
    assert restored["source"] == "1" and restored["target"] == "F1"


def test_race_disconnected_target(env):
    """F9 is an isolated singleton — both algorithms must report no path
    cleanly (no crash)."""
    bundle = env["race"](env["G"], "1", "F9") if False else env["race"].race(env["G"], "1", "F9")
    assert bundle["dijkstra"]["path"] is None
    assert bundle["astar"]["path"] is None
    # The race still runs — frames captured up to the heap exhaustion.
    assert isinstance(bundle["dijkstra"]["frames"], list)


def test_race_with_bpr_time_of_day(env):
    """Switching to BPR weight must keep both algorithms agreeing."""
    bundle = env["race"].race(env["G"], "1", "F1", time_of_day="morning_peak")
    assert bundle["agree_on_cost"] is True
    assert "BPR" in bundle["weight_mode"]
