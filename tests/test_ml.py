"""Bonus — ML traffic predictor tests."""
from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cf-ml")
    from src import config
    importlib.reload(config)
    config.DB_PATH = tmp / "test.db"
    config.DB_URL = f"sqlite:///{config.DB_PATH.as_posix()}"
    from src.db import models
    importlib.reload(models)
    from src.db import seed
    importlib.reload(seed)
    seed.ensure_seeded()
    from src.ml import traffic_predictor as tp
    importlib.reload(tp)

    with models.SessionLocal() as s:
        traffic = list(s.query(models.TrafficFlow).all())
        roads = list(s.query(models.ExistingRoad).all())
        neigh = list(s.query(models.Neighborhood).all())
        facs = list(s.query(models.Facility).all())

    p = tp.TrafficPredictor()
    metrics = p.train(traffic, roads, neigh, facs)
    return {
        "tp_module": tp, "predictor": p, "metrics": metrics,
        "traffic": traffic, "roads": roads, "neigh": neigh, "facs": facs,
        "tmp": tmp,
    }


def test_dataset_shape(env):
    """28 edges × 4 times-of-day = 112 training rows."""
    m = env["metrics"]
    assert m["n_samples"] == 112
    assert m["n_features"] == 11


def test_metrics_populated(env):
    m = env["metrics"]
    for key in ("r2", "mae", "n_train", "n_test", "baseline_mae",
                "improvement_pct", "model", "params"):
        assert key in m
    assert m["model"] == "RandomForestRegressor"


def test_model_beats_baseline(env):
    """Random Forest must do better than predicting the dataset mean."""
    m = env["metrics"]
    assert m["mae"] < m["baseline_mae"], (
        f"Model MAE {m['mae']:.4f} must beat baseline {m['baseline_mae']:.4f}"
    )
    assert m["improvement_pct"] > 0


def test_r2_positive(env):
    """R² > 0 means the model explains some variance — i.e. it learned
    something nontrivial."""
    assert env["metrics"]["r2"] > 0.0


def test_predict_edge_returns_valid_range(env):
    """v/c predictions must be clamped to [0, 2] (BPR breaks beyond)."""
    p = env["predictor"]
    road_lookup = {
        frozenset((r.from_id, r.to_id)): {
            "distance_km": r.distance_km,
            "capacity":    r.capacity,
            "condition":   r.condition,
        }
        for r in env["roads"]
    }
    node_lookup = {
        n.id: {"population": n.population, "kind": "neighborhood"}
        for n in env["neigh"]
    }
    for f in env["facs"]:
        node_lookup[f.id] = {"population": None, "kind": "facility"}
    res = p.predict_edge(("1", "3"), "morning_peak", road_lookup, node_lookup)
    assert 0.0 <= res.predicted_vc <= 2.0
    assert res.predicted_flow >= 0
    assert res.capacity > 0
    assert res.edge == ("1", "3")
    assert res.tod == "morning_peak"


def test_predict_all_edges_covers_every_road(env):
    p = env["predictor"]
    results = p.predict_all_edges(
        "morning_peak",
        env["roads"], env["neigh"], env["facs"], env["traffic"],
    )
    # 28 edges in the dataset (with the 7-15 / 15-7 duplicate from Phase 1)
    assert len(results) == len(env["roads"])
    for r in results:
        assert 0.0 <= r.predicted_vc <= 2.0
        assert r.tod == "morning_peak"


def test_predict_morning_higher_than_night_on_average(env):
    """Sanity: across all edges, peak v/c must be > night v/c on average
    (the temporal pattern the model is supposed to capture)."""
    p = env["predictor"]
    morn = p.predict_all_edges("morning_peak", env["roads"], env["neigh"], env["facs"])
    nite = p.predict_all_edges("night",        env["roads"], env["neigh"], env["facs"])
    avg_morn = sum(r.predicted_vc for r in morn) / len(morn)
    avg_nite = sum(r.predicted_vc for r in nite) / len(nite)
    assert avg_morn > avg_nite, f"Expected morning > night, got {avg_morn:.3f} vs {avg_nite:.3f}"


def test_feature_importances_sum_to_one(env):
    imp = env["predictor"].feature_importances()
    assert len(imp) == 11
    total = sum(imp.values())
    assert abs(total - 1.0) < 1e-6, f"Importances should sum to 1, got {total}"


def test_save_and_load_roundtrip(env, tmp_path):
    p = env["predictor"]
    out = tmp_path / "model.joblib"
    saved = p.save(out)
    assert saved.exists()
    tp = env["tp_module"]
    p2 = tp.TrafficPredictor.load(saved)
    # Predictions should match exactly after save/load.
    road_lookup = {
        frozenset((r.from_id, r.to_id)): {
            "distance_km": r.distance_km,
            "capacity":    r.capacity,
            "condition":   r.condition,
        }
        for r in env["roads"]
    }
    node_lookup = {
        n.id: {"population": n.population, "kind": "neighborhood"}
        for n in env["neigh"]
    }
    for f in env["facs"]:
        node_lookup[f.id] = {"population": None, "kind": "facility"}
    a = p.predict_edge(("1", "3"), "morning_peak", road_lookup, node_lookup)
    b = p2.predict_edge(("1", "3"), "morning_peak", road_lookup, node_lookup)
    assert a.predicted_vc == b.predicted_vc
    assert a.predicted_flow == b.predicted_flow


def test_invalid_tod_raises(env):
    p = env["predictor"]
    with pytest.raises(ValueError):
        p._features_for(
            distance_km=8.5, capacity=3000, condition=7,
            pop_a=250000, pop_b=100000,
            is_facility_a=0, is_facility_b=0,
            tod="lunchtime",  # not a valid TOD
        )
