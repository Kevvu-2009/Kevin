"""Strategy registry enabling plug-and-play discovery.

Decorate a ``Strategy`` subclass with ``@register("name")`` and it becomes
available to the optimizer, backtester and live engine by string key.
"""

from __future__ import annotations

from typing import Callable, Type

from quantbot.strategies.base import Strategy

_REGISTRY: dict[str, Type[Strategy]] = {}


def register(name: str) -> Callable[[Type[Strategy]], Type[Strategy]]:
    def _wrap(cls: Type[Strategy]) -> Type[Strategy]:
        key = name.lower()
        if key in _REGISTRY and _REGISTRY[key] is not cls:
            raise ValueError(f"Strategy '{key}' already registered")
        cls.name = key
        _REGISTRY[key] = cls
        return cls

    return _wrap


def get_strategy(name: str, **params) -> Strategy:
    key = name.lower()
    if key not in _REGISTRY:
        raise KeyError(f"Unknown strategy '{name}'. Available: {sorted(_REGISTRY)}")
    return _REGISTRY[key](**params)


def get_strategy_class(name: str) -> Type[Strategy]:
    return _REGISTRY[name.lower()]


def list_strategies() -> list[str]:
    return sorted(_REGISTRY)
