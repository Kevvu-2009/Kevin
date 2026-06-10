"""Walk-forward model training & prediction.

The only honest way to evaluate an ML trading signal is to ensure every
prediction comes from a model fitted strictly on the past.  This module
produces such an out-of-sample probability series by chronological refits:

    [.... train ....][gap=horizon][ predict block ]
                     [.... train ....][gap][ predict block ]  ...

The ``gap`` (label horizon) keeps the last training labels from overlapping
the prediction block.  Predictions for the warm-up period are NaN — they are
*never* backfilled with in-sample fits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quantbot.models.zoo import make_model


@dataclass
class WalkForwardModel:
    """Configuration for the walk-forward refit loop."""

    model_name: str = "gradient_boosting"
    label_horizon: int = 12          # bars over which the label is realised
    min_train: int = 1000            # bars required before the first fit
    refit_every: int = 500           # prediction block length between refits
    expanding: bool = True           # expanding (anchored) vs rolling train
    max_train: int | None = None     # rolling-window cap when expanding=False
    model_kwargs: dict = field(default_factory=dict)

    def fit_predict(self, X: pd.DataFrame, y: pd.Series) -> pd.Series:
        return walk_forward_probabilities(
            X,
            y,
            model_name=self.model_name,
            label_horizon=self.label_horizon,
            min_train=self.min_train,
            refit_every=self.refit_every,
            expanding=self.expanding,
            max_train=self.max_train,
            **self.model_kwargs,
        )


def walk_forward_probabilities(
    X: pd.DataFrame,
    y: pd.Series,
    model_name: str = "gradient_boosting",
    label_horizon: int = 12,
    min_train: int = 1000,
    refit_every: int = 500,
    expanding: bool = True,
    max_train: int | None = None,
    **model_kwargs,
) -> pd.Series:
    """P(label=1) for each bar, from strictly-past-fitted models.

    Rows with NaN labels (deadzone / timeout) are excluded from training but
    still receive predictions.  Rows before the first refit get NaN.
    """
    if not X.index.equals(y.index):
        raise ValueError("X and y must share an index")
    n = len(X)
    proba = pd.Series(np.nan, index=X.index, name="p_up")
    if n < min_train + label_horizon + 1:
        return proba

    Xv = X.to_numpy(dtype=float)
    yv = y.to_numpy(dtype=float)

    start = min_train + label_horizon
    for block_start in range(start, n, refit_every):
        block_end = min(n, block_start + refit_every)
        # Train on everything whose label window closes before the block.
        train_hi = block_start - label_horizon
        train_lo = 0 if expanding or max_train is None else max(0, train_hi - max_train)
        tr = slice(train_lo, train_hi)
        mask = np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(axis=1)
        X_tr, y_tr = Xv[tr][mask], yv[tr][mask]
        if len(np.unique(y_tr)) < 2 or len(y_tr) < 100:
            continue  # degenerate window: leave NaN rather than guess
        model = make_model(model_name, **model_kwargs)
        model.fit(X_tr, y_tr)
        X_te = Xv[block_start:block_end]
        ok = np.isfinite(X_te).all(axis=1)
        if ok.any():
            p = np.full(block_end - block_start, np.nan)
            p[ok] = model.predict_proba(X_te[ok])[:, 1]
            proba.iloc[block_start:block_end] = p
    return proba


def purged_cv_score(
    X: pd.DataFrame,
    y: pd.Series,
    model_name: str = "gradient_boosting",
    n_splits: int = 5,
    label_horizon: int = 12,
    embargo: int = 24,
    **model_kwargs,
) -> dict:
    """Mean/std AUC across purged, embargoed folds — a quick model sanity
    check (NOT a substitute for the walk-forward backtest)."""
    from sklearn.metrics import roc_auc_score

    from quantbot.models.cv import PurgedKFold

    mask = y.notna() & X.notna().all(axis=1)
    Xv, yv = X[mask].to_numpy(dtype=float), y[mask].to_numpy(dtype=float)
    cv = PurgedKFold(n_splits=n_splits, label_horizon=label_horizon, embargo=embargo)
    scores = []
    for tr_idx, te_idx in cv.split(len(Xv)):
        if len(np.unique(yv[tr_idx])) < 2 or len(np.unique(yv[te_idx])) < 2:
            continue
        model = make_model(model_name, **model_kwargs)
        model.fit(Xv[tr_idx], yv[tr_idx])
        p = model.predict_proba(Xv[te_idx])[:, 1]
        scores.append(roc_auc_score(yv[te_idx], p))
    return {
        "auc_mean": float(np.mean(scores)) if scores else float("nan"),
        "auc_std": float(np.std(scores)) if scores else float("nan"),
        "n_folds": len(scores),
    }
