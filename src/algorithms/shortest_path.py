"""Shortest-path algorithms — Dijkstra, time-dependent Dijkstra (BPR),
A*, A* emergency (BPR-aware), nearest-facility A*, and a top-K
alternative routes finder via repeated Dijkstra with edge penalties.

All implemented from first principles. NetworkX is used only as a
graph container (`G.neighbors`, `G[u][v]`); no `nx.dijkstra_path` or
`nx.astar_path` calls.

Every public entry point returns a tuple ending in an `AlgorithmTrace`
that the UI Programmer Mode renders verbatim.
"""
from __future__ import annotations

import heapq
import inspect
import math
import time
from typing import Any, Callable, Iterable

import networkx as nx

from src.algorithms.trace import AlgorithmTrace


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FREE_FLOW_KMH: float = 60.0
BPR_ALPHA: float = 0.15
BPR_BETA: int = 4

VALID_TIMES_OF_DAY: tuple[str, ...] = (
    "morning_peak", "afternoon", "evening_peak", "night",
)


# ---------------------------------------------------------------------------
# BPR + helper functions
# ---------------------------------------------------------------------------

def bpr_travel_time_hours(distance_km: float, flow: float, capacity: float) -> float:
    """Bureau of Public Roads (BPR) link performance function.

    t = t_free × (1 + α × (v/c)^β)

    With α = 0.15, β = 4, and t_free = distance / FREE_FLOW_KMH (hours).
    """
    t_free = distance_km / FREE_FLOW_KMH
    if capacity is None or capacity <= 0:
        return t_free
    ratio = (flow or 0) / capacity
    return t_free * (1 + BPR_ALPHA * ratio**BPR_BETA)


def edge_travel_time(data: dict, time_of_day: str) -> float:
    """BPR travel time for an edge `data` dict at the given time-of-day."""
    distance = float(data.get("distance_km", 0) or 0)
    cap = data.get("capacity") or 1
    traffic = data.get("traffic") or {}
    flow = float(traffic.get(time_of_day, 0) or 0)
    return bpr_travel_time_hours(distance, flow, cap)


def edge_congestion_ratio(data: dict, time_of_day: str) -> float:
    """v/c ratio for an edge at the given time-of-day. 0 if no data."""
    cap = data.get("capacity") or 0
    traffic = data.get("traffic") or {}
    flow = float(traffic.get(time_of_day, 0) or 0)
    if cap <= 0:
        return 0.0
    return flow / cap


def euclidean_km(G: nx.Graph, a_node: Any, b_node: Any) -> float:
    """Great-circle-ish distance in km using the simple lat/lon → km
    approximation requested in the spec.

        lat_km = Δy × 111.0
        lon_km = Δx × 111.0 × cos(target_lat_rad)
        h(n)   = √(lat_km² + lon_km²)

    Admissible: a straight-line distance is a lower bound on any actual
    road distance, so A* with this heuristic is optimal.
    """
    ax = float(G.nodes[a_node].get("x", 0))
    ay = float(G.nodes[a_node].get("y", 0))
    bx = float(G.nodes[b_node].get("x", 0))
    by = float(G.nodes[b_node].get("y", 0))
    lat_km = (ay - by) * 111.0
    lon_km = (ax - bx) * 111.0 * math.cos(math.radians(by))
    return math.sqrt(lat_km * lat_km + lon_km * lon_km)


def reconstruct_path(prev: dict, target: Any) -> list[Any] | None:
    """Walk `prev` chain back from target to source. Returns None if
    target was never reached."""
    if target not in prev or prev[target] is None and not _is_source(prev, target):
        # Either disconnected, or target is the source itself.
        if target in prev and prev[target] is None and not _is_source(prev, target):
            return None
    path: list[Any] = []
    cur = target
    visited = set()
    while cur is not None:
        if cur in visited:
            return None  # cycle guard, should never trigger
        visited.add(cur)
        path.append(cur)
        cur = prev.get(cur)
    path.reverse()
    return path


def _is_source(prev: dict, node: Any) -> bool:
    """A node is the source iff it has prev[node] == node."""
    return prev.get(node) is node


def path_distance_km(G: nx.Graph, path: list[Any]) -> float:
    return sum(float(G[u][v].get("distance_km", 0) or 0) for u, v in zip(path[:-1], path[1:]))


def path_travel_time_hours(G: nx.Graph, path: list[Any], time_of_day: str) -> float:
    return sum(edge_travel_time(G[u][v], time_of_day) for u, v in zip(path[:-1], path[1:]))


def path_max_congestion(G: nx.Graph, path: list[Any], time_of_day: str) -> tuple[float, tuple[Any, Any] | None]:
    """Returns (max_ratio, (u, v)) — the worst-congested segment on the path."""
    worst = (0.0, None)
    for u, v in zip(path[:-1], path[1:]):
        r = edge_congestion_ratio(G[u][v], time_of_day)
        if r > worst[0]:
            worst = (r, (u, v))
    return worst


def path_segments(G: nx.Graph, path: list[Any], time_of_day: str) -> list[dict]:
    """Per-segment metadata used by the map renderer."""
    out: list[dict] = []
    for u, v in zip(path[:-1], path[1:]):
        data = G[u][v]
        out.append({
            "from": u,
            "to": v,
            "distance_km": float(data.get("distance_km", 0) or 0),
            "travel_time_h": edge_travel_time(data, time_of_day),
            "congestion": edge_congestion_ratio(data, time_of_day),
        })
    return out


# ---------------------------------------------------------------------------
# 1) Dijkstra (static weight)
# ---------------------------------------------------------------------------

def dijkstra(
    G: nx.Graph,
    source: Any,
    target: Any,
    weight: str = "distance_km",
) -> tuple[list[Any] | None, float, AlgorithmTrace]:
    """Single-source shortest path via min-heap Dijkstra."""
    start_t = time.perf_counter()
    edges_relaxed = 0
    nodes_explored: list[Any] = []

    if source not in G or target not in G:
        return None, math.inf, _make_trace_no_path(
            "Dijkstra's Algorithm", source, target, weight, start_t,
            "Source or target not in graph.",
        )

    dist: dict[Any, float] = {n: math.inf for n in G.nodes()}
    prev: dict[Any, Any] = {source: source}
    dist[source] = 0.0
    visited: set[Any] = set()
    heap: list[tuple[float, Any]] = [(0.0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        nodes_explored.append(u)
        if u == target:
            break
        for v in G.neighbors(u):
            if v in visited:
                continue
            edges_relaxed += 1
            w = float(G[u][v].get(weight, 0) or 0)
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    runtime_ms = (time.perf_counter() - start_t) * 1000.0

    if dist[target] == math.inf:
        return None, math.inf, _make_trace(
            "Dijkstra's Algorithm",
            "O((V+E) log V)", "O(V)",
            nodes_explored, edges_relaxed, runtime_ms,
            {
                "source": source, "target": target,
                "weight_mode": weight,
                "total_cost": None,
                "total_nodes_in_graph": G.number_of_nodes(),
                "result": "no_path",
            },
            "Dijkstra explores nodes in order of increasing total cost from "
            "the source, finalizing each node exactly once. Target is "
            "unreachable in the connected component containing the source.",
            "g(v) = min(g(u) + w(u,v)) for u ∈ already-finalized set",
            inspect.getsource(dijkstra),
        )

    path = _trace_back(prev, source, target)
    return path, dist[target], _make_trace(
        "Dijkstra's Algorithm",
        "O((V+E) log V)", "O(V)",
        nodes_explored, edges_relaxed, runtime_ms,
        {
            "source": source, "target": target,
            "weight_mode": weight,
            "total_cost": round(dist[target], 4),
            "total_nodes_in_graph": G.number_of_nodes(),
            "data_structure": "Binary min-heap (heapq)",
        },
        "Dijkstra explores nodes in order of increasing total cost from "
        "the source. A binary min-heap makes each extraction O(log V), "
        "so the overall cost is O((V+E) log V).",
        "g(v) = min(g(u) + w(u,v)) for u ∈ already-finalized set",
        inspect.getsource(dijkstra),
    )


# ---------------------------------------------------------------------------
# 2) Dijkstra with time-dependent BPR weights
# ---------------------------------------------------------------------------

def dijkstra_time_dependent(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
) -> tuple[list[Any] | None, float, AlgorithmTrace]:
    """Dijkstra where edge weight is BPR-derived travel time (hours).

    Uses the BPR link-performance function, time-of-day flow, and link
    capacity to penalize congested edges during peak hours.
    """
    start_t = time.perf_counter()
    if time_of_day not in VALID_TIMES_OF_DAY:
        raise ValueError(f"time_of_day must be one of {VALID_TIMES_OF_DAY}")
    edges_relaxed = 0
    nodes_explored: list[Any] = []

    if source not in G or target not in G:
        return None, math.inf, _make_trace_no_path(
            "Time-Dependent Dijkstra", source, target, time_of_day, start_t,
            "Source or target not in graph.",
        )

    dist: dict[Any, float] = {n: math.inf for n in G.nodes()}
    prev: dict[Any, Any] = {source: source}
    dist[source] = 0.0
    visited: set[Any] = set()
    heap: list[tuple[float, Any]] = [(0.0, source)]

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        nodes_explored.append(u)
        if u == target:
            break
        for v in G.neighbors(u):
            if v in visited:
                continue
            edges_relaxed += 1
            w = edge_travel_time(G[u][v], time_of_day)
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    parameters = {
        "source": source, "target": target,
        "weight_mode": "BPR travel time (hours)",
        "time_of_day": time_of_day,
        "free_flow_kmh": FREE_FLOW_KMH,
        "alpha": BPR_ALPHA, "beta": BPR_BETA,
        "total_nodes_in_graph": G.number_of_nodes(),
        "data_structure": "Binary min-heap (heapq)",
    }
    bpr_formula = (
        "BPR: t(v) = (distance / 60 km/h) × (1 + 0.15 × (flow/capacity)^4); "
        "g(v) = min(g(u) + t(u,v)) for u in finalized set"
    )
    explanation = (
        "Standard Dijkstra with edge weights computed from the Bureau of "
        "Public Roads link performance function. Each edge cost reflects "
        "the time-of-day flow, capacity, and a free-flow assumption of "
        "60 km/h, so peak-hour edges become expensive automatically."
    )
    if dist[target] == math.inf:
        parameters["result"] = "no_path"
        return None, math.inf, _make_trace(
            "Time-Dependent Dijkstra (BPR)",
            "O((V+E) log V)", "O(V)",
            nodes_explored, edges_relaxed, runtime_ms,
            parameters, explanation, bpr_formula,
            inspect.getsource(dijkstra_time_dependent),
        )

    path = _trace_back(prev, source, target)
    parameters["total_travel_time_hours"] = round(dist[target], 4)
    parameters["total_travel_time_minutes"] = round(dist[target] * 60.0, 2)
    return path, dist[target], _make_trace(
        "Time-Dependent Dijkstra (BPR)",
        "O((V+E) log V)", "O(V)",
        nodes_explored, edges_relaxed, runtime_ms,
        parameters, explanation, bpr_formula,
        inspect.getsource(dijkstra_time_dependent),
    )


# ---------------------------------------------------------------------------
# 3) A*
# ---------------------------------------------------------------------------

def astar(
    G: nx.Graph,
    source: Any,
    target: Any,
    weight: str = "distance_km",
) -> tuple[list[Any] | None, float, AlgorithmTrace]:
    """A* with the Euclidean-km heuristic from the spec.

    Heuristic admissibility: a straight-line distance between two
    coordinates is always ≤ the actual road distance, so h(n) ≤ true
    cost-to-go and the algorithm preserves Dijkstra's optimality.
    """
    edge_w = lambda u, v, d: float(d.get(weight, 0) or 0)
    h = lambda n: euclidean_km(G, n, target)
    return _astar_core(
        G, source, target, edge_w, h,
        name="A* Search",
        weight_mode=weight,
        formula="f(n) = g(n) + h(n);  h(n) = √((Δlat·111)² + (Δlon·111·cos lat)²)",
        explanation=(
            "A* explores nodes in increasing order of f(n) = g(n) + h(n), "
            "where g is the cost from the source and h is a straight-line "
            "Euclidean estimate to the target (admissible: a straight "
            "line is always ≤ any road distance), so optimality is "
            "preserved while typically exploring far fewer nodes than "
            "plain Dijkstra."
        ),
        code_snippet_func=astar,
        extra_params={},
    )


# ---------------------------------------------------------------------------
# 4) A* Emergency — BPR-aware
# ---------------------------------------------------------------------------

def astar_emergency(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
) -> tuple[list[Any] | None, float, AlgorithmTrace]:
    """A* whose edge weights are BPR travel times. The heuristic is the
    Euclidean-km distance divided by FREE_FLOW_KMH (so it estimates a
    travel time in hours and remains admissible — no road can be faster
    than free-flow)."""
    if time_of_day not in VALID_TIMES_OF_DAY:
        raise ValueError(f"time_of_day must be one of {VALID_TIMES_OF_DAY}")

    edge_w = lambda u, v, d: edge_travel_time(d, time_of_day)
    h = lambda n: euclidean_km(G, n, target) / FREE_FLOW_KMH

    extra = {
        "time_of_day": time_of_day,
        "free_flow_kmh": FREE_FLOW_KMH,
        "alpha": BPR_ALPHA, "beta": BPR_BETA,
    }
    return _astar_core(
        G, source, target, edge_w, h,
        name="A* Emergency (BPR)",
        weight_mode="BPR travel time (hours)",
        formula=(
            "edge: t = (distance / 60) × (1 + 0.15 × (v/c)^4); "
            "f(n) = g(n) + h(n); h(n) = euclidean_km / 60"
        ),
        explanation=(
            "A* with BPR-derived edge weights for emergency dispatch. "
            "The heuristic is the straight-line distance divided by the "
            "60 km/h free-flow speed — admissible because no link is "
            "faster than free-flow, so h(n) ≤ true remaining time."
        ),
        code_snippet_func=astar_emergency,
        extra_params=extra,
    )


# ---------------------------------------------------------------------------
# 5) Nearest facility (A*-based)
# ---------------------------------------------------------------------------

def find_nearest_facility(
    G: nx.Graph,
    source: Any,
    facility_type: str,
    facilities=None,
    time_of_day: str = "morning_peak",
) -> tuple[Any | None, list[Any] | None, float, AlgorithmTrace]:
    """Returns the closest facility of `facility_type` to `source`,
    using BPR-aware A* runs against each candidate.

    `facilities` may be None (in which case we infer from the graph
    node attributes), a pandas DataFrame with `id` + `type` columns, or
    a list of objects with those attributes.
    """
    start_t = time.perf_counter()
    candidates = _facility_candidates(G, facility_type, facilities)

    best_id: Any | None = None
    best_path: list[Any] | None = None
    best_eta: float = math.inf
    total_explored: list[Any] = []
    total_relaxed = 0
    per_candidate: list[dict] = []

    for fid in candidates:
        if fid == source:
            best_id, best_path, best_eta = fid, [fid], 0.0
            per_candidate.append({"facility": fid, "eta_h": 0.0, "explored": 0})
            continue
        path, eta, trace = astar_emergency(G, source, fid, time_of_day)
        per_candidate.append({
            "facility": fid,
            "eta_h": eta if path else None,
            "explored": len(trace.nodes_explored),
        })
        total_explored.extend(trace.nodes_explored)
        total_relaxed += trace.edges_relaxed
        if path is not None and eta < best_eta:
            best_id, best_path, best_eta = fid, path, eta

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    parameters = {
        "source": source,
        "facility_type": facility_type,
        "time_of_day": time_of_day,
        "candidates": candidates,
        "selected": best_id,
        "selected_eta_minutes": round(best_eta * 60.0, 2) if best_path else None,
        "per_candidate": per_candidate,
        "total_nodes_in_graph": G.number_of_nodes(),
    }
    explanation = (
        f"Runs BPR-aware A* from the source to every '{facility_type}' "
        "facility and picks the one with the lowest ETA. With Euclidean/60 "
        "as the heuristic, each search remains optimal yet explores "
        "noticeably fewer nodes than plain Dijkstra would."
    )
    return best_id, best_path, best_eta, _make_trace(
        f"A* Nearest {facility_type}",
        "O(K · (V+E) log V)", "O(V)",
        total_explored, total_relaxed, runtime_ms,
        parameters, explanation,
        "argmin_f { ETA(source → f) } over facilities of given type",
        inspect.getsource(find_nearest_facility),
    )


def _facility_candidates(G: nx.Graph, facility_type: str, facilities) -> list[Any]:
    if facilities is None:
        out = []
        for n, data in G.nodes(data=True):
            if data.get("kind") != "facility":
                continue
            if facility_type == "Any" or data.get("type") == facility_type:
                out.append(n)
        return sorted(out, key=str)
    if hasattr(facilities, "iterrows"):
        df = facilities
        if facility_type != "Any":
            df = df[df["type"] == facility_type]
        return list(df["id"].astype(str))
    out = []
    for f in facilities:
        ft = f["type"] if isinstance(f, dict) else getattr(f, "type", None)
        fid = f["id"] if isinstance(f, dict) else getattr(f, "id", None)
        if facility_type == "Any" or ft == facility_type:
            out.append(fid)
    return sorted(out, key=str)


# ---------------------------------------------------------------------------
# 6) Top-K alternative routes (repeated Dijkstra with edge penalties)
# ---------------------------------------------------------------------------

def find_alternative_routes(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
    k: int = 3,
    excluded_edges: Iterable[tuple[Any, Any]] | None = None,
) -> tuple[list[dict], AlgorithmTrace]:
    """Returns up to k alternative routes from `source` to `target`.

    Strategy: repeated BPR-Dijkstra. After each successful path, every
    edge on that path receives a multiplicative weight penalty (×1.5)
    so the next iteration is steered toward different edges. Duplicate
    paths (same node sequence) are skipped and trigger an additional
    penalty bump.
    """
    start_t = time.perf_counter()
    excluded: set[frozenset] = set()
    if excluded_edges:
        for u, v in excluded_edges:
            excluded.add(frozenset((u, v)))

    routes: list[dict] = []
    seen: set[tuple] = set()
    penalties: dict[frozenset, float] = {}
    edges_relaxed_total = 0

    max_iters = max(k * 5, 6)
    for _ in range(max_iters):
        path, penalized_time, relaxed = _dijkstra_for_alternatives(
            G, source, target, time_of_day, excluded, penalties
        )
        edges_relaxed_total += relaxed
        if path is None:
            break
        key = tuple(path)
        if key in seen:
            for u, v in zip(path[:-1], path[1:]):
                pk = frozenset((u, v))
                penalties[pk] = penalties.get(pk, 1.0) * 2.0
            continue
        seen.add(key)
        actual_time = path_travel_time_hours(G, path, time_of_day)
        worst_ratio, worst_seg = path_max_congestion(G, path, time_of_day)
        routes.append({
            "path": path,
            "travel_time_h": actual_time,
            "travel_time_min": round(actual_time * 60.0, 2),
            "distance_km": round(path_distance_km(G, path), 2),
            "max_congestion": round(worst_ratio, 3),
            "worst_segment": worst_seg,
            "segments": path_segments(G, path, time_of_day),
        })
        if len(routes) >= k:
            break
        for u, v in zip(path[:-1], path[1:]):
            pk = frozenset((u, v))
            penalties[pk] = penalties.get(pk, 1.0) * 1.5

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    parameters = {
        "source": source, "target": target,
        "time_of_day": time_of_day,
        "k": k,
        "excluded_edges": [list(e) for e in excluded],
        "found": len(routes),
        "weight_mode": "BPR travel time (hours)",
    }
    explanation = (
        "Top-K alternatives via repeated BPR-Dijkstra. After each "
        "successful path is recorded, edges on that path are multiplied "
        "by an increasing penalty so subsequent iterations prefer "
        "genuinely different roads. Reported travel times use the real "
        "(unpenalized) BPR weights."
    )
    return routes, _make_trace(
        "Top-K Alternative Routes (penalized Dijkstra)",
        "O(K · (V+E) log V)", "O(V + E)",
        sum([r["path"] for r in routes], []),
        edges_relaxed_total, runtime_ms,
        parameters, explanation,
        "minimize Σ t_BPR(e) subject to penalty(e) on previously-used edges",
        inspect.getsource(find_alternative_routes),
    )


def _dijkstra_for_alternatives(
    G: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
    excluded: set[frozenset],
    penalties: dict[frozenset, float],
) -> tuple[list[Any] | None, float, int]:
    """Internal Dijkstra used by `find_alternative_routes`. Returns
    `(path, total_penalized_time, edges_relaxed)`.
    """
    if source not in G or target not in G:
        return None, math.inf, 0
    dist = {n: math.inf for n in G.nodes()}
    prev: dict[Any, Any] = {source: source}
    dist[source] = 0.0
    visited: set[Any] = set()
    heap: list[tuple[float, Any]] = [(0.0, source)]
    edges_relaxed = 0

    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        if u == target:
            break
        for v in G.neighbors(u):
            if v in visited:
                continue
            ek = frozenset((u, v))
            if ek in excluded:
                continue
            edges_relaxed += 1
            base = edge_travel_time(G[u][v], time_of_day)
            mult = penalties.get(ek, 1.0)
            nd = d + base * mult
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))

    if dist[target] == math.inf:
        return None, math.inf, edges_relaxed
    return _trace_back(prev, source, target), dist[target], edges_relaxed


# ---------------------------------------------------------------------------
# Internal A* core
# ---------------------------------------------------------------------------

def _astar_core(
    G: nx.Graph,
    source: Any,
    target: Any,
    edge_weight_fn: Callable[[Any, Any, dict], float],
    heuristic_fn: Callable[[Any], float],
    *,
    name: str,
    weight_mode: str,
    formula: str,
    explanation: str,
    code_snippet_func: Callable,
    extra_params: dict[str, Any],
) -> tuple[list[Any] | None, float, AlgorithmTrace]:
    start_t = time.perf_counter()
    edges_relaxed = 0
    nodes_explored: list[Any] = []

    if source not in G or target not in G:
        return None, math.inf, _make_trace_no_path(
            name, source, target, weight_mode, start_t,
            "Source or target not in graph.",
        )

    g_score: dict[Any, float] = {n: math.inf for n in G.nodes()}
    g_score[source] = 0.0
    prev: dict[Any, Any] = {source: source}
    closed: set[Any] = set()
    counter = 0  # tie-breaker so heap entries are always orderable

    h0 = heuristic_fn(source)
    heap: list[tuple[float, int, Any]] = [(h0, counter, source)]

    while heap:
        f, _, u = heapq.heappop(heap)
        if u in closed:
            continue
        closed.add(u)
        nodes_explored.append(u)
        if u == target:
            break
        gu = g_score[u]
        for v in G.neighbors(u):
            if v in closed:
                continue
            edges_relaxed += 1
            tentative_g = gu + edge_weight_fn(u, v, G[u][v])
            if tentative_g < g_score[v]:
                g_score[v] = tentative_g
                prev[v] = u
                counter += 1
                heapq.heappush(heap, (tentative_g + heuristic_fn(v), counter, v))

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    parameters = {
        "source": source, "target": target,
        "weight_mode": weight_mode,
        "heuristic": "Euclidean km (admissible)",
        "total_nodes_in_graph": G.number_of_nodes(),
        "data_structure": "Binary min-heap (heapq) + closed set",
        **extra_params,
    }
    if g_score[target] == math.inf:
        parameters["result"] = "no_path"
        return None, math.inf, _make_trace(
            name, "O((V+E) log V)", "O(V)",
            nodes_explored, edges_relaxed, runtime_ms,
            parameters, explanation, formula,
            inspect.getsource(code_snippet_func),
        )

    path = _trace_back(prev, source, target)
    parameters["total_cost"] = round(g_score[target], 4)
    if "time" in weight_mode.lower():
        parameters["total_travel_time_minutes"] = round(g_score[target] * 60.0, 2)
    return path, g_score[target], _make_trace(
        name, "O((V+E) log V)", "O(V)",
        nodes_explored, edges_relaxed, runtime_ms,
        parameters, explanation, formula,
        inspect.getsource(code_snippet_func),
    )


# ---------------------------------------------------------------------------
# Trace construction helpers
# ---------------------------------------------------------------------------

def _trace_back(prev: dict, source: Any, target: Any) -> list[Any]:
    out: list[Any] = []
    cur = target
    seen: set[Any] = set()
    while cur is not None:
        if cur in seen:
            break
        seen.add(cur)
        out.append(cur)
        if cur == source:
            break
        cur = prev.get(cur)
    out.reverse()
    return out


def _make_trace(
    name: str, ct: str, cs: str,
    nodes_explored: list, edges_relaxed: int, runtime_ms: float,
    parameters: dict, explanation: str, formula: str, code_snippet: str,
) -> AlgorithmTrace:
    return AlgorithmTrace(
        name=name,
        complexity_time=ct,
        complexity_space=cs,
        nodes_explored=nodes_explored,
        edges_relaxed=edges_relaxed,
        runtime_ms=runtime_ms,
        parameters=parameters,
        explanation=explanation,
        formula=formula,
        code_snippet=code_snippet,
    )


def _make_trace_no_path(
    name: str, source: Any, target: Any, weight_mode: str,
    start_t: float, reason: str,
) -> AlgorithmTrace:
    return _make_trace(
        name, "—", "—", [], 0,
        (time.perf_counter() - start_t) * 1000.0,
        {"source": source, "target": target, "weight_mode": weight_mode,
         "result": "error", "reason": reason},
        reason, "—", "",
    )
