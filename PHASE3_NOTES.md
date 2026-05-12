# Phase 3 — Routing, Simulation & Visual Polish

This phase delivered the shortest-path algorithm family, a formal
`TransportSimulator` framework, polished Route + Emergency mode UIs, a
visual polish pass across the whole shell, and tests covering every
Phase 3 entry point.

## What shipped

### Algorithms — `src/algorithms/shortest_path.py` (781 lines)
- `dijkstra(G, source, target, weight='distance_km')`
- `dijkstra_time_dependent(G, source, target, time_of_day)` — BPR weights
- `astar(G, source, target, weight='distance_km')` — Euclidean-km heuristic
- `astar_emergency(G, source, target, time_of_day)` — BPR weights, Euclidean/60 heuristic
- `find_nearest_facility(G, source, facility_type, facilities=None, time_of_day=...)`
- `find_alternative_routes(G, source, target, time_of_day, k=3, excluded_edges=None)` — top-K via repeated Dijkstra with edge penalties
- Module helpers: `bpr_travel_time_hours`, `edge_travel_time`, `edge_congestion_ratio`, `euclidean_km`, `path_distance_km`, `path_travel_time_hours`, `path_max_congestion`, `path_segments`

All implemented from first principles (heapq + dicts). NetworkX is
used only for `.neighbors()` / `.nodes()` traversal.

### Simulation — `src/simulation/framework.py` (438 lines)
- `TransportSimulator(graph, traffic_data=None, facilities_df=None)`
- `run_scenario(name, **params)` for `peak_rush`, `road_closure`,
  `emergency_dispatch`, `all_pairs_baseline`
- `measure_response_time(source, facility_type, time_of_day, algorithm)`
- `measure_congestion_reduction(source, target, time_of_day)`
- `compare_algorithms(source, target, time_of_day)`
- CLI: `python -m src.simulation.framework --scenario peak_rush --from 1 --to F1 [--tod morning_peak] [--json]`

### UI — Route mode (`src/ui/route_mode.py`)
- FROM / TO dropdowns with category-prefixed labels (● neighborhood / ◆ facility)
- Algorithm pills: Dijkstra / Time-Aware / A*
- Checkbox: "Show alternative routes (top 3)"
- Multi-select "Avoid these roads"
- Find Route button (cyan gradient, primary style)
- Result card with distance, travel time, max congestion + worst segment, via, weight mode
- "vs night" comparison strip
- Alternatives card with click-to-highlight cards

### UI — Emergency mode (`src/ui/emergency_mode.py`)
- Incident dropdown, Facility-type radio (Medical / Any), Traffic radio (current / ignore)
- Dispatch button (red gradient with red glow shadow)
- Three result cards: dispatch result, A*-vs-Dijkstra performance, traffic-awareness impact

### Map updates — `src/ui/map_view.py`
- New polished node radii: `r = 4 + sqrt(pop/50000) * 1.2` (capped at 14px), with halo rings (1px, 30% opacity)
- `lineCap: round`, `lineJoin: round` everywhere
- New LayerGroups: `route-glow-layer`, `route-edges-layer`, `route-markers-layer`, `route-alts-layer`, `em-glow-layer`, `em-edges-layer`, `em-markers-layer`, `em-explored-layer`
- `route_overlay_layers()` segments by congestion (green < 0.6, amber < 0.85, red ≥ 0.85)
- `route_marker_layers()` — pulsing source halo (`cf-pulse` class), target ring + dot
- `emergency_overlay_layers()` — red glow + edges
- `emergency_explored_layer()` — faded red dots showing A*'s frontier
- `emergency_marker_layers()` — pulsing red incident, red cross at facility (two short polylines)
- `alternative_routes_layer()` with weight/dash variants per rank, click-to-highlight via the `_highlight_alt_route` callback

### Visual polish CSS (`assets/style.css`, 489 → 700+ lines)
- Card radius bumped to 14px, softer shadow (0 1px 2px rgba(0,0,0,0.4) + inset highlight)
- `.cf-pill.active` — 2-tone vertical gradient, accent box-shadow
- Premium button gradients: `.cf-btn-primary` (cyan), `.cf-btn-danger` (red with red-glow shadow), `.cf-btn-accent` (outline gradient)
- Hover: `filter: brightness(1.08)` + larger shadow; active: `brightness(0.95)` + translateY(1px)
- `font-variant-numeric: tabular-nums` on `.cf-stat-value`, `.cf-prog-panel code`, `.cf-prog-snippet`
- `cf-pulse` and `cf-pulse-danger` keyframe animations for SVG `<path>` markers (animate `stroke-opacity` + `stroke-width` — Leaflet markers are SVG paths, not boxes)
- `.cf-dd` overrides for the Dash dropdown so the rendered Select control matches the dark theme (background, options, multi-select chips)
- `.cf-radio` styled radio buttons (custom radial-gradient dot when checked)
- `.cf-comparison-strip` for the off-peak comparison line
- `.cf-alt-card` hover state (cyan-tinted border + shadow)
- Inter + JetBrains Mono webfonts, antialiased, line-height 1.5
- All h1..h6 → `font-weight: 600` with `letter-spacing: -0.02em`

### Stores added — `src/ui/layout.py`
- `route-algo` (default `time_aware`)
- `route-result`
- `em-result`
- Topbar text: "Phase 3 · Routing & Simulation"

### Callbacks added — `app.py`
- `_switch_route_algo` — pattern-matching algo pills
- `_compute_route` — runs Dijkstra / time-aware / A*, applies excluded edges, paints overlay segments by congestion, optional top-3 alternates, primary result card, alternatives card, programmer panel
- `_dispatch_emergency` — A* nearest-facility, Dijkstra parallel for the comparison card, traffic-awareness card (current TOD vs night as naive baseline), explored-frontier overlay
- `_highlight_alt_route` — click-to-emphasize alternate routes (re-runs k-alts with `selected_idx`)
- TOD label-to-key mapping (`Morning` → `morning_peak`, etc.)

### Network mode — MST cost-display fix
`render_stats_card` now matches spec exactly:
- `cost == 0` → "EGP 0M  — all existing roads, no new construction"
- `cost > 0` → "EGP {cost:.1f}M  (saves N% vs. building all)" — uses
  `all_potential_cost_million_egp` from the new `mst_stats` field
- Added a Cost-effectiveness row: `EGP X.XXM per connected node`
- Units suffixed on every numeric value (edges, nodes, EGP)

### Tests — `tests/test_shortest_path.py` (14 tests) + `tests/test_simulation.py` (10 tests)

`test_shortest_path.py`:
1. Dijkstra finds correct path (1 → 3 = 8.5 km)
2. Dijkstra multi-hop (1 → F1)
3. Dijkstra returns `(None, inf)` for disconnected target (1 → F9)
4. A* matches Dijkstra's optimal cost
5. A* explores ≤ Dijkstra's nodes (12 → F1)
6. A* returns None for disconnected target
7. BPR: morning_peak > night on edge 4 → 2
8. BPR is monotonic in flow
9. BPR at v/c = 1.5 → travel_time > 1.5 × t_free
10. Time-dependent Dijkstra returns hours > 0 with BPR formula in trace
11. A* emergency admissible + finds path + explores ≤ Dijkstra
12. Nearest facility — connected type (11 → Transit Hub = F2)
13. Nearest facility — isolated Medical type → handled gracefully
14. Alternative routes — distinct paths
15. Alternative routes — excluded edges respected
16. Trace contracts (Dijkstra, A*, time-dependent)

`test_simulation.py`:
1. `peak_rush` returns dict with all four times-of-day
2. `road_closure` — every alternative avoids the closed edge
3. `emergency_dispatch` — A* nodes ≤ Dijkstra nodes
4. `all_pairs_baseline` — exactly 19 × 18 = 342 reachable pairs
5. Unknown scenario raises ValueError
6. `measure_response_time` (A*) returns positive ETA
7. `measure_response_time` (Dijkstra)
8. `compare_algorithms` returns 3 algorithm entries + speedup
9. `measure_congestion_reduction` returns ≥ 0
10. CLI `main()` callable with peak_rush args

## Decisions

### BPR threshold deviation from the spec
The Phase 3 spec said `"BPR: when v/c > 0.85, travel_time > 1.5 × t_free"`.
With α = 0.15 and β = 4 (the formula given in the same spec), at
v/c = 0.85 the multiplier is **1.078**, not > 1.5. The `1.5 × t_free`
threshold is only crossed once v/c ≈ 1.4.

The implementation uses the formula exactly as specified, and the test
asserts what's actually true: at v/c = 1.5 the multiplier exceeds 1.5.
A second test asserts BPR is monotonic across the four times-of-day,
and a third asserts morning_peak > night on edge 4 → 2 (which uses
real data: 3600 vs 750 flow on a 3800-capacity link). Documented in
the test docstring inline.

### `find_nearest_facility` Medical case
F9 (Qasr El Aini Hospital) and F10 (Maadi Military Hospital) have no
rows in either `existing_roads.csv` or `potential_roads.csv` — they
are completely isolated singletons in the Phase 1 dataset. So
`find_nearest_facility(G, '11', 'Medical', ...)` cannot return a path.

The implementation handles this by returning `(None, None, inf, trace)`
without raising, and the trace records the candidate list. The test
`test_nearest_facility_isolated_type_handled` asserts this graceful
behavior. The positive test uses Transit Hub (F2 is connected) so we
verify the success path on real data.

This is a **data limitation**, not an algorithm bug. Phase 4 should
either extend the road CSVs to give hospitals at least one connection
each, or the Emergency mode should fall back to "Any" facility type
when Medical returns no path.

### Dropdown styling complexity
Dash `dcc.Dropdown` ships with a stock react-select skin that's
white-on-white in dark themes. Phase 3 adds `.cf-dd` selector
overrides covering both v1 (`.Select-control`) and v2
(`.Select__control`) class names so it renders correctly across Dash
versions. This is the largest single CSS addition in the polish pass.

### Click-to-highlight alternative routes
The spec asked for hover-to-highlight; Dash's pattern-matching
callbacks fire on click, not hover. So clicking an alternative card
re-renders the alternatives layer with `selected_idx=N`, which boosts
the chosen route's weight + opacity. The hover styling (border tint)
is pure CSS via `:hover`. This is a deliberate substitution
documented inline.

### TOD label vs key
The map control strip uses human labels (`Morning`, `Afternoon`,
`Evening`, `Night`) — the slider's marks. Algorithms and graph
attributes use snake_case keys (`morning_peak`, `afternoon`,
`evening_peak`, `night`). A `_TOD_KEY` map in `app.py` translates
between them. Saves us from changing the slider labels (which would
hurt readability).

### Pulse animation strategy
Leaflet renders `dl.CircleMarker` as an SVG `<path>` element, not a
DOM box. CSS `transform: scale()` doesn't work because SVG paths
are positioned by coordinates. Instead, the pulse animations
(`cf-pulse`, `cf-pulse-danger`) animate `stroke-opacity` and
`stroke-width`, which work directly on SVG paths. The class is set
via `pathOptions: {"className": "cf-pulse"}`, which Leaflet forwards
to the underlying `<path>`.

### Single-callback recompute on Programmer Mode toggle
Same pattern as the Phase 2 MST callback. Toggling the global
Programmer Mode store re-runs the active mode's compute function
(cheap at our scale: ~25 nodes). This avoids a partial-update
selective-output dance that Dash doesn't elegantly support across
multi-output callbacks.

## Verification

- All Python files byte-compile cleanly.
- Stdlib-only simulation (`_sim_phase3.py`, removed after running)
  walked every test assertion against the real CSVs:

```
1->3 distance: path=['1','3'], cost=8.5
1->F1 distance: path=['1','3','5','F1'], cost=22.10
1->F9: path=None
1->F1 dijkstra=22.1000, astar=22.1000
12->F1: dijkstra explored 12, astar explored 8
edge 4-2: morning=17.04 min, night=15.20 min  (BPR monotonic ✓)
BPR v/c=1.5: t=0.2932, 1.5*t_free=0.2500  (✓ > 1.5×)
1->F1 BPR-morning: 24.60 min
A*-emerg: explored 5 vs dijkstra 12
Nearest Transit Hub from 11: F2, path=['11','F2']
Medical facilities unreachable from 11 (as documented)
1->2 alts: 3 distinct routes
  ['1','3','2']
  ['1','8','10','3','5','2']
  ['1','8','10','11','5','2']
1->3 alts excluding direct (1,3): 3 routes, none traverse (1,3)
all_pairs reachable: 19 * 18 = 342 pairs
1->F1 reduction_pct: peak=24.60 min, night=22.12 min, red=10.05%
```

- `pytest -q` not run locally — pip is unavailable in this dev
  environment (msys64 Python lacks pip; the Python 3.13 path on
  PATH is a Windows Store stub). Run `pytest -q` in your installed
  Python 3.11+ environment to confirm Phase 1 + 2 + 3 (≈ 35 tests)
  pass.

## Acceptance criteria status

| # | Criterion | Status |
|---|---|---|
| 1 | Route mode → polished route appears with congestion-colored segments | ✓ |
| 2 | "Show alternative routes" overlays 3 distinct ranked routes | ✓ |
| 3 | "Avoid these roads" excludes edges | ✓ |
| 4 | Emergency mode → red route + A*-vs-Dijkstra performance card | ✓ |
| 5 | Programmer Mode shows BPR formula, complexity, plain English | ✓ |
| 6 | morning route time > night route time | ✓ (1→F1: 24.60 vs 22.12 min) |
| 7 | `python -m src.simulation.framework --scenario peak_rush` runs | ✓ |
| 8 | pytest -q passes all tests | ⚠ See above — verified by simulation, can't run pytest |
| 9 | Visual polish: halo rings, premium buttons, units, gradients | ✓ |
| 10 | MST cost shows "EGP 0M — all existing roads, no new construction" when cost is 0 | ✓ |

## Phase 3 polish pass (post-review)

After the initial Phase 3 ship the user flagged seven quality issues.
This pass addressed all of them without touching algorithm code.

### Issue 1 — State leaks between modes
Added `_clear_overlays_on_mode_switch` callback in `app.py` that fires
on every `active-mode` change with `allow_duplicate=True` outputs to
all 11 overlay LayerGroups + 6 result/trace stores. Per the spec:

| Active mode | Cleared layers |
| --- | --- |
| `network`   | route + emergency |
| `route`     | emergency (MST stays underneath) |
| `emergency` | route (MST stays underneath) |
| `maintain`  | all overlays |
| `transit`   | all overlays |

Sidebar result cards clear automatically because mode-specific slots
(`route-result-slot`, `em-result-slot`, etc.) are unmounted whenever
the sidebar swaps `mode-content`.

### Issue 2 — Persistent Dash console errors
Root cause: each compute callback had `Input("programmer-mode", "data")`.
Toggling Programmer Mode while in a different mode forced Dash to
look up that mode's button (e.g. `mst-compute`), which is unmounted →
"nonexistent object" errors flooded the console.

Fix: split each compute callback in two.
- The compute callback now fires **only** on its own button click. It
  serializes the `AlgorithmTrace` via `dataclasses.asdict` into a
  per-mode `*-trace` Store.
- A second small callback (`_render_*_programmer_panel`) listens to
  `programmer-mode` + the trace Store and rehydrates the panel via
  `AlgorithmTrace(**trace_data)`.

Result: programmer-mode toggling never re-fires compute, never
references buttons in inactive modes. Console clean.

### Issue 3 — Cheap-feeling buttons, no click feedback
- New `cf_button(label, btn_id, variant, icon)` helper in
  `components.py` (used by every action button).
- Result slots wrapped in `dcc.Loading(type="circle", color="…")`
  for instant spinner feedback.
- `assets/clientside.js` exposes
  `dash_clientside.cf.pulseButton(data, btnId)`. Three Dash
  `clientside_callback`s wire each result store to the matching
  button. The JS removes-then-re-adds `cf-btn-success-pulse` with a
  forced reflow so the keyframe replays on every result.
- New CSS keyframes: `cf-spin` (loader rotation) and
  `cf-success-pulse` (green box-shadow ripple, 600ms).
- Hover lifts buttons via `transform: translateY(-1px)` with a
  bouncier `cubic-bezier(0.16, 1, 0.3, 1)` curve.
- Active state presses with `translateY(1px)` + `brightness(0.92)`
  on an 80ms transition (snappier than the 200ms hover).

### Issue 4 — Custom CairoFlow logo + wordmark
- `assets/logo.svg` — three-node mark forming a stylized C, gradient
  cyan strokes between nodes, Gaussian-blur glow filter. Served from
  `/assets/logo.svg` via `html.Img`.
- Wordmark: `<span class="cf-wordmark-1">Cairo</span><span class="cf-wordmark-2">Flow</span>`
  — Inter 600 white + Inter 700 cyan, `letter-spacing: -0.01em`,
  18px, no space between words.
- Topbar refinement: `backdrop-filter: blur(8px)`, semi-transparent
  background, phase label restyled with `letter-spacing: 0.12em`
  uppercase.

### Issue 5 — Lucide icons via dash-iconify
- Added `dash-iconify==0.1.2` to `requirements.txt`.
- `cf_icon(name, size, color, ...)` in `components.py` wraps
  `DashIconify` with a defensive `try/except` import — if the
  package isn't installed yet, the function falls back to a styled
  span dot so the layout still renders.
- All five mode pills now use Lucide identifiers in `config.py`
  (`lucide:network`, `lucide:route`, `lucide:siren`, `lucide:wrench`,
  `lucide:bus`). Active pill icon paints `var(--accent)` cyan.
- All buttons use Lucide icons (`lucide:zap`, `lucide:navigation`,
  `lucide:siren`, `lucide:play`).
- Every stat row across Network / Route / Emergency modes leads with
  a 14px Lucide icon — `lucide:wallet`, `lucide:clock`, `lucide:cpu`,
  `lucide:gauge`, `lucide:hospital`, `lucide:ruler`, etc.
- Programmer Mode toggle flanked by `lucide:eye` (off) and
  `lucide:code-2` (on) icons.
- Removed the Font Awesome CDN stylesheet from `app.py`.

### Issue 6 — Premium polish
- **Cards**: `linear-gradient(180deg, var(--bg-tertiary), #232326)` +
  inset highlight + 14px radius + softer shadow.
- **Sidebar**: `mask-image: linear-gradient(to bottom, black 95%, transparent 100%)`
  for a soft fade when content overflows.
- **Leaflet zoom**: dark-themed buttons matching the rest of the UI
  (bg-tertiary / accent hover). Attribution control got
  `backdrop-filter: blur(4px)` and lower opacity.
- **Empty state**: dashed-border placeholder with a faded
  `lucide:sparkles` icon — shown in every result slot before its
  first compute click.
- **Topbar**: 1px bottom border, blur backdrop, phase label in
  uppercase muted text per spec.
- **Global transitions**: single rule covering buttons, pills, cards,
  alt-route cards, inputs, selects, leaflet controls — 200ms ease
  for color/border/shadow, 180ms `cubic-bezier(0.16, 1, 0.3, 1)` for
  transforms.
- **Tabular numerals**: `font-variant-numeric: tabular-nums` on
  `.cf-stat-value`, prog-panel codes, prog-snippet, controls labels.
- **Border radii standardized**: 14px cards, 12px buttons, 8px
  inputs/dropdowns/zoom controls.

### Issue 7 — Validation
- `pytest -q` → **53 passed in 2.05s** (full Phase 1 + 2 + 3 suite).
- App boots cleanly: `app.run(...)` serves `GET /` 200 in ≈ 200ms.
  `/_dash-layout` returns the full tree (41 KB) with `logo.svg`
  referenced, `cf-wordmark` class present, 11 Lucide icons rendered,
  `mst-pulse-effect` store present, 18 callbacks registered.
- Every algorithm test still passes — no algorithm code was touched
  in this pass.

### Files touched in the polish pass

| File | Change |
| --- | --- |
| `requirements.txt` | added `dash-iconify==0.1.2` |
| `assets/logo.svg` | new — three-node mark, gradient + glow |
| `assets/clientside.js` | new — `pulseButton` helper |
| `assets/style.css` | logo + wordmark, gradient cards, sidebar fade, leaflet restyle, spinner + success-pulse keyframes, empty state, transitions, premium-button hover/active |
| `src/config.py` | mode icons → Lucide identifiers |
| `src/ui/components.py` | added `cf_icon`, `empty_state`, `cf_button`; `mode_pill` auto-detects Lucide vs FA; `programmer_panel` polished |
| `src/ui/layout.py` | new logo + wordmark, refined topbar, programmer toggle with eye/code icons, three new pulse-effect stores, three trace stores |
| `src/ui/network_mode.py` | `cf_button`, `dcc.Loading`, empty state, Lucide icons in every stat row |
| `src/ui/route_mode.py` | same pattern as Network |
| `src/ui/emergency_mode.py` | same pattern, danger button + danger-tinted `dcc.Loading` |
| `app.py` | major refactor — decoupled programmer-mode callbacks, mode-switch clearing callback, three clientside success-pulse callbacks, removed FA cdn |

## Recommendations for Phase 4

1. **Connect the hospitals.** F9 ↔ 3 and F10 ↔ 1 are obvious short
   links (~1 km each). Adding them to `potential_roads.csv` lets the
   "Medical" emergency case actually work end-to-end.
2. **Pull the TOD store into a callback Output**, not just an Input.
   Phase 3 reads it as a State on every compute; Phase 4 (DP +
   Greedy) probably wants to react to TOD changes immediately.
3. **Result-cache wiring.** Still unused. The DP scheduler in
   Phase 5 will want all-pairs Dijkstra results — perfect cache key.
4. **Animation ticker.** A shared `dcc.Interval` + `dcc.Store` would
   let `nodes_explored` lists animate in for both MST and route
   modes. Pushed forward each phase; should land before Phase 7
   polish.
5. **Reduce edge-color thresholds.** With BPR at α = 0.15, "red"
   (v/c > 0.85) only triggers on truly maxed links. Consider 0.7 as
   the amber threshold for more visual variety.
