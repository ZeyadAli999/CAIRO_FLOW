"""Multi-modal transit graph + routing.

Builds a single weighted graph that fuses road, metro, and bus edges
plus zero-distance "transfer" edges (with a fixed wait penalty) at
every node. Travel times are in **minutes** throughout this module so
the multimodal Dijkstra naturally minimizes door-to-door time.
"""
from __future__ import annotations

import heapq
import inspect
import math
import time
from typing import Any, Iterable

import networkx as nx

from src.algorithms.shortest_path import euclidean_km
from src.algorithms.trace import AlgorithmTrace


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROAD_KMH: float = 25.0   # urban average with congestion (peak-hour driving)
METRO_KMH: float = 40.0  # rail right-of-way, no signal stops
BUS_KMH: float = 25.0    # similar to road; benefit comes from reserved lanes
WALK_KMH_DEFAULT: float = 5.0
TRANSFER_PENALTY_MIN: float = 5.0  # wait + walk between modes


# ---------------------------------------------------------------------------
# 1) Build the multimodal graph
# ---------------------------------------------------------------------------

def build_multimodal_graph(
    road_graph: nx.Graph,
    metro_lines: list,
    bus_routes: list,
    walk_speed: float = WALK_KMH_DEFAULT,
    *,
    transfer_penalty_min: float = TRANSFER_PENALTY_MIN,
) -> nx.MultiGraph:
    """Construct the fused multimodal graph.

    The result is a `MultiGraph` because between any two stations we
    may have several edges of different modes (e.g. road *and* metro
    between Downtown and Heliopolis). Each edge stores:

        ``{"mode": "road"|"metro"|"bus"|"transfer", "time_min": <float>,
           "distance_km": <float>}``

    `metro_lines` and `bus_routes` are iterables of objects (or
    dicts) with at least:
        ``stations`` (metro) or ``stops`` (bus): comma-separated
        node-id strings — the same shape SQLAlchemy returns for
        `MetroLine` / `BusRoute` rows.
    """
    M = nx.MultiGraph()
    # Copy nodes and their attributes from the road graph.
    for n, data in road_graph.nodes(data=True):
        M.add_node(n, **data)

    # 1) Road edges → time at free-flow road speed.
    for u, v, data in road_graph.edges(data=True):
        d_km = float(data.get("distance_km", 0) or 0)
        time_min = (d_km / ROAD_KMH) * 60.0
        M.add_edge(u, v, mode="road", time_min=time_min, distance_km=d_km)

    # 2) Metro edges between consecutive stations on each line.
    for ml in metro_lines or []:
        stations = _split_ids(_attr(ml, "stations"))
        line_id = _attr(ml, "line_id")
        for u, v in zip(stations[:-1], stations[1:]):
            if u not in M or v not in M:
                continue
            d_km = euclidean_km(M, u, v)
            t_min = (d_km / METRO_KMH) * 60.0
            M.add_edge(u, v, mode="metro", line=line_id,
                       time_min=t_min, distance_km=d_km)

    # 3) Bus edges between consecutive stops on each route.
    for br in bus_routes or []:
        stops = _split_ids(_attr(br, "stops"))
        route_id = _attr(br, "route_id")
        for u, v in zip(stops[:-1], stops[1:]):
            if u not in M or v not in M:
                continue
            d_km = euclidean_km(M, u, v)
            t_min = (d_km / BUS_KMH) * 60.0
            M.add_edge(u, v, mode="bus", route=route_id,
                       time_min=t_min, distance_km=d_km)

    # 4) Transfer self-loops are not useful — instead, the multimodal
    #    Dijkstra adds the transfer penalty whenever the mode changes
    #    at a node. Persist a per-graph constant for callers that want
    #    to inspect it.
    M.graph["transfer_penalty_min"] = float(transfer_penalty_min)
    M.graph["walk_kmh"] = float(walk_speed)
    return M


def _attr(obj: Any, name: str):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _split_ids(s: str | None) -> list[str]:
    if not s:
        return []
    return [tok.strip() for tok in str(s).split(",") if tok.strip()]


# ---------------------------------------------------------------------------
# 2) Multimodal shortest path
# ---------------------------------------------------------------------------

def multimodal_shortest_path(
    mm_graph: nx.MultiGraph,
    source: Any,
    target: Any,
) -> tuple[list[Any] | None, float, list[dict], AlgorithmTrace]:
    """Dijkstra on the multimodal graph minimizing total time (min).

    Edge cost is `time_min` plus, when the mode changes between
    consecutive edges, a `transfer_penalty_min` charge.

    Returns ``(path, total_time_min, mode_breakdown, trace)``. If the
    target is unreachable, returns ``(None, inf, [], trace)``.

    The `mode_breakdown` is a list of legs:
        ``{"from", "to", "mode", "time_min"}``
    """
    start_t = time.perf_counter()
    if source not in mm_graph or target not in mm_graph:
        runtime_ms = (time.perf_counter() - start_t) * 1000.0
        return None, math.inf, [], _trace_no_path(source, target, runtime_ms)

    transfer_pen = float(mm_graph.graph.get("transfer_penalty_min",
                                            TRANSFER_PENALTY_MIN))

    # State key: (node, last_mode). Transfer penalty is charged on
    # mode change *or* on the very first hop when last_mode is None.
    INF = math.inf
    dist: dict[tuple[Any, str | None], float] = {(source, None): 0.0}
    prev: dict[tuple[Any, str | None], tuple | None] = {(source, None): None}
    closed: set[tuple[Any, str | None]] = set()
    nodes_explored: list[Any] = []
    edges_relaxed = 0

    heap: list[tuple[float, int, Any, str | None]] = [(0.0, 0, source, None)]
    counter = 0

    while heap:
        d, _, u, lm = heapq.heappop(heap)
        if (u, lm) in closed:
            continue
        closed.add((u, lm))
        nodes_explored.append(u)
        if u == target:
            target_state = (u, lm)
            break
        # Iterate every parallel edge between u and its neighbours.
        # MultiGraph.edges(node, keys=True, data=True) yields
        # (u, v, key, data) — we discard the leading u.
        for _, v, key, data in mm_graph.edges(u, keys=True, data=True):
            if (v, data["mode"]) in closed:
                continue
            edges_relaxed += 1
            t = float(data.get("time_min", 0) or 0)
            mode = data.get("mode")
            mode_change = (lm is not None and lm != mode)
            new_d = d + t + (transfer_pen if mode_change else 0.0)
            state = (v, mode)
            if new_d < dist.get(state, INF):
                dist[state] = new_d
                prev[state] = (u, lm, mode, key, t)
                counter += 1
                heapq.heappush(heap, (new_d, counter, v, mode))
    else:
        runtime_ms = (time.perf_counter() - start_t) * 1000.0
        return None, math.inf, [], _trace_no_path(source, target, runtime_ms)

    # Pick whichever (target, mode) state has the lowest distance.
    best_state = min(
        ((s, dist[s]) for s in dist if s[0] == target),
        key=lambda kv: kv[1], default=None,
    )
    if best_state is None:
        runtime_ms = (time.perf_counter() - start_t) * 1000.0
        return None, math.inf, [], _trace_no_path(source, target, runtime_ms)
    target_state, total_time = best_state

    # Reconstruct.
    mode_breakdown: list[dict] = []
    path_nodes: list[Any] = [target_state[0]]
    cur = target_state
    while prev.get(cur) is not None:
        u, lm, mode, key, t = prev[cur]
        mode_breakdown.append({
            "from": u, "to": cur[0], "mode": mode, "time_min": round(t, 3),
        })
        path_nodes.append(u)
        cur = (u, lm)
    path_nodes.reverse()
    mode_breakdown.reverse()

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    trace = AlgorithmTrace(
        name="Multimodal Dijkstra",
        complexity_time="O((V·M + E) log (V·M))",
        complexity_space="O(V·M)",
        nodes_explored=nodes_explored,
        edges_relaxed=edges_relaxed,
        runtime_ms=runtime_ms,
        parameters={
            "source": source, "target": target,
            "transfer_penalty_min": transfer_pen,
            "modes": ["road", "metro", "bus"],
            "data_structure": "Min-heap over (node, last_mode) states",
            "weight_mode": "time_min (with mode-change penalty)",
        },
        explanation=(
            "Dijkstra on a multimodal graph with state (node, last_mode). "
            "When the next edge uses a different mode than the previous "
            "leg, a fixed 5-minute transfer penalty is added. This lets "
            "the algorithm consider mode mixes while still finding the "
            "optimal door-to-door time."
        ),
        formula="time(u→v) = time_min(edge) + [mode change ? PENALTY : 0]",
        code_snippet=inspect.getsource(multimodal_shortest_path),
    )
    return path_nodes, total_time, mode_breakdown, trace


def _trace_no_path(source: Any, target: Any, runtime_ms: float) -> AlgorithmTrace:
    return AlgorithmTrace(
        name="Multimodal Dijkstra",
        complexity_time="—", complexity_space="—",
        nodes_explored=[], edges_relaxed=0, runtime_ms=runtime_ms,
        parameters={"source": source, "target": target, "result": "no_path"},
        explanation="Source or target unreachable in the multimodal graph.",
        formula="—",
        code_snippet="",
    )


# ---------------------------------------------------------------------------
# 3) Transfer-point analysis
# ---------------------------------------------------------------------------

def analyze_transfer_points(
    mm_graph: nx.MultiGraph,
    demand_pairs: list[dict],
) -> list[dict]:
    """Rank multimodal transfer hubs by usage × demand.

    `demand_pairs` is an iterable of dicts/objects with
    ``from_id``, ``to_id``, ``daily_passengers``.

    For each pair we compute the multimodal optimal route and count
    the nodes where the mode changed (i.e. the transfers). Each such
    node accumulates `daily_passengers` of weighted demand.

    Returns a list sorted descending by `weighted_demand`:
        [{
          "node_id", "name", "transfer_count",
          "weighted_demand", "modes_seen": [list]
        }, ...]
    """
    counts: dict[Any, int] = {}
    weighted: dict[Any, float] = {}
    modes_seen: dict[Any, set[str]] = {}

    for dp in demand_pairs or []:
        s = str(_attr(dp, "from_id"))
        t = str(_attr(dp, "to_id"))
        pax = float(_attr(dp, "daily_passengers") or 0)
        if s == t or s not in mm_graph or t not in mm_graph:
            continue
        path, _, breakdown, _ = multimodal_shortest_path(mm_graph, s, t)
        if path is None or len(breakdown) < 2:
            continue
        # Walk the breakdown, mark transfers (where leg's mode != prev mode).
        prev_mode = breakdown[0]["mode"]
        for leg in breakdown[1:]:
            if leg["mode"] != prev_mode:
                hub = leg["from"]
                counts[hub] = counts.get(hub, 0) + 1
                weighted[hub] = weighted.get(hub, 0.0) + pax
                modes_seen.setdefault(hub, set()).update([prev_mode, leg["mode"]])
            prev_mode = leg["mode"]

    out: list[dict] = []
    for n, c in counts.items():
        name = mm_graph.nodes[n].get("name", str(n)) if n in mm_graph else str(n)
        out.append({
            "node_id": n,
            "name": name,
            "transfer_count": c,
            "weighted_demand": round(weighted.get(n, 0.0), 1),
            "modes_seen": sorted(modes_seen.get(n, set())),
        })
    out.sort(key=lambda r: (-r["weighted_demand"], -r["transfer_count"], str(r["node_id"])))
    return out
