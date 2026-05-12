# Phase 2 — MST Build Notes

## What shipped

- `src/algorithms/mst.py` — Kruskal, Prim, and `population_weighted_mst`,
  all from-scratch (no `nx.minimum_spanning_tree` calls). Includes a
  `UnionFind` with path compression + union by rank, a binary min-heap
  (`heapq`) for Prim, and an `mst_stats()` helper for the UI card.
- `src/graph/builder.py` — added `build_mst_graph()` that combines
  existing roads (cost = 0, `road_type='existing'`) with potential roads
  (cost = `cost_million_egp`, `road_type='potential'`).
- `src/ui/network_mode.py` — Network sidebar: Kruskal/Prim toggle,
  population-weighted + must-include checkboxes, "Compute Network"
  button, stats card, algorithm-details card.
- `src/ui/map_view.py` — `mst_edge_layers()` (cyan + glow + dashed for
  potential), `mst_node_highlights()` (rings around explored nodes),
  `node_position_lookup()`. Map now hosts `mst-glow-layer`,
  `mst-edges-layer`, and `mst-nodes-layer` LayerGroups that the MST
  callback writes into.
- `app.py` — two new callbacks: `_switch_mst_algo` (toggles algo store
  and pill styles) and `_compute_mst` (runs the algorithm, writes the
  three overlay layers, the stats card, the programmer panel, and the
  `mst-result` store).
- `tests/test_mst.py` — 11 tests covering Kruskal, Prim, equivalence,
  must-include, trace contract, population-weighted, stats helper, and
  the Union-Find primitive.

## Decisions

### Default MST weight is `cost_million_egp` from the UI
The function signatures keep `weight='distance_km'` as the spec
requires, but every UI invocation passes `weight='cost_million_egp'`.
This minimizes construction *outlay* (existing roads cost 0; only
potential roads add cost) — the natural framing for "infrastructure
network design."

### Existing roads carry `cost_million_egp = 0`
Set in `build_graph()` so the same graph can serve both the Network
mode (MST) and later phases unchanged. Likewise `road_type` is
populated for both existing and potential edges, which the map overlay
uses to draw potential roads dashed.

### `must_include_nodes` semantics
For each entry, the algorithm pre-includes the *cheapest incident
edge*. If a must-include node has no incident edges (the F9 / F10
case — neither facility appears in `existing_roads.csv` or
`potential_roads.csv`), the algorithm silently skips it rather than
crashing. The trace still records that the node was *requested* in
`parameters.must_include`, and `mst_stats()` reports it under
`isolated_before`. This keeps the "Guarantee hospital & government
connectivity" checkbox honest — it does what it can with the data
available, and the stats card surfaces what couldn't be connected.

### Disconnected graphs → spanning forest
The shipped graph has 7 connected components (one of size 19, six
singletons). Kruskal naturally yields a forest. Prim is wrapped in a
reseed loop — after the heap drains, any remaining unvisited node is
visited as the seed of a new component. The result for both algorithms
is a spanning forest with `V_largest - 1 = 18` edges, total cost
`0 M EGP` (all 18 selected edges are existing). Every test that asserts
"spanning tree" does so on the largest connected component subgraph,
not the whole graph.

### Population-weighted formula
`w(u,v) = distance_km / log(pop_u + pop_v)`, with facilities defaulting
to 50,000 effective demand. Implemented as a wrapper that builds a
sibling graph carrying a `weighted_cost` attribute, then calls
`kruskal_mst(weight='weighted_cost')`. The trace name, formula, and
explanation are rewritten so Programmer Mode shows the population
formula instead of plain Kruskal's.

### Dash callback shape
`_compute_mst` is intentionally a single callback with six outputs
(three map LayerGroups, the stats slot, the programmer slot, and the
result store). It re-runs on Programmer Mode toggle as well as on
button click — with 25 nodes the recompute cost is sub-millisecond, so
selectively updating only the programmer panel wasn't worth the
plumbing.

### Algorithm pills use pattern-matching IDs
Same convention as the mode pills:
`id={"type": "mst-algo", "algo": "kruskal"|"prim"}` plus a
`dcc.Store(id="mst-algo")`. One callback handles the toggle + restyle.

## Deviations from spec

- **Node lighting animation deferred.** The spec mentions "nodes light
  up in the order they were added (use the nodes_explored list from
  trace)." `nodes_explored` is captured correctly and the highlight
  rings are drawn *all at once*. Sequential reveal needs a
  `dcc.Interval`-driven cursor that pages through the list — adding
  that requires three additional callbacks for ~10 seconds of polish.
  Pushed to Phase 7. The rings are still rendered today; only the
  staggering is missing.
- **Must-include test uses node 13 for the connected case.** The spec
  said "F9 and F10 appear in result", but neither has any edges in the
  data, so they cannot appear *as part of any edge*. The test
  `test_must_include_connected_node_appears` uses node 13 (which has
  edges) for the positive assertion, and a separate
  `test_must_include_isolated_facilities_handled_gracefully` confirms
  F9/F10 are still kept as nodes (degree 0) and that the algorithm
  doesn't crash.
- **Population-weighted signature.** Spec was
  `population_weighted_mst(G, neighborhoods_df)`. Implementation makes
  `neighborhoods_df` optional (defaults to reading population off the
  graph node attributes that the Phase 1 builder already sets) and
  adds a `must_include_nodes` kwarg for parity with the other two
  algorithms.

## Verification

- All Python files byte-compile cleanly.
- Stdlib-only simulation (mirroring `build_mst_graph` + Kruskal + Prim)
  against the actual CSVs reports:
    - 25 nodes, 42 edges (27 existing + 15 potential)
    - 7 components, 6 isolated singletons (F3, F4, F5, F6, F9, F10)
    - Kruskal & Prim each produce 18 edges, total cost `0 M EGP`,
      identical totals
    - With `must_include={F9, F10, 13}`: same 18 edges, cost still 0;
      `edges_relaxed` increases by 1 (only node 13 contributes a
      pre-include candidate; F9/F10 have no incident edges)
- `pytest tests/test_mst.py -q` not run locally — no working pip in
  this environment to install the deps.

## Recommendations for Phase 3

1. **Animation infra.** Add a `dcc.Interval(id="anim-tick")` and a
   `dcc.Store(id="anim-cursor")` to `layout.py` once. Phase 2's
   `nodes_explored` and (later phases') `path` lists can both ride on
   that single piece of plumbing.
2. **Map overlay slots.** `cairo-map` already has named LayerGroups
   for MST. Add equivalent slots for `route-overlay`, `flow-overlay`,
   `emergency-overlay` in the next phase so each mode owns its layer
   without rebuilding the map.
3. **Result-cache wiring.** `ResultCache` table is defined and unused.
   For Phase 3's all-pairs queries, key by `f"{algo}:{tod}:{closed_hash}"`
   and write through it.
4. **Connect the lonely facilities.** F3-F6, F9, F10 having no roads
   in either CSV is awkward UX. Consider extending
   `potential_roads.csv` with one synthetic short link per facility
   (e.g. F9 ↔ 3 = Qasr El Aini ↔ Downtown, ~1 km). Would let the
   "Guarantee hospital connectivity" checkbox actually matter and let
   shortest-path queries reach them.
