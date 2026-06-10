"""Machine-learning signal family.

Honesty-by-construction: every prediction in the position series comes from a
model fitted strictly on earlier data (walk-forward refits with a label-
horizon gap).  There is no "in-sample" version of these signals — the warm-up
period is simply flat.  Consequently the usual IS/OOS overfit gap cannot be
gamed; the residual selection bias (choice of model/threshold/horizon) is
charged to the deflated-Sharpe trial count like every other candidate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from quantbot.features.core import build_feature_matrix, trend_regime
from quantbot.features.labels import classification_labels
from quantbot.models.pipeline import walk_forward_probabilities
from quantbot.research.signals.base import ResearchSignal, register_signal


@register_signal
class MLClassifierSignal(ResearchSignal):
    name = "ml_classifier"
    family = "machine_learning"
    default_params = {
        "model": "gradient_boosting",
        "horizon": 12,            # label horizon in bars
        "deadzone_bps": 15.0,     # ignore moves smaller than round-trip cost
        "threshold": 0.58,        # act only on confident probabilities
        "min_train": 1500,
        "refit_every": 500,
        "allow_short": True,
    }
    grid = {"horizon": [6, 12, 24], "threshold": [0.55, 0.58, 0.62]}
    thesis = (
        "Non-linear interactions between momentum, volatility-state, flow "
        "and session features carry predictive information that no single "
        "indicator captures; a regularised tree ensemble can read them "
        "jointly.  Trading only high-confidence probabilities turns a weak "
        "classifier into a selective strategy (bet sizing by conviction)."
    )
    persistence = (
        "The features are causal market-state descriptors; as long as the "
        "underlying premia (momentum, vol clustering, flow persistence) "
        "exist, a properly regularised learner can re-weight them as their "
        "relative strength drifts — adaptivity is the persistence argument."
    )
    risks = (
        "Silent regime novelty: the model extrapolates confidently into "
        "states it never saw.  Capacity for overfitting is structural; only "
        "the walk-forward protocol and small model capacity contain it."
    )

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        X = build_feature_matrix(df)
        y = classification_labels(
            df["close"], int(p["horizon"]), deadzone=float(p["deadzone_bps"]) / 1e4
        )
        proba = walk_forward_probabilities(
            X,
            y,
            model_name=str(p["model"]),
            label_horizon=int(p["horizon"]),
            min_train=int(p["min_train"]),
            refit_every=int(p["refit_every"]),
        )
        th = float(p["threshold"])
        pos = pd.Series(0.0, index=df.index)
        pos[proba > th] = 1.0
        if p.get("allow_short", True):
            pos[proba < 1.0 - th] = -1.0
        return pos


@register_signal
class RegimePredictionSignal(ResearchSignal):
    name = "ml_regime_prediction"
    family = "machine_learning"
    default_params = {
        "model": "gradient_boosting",
        "horizon": 24,            # predict the trend-regime state 24 bars ahead
        "lookback": 168,          # TSMOM lookback traded when trending predicted
        "threshold": 0.60,
        "min_train": 1500,
        "refit_every": 500,
    }
    grid = {"horizon": [12, 24, 48], "threshold": [0.55, 0.60]}
    thesis = (
        "Regime is more persistent — hence more predictable — than returns.  "
        "Predict whether the market will be TRENDING shortly, and deploy "
        "momentum only then: ML supplies the gate, a simple robust rule "
        "supplies the direction."
    )
    persistence = (
        "Predicting the second moment's structure (vol/trendiness) exploits "
        "ARCH-type persistence, the strongest stylised fact available."
    )
    risks = "Gate errors cluster at regime turns, exactly when momentum is most exposed."

    def generate(self, df: pd.DataFrame) -> pd.Series:
        self._validate(df)
        p = self.params
        h = int(p["horizon"])
        X = build_feature_matrix(df)
        future_trending = (trend_regime(df) != 0).astype(float).shift(-h)
        proba = walk_forward_probabilities(
            X,
            future_trending,
            model_name=str(p["model"]),
            label_horizon=h,
            min_train=int(p["min_train"]),
            refit_every=int(p["refit_every"]),
        )
        sign = np.sign(df["close"].pct_change(int(p["lookback"])))
        gate = (proba > float(p["threshold"])).astype(float)
        return (sign * gate).fillna(0.0)
