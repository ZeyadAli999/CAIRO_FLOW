"""Minimum Spanning Tree algorithms — Kruskal, Prim, and a
population-weighted variant.

Implemented from first principles:
  * Kruskal uses a Union-Find (disjoint set) with path compression and
    union by rank.
  * Prim uses a binary min-heap (`heapq`).

NetworkX is used only as a graph container and for `.neighbors()` /
`.edges()` traversal — no `nx.minimum_spanning_tree` calls.

Every function returns `(mst_graph, AlgorithmTrace)`. The trace carries
the order in which nodes joined the MST, edge counters, runtime, the
formula, a plain-English explanation, and the function's own source so
Programmer Mode can render it verbatim.

Disconnected inputs are handled gracefully: the result is a spanning
forest. Six facilities (F3-F6, F9, F10) have no roads in either CSV, so
they remain isolated singletons in the MST. See docs/history/PHASE2_NOTES.md.
"""
from __future__ import annotations

import heapq
import inspect
import math
import time
from typing import Any, Iterable

import networkx as nx

from src.algorithms.trace import AlgorithmTrace


# ---------------------------------------------------------------------------
# Union-Find
# ---------------------------------------------------------------------------

class UnionFind:
    """Disjoint-set with path compression + union by rank.

    Amortized cost per operation is O(α(N)) — effectively O(1).
    """

    def __init__(self, nodes: Iterable[Any]):
        self.parent: dict[Any, Any] = {n: n for n in nodes}
        self.rank: dict[Any, int] = {n: 0 for n in nodes}

    def find(self, x: Any) -> Any:
        # Two-pass iterative path compression.
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, x: Any, y: Any) -> bool:
        """Merge the sets containing x and y. Returns True if a merge
        actually happened (i.e. they were in different sets)."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1
        return True


# ---------------------------------------------------------------------------
# Helpers shared by Kruskal and Prim
# ---------------------------------------------------------------------------

def _new_mst_graph(G: nx.Graph) -> nx.Graph:
    """Return an empty graph with the same nodes (and node attributes)
    as G, but no edges."""
    mst = nx.Graph()
    for n, data in G.nodes(data=True):
        mst.add_node(n, **data)
    return mst


def _sorted_edges(G: nx.Graph, weight: str) -> list[tuple[float, Any, Any, dict]]:
    """All edges sorted by `weight` ascending, with deterministic tie-break."""
    edges = []
    for u, v, data in G.edges(data=True):
        w = float(data.get(weight, 0) or 0)
        edges.append((w, u, v, data))
    edges.sort(key=lambda e: (e[0], str(e[1]), str(e[2])))
    return edges


def _cheapest_incident_edge(
    G: nx.Graph, node: Any, weight: str
) -> tuple[float, Any, Any, dict] | None:
    """The cheapest incident edge for `node`, or None if it has no neighbors."""
    if node not in G:
        return None
    cheapest = None
    for nb in G.neighbors(node):
        data = G[node][nb]
        w = float(data.get(weight, 0) or 0)
        cand = (w, node, nb, data)
        if cheapest is None or cand < cheapest:
            cheapest = cand
    return cheapest


def _total_cost(mst: nx.Graph, attr: str = "cost_million_egp") -> float:
    return sum(float(d.get(attr, 0) or 0) for _, _, d in mst.edges(data=True))


def _edge_breakdown(mst: nx.Graph) -> tuple[int, int]:
    """Returns (existing_count, potential_count) based on `road_type`."""
    existing = potential = 0
    for _, _, d in mst.edges(data=True):
        if d.get("road_type") == "potential":
            potential += 1
        else:
            existing += 1
    return existing, potential


def _isolated_nodes(G: nx.Graph) -> list[Any]:
    """Nodes with no incident edges in the input graph."""
    return sorted([n for n in G.nodes() if G.degree(n) == 0], key=str)


# ---------------------------------------------------------------------------
# Kruskal
# ---------------------------------------------------------------------------

def kruskal_mst(
    G: nx.Graph,
    weight: str = "distance_km",
    must_include_nodes: Iterable[Any] | None = None,
) -> tuple[nx.Graph, AlgorithmTrace]:
    """Greedy edge-based MST with Union-Find cycle detection.

    Pre-includes the cheapest incident edge for every `must_include_nodes`
    entry first (so hospitals and government are guaranteed to be in the
    tree if they have any edge available), then runs the textbook
    sorted-edges Kruskal loop on the remaining edges.

    Returns:
        (mst, trace) — `mst` is an nx.Graph containing all of G's nodes
        plus only the selected edges. `trace` is the AlgorithmTrace with
        complexity, runtime, and parameter metadata.
    """
    start = time.perf_counter()
    edges_relaxed = 0
    nodes_added: list[Any] = []

    mst = _new_mst_graph(G)
    uf = UnionFind(G.nodes())
    must = list(must_include_nodes or [])

    def _add_edge(u: Any, v: Any, data: dict) -> None:
        if not mst.has_edge(u, v):
            mst.add_edge(u, v, **data)
        for n in (u, v):
            if n not in nodes_added:
                nodes_added.append(n)

    # 1) Pre-include must_include cheapest edges.
    for n in must:
        cand = _cheapest_incident_edge(G, n, weight)
        if cand is None:
            continue
        edges_relaxed += 1
        _, u, v, data = cand
        if uf.union(u, v):
            _add_edge(u, v, data)

    # 2) Standard Kruskal on the sorted edge list.
    for _, u, v, data in _sorted_edges(G, weight):
        edges_relaxed += 1
        if mst.has_edge(u, v):
            continue
        if uf.union(u, v):
            _add_edge(u, v, data)

    runtime_ms = (time.perf_counter() - start) * 1000.0
    total_cost = _total_cost(mst)

    trace = AlgorithmTrace(
        name="Kruskal's Algorithm",
        complexity_time="O(E log E)",
        complexity_space="O(V)",
        nodes_explored=nodes_added,
        edges_relaxed=edges_relaxed,
        runtime_ms=runtime_ms,
        parameters={
            "weight": weight,
            "algorithm": "kruskal",
            "must_include": list(must),
            "total_cost_million_egp": round(total_cost, 2),
            "data_structure": "Union-Find with path compression",
        },
        explanation=(
            "Kruskal's algorithm sorts every candidate edge by cost and "
            "greedily adds the cheapest one whose endpoints are not yet in "
            "the same connected component. A Union-Find with path "
            "compression resolves cycle checks in near-constant amortized "
            "time (≈ O(α(V)))."
        ),
        formula="w(u,v) = construction_cost; minimize Σw(e) for e in MST",
        code_snippet=inspect.getsource(kruskal_mst),
        extra={
            "isolated_nodes": _isolated_nodes(G),
            "edge_breakdown": _edge_breakdown(mst),
        },
    )
    return mst, trace


# ---------------------------------------------------------------------------
# Prim
# ---------------------------------------------------------------------------

def prim_mst(
    G: nx.Graph,
    weight: str = "distance_km",
    start_node: Any = "3",
    must_include_nodes: Iterable[Any] | None = None,
) -> tuple[nx.Graph, AlgorithmTrace]:
    """Node-based MST that grows out from `start_node` using a min-heap.

    For graphs that are not fully connected, the algorithm reseeds from
    every remaining unvisited node — the result is a spanning forest.

    Returns:
        (mst, trace) — see `kruskal_mst` for the contract.
    """
    start = time.perf_counter()
    edges_relaxed = 0
    nodes_added: list[Any] = []

    mst = _new_mst_graph(G)
    visited: set[Any] = set()
    heap: list[tuple[float, Any, Any, dict]] = []
    must = list(must_include_nodes or [])

    def _push_edges_from(node: Any) -> None:
        nonlocal edges_relaxed
        for nb in G.neighbors(node):
            if nb in visited:
                continue
            data = G[node][nb]
            w = float(data.get(weight, 0) or 0)
            heapq.heappush(heap, (w, node, nb, data))
            edges_relaxed += 1

    def _visit(node: Any) -> None:
        if node in visited:
            return
        visited.add(node)
        nodes_added.append(node)
        _push_edges_from(node)

    def _drain() -> None:
        while heap:
            _, u, v, data = heapq.heappop(heap)
            if v in visited:
                continue
            if not mst.has_edge(u, v):
                mst.add_edge(u, v, **data)
            _visit(v)

    # 1) Pre-include must_include cheapest edges.
    for n in must:
        cand = _cheapest_incident_edge(G, n, weight)
        if cand is None:
            continue
        edges_relaxed += 1
        _, u, v, data = cand
        if not mst.has_edge(u, v):
            mst.add_edge(u, v, **data)
        _visit(u)
        _visit(v)
    _drain()

    # 2) Seed from start_node if reachable and not yet visited.
    if start_node in G and start_node not in visited:
        _visit(start_node)
        _drain()

    # 3) Reseed from any remaining components (forest behavior).
    for n in list(G.nodes()):
        if n not in visited:
            _visit(n)
            _drain()

    runtime_ms = (time.perf_counter() - start) * 1000.0
    total_cost = _total_cost(mst)

    trace = AlgorithmTrace(
        name="Prim's Algorithm",
        complexity_time="O((V+E) log V)",
        complexity_space="O(V)",
        nodes_explored=nodes_added,
        edges_relaxed=edges_relaxed,
        runtime_ms=runtime_ms,
        parameters={
            "weight": weight,
            "algorithm": "prim",
            "start_node": start_node,
            "must_include": list(must),
            "total_cost_million_egp": round(total_cost, 2),
            "data_structure": "Binary min-heap (heapq)",
        },
        explanation=(
            "Prim's algorithm starts from a single node and repeatedly "
            "extracts the cheapest edge crossing the visited frontier into "
            "an unvisited node. A binary min-heap makes each extraction "
            "O(log V), giving an overall O((V+E) log V) runtime."
        ),
        formula="w(u,v) = construction_cost; minimize Σw(e) for e in MST",
        code_snippet=inspect.getsource(prim_mst),
        extra={
            "isolated_nodes": _isolated_nodes(G),
            "edge_breakdown": _edge_breakdown(mst),
        },
    )
    return mst, trace


# ---------------------------------------------------------------------------
# Population-weighted MST (Kruskal under the hood)
# ---------------------------------------------------------------------------

_FACILITY_DEFAULT_POP = 50_000


def population_weighted_mst(
    G: nx.Graph,
    neighborhoods_df=None,
    must_include_nodes: Iterable[Any] | None = None,
) -> tuple[nx.Graph, AlgorithmTrace]:
    """MST with edge weights `distance_km / log(pop_u + pop_v)`.

    Lower weight means "easier to justify connecting these endpoints" —
    so the spanning tree is biased toward linking high-population areas.
    Facilities have no population in the schema, so they default to
    50,000 people of effective demand.

    `neighborhoods_df`, if provided, is a pandas DataFrame with `id`
    and `population` columns. If None, populations are read straight off
    the graph node attributes (which is how the Phase 1 builder seeds
    them).
    """
    pop_lookup: dict[str, int] = {}
    if neighborhoods_df is not None:
        for _, row in neighborhoods_df.iterrows():
            pop_lookup[str(row["id"])] = int(row["population"])

    def _pop(node_id: Any) -> int:
        if str(node_id) in pop_lookup:
            return pop_lookup[str(node_id)]
        attr = G.nodes[node_id].get("population")
        if attr:
            return int(attr)
        return _FACILITY_DEFAULT_POP

    # Build a sibling graph carrying a `weighted_cost` attribute on every
    # edge — leave the original graph untouched.
    H = _new_mst_graph(G)
    for u, v, data in G.edges(data=True):
        d = float(data.get("distance_km", 0) or 0)
        denom = math.log(_pop(u) + _pop(v))
        w = d / denom if denom > 0 else d
        new_data = dict(data)
        new_data["weighted_cost"] = round(w, 6)
        H.add_edge(u, v, **new_data)

    mst, trace = kruskal_mst(
        H, weight="weighted_cost", must_include_nodes=must_include_nodes
    )

    trace.name = "Population-Weighted MST (Kruskal)"
    trace.explanation = (
        "Population-weighted MST scales each edge's distance by the "
        "inverse log of the combined endpoint populations. This biases "
        "the spanning tree toward connecting high-population areas at "
        "lower effective cost — facilities default to 50,000 demand."
    )
    trace.formula = (
        "w(u,v) = distance_km(u,v) / log(pop_u + pop_v); "
        "minimize Σw(e) for e in MST"
    )
    trace.parameters["weight"] = "weighted_cost"
    trace.parameters["facility_default_pop"] = _FACILITY_DEFAULT_POP
    trace.code_snippet = inspect.getsource(population_weighted_mst)
    return mst, trace


# ---------------------------------------------------------------------------
# Convenience: bundle stats for the UI
# ---------------------------------------------------------------------------

def mst_stats(mst: nx.Graph, source: nx.Graph) -> dict[str, Any]:
    """Quick summary used by the Network mode stats card."""
    existing, potential = _edge_breakdown(mst)
    isolated = _isolated_nodes(source)
    # Was the connected portion of the source graph fully linked by the MST?
    source_components = list(nx.connected_components(source))
    largest_source = max(source_components, key=len) if source_components else set()
    mst_sub = mst.subgraph(largest_source)
    all_connected = nx.is_connected(mst_sub) if mst_sub.number_of_nodes() else False
    # Reference baseline for the "saves X% vs building all" line.
    all_potential_cost = sum(
        float(d.get("cost_million_egp", 0) or 0)
        for _, _, d in source.edges(data=True)
        if d.get("road_type") == "potential"
    )
    return {
        "total_cost_million_egp": round(_total_cost(mst), 2),
        "all_potential_cost_million_egp": round(all_potential_cost, 2),
        "roads_included": mst.number_of_edges(),
        "new_roads_needed": potential,
        "existing_roads_used": existing,
        "isolated_before": isolated,
        "all_connected_after": all_connected,
        "covered_nodes": len(largest_source),
        "total_nodes": source.number_of_nodes(),
    }
