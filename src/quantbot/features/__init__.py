"""Feature engineering for research and ML models.

Every feature is *causal*: the value at bar ``t`` uses only information
available at the close of bar ``t``.  Higher-timeframe features are joined on
bar *completion* time so a 4h bar is never visible before it closes.
"""

from quantbot.features.core import (
    FEATURE_CATALOG,
    build_feature_matrix,
    multi_timeframe_feature,
    session_features,
    time_features,
)
from quantbot.features.labels import (
    forward_return,
    classification_labels,
    triple_barrier_labels,
)

__all__ = [
    "FEATURE_CATALOG",
    "build_feature_matrix",
    "multi_timeframe_feature",
    "session_features",
    "time_features",
    "forward_return",
    "classification_labels",
    "triple_barrier_labels",
]
