"""Tabular ML layer: logistic-regression risk models for heart disease (UCI
Cleveland) and diabetes (Pima Indians). Models are loaded from ``models/`` and
are transparently retrained from the bundled CSVs when the artifact is missing
or was built with a different scikit-learn version."""
from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

log = logging.getLogger("clinical.ml")
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR, MODEL_DIR = ROOT / "data", ROOT / "models"

HEART_FEATURES = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal"]
DIABETES_FEATURES = ["Pregnancies", "Glucose", "BloodPressure", "SkinThickness", "Insulin", "BMI", "DiabetesPedigreeFunction", "Age"]
ZERO_AS_MISSING = ["Glucose", "BloodPressure", "SkinThickness", "Insulin", "BMI"]

SPECS: dict[str, dict[str, Any]] = {
    "heart": {"label": "Heart disease", "features": HEART_FEATURES, "csv": DATA_DIR / "cleveland.csv", "path": MODEL_DIR / "heart-risk.joblib",
              "model": "Logistic regression (UCI Cleveland, n=297)", "target": "angiographic heart-disease label in the historical UCI cohort"},
    "diabetes": {"label": "Diabetes", "features": DIABETES_FEATURES, "csv": DATA_DIR / "pima-diabetes.csv", "path": MODEL_DIR / "diabetes-risk.joblib",
                 "model": "Logistic regression (Pima Indians diabetes, n=768)", "target": "diabetes diagnosis within 5 years in the historical Pima cohort"},
}
_loaded: dict[str, dict[str, Any] | None] = {}


def _load_frame(key: str) -> tuple[pd.DataFrame, pd.Series]:
    spec = SPECS[key]
    if key == "heart":
        df = pd.read_csv(spec["csv"]).replace("?", pd.NA)
        df = df[HEART_FEATURES + ["target"]].apply(pd.to_numeric, errors="coerce").dropna()
        return df[HEART_FEATURES], (df["target"] > 0).astype(int)
    df = pd.read_csv(spec["csv"])
    df[ZERO_AS_MISSING] = df[ZERO_AS_MISSING].replace(0, np.nan)
    return df[DIABETES_FEATURES], df["Outcome"].astype(int)


def train(key: str, save: bool = True) -> dict[str, Any]:
    spec = SPECS[key]
    x, y = _load_frame(key)
    steps = [StandardScaler(), LogisticRegression(max_iter=3000, class_weight="balanced", random_state=42)]
    if key == "diabetes":
        steps.insert(0, SimpleImputer(strategy="median"))
    pipe = make_pipeline(*steps)
    xtr, xte, ytr, yte = train_test_split(x, y, test_size=0.25, random_state=42, stratify=y)
    pipe.fit(xtr, ytr)
    proba = pipe.predict_proba(xte)[:, 1]
    cv = cross_val_score(make_pipeline(*steps), x, y, cv=5, scoring="roc_auc")
    payload = {"pipeline": pipe.fit(x, y), "features": spec["features"], "sklearn": sklearn.__version__, "trained": dt.date.today().isoformat(),
               "metrics": {"holdout_accuracy": round(float(accuracy_score(yte, proba >= .5)), 3), "holdout_roc_auc": round(float(roc_auc_score(yte, proba)), 3),
                           "cv_roc_auc_mean": round(float(cv.mean()), 3), "rows": int(len(x)), "positive_rate": round(float(y.mean()), 3)}}
    if save:
        try:
            spec["path"].parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(payload, spec["path"])
        except OSError as exc:  # read-only container volume etc.
            log.warning("Could not save %s: %s", spec["path"], exc)
    log.info("Trained %s model: %s", key, payload["metrics"])
    return payload


def get_model(key: str) -> dict[str, Any] | None:
    if key in _loaded:
        return _loaded[key]
    spec, payload = SPECS[key], None
    if spec["path"].exists():
        try:
            cand = joblib.load(spec["path"])
            if isinstance(cand, dict) and cand.get("sklearn") == sklearn.__version__ and cand.get("features") == spec["features"]:
                payload = cand
        except Exception as exc:
            log.warning("Stale/unreadable %s (%s); retraining", spec["path"].name, exc)
    if payload is None and spec["csv"].exists():
        try:
            payload = train(key)
        except Exception as exc:
            log.error("Training %s failed: %s", key, exc)
    _loaded[key] = payload
    return payload


def model_info() -> dict[str, Any]:
    out = {}
    for key, spec in SPECS.items():
        m = get_model(key)
        out[key] = {"label": spec["label"], "available": m is not None, "model": spec["model"], "target": spec["target"],
                    "features": spec["features"], "metrics": m["metrics"] if m else None}
    return out


def _level(p: float) -> str:
    return "low" if p < .34 else "moderate" if p < .67 else "high"


def _drivers(pipe: Any, row: pd.DataFrame, names: list[str]) -> list[dict[str, Any]]:
    try:
        scaled = pipe[:-1].transform(row)[0]
        contrib = pipe[-1].coef_[0] * scaled
        order = np.argsort(-np.abs(contrib))[:3]
        return [{"feature": names[i], "effect": "raises" if contrib[i] > 0 else "lowers", "magnitude": round(float(abs(contrib[i])), 2)} for i in order if abs(contrib[i]) > 0.05]
    except Exception:
        return []


def predict(key: str, features: dict[str, float]) -> dict[str, Any]:
    spec = SPECS[key]
    base = {"key": key, "disease": spec["label"], "model": spec["model"], "target": spec["target"]}
    m = get_model(key)
    if m is None:
        return {**base, "available": False, "message": f"{spec['label']} model unavailable: training data not found in backend/data."}
    names = spec["features"]
    given = {k: v for k, v in features.items() if k in names and v is not None and not (isinstance(v, float) and np.isnan(v))}
    caveat = "Research prototype. Output reflects a historical dataset, is not a calibrated personal probability or diagnosis, and must not guide care."
    if key == "heart":
        missing = [n for n in names if n not in given]
        if missing:
            return {**base, "available": False, "metrics": m["metrics"], "message": f"Heart model needs all 13 UCI fields. Missing: {', '.join(missing)}."}
        imputed: list[str] = []
    else:
        core = [n for n in ("Glucose", "Age", "BMI") if n not in given]
        if core:
            return {**base, "available": False, "metrics": m["metrics"], "message": f"Diabetes model needs at least Glucose, BMI and Age. Missing: {', '.join(core)}."}
        imputed = [n for n in names if n not in given and n != "Pregnancies"]
        if "Pregnancies" not in given:
            given["Pregnancies"] = 0.0
        caveat += " The Pima cohort is adult women of a specific population; applicability to other groups is unknown."
        if imputed:
            caveat += f" Missing inputs were filled with training-set medians: {', '.join(imputed)}."
    row = pd.DataFrame([{n: given.get(n, np.nan) for n in names}], columns=names)
    p = float(m["pipeline"].predict_proba(row)[0][1])
    return {**base, "available": True, "probability": round(p, 3), "level": _level(p), "threshold": 0.5,
            "label": f"{_level(p)} model signal ({round(p * 100)}%)", "drivers": _drivers(m["pipeline"], row, names),
            "imputed": imputed, "metrics": m["metrics"], "caveat": caveat}
