# Phase 1 — Build Notes

This document records decisions made during the Phase 1 scaffold, any
deviations from the spec, and recommendations for Phase 2.

## Decisions

### Node identifiers are strings everywhere
The spec mixes integer IDs (`1`, `2`, ...) for neighborhoods with
prefixed string IDs (`F1`, `F2`, ...) for facilities. Rather than
maintain two namespaces, every node ID is stored and queried as a
**string**. Pandas auto-casts the integer column on CSV load, so
`src/db/seed.py` explicitly stringifies IDs before insert. This keeps
graph building, route queries, and UI lookups uniform.

### Edges are stored once, traversed both ways
`existing_roads.csv` contains 28 directed pairs that represent
bidirectional roads. The graph builder normalizes endpoints with
`tuple(sorted(...))` before merging traffic flow data, then adds an
**undirected** edge. Phase 2 can layer directional time-of-day costs on
top without restructuring the graph.

### `ensure_seeded()` is idempotent
Each table is checked for emptiness before insert. This keeps
`python app.py` cheap on subsequent runs and prevents tests from
duplicating fixtures when run repeatedly.

### Programmer Mode is a `dcc.Store`
The toggle in the top bar updates a `dcc.Store(id="programmer-mode")`
which Phase 2+ components can subscribe to. The visual switch is a
hand-rolled HTML toggle (not a stock `dbc.Switch`) to keep the dark
aesthetic consistent without restyling Bootstrap.

### CartoDB Dark Matter tiles
Used as specified. Attribution is rendered with reduced opacity to keep
focus on the network. The tile request URL is in `src/config.py` so it
can be swapped out (e.g. for an offline tile server) in one place.

### Sidebar mode pills use pattern-matching IDs
Each pill is `id={"type": "mode-pill", "mode": <mode_id>}`. The
callback uses `Input({"type": "mode-pill", "mode": ALL}, "n_clicks")`
plus `ctx.triggered_id` to detect which pill fired without writing five
parallel callbacks.

## Deviations from spec

- **None functional.** All eight CSVs, all eleven tables, all five mode
  pills, both placeholder buttons, the time-of-day slider, and the
  Programmer Mode toggle are present.
- The `info_card` helper takes the title via the `title=` parameter
  rather than as the first positional arg — the spec didn't enforce
  signatures, this just felt clearer at call sites.
- Added a small `empty_panel(message)` helper — useful for empty states
  and not adding scope, just convenience for Phase 2.

## Data findings

### Duplicate road in existing_roads.csv
Rows 15 (`7,15,9.8,3000,9`) and 24 (`15,7,9.8,3000,9`) describe the
same undirected road between Sheikh Zayed (15) and 6th October City
(7) with identical attributes. The DB ingests both rows (so
`test_existing_roads_loaded` asserts 28), but the graph builder
collapses them via `has_edge()`, yielding 27 unique undirected edges.
`test_edge_count` therefore asserts 27, not 28. Documented inline in
`src/graph/builder.py` so the next reader doesn't chase a phantom bug.

### Six unconnected facilities
F3 (Cairo University), F4 (Al-Azhar University), F5 (Egyptian Museum),
F6 (Cairo International Stadium), F9 (Qasr El Aini Hospital), and F10
(Maadi Military Hospital) have **no rows** in `existing_roads.csv`.
They appear on the map (and in `node_lookup()`) but are isolated
singletons in the graph. Phase 1 ships them as-is; Phase 2's MST /
road-expansion mode will connect them using `potential_roads.csv`.
The connectivity test threshold is 0.76 (19 connected nodes / 25
total) to reflect this.

## Recommendations for Phase 2

1. **Algorithm contract.** When implementing Dijkstra, return
   `(path, AlgorithmTrace)` — fill `nodes_explored` with the visit
   order, `edges_relaxed` with a counter, `code_snippet` with
   `inspect.getsource(<func>)`. This unlocks Programmer Mode rendering
   for free via `programmer_panel(trace)`.
2. **Time-of-day cost.** Edge weight should be
   `distance_km * traffic_factor(time_of_day, capacity, flow)`. The
   `traffic` dict already lives on every edge — no DB round-trip
   needed.
3. **Route picker UI.** Reuse `info_card` in the sidebar; add two
   `dcc.Dropdown`s populated from `node_lookup()`.
4. **Result drawing.** Add a `LayerGroup(id="route-overlay")` to the
   map, then update its children from the route callback. Don't rebuild
   the whole map.
5. **Persistence.** Every successful query should write to
   `RouteQuery` — that table already exists and gives Phase 7 a free
   "recent queries" feature.
6. **Caching.** `ResultCache` exists for memoization of expensive
   queries (e.g. all-pairs shortest paths used in the maintenance DP).
   Use a stable cache key: `f"{algo}:{from}:{to}:{tod}:{closed_hash}"`.

## Open questions for the user

- Should `13` (New Administrative Capital) be considered "in scope" for
  shortest-path queries, or filtered out by default? It's a 35–82 km
  outlier that will dominate every chart unless the UI handles it.
- Is the "What If?" button supposed to mutate scenario state in the
  store, or open a modal? Phase 1 ships it as a no-op — clarify before
  Phase 2.
