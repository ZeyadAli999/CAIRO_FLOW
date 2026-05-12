"""Graph tests: build from DB, verify node/edge counts and connectivity."""
from __future__ import annotations

import importlib

import networkx as nx
import pytest


@pytest.fixture(scope="module")
def graph(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-graph")
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
    return builder.build_graph(), builder


def test_node_count(graph):
    g, _ = graph
    # 15 neighborhoods + 10 facilities = 25 nodes total
    assert g.number_of_nodes() == 25


def test_edge_count(graph):
    g, _ = graph
    # existing_roads.csv has 28 rows but two of them describe the same
    # undirected road (7-15 appears as both "7,15,..." on row 15 and
    # "15,7,..." on row 24, with identical distance/capacity/condition).
    # The builder correctly dedupes these into a single edge, so the
    # graph holds 27 unique undirected edges, not 28. The DB-level test
    # `test_existing_roads_loaded` still asserts the full 28 rows were
    # ingested — this is a graph-shape assertion only.
    assert g.number_of_edges() == 27


def test_node_attributes(graph):
    g, _ = graph
    for nid in ("1", "F1"):
        data = g.nodes[nid]
        assert "name" in data
        assert "x" in data and "y" in data
        assert "kind" in data


def test_edge_attributes(graph):
    g, _ = graph
    # Pick a known edge from the dataset: (1, 3) = Maadi <-> Downtown.
    assert g.has_edge("1", "3")
    edge = g["1"]["3"]
    assert edge["distance_km"] == pytest.approx(8.5)
    assert edge["capacity"] == 3000
    assert edge["condition"] == 7
    assert edge["traffic"] is not None
    assert edge["traffic"]["morning_peak"] == 2800


def test_connectivity_report(graph):
    g, builder = graph
    summary = builder.graph_summary(g)
    components = list(nx.connected_components(g))
    assert summary["nodes"] == g.number_of_nodes()
    assert summary["edges"] == g.number_of_edges()
    # Print isolated components for visibility — not all nodes are
    # required to be connected (Phase 1 is exploratory).
    if summary["components"] > 1:
        print("Isolated components:", summary["isolated"])
    # The largest component should hold the bulk of the graph. Six
    # facilities (F3 Cairo University, F4 Al-Azhar, F5 Egyptian Museum,
    # F6 Cairo Stadium, F9 Qasr El Aini Hospital, F10 Maadi Military
    # Hospital) have no rows in existing_roads.csv and are therefore
    # isolated singletons in Phase 1. Phase 2's MST / road-expansion
    # mode will connect them via potential_roads.csv, so the threshold
    # only needs to cover the 19 connected nodes (19/25 = 0.76).
    largest = max(len(c) for c in components)
    assert largest >= g.number_of_nodes() * 0.76, (
        f"Largest component ({largest}) is unexpectedly small; check road data."
    )
