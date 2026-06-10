"""Feature engineering + ML layer: causality, purged CV, walk-forward."""

import numpy as np
import pandas as pd
import pytest

from quantbot.data.synthetic import generate_ohlcv
from quantbot.features.core import (
    FEATURE_CATALOG,
    build_feature_matrix,
    multi_timeframe_feature,
    resample_ohlcv,
)
from quantbot.features.labels import classification_labels, forward_return, triple_barrier_labels
from quantbot.models.cv import PurgedKFold
from quantbot.models.pipeline import walk_forward_probabilities
from quantbot.models.zoo import AVAILABLE_MODELS, make_model


@pytest.fixture(scope="module")
def df():
    return generate_ohlcv(n=2000, seed=17)


def test_feature_matrix_matches_catalog(df):
    X = build_feature_matrix(df)
    assert list(X.columns) == list(FEATURE_CATALOG)
    assert X.index.equals(df.index)
    assert not np.isinf(X.to_numpy(dtype=float)).any()


def test_feature_matrix_is_causal(df):
    """Features on a prefix == features on the full set, on that prefix."""
    cut = 1500
    full = build_feature_matrix(df).iloc[:cut]
    pre = build_feature_matrix(df.iloc[:cut])
    pd.testing.assert_frame_equal(full, pre)


def test_htf_feature_uses_completed_bars_only(df):
    htf = resample_ohlcv(df, "1D")
    # Every resampled stamp must mark a COMPLETED day: stamp - 1D >= first ltf ts.
    assert (htf.index[1:] - pd.Timedelta("1D") >= df.index[0]).all()
    feat = multi_timeframe_feature(df, "1D", lambda h: h["close"])
    # The aligned value at any time t must equal a daily CLOSE from strictly
    # before t (never the in-progress day's latest price).
    t = df.index[500]
    daily_before = htf.loc[htf.index <= t, "close"]
    assert feat.loc[t] == daily_before.iloc[-1]


def test_labels_forward_and_deadzone(df):
    fwd = forward_return(df["close"], 12)
    assert fwd.iloc[-12:].isna().all()
    y = classification_labels(df["close"], 12, deadzone=0.001)
    assert set(y.dropna().unique()) <= {0.0, 1.0}
    dead = fwd.abs() <= 0.001
    assert y[dead].isna().all()


def test_triple_barrier_labels(df):
    y = triple_barrier_labels(df, horizon=24, tp_atr=2.0, sl_atr=1.0)
    vals = set(y.dropna().unique())
    assert vals <= {0.0, 1.0}
    assert y.notna().sum() > 100  # decisive moves exist in synthetic data


def test_purged_kfold_no_leakage():
    n, horizon, embargo = 1000, 24, 12
    cv = PurgedKFold(n_splits=5, label_horizon=horizon, embargo=embargo)
    folds = list(cv.split(n))
    assert len(folds) == 5
    covered = np.concatenate([te for _, te in folds])
    assert sorted(covered) == list(range(n))  # test folds tile the sample
    for tr, te in folds:
        te_lo, te_hi = te[0], te[-1]
        # No train sample inside the test fold.
        assert not ((tr >= te_lo) & (tr <= te_hi)).any()
        # Purge: no train label window reaching into the fold.
        assert not ((tr >= te_lo - horizon) & (tr < te_lo)).any()
        # Embargo after the fold.
        assert not ((tr > te_hi) & (tr <= te_hi + embargo)).any()


@pytest.mark.parametrize("name", [m for m in AVAILABLE_MODELS if m != "xgboost"])
def test_model_zoo_builds_and_fits(name):
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 5))
    y = (X[:, 0] + rng.normal(0, 0.5, 300) > 0).astype(float)
    model = make_model(name)
    model.fit(X, y)
    p = model.predict_proba(X)[:, 1]
    assert p.shape == (300,)
    assert ((p >= 0) & (p <= 1)).all()


def test_walk_forward_probabilities_causal_and_warm():
    rng = np.random.default_rng(5)
    n = 1200
    idx = pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC")
    X = pd.DataFrame(rng.normal(size=(n, 4)), index=idx, columns=list("abcd"))
    # Learnable pattern: y depends on feature 'a'.
    y = pd.Series((X["a"] > 0).astype(float), index=idx)
    proba = walk_forward_probabilities(
        X, y, model_name="logistic", label_horizon=5, min_train=400, refit_every=200
    )
    assert proba.iloc[:405].isna().all()          # warm-up untouched
    assert proba.iloc[405:].notna().mean() > 0.9  # predictions afterwards
    # The pattern is learnable: prob should track the feature sign OOS.
    oos = proba.iloc[405:].dropna()
    acc = ((oos > 0.5).astype(float) == y.loc[oos.index]).mean()
    assert acc > 0.9
