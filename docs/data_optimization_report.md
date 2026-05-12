# Data Optimization Report

## Summary

We preserved the original dataset as the source of truth and added a
backward-compatible optimization layer. This layer enriches the data with
travel-time weights, congestion scores, maintenance priorities, and inferred
medical emergency connectors. The inferred connectors are used only in
emergency/routing graph views and are clearly marked as non-original.

## Why The Original Dataset Was Not Edited

The raw CSE112 dataset in `data/raw/*.csv` remains unchanged so existing tests,
seed logic, UI callbacks, and algorithm assumptions continue to work. The
legacy graph builder still creates the same base graph from seeded data. Any
calculated fields or inferred edges live only in copied records and opt-in graph
views under `src/data`.

## What The Optimization Layer Adds

- Validation for IDs, road endpoints, traffic rows, numeric ranges, transit
  station/stop IDs, demand pairs, duplicate bidirectional roads, isolated nodes,
  isolated Medical facilities, and connectivity.
- Enriched road copies with `estimated_speed_kmh`, `base_travel_time_min`,
  utilization by time period, time-dependent costs, congestion score,
  maintenance priority score, emergency priority score, `is_original=True`, and
  `is_inferred=False`.
- Inferred Medical emergency connector edges for isolated Medical facilities.
- Graph views for base, routing, emergency, MST, traffic-by-time, and transit
  analysis.

## Inferred Medical Emergency Connectors

F9 (`Qasr El Aini Hospital`) and F10 (`Maadi Military Hospital`) are Medical
facilities in the original dataset, but they have no existing road edges. The
optimization layer detects this and creates one connector from each isolated
Medical facility to the nearest connected road node by coordinate distance.

Every connector is marked with:

- `is_inferred = True`
- `is_original = False`
- `connector_type = "medical_emergency_connector"`
- `connected_to_nearest_node = True`
- `reason = "Medical facility was isolated in the original dataset and was connected for emergency routing."`
- a positive confidence score

These connectors are not written back to CSV or database tables.

## Graph Views

- `base_graph`: original existing roads only, no inferred connectors. Preserves
  original behavior, including no path to isolated F9/F10.
- `routing_graph`: original roads plus inferred connectors for opt-in route
  planning.
- `emergency_graph`: original roads plus inferred Medical emergency connectors.
  This is the intended view for emergency A* routing.
- `mst_graph`: undirected normalized view for MST analysis. Duplicate
  bidirectional roads are normalized in the view only.
- `traffic_graph_morning`, `traffic_graph_afternoon`,
  `traffic_graph_evening`, `traffic_graph_night`: enriched views with positive
  time-dependent weights.
- `transit_graph`: multimodal graph built from the optimized base graph plus
  bus and metro records.

## Before / After Results

| Metric | Before | After |
| --- | ---: | ---: |
| Original node count | 25 | 25 |
| Original existing-road row count | 28 | 28 |
| Base graph edge count | 27 | 27 |
| Inferred connectors | 0 | 2 |
| Medical facilities connected | 0 / 2 | 2 / 2 |
| Isolated Medical facilities | F9, F10 | none in `emergency_graph` |
| Emergency route 1 -> F9 | no path | `1 -> 3 -> F9`, 10.94 min |
| Emergency route 1 -> F10 | no path | `1 -> F10`, 1.11 min |
| Dijkstra 1 -> F1 | `1 -> 3 -> 5 -> F1`, 22.1 km | unchanged |
| A* 1 -> F1 | `1 -> 3 -> 5 -> F1`, 22.1 km | unchanged |
| MST largest component | 19 nodes, 18 MST edges | unchanged |

## Highest Risk Roads

Top congestion-risk existing roads:

1. `6-9` with congestion score `1.00`
2. `2-3` with congestion score `0.96`
3. `3-10` with congestion score `0.96`
4. `11-F2` with congestion score `0.95`
5. `3-6` with congestion score `0.95`

Top maintenance-priority existing roads:

1. `8-12` with maintenance score `119.54`
2. `12-1` with maintenance score `82.32`
3. `7-8` with maintenance score `79.10`
4. `14-13` with maintenance score `57.80`
5. `10-11` with maintenance score `56.91`

Top recommended potential roads by simple capacity-per-cost-per-distance score:

1. `9-11` with score `2898.55`
2. `6-8` with score `2222.22`
3. `5-4` with score `651.04`
4. `14-5` with score `503.66`
5. `1-4` with score `389.86`

## Test Results

Before changes:

- `pytest -q` using the ambient Python failed during collection because old
  workspace temp folders were inaccessible on Windows.
- `pytest -q tests` using the ambient Python failed because that interpreter
  did not have project dependencies such as SQLAlchemy installed.
- `.\.venv\Scripts\python.exe -m pytest -q tests` passed: `110 passed`.

After changes:

- `.\.venv\Scripts\python.exe -m pytest -q tests\test_data_optimization.py`
  passed: `11 passed`.
- `.\.venv\Scripts\python.exe -m pytest -q tests` passed: `121 passed`.

## Remaining Limitations

- Inferred connectors are coordinate-based approximations, not surveyed road
  segments.
- The connector confidence score is conservative and should not be treated as
  ground-truth infrastructure quality.
- The existing UI still uses the legacy graph builder unless a caller opts into
  the new graph views.
- F3, F4, F5, and F6 remain isolated in the base graph because they are not
  Medical emergency targets.

## How To Disable The Optimized Layer

Use the existing legacy imports:

```python
from src.graph.builder import build_graph, build_mst_graph
```

To use the optimized layer, import graph views explicitly:

```python
from src.data.graph_views import build_emergency_graph

G = build_emergency_graph()
```

