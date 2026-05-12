# AI Tools and Technologies

CairoFlow combines classical graph algorithms, optimization techniques,
simulation, and a small machine-learning component into one smart-city
transportation dashboard.

## Machine Learning Traffic Prediction

The bonus ML feature uses scikit-learn's `RandomForestRegressor` to
forecast traffic volume-to-capacity behavior from the provided temporal
traffic dataset.

The model is trained on rows derived from the existing traffic flow data
across time periods:

- morning peak
- afternoon
- evening peak
- night

It uses road, node, capacity, condition, distance, and time-period
features to predict congestion-related values. The ML Forecast card is
available in Route Mode and is demo-ready: clicking `ML forecast` shows
model metrics, feature importance, and sample predictions near the
button.

## Algorithmic Technologies

CairoFlow includes:

- Dijkstra shortest path routing.
- A* routing with geographic heuristic.
- Time-dependent routing with BPR-style traffic costs.
- Emergency dispatch using an opt-in emergency graph with inferred
  non-original Medical connectors.
- Minimum Spanning Tree infrastructure planning.
- Dynamic Programming for public transport allocation and maintenance
  budgeting.
- Greedy traffic signal and priority optimization.
- Multimodal routing over road, metro, bus, and transfer segments.
- Simulation scenarios for traffic, closures, emergency dispatch,
  maintenance, transit, and multimodal demand.

## Dijkstra vs A* Race Visualizer

The Route Mode bonus visualizer compares Dijkstra and A* side by side.
The server captures step-by-step search frames, and the browser animates
the race so users can compare explored nodes, runtime, cost agreement,
and winner by node count.

## Development Support From AI Tools

AI tools were used as engineering assistants for:

- reviewing project structure and feature coverage,
- designing safe validation and test plans,
- drafting documentation,
- identifying integration risks,
- proposing minimal patches,
- strengthening regression tests,
- checking deployment-readiness gaps.

The AI tools did not replace algorithmic understanding or project
validation. Every production-relevant change was verified through the
pytest suite and import smoke checks, and the original raw dataset
remained the source of truth.

## Verification

Current verification command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests
```

Current verified result:

```text
151 passed
```
