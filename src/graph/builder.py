"""Builds a NetworkX graph from the seeded database.

Nodes are keyed by their string ID (e.g. "1", "F1") and carry the attributes:
  name, x, y, type, kind ("neighborhood" | "facility"), population.
Edges carry: distance_km, capacity, condition, traffic (a dict with all
four time-of-day flows when available).

The graph is undirected — roads are bidirectional. If a duplicate edge is
encountered, the cheaper distance wins (this never happens with the
shipped dataset but keeps the builder safe).
"""
from __future__ import annotations

import networkx as nx

from src.db.queries import (
    all_existing_roads,
    all_facilities,
    all_neighborhoods,
    all_potential_roads,
    all_traffic_flow,
)


def build_graph() -> nx.Graph:
    g = nx.Graph()

    for n in all_neighborhoods():
        g.add_node(
            n.id,
            name=n.name, x=n.x, y=n.y, type=n.type,
            kind="neighborhood", population=n.population,
        )

    for f in all_facilities():
        g.add_node(
            f.id,
            name=f.name, x=f.x, y=f.y, type=f.type,
            kind="facility", population=None,
        )

    # Build a (from, to) -> traffic dict, normalized to undirected pairs.
    traffic_lookup: dict[tuple[str, str], dict] = {}
    for t in all_traffic_flow():
        key = tuple(sorted((t.from_id, t.to_id)))
        traffic_lookup[key] = {
            "morning_peak": t.morning_peak,
            "afternoon": t.afternoon,
            "evening_peak": t.evening_peak,
            "night": t.night,
        }

    # NOTE: existing_roads.csv contains 28 rows but row 15 ("7,15,...")
    # and row 24 ("15,7,...") describe the same undirected road with
    # identical attributes. The has_edge() check below collapses them
    # into a single edge, so the resulting graph has 27 edges — see
    # tests/test_graph.py::test_edge_count for the full explanation.
    for r in all_existing_roads():
        u, v = r.from_id, r.to_id
        key = tuple(sorted((u, v)))
        traffic = traffic_lookup.get(key)
        if g.has_edge(u, v):
            existing = g[u][v]
            if existing["distance_km"] <= r.distance_km:
                continue
        g.add_edge(
            u, v,
            distance_km=r.distance_km,
            capacity=r.capacity,
            condition=r.condition,
            traffic=traffic,
            cost_million_egp=0.0,
            road_type="existing",
        )

    return g


def build_mst_graph() -> nx.Graph:
    """Graph used by MST: existing roads (cost 0) plus potential roads
    (cost = `cost_million_egp`), sharing the same node set.

    Existing roads are reused for free since they already exist; the MST
    weight (when called with `weight='cost_million_egp'`) therefore
    minimizes the construction outlay required to span all reachable
    nodes.

    Caveat: F3, F4, F5, F6, F9, F10 have no rows in either road CSV and
    remain isolated singletons here too. The MST result is a spanning
    *forest*, with those six nodes as zero-degree singletons.
    """
    g = build_graph()

    for r in all_potential_roads():
        u, v = r.from_id, r.to_id
        if u not in g:
            g.add_node(u)
        if v not in g:
            g.add_node(v)
        if g.has_edge(u, v):
            # Existing road already covers this pair — keep it (cost=0)
            # rather than the potential one.
            continue
        g.add_edge(
            u, v,
            distance_km=r.distance_km,
            capacity=r.capacity,
            condition=None,
            traffic=None,
            cost_million_egp=float(r.cost_million_egp),
            road_type="potential",
        )

    return g


def graph_summary(g: nx.Graph) -> dict:
    """Quick stats used in tests and (later) the Network mode."""
    components = list(nx.connected_components(g))
    largest = max((len(c) for c in components), default=0)
    return {
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
        "components": len(components),
        "largest_component": largest,
        "isolated": [
            sorted(c) for c in components if len(c) < largest
        ],
    }
