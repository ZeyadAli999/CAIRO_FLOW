"""Dynamic programming algorithms for CairoFlow.

Implements four DP entry points used in Phase 4:

* `transit_scheduling`        — bus allocation across routes (knapsack-ish)
* `metro_scheduling`          — train-hour allocation across metro lines
* `road_maintenance_knapsack` — 0/1 knapsack for road repair budgeting
* `memoized_route_query`      — top-down memoization wrapper around
                                `dijkstra_time_dependent`

All returns include an `AlgorithmTrace` (or, for plain DP entry points,
the trace lives inside the result dict) so Programmer Mode can render
complexity, formula, runtime and the function source.
"""
from __future__ import annotations

import inspect
import math
import time
from dataclasses import asdict
from typing import Any, Iterable

import networkx as nx

from src.algorithms.shortest_path import dijkstra_time_dependent
from src.algorithms.trace import AlgorithmTrace


# ---------------------------------------------------------------------------
# 1) Transit scheduling — bus allocation
# ---------------------------------------------------------------------------

# Per-route cap so the DP doesn't blow up: any one route can absorb at
# most this many extra buses on top of its baseline.
_BUS_CAP_PER_ROUTE = 60

# Diminishing-returns multiplier: each extra bus on top of the existing
# fleet adds (1 - 0.85) * remaining_demand worth of riders.
_BUS_DECAY = 0.85


def _bus_benefit(daily_passengers: int, extra_buses: int) -> float:
    """Diminishing-returns benefit of adding `extra_buses` to a route
    that already serves `daily_passengers`.

        benefit = daily_passengers * (1 - 0.85**extra_buses)

    `extra_buses == 0` yields zero — assigning zero new buses adds no
    riders. The function is monotone non-decreasing and concave in
    `extra_buses`, which is exactly what the DP needs to make the
    bounded-knapsack reduction safe.
    """
    if extra_buses <= 0:
        return 0.0
    return float(daily_passengers) * (1.0 - _BUS_DECAY ** extra_buses)


def transit_scheduling(
    routes: list[dict],
    total_buses: int,
    demand_data: Any | None = None,
    *,
    per_route_cap: int = _BUS_CAP_PER_ROUTE,
) -> dict[str, Any]:
    """Allocate `total_buses` extra buses across `routes` to maximize
    cumulative diminishing-returns ridership.

    `routes` is a list of dicts (or objects with attribute access) each
    carrying ``route_id`` and ``daily_passengers``.

    Builds a 2D DP table ``dp[i][b]`` = best total benefit using the
    first ``i`` routes and ``b`` buses; recurrence:

        dp[i][b] = max_{0 ≤ k ≤ min(b, cap)} (
            dp[i-1][b-k] + benefit_i(k)
        )

    O(n · B²) time, O(n · B) space, where n = len(routes), B = total_buses.
    """
    start_t = time.perf_counter()
    if total_buses < 0:
        raise ValueError("total_buses must be >= 0")
    n = len(routes)
    B = int(total_buses)

    def _get(r, key):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)

    rids: list[str] = [str(_get(r, "route_id")) for r in routes]
    pax: list[int] = [int(_get(r, "daily_passengers") or 0) for r in routes]

    # dp[i][b] over (n+1) × (B+1)
    dp: list[list[float]] = [[0.0] * (B + 1) for _ in range(n + 1)]
    choice: list[list[int]] = [[0] * (B + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        ridership = pax[i - 1]
        cap_i = min(per_route_cap, B)
        for b in range(B + 1):
            best, best_k = dp[i - 1][b], 0
            kmax = min(b, cap_i)
            for k in range(0, kmax + 1):
                val = dp[i - 1][b - k] + _bus_benefit(ridership, k)
                if val > best:
                    best, best_k = val, k
            dp[i][b] = best
            choice[i][b] = best_k

    # Walk back to find the allocation.
    allocations: dict[str, int] = {rid: 0 for rid in rids}
    b_left = B
    for i in range(n, 0, -1):
        k = choice[i][b_left]
        allocations[rids[i - 1]] = k
        b_left -= k

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    total_benefit = round(dp[n][B], 2)

    trace = AlgorithmTrace(
        name="Transit Scheduling DP",
        complexity_time="O(n · B²)",
        complexity_space="O(n · B)",
        nodes_explored=list(allocations.keys()),
        edges_relaxed=n * (B + 1),
        runtime_ms=runtime_ms,
        parameters={
            "n_routes": n,
            "total_buses": B,
            "per_route_cap": per_route_cap,
            "data_structure": "2D DP table with parent-choice array",
            "objective": "max Σ daily_pax × (1 − 0.85^extra)",
        },
        explanation=(
            "Bounded-knapsack DP that distributes extra buses across "
            "bus routes. Each route's marginal benefit is concave "
            "(diminishing returns), so the inner loop tries every "
            "feasible allocation k and picks the one that maximizes "
            "benefit on the partial fleet. A parent-choice array makes "
            "reconstruction O(n)."
        ),
        formula="dp[i][b] = max_k(dp[i-1][b-k] + p_i · (1 − 0.85^k))",
        code_snippet=inspect.getsource(transit_scheduling),
    )
    return {
        "allocations": allocations,
        "total_benefit": total_benefit,
        "table_size": (n + 1, B + 1),
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# 2) Metro scheduling — train-hour allocation across metro lines
# ---------------------------------------------------------------------------

_METRO_DECAY = 0.92  # gentler than buses: trains are higher-capacity
_METRO_CAP_PER_LINE = 200


def _metro_benefit(daily_passengers: int, extra_hours: int) -> float:
    if extra_hours <= 0:
        return 0.0
    return float(daily_passengers) * (1.0 - _METRO_DECAY ** extra_hours)


def metro_scheduling(
    metro_lines: list[dict],
    total_train_hours: int,
    demand: Any | None = None,
    *,
    per_line_cap: int = _METRO_CAP_PER_LINE,
) -> dict[str, Any]:
    """Same DP shape as `transit_scheduling`, applied to metro lines."""
    start_t = time.perf_counter()
    if total_train_hours < 0:
        raise ValueError("total_train_hours must be >= 0")
    n = len(metro_lines)
    H = int(total_train_hours)

    def _get(r, key):
        if isinstance(r, dict):
            return r.get(key)
        return getattr(r, key, None)

    lids: list[str] = [str(_get(r, "line_id")) for r in metro_lines]
    pax: list[int] = [int(_get(r, "daily_passengers") or 0) for r in metro_lines]

    dp: list[list[float]] = [[0.0] * (H + 1) for _ in range(n + 1)]
    choice: list[list[int]] = [[0] * (H + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ridership = pax[i - 1]
        cap_i = min(per_line_cap, H)
        for h in range(H + 1):
            best, best_k = dp[i - 1][h], 0
            kmax = min(h, cap_i)
            for k in range(0, kmax + 1):
                val = dp[i - 1][h - k] + _metro_benefit(ridership, k)
                if val > best:
                    best, best_k = val, k
            dp[i][h] = best
            choice[i][h] = best_k

    allocations: dict[str, int] = {lid: 0 for lid in lids}
    left = H
    for i in range(n, 0, -1):
        k = choice[i][left]
        allocations[lids[i - 1]] = k
        left -= k

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    trace = AlgorithmTrace(
        name="Metro Scheduling DP",
        complexity_time="O(n · H²)",
        complexity_space="O(n · H)",
        nodes_explored=list(allocations.keys()),
        edges_relaxed=n * (H + 1),
        runtime_ms=runtime_ms,
        parameters={
            "n_lines": n,
            "total_train_hours": H,
            "per_line_cap": per_line_cap,
            "data_structure": "2D DP table",
        },
        explanation=(
            "Allocates train-hours across metro lines using the same "
            "diminishing-returns DP as the bus scheduler — the gentler "
            "0.92 decay reflects that trains carry far more riders per "
            "unit of capacity than buses do."
        ),
        formula="dp[i][h] = max_k(dp[i-1][h-k] + pax_i · (1 − 0.92^k))",
        code_snippet=inspect.getsource(metro_scheduling),
    )
    return {
        "allocations": allocations,
        "total_benefit": round(dp[n][H], 2),
        "table_size": (n + 1, H + 1),
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# 3) Road maintenance — 0/1 knapsack
# ---------------------------------------------------------------------------

_REPAIR_RATE_PER_KM = 5.0   # M EGP per km of road in poor condition
_KNAPSACK_SCALE = 10        # multiply costs/budget to keep DP integer

_POOR_CONDITION_MAX = 6


def _road_value(condition: int, pop_a: int, pop_b: int) -> float:
    """Heuristic value: worse roads → more value, more population
    served → exponentially more value.

        value = (10 − condition) × log(1 + pop_a + pop_b)
    """
    pop = max(0, int(pop_a or 0)) + max(0, int(pop_b or 0))
    return float(10 - int(condition)) * math.log(1.0 + pop)


def road_maintenance_knapsack(
    roads_with_condition: list[dict],
    budget_million_egp: float,
) -> dict[str, Any]:
    """0/1 knapsack over poor-condition roads.

    Each road in `roads_with_condition` is a dict with keys
    ``from``, ``to``, ``distance_km``, ``condition``, ``pop_a``, ``pop_b``.

    Cost per road is `distance_km × 5 M EGP`; value is
    `(10 − condition) × log(1 + pop_total)`. Costs and budget are
    multiplied by 10 then truncated to integers so the DP table runs
    on small ints — keeps the table bounded for reasonable budgets.
    """
    start_t = time.perf_counter()
    candidates = [r for r in roads_with_condition
                  if int(r.get("condition", 10)) <= _POOR_CONDITION_MAX]
    n = len(candidates)
    W = max(0, int(round(float(budget_million_egp) * _KNAPSACK_SCALE)))

    if n == 0 or W == 0:
        runtime_ms = (time.perf_counter() - start_t) * 1000.0
        return {
            "selected_roads": [],
            "total_cost": 0.0,
            "total_value": 0.0,
            "trace": AlgorithmTrace(
                name="Road Maintenance Knapsack DP",
                complexity_time="O(n · W)", complexity_space="O(n · W)",
                nodes_explored=[], edges_relaxed=0,
                runtime_ms=runtime_ms,
                parameters={
                    "n_candidates": n,
                    "budget_million_egp": float(budget_million_egp),
                    "data_structure": "2D DP table (scaled int costs)",
                    "scale": _KNAPSACK_SCALE,
                },
                explanation=(
                    "No-op case: either no poor-condition roads or zero "
                    "budget."
                ),
                formula="dp[i][w] = max(dp[i-1][w], dp[i-1][w-c_i] + v_i)",
                code_snippet=inspect.getsource(road_maintenance_knapsack),
            ),
        }

    # Pre-compute scaled cost and value per candidate.
    scaled_costs: list[int] = []
    values: list[float] = []
    for r in candidates:
        d = float(r.get("distance_km", 0) or 0)
        cost_m_egp = d * _REPAIR_RATE_PER_KM
        scaled_costs.append(max(1, int(round(cost_m_egp * _KNAPSACK_SCALE))))
        values.append(_road_value(
            int(r.get("condition", 10)),
            int(r.get("pop_a", 0) or 0),
            int(r.get("pop_b", 0) or 0),
        ))

    # 2D DP — keep both dp and choice tables for path reconstruction.
    dp: list[list[float]] = [[0.0] * (W + 1) for _ in range(n + 1)]
    take: list[list[bool]] = [[False] * (W + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        ci, vi = scaled_costs[i - 1], values[i - 1]
        for w in range(W + 1):
            dp[i][w] = dp[i - 1][w]
            if ci <= w:
                cand = dp[i - 1][w - ci] + vi
                if cand > dp[i][w]:
                    dp[i][w] = cand
                    take[i][w] = True

    selected = []
    w = W
    for i in range(n, 0, -1):
        if take[i][w]:
            r = candidates[i - 1]
            selected.append({
                "from": r.get("from"),
                "to": r.get("to"),
                "cost_million_egp": round(scaled_costs[i - 1] / _KNAPSACK_SCALE, 2),
                "value": round(values[i - 1], 4),
                "condition": int(r.get("condition", 10)),
                "distance_km": float(r.get("distance_km", 0) or 0),
            })
            w -= scaled_costs[i - 1]
    selected.reverse()

    total_cost = round(sum(s["cost_million_egp"] for s in selected), 2)
    total_value = round(sum(s["value"] for s in selected), 4)

    runtime_ms = (time.perf_counter() - start_t) * 1000.0
    trace = AlgorithmTrace(
        name="Road Maintenance Knapsack DP",
        complexity_time="O(n · W)",
        complexity_space="O(n · W)",
        nodes_explored=[s["from"] for s in selected],
        edges_relaxed=n * (W + 1),
        runtime_ms=runtime_ms,
        parameters={
            "n_candidates": n,
            "budget_million_egp": float(budget_million_egp),
            "scale": _KNAPSACK_SCALE,
            "selected_count": len(selected),
            "data_structure": "2D DP table with take[] for reconstruction",
            "repair_rate_per_km": _REPAIR_RATE_PER_KM,
            "poor_condition_max": _POOR_CONDITION_MAX,
        },
        explanation=(
            "Classic 0/1 knapsack adapted to road repair: each "
            "poor-condition link is a candidate. Costs are integer-"
            "scaled (×10) so the DP table size stays bounded for "
            "any reasonable budget."
        ),
        formula="dp[i][w] = max(dp[i-1][w], dp[i-1][w-c_i] + v_i)",
        code_snippet=inspect.getsource(road_maintenance_knapsack),
    )
    return {
        "selected_roads": selected,
        "total_cost": total_cost,
        "total_value": total_value,
        "trace": trace,
    }


# ---------------------------------------------------------------------------
# 4) Memoized route query — caches BPR-Dijkstra results
# ---------------------------------------------------------------------------

_ROUTE_CACHE: dict[tuple, dict[str, Any]] = {}
_CACHE_HITS = 0
_CACHE_MISSES = 0


def memoized_route_query(
    graph: nx.Graph,
    source: Any,
    target: Any,
    time_of_day: str,
    _cache: dict | None = None,
) -> dict[str, Any]:
    """Cached BPR-Dijkstra. Returns ``{"path", "cost", "trace"}``.

    On a hit, runtime_ms ≈ 0 and `parameters["cache_hit"] = True`.
    On a miss, the original trace is returned, augmented with the
    cache miss flag.

    `_cache` is module-level by default; pass an explicit dict to
    isolate caches in tests.
    """
    global _CACHE_HITS, _CACHE_MISSES
    cache = _cache if _cache is not None else _ROUTE_CACHE
    key = (str(source), str(target), str(time_of_day))

    if key in cache:
        _CACHE_HITS += 1
        cached = cache[key]
        # Build a fresh trace marked as a hit. Runtime tracks the
        # cache lookup itself, which should be sub-microsecond.
        t0 = time.perf_counter()
        # Touch the cache (already done).
        runtime_ms = (time.perf_counter() - t0) * 1000.0
        trace = AlgorithmTrace(
            name="Memoized BPR Route (cache hit)",
            complexity_time="O(1)",
            complexity_space="O(K) cache",
            nodes_explored=list(cached.get("nodes_explored", [])),
            edges_relaxed=0,
            runtime_ms=runtime_ms,
            parameters={
                "source": source, "target": target,
                "time_of_day": time_of_day,
                "cache_hit": True,
                "cache_size": len(cache),
            },
            explanation=(
                "Top-down memoization wrapper around time-dependent "
                "Dijkstra. Cache key is (source, target, time_of_day); "
                "this query was a hit."
            ),
            formula="cache[(s,t,tod)] → (path, cost)",
            code_snippet=inspect.getsource(memoized_route_query),
        )
        return {
            "path": list(cached["path"]) if cached["path"] is not None else None,
            "cost": cached["cost"],
            "trace": trace,
        }

    _CACHE_MISSES += 1
    path, cost, trace = dijkstra_time_dependent(graph, source, target, time_of_day)
    cache[key] = {
        "path": list(path) if path is not None else None,
        "cost": cost,
        "nodes_explored": list(trace.nodes_explored),
    }
    # Augment the returned trace with cache-miss bookkeeping.
    trace.parameters["cache_hit"] = False
    trace.parameters["cache_size"] = len(cache)
    return {"path": path, "cost": cost, "trace": trace}


def cache_clear() -> None:
    """Reset the module-level memoization cache + stats."""
    global _CACHE_HITS, _CACHE_MISSES
    _ROUTE_CACHE.clear()
    _CACHE_HITS = 0
    _CACHE_MISSES = 0


def cache_stats() -> dict[str, int]:
    return {
        "size": len(_ROUTE_CACHE),
        "hits": _CACHE_HITS,
        "misses": _CACHE_MISSES,
    }
