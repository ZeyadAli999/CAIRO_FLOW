"""Explain Emergency Mode facility choices without changing selection logic."""
from __future__ import annotations

import math
from typing import Any

import networkx as nx

from src.algorithms.shortest_path import astar_emergency


def explain_emergency_facility_choice(
    G: nx.Graph,
    source_id: Any,
    selected_facility_id: Any,
    facility_type: str = "Medical",
    time_of_day: str = "morning_peak",
) -> dict[str, Any]:
    """Compare the selected emergency facility with the best alternative.

    This helper recomputes candidate ETAs for explanation only. It does not
    choose, override, or mutate the selected facility.
    """
    selected = str(selected_facility_id) if selected_facility_id is not None else None
    candidates = _facility_candidates_from_graph(G, facility_type)
    reachable: list[dict[str, Any]] = []

    for fid in candidates:
        path, eta_h, _ = astar_emergency(G, source_id, fid, time_of_day)
        if path is None or not math.isfinite(eta_h):
            continue
        reachable.append({
            "facility": fid,
            "eta_minutes": round(eta_h * 60.0, 2),
            "path": path,
            "nodes": len(path),
        })

    selected_info = next((row for row in reachable if row["facility"] == selected), None)
    if selected_info is None:
        return {
            "selected": selected,
            "alternative": None,
            "selected_eta": None,
            "alternative_eta": None,
            "eta_saved": None,
            "selected_nodes": None,
            "alternative_nodes": None,
            "extra_nodes_if_alternative": None,
            "reason": (
                f"No explanation available because selected facility {selected} "
                "was not reachable in the emergency graph."
            ),
        }

    alternatives = [row for row in reachable if row["facility"] != selected]
    alternatives.sort(key=lambda row: (row["eta_minutes"], row["nodes"], row["facility"]))
    if not alternatives:
        return {
            "selected": selected,
            "alternative": None,
            "selected_eta": selected_info["eta_minutes"],
            "alternative_eta": None,
            "eta_saved": None,
            "selected_nodes": selected_info["nodes"],
            "alternative_nodes": None,
            "extra_nodes_if_alternative": None,
            "reason": (
                f"Selected {selected} because it was the only reachable "
                f"{facility_type} facility from {source_id}."
            ),
        }

    alternative = alternatives[0]
    eta_saved = round(alternative["eta_minutes"] - selected_info["eta_minutes"], 2)
    node_delta = alternative["nodes"] - selected_info["nodes"]
    node_phrase = _node_delta_phrase(node_delta)
    if eta_saved >= 0:
        reason = (
            f"Selected {selected} because it has the lowest ETA. "
            f"{alternative['facility']} would take {eta_saved:.2f} more minutes "
            f"and {node_phrase}."
        )
    else:
        reason = (
            f"Selected {selected}. Note: {alternative['facility']} appears "
            f"{abs(eta_saved):.2f} minutes faster in this explanatory check; "
            "review routing inputs if this occurs."
        )

    return {
        "selected": selected,
        "alternative": alternative["facility"],
        "selected_eta": selected_info["eta_minutes"],
        "alternative_eta": alternative["eta_minutes"],
        "eta_saved": eta_saved,
        "selected_nodes": selected_info["nodes"],
        "alternative_nodes": alternative["nodes"],
        "extra_nodes_if_alternative": node_delta,
        "reason": reason,
    }


def _facility_candidates_from_graph(G: nx.Graph, facility_type: str) -> list[str]:
    candidates = []
    for node, data in G.nodes(data=True):
        if data.get("kind") != "facility":
            continue
        if facility_type == "Any" or data.get("type") == facility_type:
            candidates.append(str(node))
    return sorted(candidates)


def _node_delta_phrase(delta: int) -> str:
    if delta == 0:
        return "the same number of path nodes"
    if delta > 0:
        unit = "node" if delta == 1 else "nodes"
        return f"{delta} more {unit}"
    unit = "node" if abs(delta) == 1 else "nodes"
    return f"{abs(delta)} fewer {unit}"

