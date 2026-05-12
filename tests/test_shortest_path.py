"""Phase 3 tests — Dijkstra, A*, BPR variants, nearest facility,
alternative routes. Mirrors the DB fixture pattern from test_mst.py.
"""
from __future__ import annotations

import importlib
import math

import networkx as nx
import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-sp")
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

    G = builder.build_graph()
    return {"G": G, "sp": sp, "builder": builder}


# ---------------------------------------------------------------------------
# Dijkstra
# ---------------------------------------------------------------------------

def test_dijkstra_finds_shortest_path(env):
    """1 → 3 should be the direct edge (8.5 km)."""
    G, sp = env["G"], env["sp"]
    path, cost, trace = sp.dijkstra(G, "1", "3", weight="distance_km")
    assert path == ["1", "3"]
    assert cost == pytest.approx(8.5)
    assert trace.runtime_ms > 0
    assert trace.edges_relaxed > 0
    assert "1" in trace.nodes_explored


def test_dijkstra_multi_hop(env):
    """1 → F1 has no direct edge; route must go via at least one hop."""
    G, sp = env["G"], env["sp"]
    path, cost, _ = sp.dijkstra(G, "1", "F1", weight="distance_km")
    assert path is not None
    assert path[0] == "1"
    assert path[-1] == "F1"
    assert len(path) >= 3


def test_dijkstra_disconnected_returns_none(env):
    """F9 (Qasr El Aini Hospital) is an isolated singleton — no path."""
    G, sp = env["G"], env["sp"]
    path, cost, trace = sp.dijkstra(G, "1", "F9", weight="distance_km")
    assert path is None
    assert cost == math.inf
    assert trace.parameters.get("result") == "no_path"


# ---------------------------------------------------------------------------
# A*
# ---------------------------------------------------------------------------

def test_astar_matches_dijkstra_optimal_cost(env):
    """A* with Euclidean-km heuristic must produce the same total cost
    as Dijkstra (the heuristic is admissible)."""
    G, sp = env["G"], env["sp"]
    src, dst = "1", "F1"
    _, d_cost, _ = sp.dijkstra(G, src, dst, weight="distance_km")
    _, a_cost, _ = sp.astar(G, src, dst, weight="distance_km")
    assert a_cost == pytest.approx(d_cost, rel=1e-9)


def test_astar_explores_no_more_than_dijkstra(env):
    """For an admissible heuristic, A* visits ≤ Dijkstra's node count."""
    G, sp = env["G"], env["sp"]
    src, dst = "12", "F1"  # diagonally across the city — gives the heuristic something to do
    _, _, d_trace = sp.dijkstra(G, src, dst, weight="distance_km")
    _, _, a_trace = sp.astar(G, src, dst, weight="distance_km")
    assert len(a_trace.nodes_explored) <= len(d_trace.nodes_explored)


def test_astar_disconnected_returns_none(env):
    G, sp = env["G"], env["sp"]
    path, _, _ = sp.astar(G, "1", "F10", weight="distance_km")
    assert path is None


# ---------------------------------------------------------------------------
# Time-dependent BPR
# ---------------------------------------------------------------------------

def test_bpr_morning_slower_than_night(env):
    """Edge 4→2 has very high morning_peak flow (3600 vs night 750)
    and capacity 3800. Travel time at morning_peak must exceed night."""
    G, sp = env["G"], env["sp"]
    data = G["4"]["2"]
    morning = sp.edge_travel_time(data, "morning_peak")
    night = sp.edge_travel_time(data, "night")
    assert morning > night, f"Expected morning > night, got {morning} vs {night}"


def test_bpr_is_monotonic_in_flow(env):
    """BPR is monotonically increasing in v/c — bumping flow up never
    makes a link cheaper."""
    G, sp = env["G"], env["sp"]
    data = G["4"]["2"]
    night = sp.edge_travel_time(data, "night")
    afternoon = sp.edge_travel_time(data, "afternoon")
    morning = sp.edge_travel_time(data, "morning_peak")
    assert night <= afternoon <= morning


def test_bpr_high_congestion_inflates_travel_time(env):
    """At v/c = 1.5 (well above capacity), BPR adds at least 50% on
    top of free-flow time. Documented deviation: with α=0.15, β=4 the
    crossover happens around v/c ≈ 1.4 — `> 1.5 × t_free` requires
    significant over-capacity, NOT v/c > 0.85 as the spec hinted."""
    sp = env["sp"]
    distance, capacity = 10.0, 1000.0
    t_free = distance / sp.FREE_FLOW_KMH
    high = sp.bpr_travel_time_hours(distance, flow=1500, capacity=capacity)  # v/c=1.5
    assert high > 1.5 * t_free


def test_dijkstra_time_dependent_returns_hours(env):
    G, sp = env["G"], env["sp"]
    path, hours, trace = sp.dijkstra_time_dependent(G, "1", "F1", "morning_peak")
    assert path is not None
    assert hours > 0
    assert "BPR" in (trace.formula or "")


# ---------------------------------------------------------------------------
# A* emergency
# ---------------------------------------------------------------------------

def test_astar_emergency_admissible_and_finds_path(env):
    G, sp = env["G"], env["sp"]
    path, eta_h, trace = sp.astar_emergency(G, "1", "F1", "morning_peak")
    assert path is not None
    assert eta_h > 0
    # Should explore no more than Dijkstra would.
    _, _, d_trace = sp.dijkstra_time_dependent(G, "1", "F1", "morning_peak")
    assert len(trace.nodes_explored) <= len(d_trace.nodes_explored)


# ---------------------------------------------------------------------------
# find_nearest_facility
# ---------------------------------------------------------------------------

def test_nearest_facility_connected_type(env):
    """Source=11 (Shubra) → Transit Hub: F2 is the only facility of
    that type and 11→F2 is a direct edge, so F2 wins."""
    G, sp = env["G"], env["sp"]
    fid, path, eta, trace = sp.find_nearest_facility(
        G, "11", "Transit Hub", time_of_day="morning_peak"
    )
    assert fid == "F2"
    assert path == ["11", "F2"]
    assert eta > 0
    assert "Transit Hub" in trace.name


def test_nearest_facility_isolated_type_handled(env):
    """All Medical facilities (F9, F10) are isolated singletons in the
    Phase 1 dataset — no path exists. The function must return cleanly
    with `(None, None, inf)` rather than raising."""
    G, sp = env["G"], env["sp"]
    fid, path, eta, trace = sp.find_nearest_facility(
        G, "11", "Medical", time_of_day="morning_peak"
    )
    assert fid is None
    assert path is None
    assert eta == math.inf
    # Trace still records the attempt:
    assert "F9" in trace.parameters["candidates"]
    assert "F10" in trace.parameters["candidates"]


# ---------------------------------------------------------------------------
# find_alternative_routes
# ---------------------------------------------------------------------------

def test_alternative_routes_returns_distinct_paths(env):
    """For 1 → 2 the network has multiple plausible paths (via 3, via 8/10/3,
    etc.). Top-3 must yield distinct node sequences."""
    G, sp = env["G"], env["sp"]
    routes, trace = sp.find_alternative_routes(
        G, "1", "2", "morning_peak", k=3
    )
    assert 1 <= len(routes) <= 3
    keys = {tuple(r["path"]) for r in routes}
    assert len(keys) == len(routes), "Returned routes are not all distinct"
    for r in routes:
        assert r["travel_time_min"] > 0
        assert 0 <= r["max_congestion"] <= 5  # sanity bound


def test_alternative_routes_excluded_edges_respected(env):
    """If we exclude the only direct edge (1, 3), the first route must
    detour. Either no path is found, or every returned path avoids the
    excluded edge."""
    G, sp = env["G"], env["sp"]
    excluded = [("1", "3")]
    routes, _ = sp.find_alternative_routes(
        G, "1", "3", "morning_peak", k=3, excluded_edges=excluded,
    )
    excl_set = {frozenset(e) for e in excluded}
    for r in routes:
        for u, v in zip(r["path"][:-1], r["path"][1:]):
            assert frozenset((u, v)) not in excl_set, (
                f"Route {r['path']} traverses excluded edge ({u},{v})"
            )


# ---------------------------------------------------------------------------
# Trace contract
# ---------------------------------------------------------------------------

def test_dijkstra_trace_fields_populated(env):
    G, sp = env["G"], env["sp"]
    _, _, trace = sp.dijkstra(G, "1", "F1", weight="distance_km")
    assert trace.name == "Dijkstra's Algorithm"
    assert trace.complexity_time == "O((V+E) log V)"
    assert trace.complexity_space == "O(V)"
    assert trace.runtime_ms > 0
    assert trace.edges_relaxed > 0
    assert trace.parameters["weight_mode"] == "distance_km"
    assert "def dijkstra" in trace.code_snippet
    assert trace.formula
    assert trace.explanation


def test_astar_trace_fields_populated(env):
    G, sp = env["G"], env["sp"]
    _, _, trace = sp.astar(G, "1", "F1", weight="distance_km")
    assert trace.name == "A* Search"
    assert trace.parameters["heuristic"] == "Euclidean km (admissible)"
    assert "def astar" in trace.code_snippet


def test_time_dependent_trace_includes_bpr_formula(env):
    G, sp = env["G"], env["sp"]
    _, _, trace = sp.dijkstra_time_dependent(G, "1", "F1", "morning_peak")
    assert "BPR" in trace.name or "BPR" in (trace.formula or "")
    assert trace.parameters["alpha"] == sp.BPR_ALPHA
    assert trace.parameters["beta"] == sp.BPR_BETA
    assert trace.parameters["free_flow_kmh"] == sp.FREE_FLOW_KMH
