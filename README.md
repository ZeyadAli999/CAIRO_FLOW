# CairoFlow

Smart City Transportation Network Optimizer for Greater Cairo. Built
for CSE112 (Design & Analysis of Algorithms). All four phases shipped.

## Submission Links

| Item | Link |
|---|---|
| GitHub repository | TODO: add GitHub repo URL |
| Live demo | TODO: add Render live demo URL |
| Demo video | TODO: add demo video URL |
| LinkedIn post | TODO: add LinkedIn post URL |

Deployment and bonus documentation:

- [Deployment guide](docs/deployment.md)
- [AI tools and technologies](docs/ai_tools_and_technologies.md)
- [Submission notes](docs/submission_notes.md)

## What's inside

- **Network mode** — Kruskal & Prim MST, population-weighted variant,
  cost-effectiveness analysis vs building all potential roads.
- **Route mode** — Dijkstra, time-aware Dijkstra (BPR), A*, top-K
  alternative routes with edge penalties, "avoid these roads"
  exclusions, congestion-segmented overlays.
- **Emergency mode** — A* with admissible heuristic, A*-vs-Dijkstra
  performance comparison, traffic-aware vs naive-routing impact card,
  faded exploration frontier on the map.
- **Maintain mode** — 0/1 knapsack DP for road repair budgeting at any
  budget from 200 to 2000 M EGP.
- **Transit mode** — bus & metro fleet allocation DPs, multimodal
  Dijkstra (road + metro + bus + transfer penalty), transfer-hub
  ranking by usage × demand.
- **Simulation framework** — 8 scenarios with both Python API and
  CLI: `peak_rush`, `road_closure`, `emergency_dispatch`,
  `all_pairs_baseline`, `transit_optimization`, `maintenance_budget`,
  `signal_audit`, `multimodal_demand`.
- **Programmer Mode** — every algorithm exposes an `AlgorithmTrace`
  dataclass with complexity, runtime, formula, plain-English
  explanation, and the function source — toggled live from the topbar.
- **Bonus route lab** — side-by-side Dijkstra vs A* race replay and an
  ML traffic-forecast card powered by a scikit-learn random forest.
  The ML Forecast card is demo-ready in Route Mode and appears
  immediately below the `ML forecast` button.
- **Premium Cairo control map** - MapLibre GL JS front end centered on
  Egypt and Greater Cairo, with 3D-style facility/neighborhood
  extrusions, traffic-colored corridors, day/night atmosphere, route
  glow, transit overlays, and maintenance/scenario highlighting.
- **Interactive city controls** - Play 24h advances Morning,
  Afternoon, Evening, Night, then back to Morning while preserving the
  current route/scenario. What If scenarios temporarily adjust a copied
  graph in memory and compare before/after ETA without changing the
  seeded data or algorithm implementations.

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate              # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                         # or: .\.venv\Scripts\python.exe app.py
```

Then open http://127.0.0.1:8050.

On first run, `data/cairo.db` is seeded from the CSVs in `data/raw/`.

## Docker

```bash
docker build -t cairoflow .
docker run --rm -p 8050:8050 cairoflow
```

Then open http://127.0.0.1:8050.

The container uses the existing `requirements.txt` and starts the app
with:

```bash
gunicorn app:server --bind 0.0.0.0:${PORT:-8050}
```

## Render Deployment

The repository includes `render.yaml` for Render Web Service deployment.

Render settings:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:server --bind 0.0.0.0:$PORT`
- Health check path: `/healthz`

See [docs/deployment.md](docs/deployment.md) for the full deployment
checklist.

## Premium 3D Map Setup

The dashboard map uses MapLibre GL JS with vector styles, not pitched
raster tiles. The browser needs internet access for MapLibre and vector
tile/CDN resources.

Style priority:

1. `MAP_STYLE_URL` - use any MapLibre-compatible style JSON URL.
2. `MAPTILER_KEY` - uses MapTiler `streets-v2`.
3. OpenFreeMap Bright - keyless vector fallback used for local demos.

Real 3D building extrusions appear when the loaded vector style exposes a
building source/layer. If no real building source is available, CairoFlow
uses dataset-based operational extrusions for neighborhoods/facilities.
Those fallback extrusions are an operational visualization, not real
Cairo building footprints.

If vector resources cannot load, the map shows a non-blocking warning
instead of silently presenting a blurry raster fallback as premium.

## Demo Flow

1. Start the app with `python app.py`.
2. Click `Start Simulation`.
3. Show the Morning view.
4. Switch to Afternoon.
5. Switch to Evening.
6. Switch to Night.
7. Run Maadi -> Cairo International Airport.
8. Press `Play 24h`.
9. Open `What If?`.
10. Apply `Road closure`.
11. Show before/after ETA.
12. Click `Reset Scenario`.
13. Run `Dijkstra vs A*` race.
14. Click `ML forecast` and show the visible ML prediction card.
15. Show Emergency mode.
16. Show Transit mode.

## Data optimization layer

The original CSV dataset in `data/raw/` remains the source of truth.
CairoFlow also includes an opt-in data optimization layer under
`src/data/` for validation, enriched graph views, inferred Medical
emergency connectors, and heuristic potential-road recommendations.

- `build_base_graph()` preserves original existing-road behavior.
- `build_emergency_graph()` adds clearly marked inferred Medical
  connectors for F9/F10 emergency routing.
- `recommend_potential_roads()` ranks potential roads with an
  explainable heuristic; it does not edit source data.

## Bonus Coverage

| Bonus item | Current evidence |
|---|---|
| Early submission | External proof required; record it in `docs/submission_notes.md`. |
| AI tools & technologies | Documented in `docs/ai_tools_and_technologies.md`. |
| Enhanced visualization & UI | Dash dashboard, MapLibre map, algorithm panels, race visualizer, ML Forecast card. |
| Deployment & engineering | `Dockerfile`, `.dockerignore`, `render.yaml`, `/healthz`, reliable pytest command. |
| GitHub + demo + LinkedIn | Placeholders included above; final links must be added after publishing. |
| ML traffic prediction | `src/ml/traffic_predictor.py`, Route Mode ML Forecast card, and ML tests. |
| Dijkstra vs A* comparison | `src/algorithms/race.py`, `src/ui/race_view.py`, `assets/race.js`, and race tests. |
| Live web app | Render config is present; final URL must be added after deployment. |
| Docker containerization | `Dockerfile` and `.dockerignore` are present. |

## Run tests

```bash
.\.venv\Scripts\python.exe -m pytest -q tests
```

The full suite covers Phase 1 (DB, graph), Phase 2 (MST), Phase 3
(shortest path + simulator), Phase 4 (DP + greedy + multimodal +
correctness suite), the safe data optimization layer, Emergency Medical
coverage, potential-road recommendations, plus bonus ML and
algorithm-race coverage. 151 tests are currently passing.

With the virtual environment activated, `pytest -q` also works because
`pytest.ini` limits discovery to `tests/` and ignores old temporary
workspace folders.

## Verify health (live)

```bash
curl -s http://127.0.0.1:8050/healthz | python -m json.tool
```

Returns `tests_passing`, `callbacks_registered`,
`assets_present`, `lucide_icons_in_layout`, current ISO timestamp.

## Run a simulation scenario from the command line

```bash
# DP scenarios
python -m src.simulation.framework --scenario maintenance_budget
python -m src.simulation.framework --scenario transit_optimization --total-buses 200

# Greedy
python -m src.simulation.framework --scenario signal_audit --tod morning_peak

# Multimodal
python -m src.simulation.framework --scenario multimodal_demand

# Phase 3 scenarios
python -m src.simulation.framework --scenario peak_rush --from 1 --to F1
python -m src.simulation.framework --scenario road_closure --from 1 --to 2 --closed "1-3"
python -m src.simulation.framework --scenario emergency_dispatch --from 11 --facility-type "Transit Hub"
python -m src.simulation.framework --scenario all_pairs_baseline
```

Add `--json` to any scenario to emit machine-readable output.

## Browser cache

The app sends `Cache-Control: no-cache, no-store, must-revalidate`
on the index page so a hard refresh (`Ctrl+Shift+R` / `Cmd+Shift+R`)
isn't usually needed. If you see stale CSS or assets, hard-refresh
once or open an incognito window.

## Layout

```
cairoflow/
├── app.py                    Dash entry point + 29 callbacks + /healthz
├── conftest.py
├── requirements.txt
├── data/
│   ├── raw/*.csv             8 source datasets
│   └── cairo.db              SQLite, created on first run
├── src/
│   ├── config.py
│   ├── db/                   SQLAlchemy models, seed, queries
│   ├── graph/                NetworkX builder (build_graph + build_mst_graph)
│   ├── algorithms/
│   │   ├── trace.py          AlgorithmTrace dataclass — UI contract
│   │   ├── mst.py            Kruskal, Prim, population-weighted MST
│   │   ├── shortest_path.py  Dijkstra, BPR, A*, alternatives, nearest facility
│   │   ├── race.py           Step-captured Dijkstra vs A* replay data
│   │   ├── dp.py             Bus/metro scheduling, knapsack, memoization
│   │   ├── greedy.py         Signal allocation, preemption, audit
│   │   └── multimodal.py     Road+metro+bus fused graph, transfer analysis
│   ├── ml/
│   │   └── traffic_predictor.py
│   ├── simulation/
│   │   └── framework.py      TransportSimulator + 8 scenarios + CLI
│   └── ui/
│       ├── components.py     cf_icon, cf_button, empty_state, programmer_panel
│       ├── layout.py         topbar, control strip, dcc.Stores
│       ├── sidebar.py        mode-pill dispatcher
│       ├── network_mode.py   MST controls
│       ├── route_mode.py     Routing controls
│       ├── emergency_mode.py Dispatch controls
│       ├── maintain_mode.py  Repair-budget DP
│       ├── transit_mode.py   Bus / metro / multimodal / transfers
│       ├── map_view.py       Map shell + hidden Leaflet compatibility layers
│       └── theme.py          Color tokens
├── assets/
│   ├── NEW_LOGO.png          User-supplied logo
│   ├── style.css
│   ├── clientside.js         Success-pulse, hero bridge, MapLibre bridge
│   ├── maplibre_view.html    Premium Cairo MapLibre iframe
│   ├── maplibre_view.js      MapLibre layers, 24h visuals, scenario overlays
│   ├── race.js               Route race canvas animator
│   └── logo.svg              (vestigial; kept on disk per spec)
├── tests/                    151 passing pytest tests
├── PHASE1_NOTES.md
├── PHASE2_NOTES.md
├── PHASE3_NOTES.md
└── PHASE4_NOTES.md
```

## License

Coursework submission. Copyright held by the authors.
