"""Research-signal library.

Importing this package registers every signal family in SIGNAL_REGISTRY.
"""

from quantbot.research.signals.base import (
    SIGNAL_REGISTRY,
    PanelSignal,
    ResearchSignal,
    get_signal,
    hysteresis_positions,
    list_signals,
    register_signal,
    signal_families,
)

# Import for registration side-effects (order matters only for readability).
from quantbot.research.signals import trend  # noqa: F401,E402
from quantbot.research.signals import momentum  # noqa: F401,E402
from quantbot.research.signals import mean_reversion  # noqa: F401,E402
from quantbot.research.signals import volatility  # noqa: F401,E402
from quantbot.research.signals import structure  # noqa: F401,E402
from quantbot.research.signals import regime  # noqa: F401,E402
from quantbot.research.signals import statarb  # noqa: F401,E402
from quantbot.research.signals import ml_signal  # noqa: F401,E402
from quantbot.research.signals import hybrid  # noqa: F401,E402

__all__ = [
    "SIGNAL_REGISTRY",
    "PanelSignal",
    "ResearchSignal",
    "get_signal",
    "hysteresis_positions",
    "list_signals",
    "register_signal",
    "signal_families",
]
