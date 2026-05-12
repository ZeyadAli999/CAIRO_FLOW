"""TransportSimulator — formal scenario-driven test harness.

Satisfies the explicit "simulation framework" grading requirement.
Algorithms are reused as-is from `src.algorithms.shortest_path`; this
module only orchestrates scenarios and produces summaries the technical
report can paste straight into a table.

CLI:
    python -m src.simulation.framework --scenario peak_rush \\
        --from 1 --to F1 --tod morning_peak

Supported scenarios:
    peak_rush, road_closure, emergency_dispatch, all_pairs_baseline
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any

import networkx as nx

from src.algorithms.shortest_path import (
    VALID_TIMES_OF_DAY,
    astar,
    astar_emergency,
    dijkstra,
    dijkstra_time_dependent,
    edge_congestion_ratio,
    edge_travel_time,
    find_alternative_routes,
    find_nearest_facility,
    path_distance_km,
    path_max_congestion,
    path_segments,
    path_travel_time_hours,
)


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    name: str
    summary: dict[str, Any]
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"scenario": self.name, "summary": self.summary, "detail": self.detail}


class TransportSimulator:
    """Runs canned scenarios on a CairoFlow road graph."""

    def __init__(self, graph: nx.Graph, traffic_data=None, facilities_df=None):
        self.G = graph
        self.traffic_data = traffic_data  # not strictly needed — graph carries flows
        self.facilities_df = facilities_df

    # -- Public API --------------------------------------------------------

    def run_scenario(self, scenario_name: str, **params) -> ScenarioResult:
        if scenario_name == "peak_rush":
            return self._scenario_peak_rush(**params)
        if scenario_name == "road_closure":
            return self._scenario_road_closure(**params)
        if scenario_name == "emergency_dispatch":
            return self._scenario_emergency_dispatch(**params)
        if scenario_name == "all_pairs_baseline":
            return self._scenario_all_pairs_baseline(**params)
        # Phase 4 scenarios
        if scenario_name == "transit_optimization":
            return self._scenario_transit_optimization(**params)
        if scenario_name == "maintenance_budget":
            return self._scenario_maintenance_budget(**params)
        if scenario_name == "signal_audit":
            return self._scenario_signal_audit(**params)
        if scenario_name == "multimodal_demand":
            return self._scenario_multimodal_demand(**params)
        raise ValueError(
            f"Unknown scenario '{scenario_name}'. "
            "Choose: peak_rush, road_closure, emergency_dispatch, "
            "all_pairs_baseline, transit_optimization, "
            "maintenance_budget, signal_audit, multimodal_demand."
        )

    def measure_response_time(
        self, source: Any, facility_type: str,
        time_of_day: str = "morning_peak",
        algorithm: str = "astar",
    ) -> dict[str, Any]:
        """ETA from `source` to the nearest `facility_type` facility."""
        if algorithm not in ("astar", "dijkstra"):
            raise ValueError("algorithm must be 'astar' or 'dijkstra'")
        if algorithm == "astar":
            facility, path, eta_h, trace = find_nearest_facility(
                self.G, source, facility_type,
                facilities=self.facilities_df,
                time_of_day=time_of_day,
            )
        else:
            facility, path, eta_h, trace = self._nearest_facility_dijkstra(
                source, facility_type, time_of_day,
            )
        return {
            "source": source,
            "facility_type": facility_type,
            "time_of_day": time_of_day,
            "algorithm": algorithm,
            "selected_facility": facility,
            "eta_minutes": round(eta_h * 60.0, 2) if path else None,
            "distance_km": round(path_distance_km(self.G, path), 2) if path else None,
            "nodes_explored": len(trace.nodes_explored),
            "runtime_ms": round(trace.runtime_ms, 3),
            "path": path,
        }

    def measure_congestion_reduction(
        self, source: Any, target: Any, time_of_day: str = "morning_peak",
    ) -> dict[str, Any]:
        """Compares same-route travel time at peak vs off-peak (night)."""
        peak_path, peak_t, _ = dijkstra_time_dependent(self.G, source, target, time_of_day)
        off_path, off_t, _ = dijkstra_time_dependent(self.G, source, target, "night")
        if peak_path is None or off_path is None:
            return {
                "source": source, "target": target,
                "time_of_day": time_of_day,
                "peak_minutes": None, "offpeak_minutes": None,
                "reduction_pct": 0.0,
                "segments_peak": [], "segments_off": [],
                "note": "Source or target unreachable.",
            }
        peak_min = peak_t * 60.0
        off_min = off_t * 60.0
        reduction_pct = max(0.0, (peak_min - off_min) / peak_min * 100.0) if peak_min > 0 else 0.0
        return {
            "source": source, "target": target,
            "time_of_day": time_of_day,
            "peak_minutes": round(peak_min, 2),
            "offpeak_minutes": round(off_min, 2),
            "reduction_pct": round(reduction_pct, 2),
            "segments_peak": path_segments(self.G, peak_path, time_of_day),
            "segments_off": path_segments(self.G, off_path, "night"),
        }

    def compare_algorithms(
        self, source: Any, target: Any, time_of_day: str = "morning_peak",
    ) -> dict[str, Any]:
        """Runs Dijkstra (distance), BPR-Dijkstra, and A* on the same query."""
        results: dict[str, Any] = {}
        # 1) Plain distance Dijkstra
        d_path, d_cost, d_trace = dijkstra(self.G, source, target, weight="distance_km")
        results["dijkstra_distance"] = self._algo_summary(
            "Dijkstra (distance)", d_path, d_trace,
            extra={"total_distance_km": d_cost if d_path else None,
                   "travel_time_minutes": round(
                       path_travel_time_hours(self.G, d_path, time_of_day) * 60.0, 2
                   ) if d_path else None},
        )
        # 2) Time-dependent Dijkstra
        td_path, td_cost, td_trace = dijkstra_time_dependent(
            self.G, source, target, time_of_day
        )
        results["dijkstra_time"] = self._algo_summary(
            "Dijkstra (BPR time)", td_path, td_trace,
            extra={"travel_time_minutes": round(td_cost * 60.0, 2) if td_path else None,
                   "distance_km": round(path_distance_km(self.G, td_path), 2) if td_path else None},
        )
        # 3) A* (distance)
        a_path, a_cost, a_trace = astar(self.G, source, target, weight="distance_km")
        results["astar"] = self._algo_summary(
            "A* (distance)", a_path, a_trace,
            extra={"total_distance_km": a_cost if a_path else None},
        )
        # Speedup: A* nodes vs Dijkstra nodes
        d_nodes = max(1, len(d_trace.nodes_explored))
        a_nodes = len(a_trace.nodes_explored)
        results["speedup_pct_nodes"] = round((d_nodes - a_nodes) / d_nodes * 100.0, 2)
        return results

    # -- Scenario impls ----------------------------------------------------

    def _scenario_peak_rush(self, source: Any, target: Any, **_) -> ScenarioResult:
        comparison = {}
        for tod in VALID_TIMES_OF_DAY:
            path, t_h, _ = dijkstra_time_dependent(self.G, source, target, tod)
            comparison[tod] = {
                "found": path is not None,
                "travel_time_minutes": round(t_h * 60.0, 2) if path else None,
                "distance_km": round(path_distance_km(self.G, path), 2) if path else None,
                "max_congestion": round(path_max_congestion(self.G, path, tod)[0], 3) if path else None,
                "via": path,
            }
        peak = comparison["morning_peak"]["travel_time_minutes"]
        night = comparison["night"]["travel_time_minutes"]
        savings = round(peak - night, 2) if peak and night else None
        return ScenarioResult(
            name="peak_rush",
            summary={
                "from": source, "to": target,
                "morning_peak_min": peak,
                "night_min": night,
                "off_peak_savings_min": savings,
            },
            detail=comparison,
        )

    def _scenario_road_closure(
        self, source: Any, target: Any,
        closed: list[tuple[Any, Any]] | None = None,
        time_of_day: str = "morning_peak",
        k: int = 3,
        **_,
    ) -> ScenarioResult:
        closed = closed or []
        baseline_path, baseline_t, _ = dijkstra_time_dependent(self.G, source, target, time_of_day)
        alts, _ = find_alternative_routes(
            self.G, source, target, time_of_day,
            k=k, excluded_edges=closed,
        )
        return ScenarioResult(
            name="road_closure",
            summary={
                "from": source, "to": target,
                "time_of_day": time_of_day,
                "closed_edges": closed,
                "baseline_min": round(baseline_t * 60.0, 2) if baseline_path else None,
                "alternatives_found": len(alts),
                "best_alt_min": round(alts[0]["travel_time_min"], 2) if alts else None,
            },
            detail={"alternatives": alts, "baseline_path": baseline_path},
        )

    def _scenario_emergency_dispatch(
        self, source: Any, facility_type: str = "Medical",
        time_of_day: str = "morning_peak", **_,
    ) -> ScenarioResult:
        astar_resp = self.measure_response_time(source, facility_type, time_of_day, "astar")
        dij_resp = self.measure_response_time(source, facility_type, time_of_day, "dijkstra")
        if astar_resp["nodes_explored"] and dij_resp["nodes_explored"]:
            speedup_pct = round(
                (dij_resp["nodes_explored"] - astar_resp["nodes_explored"])
                / dij_resp["nodes_explored"] * 100.0,
                2,
            )
        else:
            speedup_pct = 0.0
        return ScenarioResult(
            name="emergency_dispatch",
            summary={
                "incident": source,
                "facility_type": facility_type,
                "selected_facility": astar_resp["selected_facility"],
                "eta_minutes": astar_resp["eta_minutes"],
                "astar_nodes": astar_resp["nodes_explored"],
                "dijkstra_nodes": dij_resp["nodes_explored"],
                "astar_speedup_pct_nodes": speedup_pct,
            },
            detail={"astar": astar_resp, "dijkstra": dij_resp},
        )

    def _scenario_all_pairs_baseline(self, time_of_day: str = "morning_peak", **_) -> ScenarioResult:
        nodes = list(self.G.nodes())
        rows = []
        unreachable = 0
        for s in nodes:
            for t in nodes:
                if s == t:
                    continue
                path, t_h, _ = dijkstra_time_dependent(self.G, s, t, time_of_day)
                if path is None:
                    unreachable += 1
                    continue
                rows.append({
                    "from": s, "to": t,
                    "minutes": round(t_h * 60.0, 2),
                    "km": round(path_distance_km(self.G, path), 2),
                })
        if rows:
            mean_min = round(sum(r["minutes"] for r in rows) / len(rows), 2)
            max_row = max(rows, key=lambda r: r["minutes"])
        else:
            mean_min, max_row = None, None
        return ScenarioResult(
            name="all_pairs_baseline",
            summary={
                "time_of_day": time_of_day,
                "pairs_evaluated": len(rows),
                "unreachable_pairs": unreachable,
                "mean_travel_minutes": mean_min,
                "longest_pair": max_row,
            },
            detail={"first_10": rows[:10]},
        )

    # -- Phase 4 scenarios -------------------------------------------------

    def _scenario_transit_optimization(
        self, total_buses: int = 200, **_,
    ) -> ScenarioResult:
        """DP-driven bus reallocation. Reports `total_benefit` (the DP
        objective) and a per-route allocation table. Compares against
        an even-split baseline."""
        from src.algorithms.dp import transit_scheduling
        from src.db.models import BusRoute, SessionLocal

        with SessionLocal() as s:
            routes = [
                {"route_id": r.route_id,
                 "daily_passengers": r.daily_passengers,
                 "buses_assigned": r.buses_assigned}
                for r in s.query(BusRoute).all()
            ]

        result = transit_scheduling(routes, total_buses=total_buses)
        # Even-split baseline benefit, for comparison.
        from src.algorithms.dp import _bus_benefit
        n = len(routes)
        even = total_buses // n if n else 0
        even_benefit = round(sum(_bus_benefit(r["daily_passengers"], even)
                                 for r in routes), 2)
        gain_pct = (
            round((result["total_benefit"] - even_benefit)
                  / even_benefit * 100.0, 2)
            if even_benefit else 0.0
        )
        return ScenarioResult(
            name="transit_optimization",
            summary={
                "total_buses": total_buses,
                "n_routes": n,
                "dp_benefit": result["total_benefit"],
                "even_split_benefit": even_benefit,
                "gain_vs_even_pct": gain_pct,
                "table_size": result["table_size"],
            },
            detail={
                "allocations": result["allocations"],
                "current_assignments": {r["route_id"]: r["buses_assigned"] for r in routes},
            },
        )

    def _scenario_maintenance_budget(self, **_) -> ScenarioResult:
        """Run road_maintenance_knapsack at three budget levels."""
        from src.algorithms.dp import road_maintenance_knapsack
        from src.db.models import (ExistingRoad, Neighborhood, SessionLocal)

        with SessionLocal() as s:
            pop = {n.id: n.population for n in s.query(Neighborhood).all()}
            roads = []
            for er in s.query(ExistingRoad).all():
                roads.append({
                    "from": er.from_id, "to": er.to_id,
                    "distance_km": er.distance_km,
                    "condition": er.condition,
                    "pop_a": pop.get(er.from_id, 0),
                    "pop_b": pop.get(er.to_id, 0),
                })

        budgets = (200.0, 500.0, 1000.0)
        comparisons = []
        for b in budgets:
            r = road_maintenance_knapsack(roads, b)
            comparisons.append({
                "budget_million_egp": b,
                "selected_roads": len(r["selected_roads"]),
                "total_cost": r["total_cost"],
                "total_value": r["total_value"],
                "details": r["selected_roads"],
            })
        return ScenarioResult(
            name="maintenance_budget",
            summary={
                "budgets_evaluated": list(budgets),
                "best_total_value": max(c["total_value"] for c in comparisons),
                "n_poor_candidates": sum(1 for r in roads if r["condition"] <= 6),
            },
            detail={"comparisons": comparisons},
        )

    def _scenario_signal_audit(
        self, time_of_day: str = "morning_peak", **_,
    ) -> ScenarioResult:
        """Greedy traffic-signal audit across every degree-≥3 node."""
        from src.algorithms.greedy import signal_audit_report
        rep = signal_audit_report(self.G, time_of_day)
        return ScenarioResult(
            name="signal_audit",
            summary={
                "time_of_day": time_of_day,
                "intersections_audited": rep["intersections_audited"],
                "optimal_count": len(rep["optimal_cases"]),
                "suboptimal_count": len(rep["suboptimal_cases"]),
                "gini_overall": rep["gini_overall"],
            },
            detail={
                "optimal_cases": rep["optimal_cases"][:5],
                "suboptimal_cases": rep["suboptimal_cases"][:5],
            },
        )

    def _scenario_multimodal_demand(self, **_) -> ScenarioResult:
        """Fuse road / metro / bus and rank transfer hubs by demand."""
        from src.algorithms.multimodal import (
            analyze_transfer_points, build_multimodal_graph,
        )
        from src.db.models import (BusRoute, MetroLine, SessionLocal,
                                   TransitDemand)

        with SessionLocal() as s:
            metros = list(s.query(MetroLine).all())
            buses = list(s.query(BusRoute).all())
            pairs = list(s.query(TransitDemand).all())

        mm = build_multimodal_graph(self.G, metros, buses)
        ranking = analyze_transfer_points(mm, pairs)
        return ScenarioResult(
            name="multimodal_demand",
            summary={
                "n_pairs": len(pairs),
                "mm_nodes": mm.number_of_nodes(),
                "mm_edges": mm.number_of_edges(),
                "n_transfer_hubs": len(ranking),
                "top_hub": ranking[0] if ranking else None,
            },
            detail={"ranking": ranking[:10]},
        )

    # -- Private helpers ---------------------------------------------------

    def _nearest_facility_dijkstra(
        self, source: Any, facility_type: str, time_of_day: str,
    ):
        """Multi-target search using time-dependent Dijkstra. Picks the
        facility of `facility_type` with the lowest ETA. Returns the
        same shape as `find_nearest_facility` for parity."""
        from src.algorithms.shortest_path import _facility_candidates  # type: ignore

        candidates = _facility_candidates(self.G, facility_type, self.facilities_df)
        best_id, best_path, best_eta = None, None, float("inf")
        total_explored: list = []
        total_relaxed = 0
        total_runtime_ms = 0.0
        for fid in candidates:
            path, eta, trace = dijkstra_time_dependent(self.G, source, fid, time_of_day)
            total_explored.extend(trace.nodes_explored)
            total_relaxed += trace.edges_relaxed
            total_runtime_ms += trace.runtime_ms
            if path is not None and eta < best_eta:
                best_id, best_path, best_eta = fid, path, eta
        # Mimic AlgorithmTrace shape minimally
        from src.algorithms.trace import AlgorithmTrace
        trace = AlgorithmTrace(
            name=f"Dijkstra Nearest {facility_type}",
            complexity_time="O(K · (V+E) log V)",
            complexity_space="O(V)",
            nodes_explored=total_explored,
            edges_relaxed=total_relaxed,
            runtime_ms=total_runtime_ms,
            parameters={
                "source": source, "facility_type": facility_type,
                "time_of_day": time_of_day, "candidates": candidates,
            },
            explanation="Plain time-dependent Dijkstra to every candidate facility.",
            formula="argmin over facilities of ETA(source → f)",
        )
        return best_id, best_path, best_eta, trace

    def _algo_summary(self, label: str, path, trace, extra: dict | None = None):
        return {
            "label": label,
            "path": path,
            "nodes_explored": len(trace.nodes_explored),
            "edges_relaxed": trace.edges_relaxed,
            "runtime_ms": round(trace.runtime_ms, 3),
            **(extra or {}),
        }


# ---------------------------------------------------------------------------
# Pretty-printer for the CLI
# ---------------------------------------------------------------------------

def _print_table(title: str, rows: list[tuple[str, Any]]) -> None:
    print()
    print(f"  {title}")
    print(f"  {'-' * (len(title))}")
    if not rows:
        print("  (empty)")
        return
    label_w = max(len(str(k)) for k, _ in rows) + 2
    for k, v in rows:
        print(f"  {str(k).ljust(label_w)} {v}")


def _print_scenario(result: ScenarioResult) -> None:
    print(f"\n=== Scenario: {result.name} ===")
    rows = [(k, v) for k, v in result.summary.items()]
    _print_table("Summary", rows)
    if result.name == "peak_rush":
        print()
        print("  Per time-of-day")
        print("  ---------------")
        print(f"  {'tod':<14}{'minutes':>10}{'km':>8}{'max_v/c':>10}")
        for tod, info in result.detail.items():
            mins = info.get("travel_time_minutes")
            km = info.get("distance_km")
            mc = info.get("max_congestion")
            print(f"  {tod:<14}{(mins if mins is not None else '—'):>10}"
                  f"{(km if km is not None else '—'):>8}"
                  f"{(mc if mc is not None else '—'):>10}")
    elif result.name == "road_closure":
        for i, alt in enumerate(result.detail.get("alternatives", []), 1):
            via = " → ".join(map(str, alt["path"]))
            print(f"  Alt {i}: {alt['travel_time_min']:.2f} min, "
                  f"{alt['distance_km']} km, max v/c {alt['max_congestion']}")
            print(f"         via: {via}")
    elif result.name == "transit_optimization":
        print()
        print("  Allocations vs current")
        print("  ----------------------")
        print(f"  {'route':<6}{'current':>10}{'optimized':>12}{'pax/day':>10}")
        cur = result.detail.get("current_assignments", {})
        for rid, opt in result.detail.get("allocations", {}).items():
            print(f"  {rid:<6}{cur.get(rid, '—'):>10}{opt:>12}{'':>10}")
    elif result.name == "maintenance_budget":
        print()
        print("  Budget comparison")
        print("  -----------------")
        print(f"  {'budget':>10}{'roads':>8}{'cost':>10}{'value':>12}")
        for c in result.detail.get("comparisons", []):
            print(f"  {c['budget_million_egp']:>10.0f}"
                  f"{c['selected_roads']:>8}"
                  f"{c['total_cost']:>10.1f}"
                  f"{c['total_value']:>12.2f}")
    elif result.name == "signal_audit":
        print()
        print("  Optimal-case examples")
        print("  ---------------------")
        for c in result.detail.get("optimal_cases", [])[:3]:
            print(f"  {c['intersection']}: max/min ratio {c.get('max_min_ratio', '—')}, "
                  f"flow gini {c['flow_gini']}")
        print()
        print("  Suboptimal-case examples")
        print("  ------------------------")
        for c in result.detail.get("suboptimal_cases", [])[:3]:
            print(f"  {c['intersection']}: starved direction {c['starved_direction']} "
                  f"({c['starved_flow']} veh/h, {c['green_s']}s green)")
    elif result.name == "multimodal_demand":
        print()
        print("  Top transfer hubs")
        print("  -----------------")
        print(f"  {'node':<6}{'name':<24}{'count':>6}{'demand':>10}{'modes':>20}")
        for r in result.detail.get("ranking", [])[:10]:
            modes = "/".join(r.get("modes_seen", []))
            print(f"  {str(r['node_id']):<6}{r['name'][:22]:<24}"
                  f"{r['transfer_count']:>6}{r['weighted_demand']:>10.0f}"
                  f"  {modes}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_default_graph():
    """Lazy import so this module is importable without a populated DB
    (e.g. for static tests of the class structure)."""
    from src.db.seed import ensure_seeded
    from src.graph.builder import build_graph
    ensure_seeded()
    return build_graph()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CairoFlow simulation runner.")
    p.add_argument("--scenario", required=True,
                   choices=["peak_rush", "road_closure", "emergency_dispatch",
                            "all_pairs_baseline",
                            "transit_optimization", "maintenance_budget",
                            "signal_audit", "multimodal_demand"])
    p.add_argument("--from", dest="source", help="Source node id (e.g. 1, F1).")
    p.add_argument("--to", dest="target", help="Target node id (e.g. F1).")
    p.add_argument("--tod", default="morning_peak", choices=list(VALID_TIMES_OF_DAY))
    p.add_argument("--facility-type", default="Medical")
    p.add_argument("--closed", default="",
                   help='Comma-separated edges to close, e.g. "1-3,F2-3".')
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--total-buses", type=int, default=200,
                   help="Used by --scenario transit_optimization.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    args = p.parse_args(argv)

    G = _build_default_graph()
    sim = TransportSimulator(G)

    closed_pairs: list[tuple[str, str]] = []
    for token in [t for t in args.closed.split(",") if t]:
        if "-" in token:
            a, b = token.split("-", 1)
            closed_pairs.append((a, b))

    if args.scenario == "peak_rush":
        result = sim.run_scenario("peak_rush", source=args.source, target=args.target)
    elif args.scenario == "road_closure":
        result = sim.run_scenario(
            "road_closure", source=args.source, target=args.target,
            closed=closed_pairs, time_of_day=args.tod, k=args.k,
        )
    elif args.scenario == "emergency_dispatch":
        result = sim.run_scenario(
            "emergency_dispatch", source=args.source,
            facility_type=args.facility_type, time_of_day=args.tod,
        )
    elif args.scenario == "all_pairs_baseline":
        result = sim.run_scenario("all_pairs_baseline", time_of_day=args.tod)
    elif args.scenario == "transit_optimization":
        result = sim.run_scenario("transit_optimization",
                                  total_buses=args.total_buses)
    elif args.scenario == "maintenance_budget":
        result = sim.run_scenario("maintenance_budget")
    elif args.scenario == "signal_audit":
        result = sim.run_scenario("signal_audit", time_of_day=args.tod)
    else:  # multimodal_demand
        result = sim.run_scenario("multimodal_demand")

    if args.json:
        print(json.dumps(result.to_dict(), default=str, indent=2))
    else:
        _print_scenario(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
