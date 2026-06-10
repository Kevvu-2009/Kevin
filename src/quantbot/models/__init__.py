"""Machine-learning layer: leakage-safe CV, model zoo, walk-forward pipeline.

scikit-learn (and optionally xgboost) are imported lazily inside the modules
that need them so the rest of the package works without them installed.
"""

from quantbot.models.cv import PurgedKFold
from quantbot.models.pipeline import WalkForwardModel, walk_forward_probabilities

__all__ = ["PurgedKFold", "WalkForwardModel", "walk_forward_probabilities"]
