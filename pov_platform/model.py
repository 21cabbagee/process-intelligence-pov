"""Predict SLA breach at requisition time, so slow cases can be fast-tracked before they stall.

Only attributes known when the requisition is raised are used (no leakage from later events).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, confusion_matrix, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORICAL = ["vendor", "category", "region", "channel"]
NUMERIC = ["log_amount", "start_weekday", "month_end"]


def make_features(cases: pd.DataFrame) -> pd.DataFrame:
    x = cases[CATEGORICAL].copy()
    x["log_amount"] = np.log10(cases["amount"])
    x["start_weekday"] = cases["start"].dt.day_of_week
    x["month_end"] = (cases["start"].dt.day >= 25).astype(int)
    return x


def train_breach_model(cases: pd.DataFrame, seed: int = 0) -> dict:
    x, y = make_features(cases), cases["sla_breach"].astype(int)
    x_tr, x_te, y_tr, y_te = train_test_split(x, y, test_size=0.25, random_state=seed, stratify=y)
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
                             ("num", StandardScaler(), NUMERIC)])
    models = {
        "Logistic regression (baseline)": LogisticRegression(max_iter=1000),
        "Gradient boosting": GradientBoostingClassifier(random_state=seed, n_estimators=200, max_depth=3, learning_rate=0.05),
    }
    results, fitted = {}, {}
    for name, clf in models.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)]).fit(x_tr, y_tr)
        p = pipe.predict_proba(x_te)[:, 1]
        pred = (p >= 0.5).astype(int)
        results[name] = {
            "roc_auc": round(float(roc_auc_score(y_te, p)), 3),
            "avg_precision": round(float(average_precision_score(y_te, p)), 3),
            "precision": round(float(precision_score(y_te, pred, zero_division=0)), 3),
            "recall": round(float(recall_score(y_te, pred)), 3),
            "confusion": confusion_matrix(y_te, pred).tolist(),
        }
        fitted[name] = pipe
    best = max(results, key=lambda k: results[k]["roc_auc"])
    imp = permutation_importance(fitted[best], x_te, y_te, scoring="roc_auc", n_repeats=8, random_state=seed)
    importances = sorted(
        ({"feature": f, "importance": round(float(m), 4)} for f, m in zip(x.columns, imp.importances_mean)),
        key=lambda d: -d["importance"])

    # Risk-tiering: how much breach volume the top-scored 20% of cases would catch.
    p_best = fitted[best].predict_proba(x_te)[:, 1]
    order = np.argsort(-p_best)
    top = order[: max(1, len(order) // 5)]
    capture = float(y_te.to_numpy()[top].sum() / max(1, y_te.sum()))
    return {
        "target": "cycle time > SLA",
        "base_rate": round(float(y.mean()), 3),
        "train_rows": int(len(x_tr)), "test_rows": int(len(x_te)),
        "models": results, "best": best, "importances": importances,
        "top20_breach_capture": round(capture, 3),
        "pipeline": fitted[best],
    }
