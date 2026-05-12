"""MST tests: Kruskal, Prim, and the population-weighted variant.

Mirrors the DB fixture pattern from test_db.py / test_graph.py — config,
models, seed, queries, builder, and finally the algorithm module are all
reloaded so they pick up an isolated SQLite file in the test tmp dir.
"""
from __future__ import annotations

import importlib

import networkx as nx
import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-mst")
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
    from src.algorithms import mst as mst_mod
    importlib.reload(mst_mod)

    G = builder.build_mst_graph()
    return {"G": G, "mst_mod": mst_mod, "builder": builder}


# ---------------------------------------------------------------------------
# Kruskal
# ---------------------------------------------------------------------------

def test_kruskal_spans_largest_component(env):
    """Kruskal on the whole graph yields a forest. Restricted to the
    largest connected component of the source graph, that forest is a
    spanning tree (V'-1 edges, fully connected, acyclic)."""
    G = env["G"]
    mst, trace = env["mst_mod"].kruskal_mst(G, weight="cost_million_egp")

    # Forest property over all 25 nodes.
    assert nx.is_forest(mst)

    # Spanning tree property over the largest CC of the source graph.
    largest_cc = max(nx.connected_components(G), key=len)
    sub = mst.subgraph(largest_cc)
    assert nx.is_connected(sub)
    assert sub.number_of_edges() == sub.number_of_nodes() - 1


def test_kruskal_includes_all_nodes(env):
    """The MST graph carries every node from the source (even isolated)."""
    G = env["G"]
    mst, _ = env["mst_mod"].kruskal_mst(G, weight="cost_million_egp")
    assert set(mst.nodes()) == set(G.nodes())


# ---------------------------------------------------------------------------
# Prim
# ---------------------------------------------------------------------------

def test_prim_spans_largest_component(env):
    G = env["G"]
    mst, trace = env["mst_mod"].prim_mst(
        G, weight="cost_million_egp", start_node="3"
    )
    assert nx.is_forest(mst)
    largest_cc = max(nx.connected_components(G), key=len)
    sub = mst.subgraph(largest_cc)
    assert nx.is_connected(sub)
    assert sub.number_of_edges() == sub.number_of_nodes() - 1


# ---------------------------------------------------------------------------
# Equivalence
# ---------------------------------------------------------------------------

def test_kruskal_and_prim_agree_on_total_weight(env):
    """When edge weights are distinct enough, Kruskal and Prim produce
    the same total weight. With cost_million_egp many existing roads tie
    at 0 — ties are valid alternates, so the totals still match."""
    G = env["G"]
    mst_k, _ = env["mst_mod"].kruskal_mst(G, weight="cost_million_egp")
    mst_p, _ = env["mst_mod"].prim_mst(G, weight="cost_million_egp", start_node="3")

    def total(g, attr):
        return round(sum(d.get(attr, 0) or 0 for _, _, d in g.edges(data=True)), 4)

    assert total(mst_k, "cost_million_egp") == total(mst_p, "cost_million_egp")
    # Edge counts also match (same span over the same component).
    assert mst_k.number_of_edges() == mst_p.number_of_edges()


# ---------------------------------------------------------------------------
# must_include_nodes
# ---------------------------------------------------------------------------

def test_must_include_connected_node_appears(env):
    """Node 13 (New Administrative Capital) has edges to 4, 14, F1, etc.,
    so it must show up in the MST when listed as must-include."""
    G = env["G"]
    mst, _ = env["mst_mod"].kruskal_mst(
        G, weight="cost_million_egp", must_include_nodes=["13"]
    )
    assert "13" in mst.nodes()
    assert mst.degree("13") >= 1, "must_include node 13 should have at least one edge"


def test_must_include_isolated_facilities_handled_gracefully(env):
    """F9 and F10 have NO rows in either road CSV so no edge can be
    pre-included. The algorithm must still return cleanly with both as
    isolated singleton nodes (degree 0)."""
    G = env["G"]
    mst, trace = env["mst_mod"].kruskal_mst(
        G, weight="cost_million_egp", must_include_nodes=["F9", "F10"]
    )
    assert "F9" in mst.nodes()
    assert "F10" in mst.nodes()
    assert mst.degree("F9") == 0
    assert mst.degree("F10") == 0
    # The trace records what we tried to include even when no edges exist.
    assert trace.parameters["must_include"] == ["F9", "F10"]


# ---------------------------------------------------------------------------
# AlgorithmTrace contract
# ---------------------------------------------------------------------------

def test_kruskal_trace_fields(env):
    G = env["G"]
    _, trace = env["mst_mod"].kruskal_mst(G, weight="cost_million_egp")
    assert trace.name == "Kruskal's Algorithm"
    assert trace.complexity_time == "O(E log E)"
    assert trace.complexity_space == "O(V)"
    assert trace.runtime_ms > 0
    assert trace.edges_relaxed > 0
    assert len(trace.nodes_explored) > 0
    assert trace.parameters["algorithm"] == "kruskal"
    assert trace.parameters["weight"] == "cost_million_egp"
    assert "total_cost_million_egp" in trace.parameters
    assert "data_structure" in trace.parameters
    assert trace.formula
    assert trace.explanation
    assert "def kruskal_mst" in trace.code_snippet


def test_prim_trace_fields(env):
    G = env["G"]
    _, trace = env["mst_mod"].prim_mst(G, weight="cost_million_egp")
    assert trace.name == "Prim's Algorithm"
    assert trace.complexity_time == "O((V+E) log V)"
    assert trace.complexity_space == "O(V)"
    assert trace.runtime_ms > 0
    assert trace.parameters["algorithm"] == "prim"
    assert trace.parameters["start_node"] == "3"
    assert "def prim_mst" in trace.code_snippet


# ---------------------------------------------------------------------------
# Population-weighted variant
# ---------------------------------------------------------------------------

def test_population_weighted_runs_and_spans(env):
    G = env["G"]
    mst, trace = env["mst_mod"].population_weighted_mst(G)
    assert "Population-Weighted" in trace.name
    assert trace.parameters["weight"] == "weighted_cost"
    assert trace.parameters["facility_default_pop"] == 50_000
    # Same span guarantee as plain Kruskal.
    largest_cc = max(nx.connected_components(G), key=len)
    sub = mst.subgraph(largest_cc)
    assert nx.is_connected(sub)
    assert sub.number_of_edges() == sub.number_of_nodes() - 1


# ---------------------------------------------------------------------------
# Stats helper
# ---------------------------------------------------------------------------

def test_mst_stats_reports_isolated_facilities(env):
    G = env["G"]
    mst, _ = env["mst_mod"].kruskal_mst(G, weight="cost_million_egp")
    stats = env["mst_mod"].mst_stats(mst, G)
    isolated = set(stats["isolated_before"])
    assert {"F3", "F4", "F5", "F6", "F9", "F10"}.issubset(isolated)
    # The MST covers the largest CC fully.
    assert stats["all_connected_after"] is True
    assert stats["covered_nodes"] == 19
    assert stats["total_nodes"] == 25


# ---------------------------------------------------------------------------
# Union-Find sanity
# ---------------------------------------------------------------------------

def test_union_find_basic(env):
    UF = env["mst_mod"].UnionFind
    uf = UF([1, 2, 3, 4, 5])
    assert uf.find(1) == 1
    assert uf.union(1, 2) is True
    assert uf.find(1) == uf.find(2)
    assert uf.union(1, 2) is False  # already connected
    uf.union(3, 4)
    uf.union(2, 4)
    assert uf.find(1) == uf.find(3) == uf.find(4)
    assert uf.find(5) != uf.find(1)
