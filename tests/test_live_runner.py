"""Live runner safety preflight + YAML config loading."""

import json

import pytest

from quantbot.config_files import discovery_config_from_yaml, load_yaml
from quantbot.execution.live_runner import LiveRunner, LiveRunnerConfig

DISCOVERY_YAML = """
data:
  exchange: binance
  symbols: [BTC/USDT]
  timeframe: 4h
research:
  families: [trend]
  include_ml: false
costs:
  fee_bps: 5.0
gates:
  min_oos_sharpe: 1.5
output:
  dir: out
"""

LIVE_YAML = """
venue:
  name: hyperliquid
  testnet: true
mode: {mode}
trading:
  symbols: [BTC/USDT]
  timeframe: 4h
  leverage: 2
  strategies:
    - name: trend_following
      params: {{}}
safety:
  require_validation_report: {require}
"""


def test_discovery_yaml_roundtrip(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text(DISCOVERY_YAML)
    cfg, raw = discovery_config_from_yaml(p)
    assert cfg.timeframe == "4h"
    assert cfg.families == ("trend",)
    assert cfg.include_ml is False
    assert cfg.costs.fee_bps == 5.0
    assert cfg.gates.min_oos_sharpe == 1.5
    assert raw["output"]["dir"] == "out"


def test_discovery_yaml_rejects_unknown_gate(tmp_path):
    p = tmp_path / "d.yaml"
    p.write_text("gates: {min_oos_sharp: 1.0}\n")  # typo must not pass silently
    with pytest.raises(ValueError, match="unknown gate"):
        discovery_config_from_yaml(p)


def test_load_yaml_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_yaml(tmp_path / "nope.yaml")


def test_live_config_from_yaml(tmp_path):
    p = tmp_path / "live.yaml"
    p.write_text(LIVE_YAML.format(mode="paper", require="true"))
    cfg = LiveRunnerConfig.from_yaml(p)
    assert cfg.mode == "paper" and cfg.testnet is True
    assert cfg.symbols == ["BTC/USDT"] and cfg.leverage == 2
    assert cfg.strategies[0]["name"] == "trend_following"


def test_live_mode_refused_without_env_switch(tmp_path, monkeypatch):
    """config mode=live alone must NOT be enough to trade."""
    monkeypatch.setenv("QUANTBOT_MODE", "paper")
    from quantbot.config import get_settings

    get_settings.cache_clear()
    cfg = LiveRunnerConfig(symbols=["BTC/USDT"], mode="live",
                           strategies=[{"name": "trend_following"}])
    with pytest.raises(SystemExit, match="QUANTBOT_MODE"):
        LiveRunner(cfg)
    get_settings.cache_clear()


def test_live_mode_refused_without_validation_report(tmp_path, monkeypatch):
    monkeypatch.setenv("QUANTBOT_MODE", "live")
    monkeypatch.chdir(tmp_path)  # no reports/research/summary.json here
    from quantbot.config import get_settings

    get_settings.cache_clear()
    cfg = LiveRunnerConfig(symbols=["BTC/USDT"], mode="live",
                           strategies=[{"name": "trend_following"}])
    with pytest.raises(SystemExit, match="no validation report"):
        LiveRunner(cfg)
    get_settings.cache_clear()


def test_paper_mode_constructs_engine(monkeypatch):
    monkeypatch.setenv("QUANTBOT_MODE", "paper")
    from quantbot.config import get_settings

    get_settings.cache_clear()
    cfg = LiveRunnerConfig(symbols=["BTC/USDT"], mode="paper",
                           strategies=[{"name": "trend_following"}])
    runner = LiveRunner(cfg)
    assert runner.trade_venue.__class__.__name__ == "PaperBroker"
    assert set(runner.engine.strategies) == {"BTC/USDT"}
    get_settings.cache_clear()


def test_runner_requires_strategies():
    with pytest.raises(SystemExit, match="no strategies"):
        LiveRunner(LiveRunnerConfig(symbols=["BTC/USDT"], strategies=[]))
