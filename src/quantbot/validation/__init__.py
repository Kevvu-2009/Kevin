"""Validation: IS/OOS splits, walk-forward, Monte Carlo, sensitivity, gates."""

from quantbot.validation.gates import AcceptanceCriteria, GateReport, evaluate_gates
from quantbot.validation.monte_carlo import monte_carlo_equity
from quantbot.validation.sensitivity import parameter_sensitivity
from quantbot.validation.splits import is_oos_split
from quantbot.validation.walk_forward import walk_forward

__all__ = [
    "AcceptanceCriteria",
    "GateReport",
    "evaluate_gates",
    "monte_carlo_equity",
    "parameter_sensitivity",
    "is_oos_split",
    "walk_forward",
]
