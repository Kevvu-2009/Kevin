"""Model factory.

Small, regularised models only.  With a few thousand bars of training data and
noisy labels, model capacity — not model cleverness — is the overfitting lever
that matters.  XGBoost is used when installed; otherwise sklearn's
HistGradientBoosting is a drop-in (same family, same regularisation story).
"""

from __future__ import annotations

from typing import Any

AVAILABLE_MODELS = ("logistic", "random_forest", "gradient_boosting", "xgboost", "ensemble")


def make_model(name: str, random_state: int = 7, **overrides: Any):
    """Build a classifier by name.  All models expose predict_proba."""
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    name = name.lower()

    def logistic():
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("clf", LogisticRegression(C=overrides.get("C", 0.1), max_iter=2000)),
            ]
        )

    def random_forest():
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "clf",
                    RandomForestClassifier(
                        n_estimators=overrides.get("n_estimators", 300),
                        max_depth=overrides.get("max_depth", 4),
                        min_samples_leaf=overrides.get("min_samples_leaf", 50),
                        max_features="sqrt",
                        n_jobs=-1,
                        random_state=random_state,
                    ),
                ),
            ]
        )

    def gradient_boosting():
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "clf",
                    HistGradientBoostingClassifier(
                        max_depth=overrides.get("max_depth", 3),
                        learning_rate=overrides.get("learning_rate", 0.05),
                        max_iter=overrides.get("max_iter", 200),
                        min_samples_leaf=overrides.get("min_samples_leaf", 50),
                        l2_regularization=overrides.get("l2_regularization", 1.0),
                        random_state=random_state,
                    ),
                ),
            ]
        )

    def xgboost():
        try:
            from xgboost import XGBClassifier
        except ImportError:
            # xgboost is optional; HistGradientBoosting is the same model
            # family with equivalent regularisation controls.
            return gradient_boosting()
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "clf",
                    XGBClassifier(
                        n_estimators=overrides.get("n_estimators", 300),
                        max_depth=overrides.get("max_depth", 3),
                        learning_rate=overrides.get("learning_rate", 0.05),
                        subsample=0.8,
                        colsample_bytree=0.8,
                        reg_lambda=overrides.get("reg_lambda", 1.0),
                        eval_metric="logloss",
                        random_state=random_state,
                        n_jobs=-1,
                    ),
                ),
            ]
        )

    if name == "logistic":
        return logistic()
    if name == "random_forest":
        return random_forest()
    if name == "gradient_boosting":
        return gradient_boosting()
    if name == "xgboost":
        return xgboost()
    if name == "ensemble":
        return VotingClassifier(
            estimators=[
                ("logistic", logistic()),
                ("rf", random_forest()),
                ("gb", gradient_boosting()),
            ],
            voting="soft",
        )
    raise ValueError(f"unknown model '{name}'; available: {AVAILABLE_MODELS}")
