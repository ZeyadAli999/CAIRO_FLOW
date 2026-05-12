"""ML-based traffic prediction (BONUS · CSE112).

A scikit-learn `RandomForestRegressor` trained on the temporal traffic
data shipped with the project (`traffic_flow.csv` × 4 times-of-day, 28
edges → 112 (edge, time-of-day) samples). Targets the v/c ratio
(observed flow / link capacity) and exposes both per-edge and
batch predictions.

Why this lives next to the algorithms — not inside them:
The classical Phase 1–4 algorithms read the **observed** v/c straight
from the database. The ML predictor instead **forecasts** v/c from
edge / endpoint features, so the route planner can ask
"what would Maadi → Downtown look like at evening_peak if traffic
patterns held steady?" without needing a live measurement on every
edge.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TODS: tuple[str, ...] = ("morning_peak", "afternoon", "evening_peak", "night")

FEATURE_COLS: list[str] = [
    "distance_km", "capacity", "condition",
    "pop_a", "pop_b",
    "is_facility_a", "is_facility_b",
    "tod_morning_peak", "tod_afternoon",
    "tod_evening_peak", "tod_night",
]

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "traffic_model.joblib"


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

@dataclass
class PredictResult:
    """Single-edge prediction shape (used by UI + simulator)."""
    edge: tuple[str, str]
    tod: str
    predicted_vc: float
    predicted_flow: int
    actual_vc: float | None = None     # None when the edge wasn't in training data
    actual_flow: int | None = None
    capacity: int = 0


class TrafficPredictor:
    """A small, deterministic, scikit-learn-based congestion forecaster.

    Public API:
      * `train(rows...)` — builds the dataset and fits the model. Returns
        the held-out metrics dict.
      * `predict_edge(...)` — single (edge, tod) prediction with both
        the v/c ratio and the implied flow.
      * `predict_all_edges(tod, ...)` — batch prediction for every
        edge in the road network at a chosen time-of-day.
      * `feature_importances()` — the model's view of which features
        matter most. Useful for the technical report.
      * `save(path)` / `load(path)` — joblib persistence.
    """

    def __init__(self) -> None:
        self.model: RandomForestRegressor | None = None
        self.metrics: dict[str, Any] = {}
        self.feature_names: list[str] = list(FEATURE_COLS)
        self._dataset: pd.DataFrame | None = None

    # ------------------------------------------------------------------
    # Dataset construction
    # ------------------------------------------------------------------

    def _build_dataset(
        self,
        traffic_rows: list,
        road_rows: list,
        neighborhood_rows: list,
        facility_rows: list,
    ) -> pd.DataFrame:
        """Join `traffic_flow.csv` × `existing_roads.csv` × neighborhoods
        & facilities into a feature dataframe (one row per (edge, tod))."""
        pop = {n.id: int(n.population) for n in neighborhood_rows}
        is_facility = {n.id: 0 for n in neighborhood_rows}
        for f in facility_rows:
            is_facility[f.id] = 1

        road_lookup: dict[frozenset, dict] = {}
        for r in road_rows:
            key = frozenset((r.from_id, r.to_id))
            road_lookup[key] = {
                "distance_km": float(r.distance_km),
                "capacity":    int(r.capacity),
                "condition":   int(r.condition),
            }

        rows: list[dict[str, Any]] = []
        for t in traffic_rows:
            key = frozenset((t.from_id, t.to_id))
            road = road_lookup.get(key, {"distance_km": 0.0, "capacity": 1, "condition": 5})
            for tod in TODS:
                flow = int(getattr(t, tod, 0) or 0)
                cap = max(1, road["capacity"])
                rows.append({
                    "from": t.from_id, "to": t.to_id, "tod": tod,
                    "distance_km":     road["distance_km"],
                    "capacity":        road["capacity"],
                    "condition":       road["condition"],
                    "pop_a":           pop.get(t.from_id, 0),
                    "pop_b":           pop.get(t.to_id, 0),
                    "is_facility_a":   is_facility.get(t.from_id, 0),
                    "is_facility_b":   is_facility.get(t.to_id, 0),
                    "tod_morning_peak":  int(tod == "morning_peak"),
                    "tod_afternoon":     int(tod == "afternoon"),
                    "tod_evening_peak":  int(tod == "evening_peak"),
                    "tod_night":         int(tod == "night"),
                    "flow":     flow,
                    "vc_ratio": flow / cap,
                })
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # Train
    # ------------------------------------------------------------------

    def train(
        self,
        traffic_rows: list,
        road_rows: list,
        neighborhood_rows: list,
        facility_rows: list,
        test_size: float = 0.2,
        random_state: int = 42,
        n_estimators: int = 120,
        max_depth: int = 8,
    ) -> dict[str, Any]:
        df = self._build_dataset(
            traffic_rows, road_rows, neighborhood_rows, facility_rows
        )
        if df.empty:
            raise ValueError("Empty dataset — no traffic rows to train on.")

        X = df[FEATURE_COLS].to_numpy()
        y = df["vc_ratio"].to_numpy()

        # Stratify-ish: shuffle deterministically so test_size cuts cleanly.
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y, test_size=test_size, random_state=random_state,
        )
        self.model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=random_state,
            n_jobs=1,                # determinism + free-tier CPU friendliness
        )
        self.model.fit(X_tr, y_tr)
        y_pred = self.model.predict(X_te)

        # Plain Dijkstra-style baseline: predict mean of training labels.
        baseline_pred = np.full_like(y_te, fill_value=float(np.mean(y_tr)))
        self.metrics = {
            "n_samples":     int(len(df)),
            "n_train":       int(len(X_tr)),
            "n_test":        int(len(X_te)),
            "n_features":    int(len(FEATURE_COLS)),
            "r2":            float(r2_score(y_te, y_pred)),
            "mae":           float(mean_absolute_error(y_te, y_pred)),
            "baseline_mae":  float(mean_absolute_error(y_te, baseline_pred)),
            "baseline_r2":   float(r2_score(y_te, baseline_pred)),
            "improvement_pct": float(
                (mean_absolute_error(y_te, baseline_pred) - mean_absolute_error(y_te, y_pred))
                / max(1e-9, mean_absolute_error(y_te, baseline_pred)) * 100.0
            ),
            "model": "RandomForestRegressor",
            "params": {"n_estimators": n_estimators, "max_depth": max_depth,
                       "random_state": random_state},
        }
        self._dataset = df
        return self.metrics

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def _features_for(
        self,
        *,
        distance_km: float, capacity: int, condition: int,
        pop_a: int, pop_b: int,
        is_facility_a: int, is_facility_b: int,
        tod: str,
    ) -> np.ndarray:
        if tod not in TODS:
            raise ValueError(f"tod must be one of {TODS}, got {tod!r}")
        return np.array([[
            float(distance_km),
            int(capacity),
            int(condition),
            int(pop_a), int(pop_b),
            int(is_facility_a), int(is_facility_b),
            int(tod == "morning_peak"),
            int(tod == "afternoon"),
            int(tod == "evening_peak"),
            int(tod == "night"),
        ]])

    def predict_edge(
        self,
        edge: tuple[str, str], tod: str,
        road_lookup: dict[frozenset, dict],
        node_lookup: dict[str, dict],
        actual_flow: int | None = None,
    ) -> PredictResult:
        """Predict v/c for a specific edge at the given time-of-day."""
        if self.model is None:
            raise RuntimeError("Model is not trained. Call .train() first.")
        u, v = edge
        road = road_lookup.get(frozenset(edge))
        if road is None:
            raise KeyError(f"Edge {edge} not in road_lookup")
        a = node_lookup.get(u, {})
        b = node_lookup.get(v, {})
        feats = self._features_for(
            distance_km=road["distance_km"],
            capacity=road["capacity"],
            condition=road["condition"],
            pop_a=int(a.get("population") or 0),
            pop_b=int(b.get("population") or 0),
            is_facility_a=int(a.get("kind") == "facility"),
            is_facility_b=int(b.get("kind") == "facility"),
            tod=tod,
        )
        vc = float(self.model.predict(feats)[0])
        # Clamp to a reasonable range (BPR-friendly)
        vc = max(0.0, min(2.0, vc))
        flow = int(round(vc * road["capacity"]))
        actual_vc = (actual_flow / road["capacity"]) if actual_flow is not None else None
        return PredictResult(
            edge=(u, v), tod=tod,
            predicted_vc=round(vc, 4),
            predicted_flow=flow,
            actual_vc=round(actual_vc, 4) if actual_vc is not None else None,
            actual_flow=actual_flow,
            capacity=road["capacity"],
        )

    def predict_all_edges(
        self,
        tod: str,
        road_rows: list,
        neighborhood_rows: list,
        facility_rows: list,
        traffic_rows: list | None = None,
    ) -> list[PredictResult]:
        if self.model is None:
            raise RuntimeError("Model is not trained. Call .train() first.")
        # Build lookups
        pop = {n.id: int(n.population) for n in neighborhood_rows}
        kind = {n.id: "neighborhood" for n in neighborhood_rows}
        for f in facility_rows:
            kind[f.id] = "facility"
        actual: dict[frozenset, int] = {}
        if traffic_rows is not None:
            for t in traffic_rows:
                actual[frozenset((t.from_id, t.to_id))] = int(getattr(t, tod, 0) or 0)
        results: list[PredictResult] = []
        for r in road_rows:
            key = frozenset((r.from_id, r.to_id))
            actual_flow = actual.get(key)
            feats = self._features_for(
                distance_km=float(r.distance_km),
                capacity=int(r.capacity),
                condition=int(r.condition),
                pop_a=pop.get(r.from_id, 0),
                pop_b=pop.get(r.to_id, 0),
                is_facility_a=int(kind.get(r.from_id) == "facility"),
                is_facility_b=int(kind.get(r.to_id) == "facility"),
                tod=tod,
            )
            vc = max(0.0, min(2.0, float(self.model.predict(feats)[0])))
            flow = int(round(vc * r.capacity))
            actual_vc = (actual_flow / r.capacity) if actual_flow is not None and r.capacity else None
            results.append(PredictResult(
                edge=(r.from_id, r.to_id), tod=tod,
                predicted_vc=round(vc, 4),
                predicted_flow=flow,
                actual_vc=round(actual_vc, 4) if actual_vc is not None else None,
                actual_flow=actual_flow,
                capacity=int(r.capacity),
            ))
        return results

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def feature_importances(self) -> dict[str, float]:
        if self.model is None:
            return {}
        return {
            name: float(imp)
            for name, imp in zip(self.feature_names, self.model.feature_importances_)
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path = DEFAULT_MODEL_PATH) -> Path:
        if self.model is None:
            raise RuntimeError("Cannot save an untrained model.")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "model": self.model,
            "metrics": self.metrics,
            "feature_names": self.feature_names,
        }, path)
        return path

    @classmethod
    def load(cls, path: str | Path = DEFAULT_MODEL_PATH) -> "TrafficPredictor":
        obj = joblib.load(Path(path))
        p = cls()
        p.model = obj["model"]
        p.metrics = dict(obj.get("metrics") or {})
        p.feature_names = list(obj.get("feature_names") or FEATURE_COLS)
        return p


# ---------------------------------------------------------------------------
# Convenience: train + save from the seeded DB in one call
# ---------------------------------------------------------------------------

def train_from_db(model_path: str | Path = DEFAULT_MODEL_PATH) -> tuple[TrafficPredictor, dict]:
    """Train the predictor against the live SQLite database (DB must
    already be seeded — call `ensure_seeded()` first if not)."""
    from src.db.models import (
        ExistingRoad, Facility, Neighborhood, SessionLocal, TrafficFlow,
    )
    with SessionLocal() as s:
        traffic = list(s.query(TrafficFlow).all())
        roads = list(s.query(ExistingRoad).all())
        neigh = list(s.query(Neighborhood).all())
        facs = list(s.query(Facility).all())
    p = TrafficPredictor()
    metrics = p.train(traffic, roads, neigh, facs)
    p.save(model_path)
    return p, metrics


def load_or_train(model_path: str | Path = DEFAULT_MODEL_PATH) -> TrafficPredictor:
    """Load the cached model from disk, or train + save fresh if missing."""
    path = Path(model_path)
    if path.exists():
        try:
            return TrafficPredictor.load(path)
        except Exception:
            pass
    p, _ = train_from_db(path)
    return p
