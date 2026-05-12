"""Bonus — side-by-side Dijkstra vs A* race instrumentation.

The Phase 3 `dijkstra` and `astar` already record their full
`nodes_explored` order in the AlgorithmTrace. This module adds **per-step
state snapshots** so a UI can replay the race frame-by-frame:

  * which node was just finalized
  * which nodes are currently in the open set / heap (the frontier)
  * how many edges have been relaxed so far
  * the running `g(target)` (best known distance)

Both runners reuse the SAME core logic as the production algorithms;
they're not toy reimplementations. The trace they emit is identical to
the original — we just additionally capture frames.
"""
from __future__ import annotations

import heapq
import math
import time
from dataclasses import dataclass, field
from typing import Any

import networkx as nx

from src.algorithms.shortest_path import edge_travel_time, euclidean_km


# ---------------------------------------------------------------------------
# Per-step frame
# ---------------------------------------------------------------------------

@dataclass
class RaceFrame:
    """One step in an algorithm's exploration."""
    step: int
    current: Any                          # node finalized this step
    visited: list[Any]                    # all nodes finalized so far (ordered)
    frontier: list[Any]                   # nodes currently in the open set
    edges_relaxed: int                    # cumulative count
    best_target_dist: float               # current best dist to target (inf if unreached)


@dataclass
class RaceResult:
    """Complete race output for one algorithm."""
    name: str
    path: list[Any] | None
    cost: float
    frames: list[RaceFrame] = field(default_factory=list)
    runtime_ms: float = 0.0
    edges_relaxed: int = 0

    def to_serializable(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "cost": (None if math.isinf(self.cost) else round(self.cost, 4)),
            "edges_relaxed": self.edges_relaxed,
            "runtime_ms": round(self.runtime_ms, 3),
            "n_frames": len(self.frames),
            "frames": [
                {
                    "step": f.step,
                    "current": f.current,
                    "visited": list(f.visited),
                    "frontier": list(f.frontier),
                    "edges_relaxed": f.edges_relaxed,
                    "best_target_dist": (None if math.isinf(f.best_target_dist)
                                          else round(f.best_target_dist, 4)),
                }
                for f in self.frames
            ],
        }


# ---------------------------------------------------------------------------
# Step-capturing Dijkstra
# ---------------------------------------------------------------------------

def dijkstra_with_steps(
    G: nx.Graph,
    source: Any,
    target: Any,
    weight: str = "distance_km",
    time_of_day: str | None = None,
) -> RaceResult:
    """Min-heap Dijkstra that captures one RaceFrame per finalized node.

    If `time_of_day` is provided, edge weight = BPR travel time at that
    TOD; otherwise the static `weight` attribute is used (default
    distance_km)."""
    start_t = time.perf_counter()
    if source not in G or target not in G:
        return RaceResult(name="Dijkstra", path=None, cost=math.inf)

    dist: dict[Any, float] = {n: math.inf for n in G.nodes()}
    prev: dict[Any, Any] = {source: source}
    dist[source] = 0.0
    visited: set[Any] = set()
    visited_order: list[Any] = []
    heap: list[tuple[float, Any]] = [(0.0, source)]
    edges_relaxed = 0
    frames: list[RaceFrame] = []
    step = 0

    def _frontier() -> list[Any]:
        return [n for _, n in heap if n not in visited]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        visited_order.append(u)
        step += 1
        frames.append(RaceFrame(
            step=step, current=u,
            visited=list(visited_order),
            frontier=_frontier(),
            edges_relaxed=edges_relaxed,
            best_target_dist=dist[target],
        ))
        if u == target:
            break
        for v in G.neighbors(u):
            if v in visited:
                continue
            edges_relaxed += 1
            if time_of_day is not None:
                w = edge_travel_time(G[u][v], time_of_day)
            else:
                w = float(G[u][v].get(weight, 0) or 0)
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    if dist[target] == math.inf:
        return RaceResult(
            name="Dijkstra", path=None, cost=math.inf,
            frames=frames, runtime_ms=runtime_ms,
            edges_relaxed=edges_relaxed,
        )
    # Trace back path
    path = [target]
    cur = target
    seen = {target}
    while cur != source:
        cur = prev.get(cur)
        if cur is None or cur in seen:
            break
        seen.add(cur)
        path.append(cur)
    path.reverse()
    return RaceResult(
        name="Dijkstra", path=path, cost=dist[target],
        frames=frames, runtime_ms=runtime_ms,
        edges_relaxed=edges_relaxed,
    )


# ---------------------------------------------------------------------------
# Step-capturing A*
# ---------------------------------------------------------------------------

def astar_with_steps(
    G: nx.Graph,
    source: Any,
    target: Any,
    weight: str = "distance_km",
    time_of_day: str | None = None,
) -> RaceResult:
    """A* with the Euclidean-km admissible heuristic. Captures one
    RaceFrame per node finalization (same shape as Dijkstra's frames so
    the UI can replay them in lockstep)."""
    start_t = time.perf_counter()
    if source not in G or target not in G:
        return RaceResult(name="A*", path=None, cost=math.inf)

    g_score: dict[Any, float] = {n: math.inf for n in G.nodes()}
    g_score[source] = 0.0
    prev: dict[Any, Any] = {source: source}
    closed: set[Any] = set()
    closed_order: list[Any] = []
    counter = 0
    h0 = euclidean_km(G, source, target)
    if time_of_day is not None:
        from src.algorithms.shortest_path import FREE_FLOW_KMH
        h0 = h0 / FREE_FLOW_KMH      # heuristic in hours, admissible
    heap: list[tuple[float, int, Any]] = [(h0, counter, source)]
    edges_relaxed = 0
    frames: list[RaceFrame] = []
    step = 0

    def _frontier() -> list[Any]:
        return [n for _, _, n in heap if n not in closed]

    while heap:
        f, _, u = heapq.heappop(heap)
        if u in closed:
            continue
        closed.add(u)
        closed_order.append(u)
        step += 1
        frames.append(RaceFrame(
            step=step, current=u,
            visited=list(closed_order),
            frontier=_frontier(),
            edges_relaxed=edges_relaxed,
            best_target_dist=g_score[target],
        ))
        if u == target:
            break
        gu = g_score[u]
        for v in G.neighbors(u):
            if v in closed:
                continue
            edges_relaxed += 1
            if time_of_day is not None:
                w = edge_travel_time(G[u][v], time_of_day)
            else:
                w = float(G[u][v].get(weight, 0) or 0)
            tentative = gu + w
            if tentative < g_score[v]:
                g_score[v] = tentative
                prev[v] = u
                counter += 1
                h = euclidean_km(G, v, target)
                if time_of_day is not None:
                    from src.algorithms.shortest_path import FREE_FLOW_KMH
                    h = h / FREE_FLOW_KMH
                heapq.heappush(heap, (tentative + h, counter, v))

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    if g_score[target] == math.inf:
        return RaceResult(
            name="A*", path=None, cost=math.inf,
            frames=frames, runtime_ms=runtime_ms,
            edges_relaxed=edges_relaxed,
        )
    path = [target]
    cur = target
    seen = {target}
    while cur != source:
        cur = prev.get(cur)
        if cur is None or cur in seen:
            break
        seen.add(cur)
        path.append(cur)
    path.reverse()
    return RaceResult(
        name="A*", path=path, cost=g_score[target],
        frames=frames, runtime_ms=runtime_ms,
        edges_relaxed=edges_relaxed,
    )


# ---------------------------------------------------------------------------
# Race orchestrator
# ---------------------------------------------------------------------------

def race(
    G: nx.Graph,
    source: Any,
    target: Any,
    weight: str = "distance_km",
    time_of_day: str | None = None,
) -> dict[str, Any]:
    """Run both algorithms back-to-back and bundle a JSON-serializable
    summary the UI can hand straight to a clientside animator."""
    d_res = dijkstra_with_steps(G, source, target, weight, time_of_day)
    a_res = astar_with_steps(G, source, target, weight, time_of_day)
    same_cost = (
        d_res.path is not None and a_res.path is not None
        and abs(d_res.cost - a_res.cost) < 1e-6
    )
    speedup_pct_nodes = 0.0
    if d_res.frames:
        speedup_pct_nodes = (
            (len(d_res.frames) - len(a_res.frames)) / max(1, len(d_res.frames)) * 100.0
        )
    return {
        "source": source,
        "target": target,
        "weight_mode": (
            f"BPR ({time_of_day})" if time_of_day else weight
        ),
        "dijkstra": d_res.to_serializable(),
        "astar": a_res.to_serializable(),
        "agree_on_cost": same_cost,
        "speedup_pct_nodes": round(speedup_pct_nodes, 2),
        "winner": (
            "A*" if len(a_res.frames) < len(d_res.frames)
            else ("tie" if len(a_res.frames) == len(d_res.frames) else "Dijkstra")
        ),
    }
