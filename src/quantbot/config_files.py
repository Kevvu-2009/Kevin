"""YAML configuration loading for discovery and live trading.

Secrets never live in YAML — they come from the environment (see config.py).
PyYAML is imported lazily; a clear error tells the user to install it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from quantbot.research.discovery import DiscoveryConfig
from quantbot.research.validation import CostModel, ResearchGates


def load_yaml(path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PyYAML required for config files: pip install pyyaml") from e
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    with open(p) as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {p}")
    return data


def discovery_config_from_yaml(path: str | Path) -> tuple[DiscoveryConfig, dict[str, Any]]:
    """Build a DiscoveryConfig from YAML; returns (config, raw_dict).

    Unknown keys raise — silent typos in gate names would silently weaken
    the validation, which is the one failure mode this file must not have.
    """
    raw = load_yaml(path)
    research = dict(raw.get("research", {}))
    costs_d = dict(raw.get("costs", {}))
    gates_d = dict(raw.get("gates", {}))
    data = dict(raw.get("data", {}))

    allowed_costs = {"fee_bps", "slippage_bps", "spread_bps"}
    unknown = set(costs_d) - allowed_costs
    if unknown:
        raise ValueError(f"unknown cost keys: {sorted(unknown)}")
    costs = CostModel(**costs_d)

    allowed_gates = set(ResearchGates.__dataclass_fields__)
    unknown = set(gates_d) - allowed_gates
    if unknown:
        raise ValueError(f"unknown gate keys: {sorted(unknown)}")
    gates = ResearchGates(**gates_d)

    cfg = DiscoveryConfig(
        timeframe=data.get("timeframe", "1h"),
        families=tuple(research.get("families", ()) or ()),
        exclude_signals=tuple(research.get("exclude_signals", ()) or ()),
        costs=costs,
        gates=gates,
        is_frac=float(research.get("is_frac", 0.7)),
        wf_splits=int(research.get("wf_splits", 4)),
        mc_sims=int(research.get("mc_sims", 500)),
        min_bars=int(research.get("min_bars", 2000)),
        max_pairs=int(research.get("max_pairs", 4)),
        include_ml=bool(research.get("include_ml", True)),
    )
    return cfg, raw
