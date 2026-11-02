"""Tabular ML layer: logistic-regression risk models for heart disease (UCI
Cleveland) and diabetes (Pima Indians). Models are loaded from ``models/`` and
are transparently retrained from the bundled CSVs when the artifact is missing,
was built with a different scikit-learn version or schema, or fails its SHA-256
integrity check (joblib artifacts execute code on load, so an unverified file is
never deserialised).

Each artifact records a version derived from the training-data hash, holdout
discrimination *and* calibration metrics, and per-feature training ranges used
to warn when an input lies outside the data the model has seen."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, roc_auc_score
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
SCHEMA = 3
CARDS: dict[str, dict[str, Any]] = {
    "heart": {"intended_use": "Research and education: illustrate how a tabular model combines the 13 UCI Cleveland exercise-test and clinical fields.",
              "out_of_scope": ["Individual diagnosis or triage", "Patients without a full exercise test / fluoroscopy work-up",
                               "Populations unlike the 1980s Cleveland Clinic referral cohort"],
              "population": "303 patients referred for coronary angiography at the Cleveland Clinic (1981-1984); 297 complete rows used.",
              "limitations": ["Small, old, single-centre referral cohort with high disease prevalence (~46%)", "Not externally validated or recalibrated",
                              "class_weight='balanced' shifts probabilities toward 50%; outputs are rankings, not calibrated risks"]},
    "diabetes": {"intended_use": "Research and education: illustrate a tabular diabetes model on the Pima Indians cohort.",
                 "out_of_scope": ["Individual diagnosis or screening decisions", "Men, children, or populations other than adult Pima women", "Pregnancy"],
                 "population": "768 adult women of Pima heritage near Phoenix, Arizona (NIDDK), onset within 5 years.",
                 "limitations": ["Narrow single-population cohort", "Zero values used as missing markers were median-imputed",
                                 "Not externally validated or recalibrated", "class_weight='balanced' shifts probabilities toward 50%"]},
}
_loaded: dict[str, dict[str, Any] | None] = {}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def calibration(y: np.ndarray, p: np.ndarray, bins: int = 5) -> dict[str, Any]:
    """Expected calibration error and a reliability table (mean predicted vs observed rate per probability bin)."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    table, ece = [], 0.0
    for b in range(bins):
        mask = idx == b
        if mask.any():
            pred, obs = float(p[mask].mean()), float(y[mask].mean())
            ece += mask.mean() * abs(pred - obs)
            table.append({"bin": f"{edges[b]:.1f}-{edges[b + 1]:.1f}", "n": int(mask.sum()), "mean_predicted": round(pred, 3), "observed_rate": round(obs, 3)})
    return {"holdout_ece": round(float(ece), 3), "calibration_table": table}


def _sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


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
    tn, fp, fn, tp = confusion_matrix(yte, proba >= .5, labels=[0, 1]).ravel()
    cv = cross_val_score(make_pipeline(*steps), x, y, cv=5, scoring="roc_auc")
    data_hash = _file_sha256(spec["csv"])
    payload = {"pipeline": pipe.fit(x, y), "features": spec["features"], "sklearn": sklearn.__version__, "schema": SCHEMA,
               "trained": dt.date.today().isoformat(), "version": f"{key}-lr-{data_hash[:10]}", "data_sha256": data_hash,
               "ranges": {c: [float(x[c].min()), float(x[c].max())] for c in spec["features"]},
               "metrics": {"holdout_accuracy": round(float(accuracy_score(yte, proba >= .5)), 3), "holdout_roc_auc": round(float(roc_auc_score(yte, proba)), 3),
                           "cv_roc_auc_mean": round(float(cv.mean()), 3), "cv_roc_auc_std": round(float(cv.std()), 3),
                           "holdout_sensitivity": round(float(tp / (tp + fn)), 3) if tp + fn else None,
                           "holdout_specificity": round(float(tn / (tn + fp)), 3) if tn + fp else None,
                           "holdout_brier": round(float(brier_score_loss(yte, proba)), 3),
                           **calibration(np.asarray(yte), proba),
                           "holdout_rows": int(len(yte)), "rows": int(len(x)), "positive_rate": round(float(y.mean()), 3)}}
    if save:
        try:
            spec["path"].parent.mkdir(parents=True, exist_ok=True)
            joblib.dump(payload, spec["path"])
            _sidecar(spec["path"]).write_text(_file_sha256(spec["path"]), encoding="ascii")
        except OSError as exc:  # read-only container volume etc.
            log.warning("Could not save %s: %s", spec["path"], exc)
    log.info("Trained %s model: %s", key, payload["metrics"])
    return payload


def get_model(key: str) -> dict[str, Any] | None:
    if key in _loaded:
        return _loaded[key]
    spec, payload = SPECS[key], None
    sidecar = _sidecar(spec["path"])
    if spec["path"].exists():
        try:
            if not sidecar.exists() or sidecar.read_text(encoding="ascii").strip() != _file_sha256(spec["path"]):
                raise ValueError("integrity check failed")
            cand = joblib.load(spec["path"])
            if (isinstance(cand, dict) and cand.get("sklearn") == sklearn.__version__ and cand.get("features") == spec["features"]
                    and cand.get("schema") == SCHEMA):
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
                    "features": spec["features"], "metrics": m["metrics"] if m else None, "version": m["version"] if m else None,
                    "trained": m["trained"] if m else None, "data_sha256": m["data_sha256"] if m else None, "card": CARDS[key]}
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
    assumed: list[str] = []
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
            assumed.append("Pregnancies")
            caveat += " Pregnancies was not supplied and was assumed to be 0."
        caveat += " The Pima cohort is adult women of a specific population; applicability to other groups is unknown."
        if imputed:
            caveat += f" Missing inputs were filled with training-set medians: {', '.join(imputed)}."
    out_of_range = [f"{n}={given[n]:g} (trained on {lo:g}-{hi:g})" for n, (lo, hi) in m["ranges"].items()
                    if n in given and n not in imputed and not lo <= given[n] <= hi]
    if out_of_range:
        caveat += " Inputs outside the training range make this output unreliable: " + "; ".join(out_of_range) + "."
    row = pd.DataFrame([{n: given.get(n, np.nan) for n in names}], columns=names)
    p = float(m["pipeline"].predict_proba(row)[0][1])
    return {**base, "available": True, "probability": round(p, 3), "level": _level(p), "threshold": 0.5,
            "label": f"{_level(p)} model signal ({round(p * 100)}%)",
            # only supplied values can be called drivers; imputed/assumed ones would explain the median, not the patient
            "drivers": [d for d in _drivers(m["pipeline"], row, names) if d["feature"] not in imputed and d["feature"] not in assumed],
            "imputed": imputed, "out_of_range": out_of_range, "reliability": "low" if out_of_range or len(imputed) > 3 else "standard",
            "metrics": m["metrics"], "version": m["version"], "caveat": caveat}
