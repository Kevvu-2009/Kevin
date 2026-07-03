"""Corridor collision rule + greedy peel.

Collision rule (the key game mechanic): an arrow escapes iff the corridor
directly in front of its ARROWHEAD is clear of other arrows - a strip as
wide as the arrow, from the head straight out to the board edge.  The bent
body slides along its own path and exits through the head, so only that
forward corridor matters.

Greedy peel is complete & optimal: removing an arrow never blocks another,
so repeatedly tapping ANY escapable arrow clears every solvable board.  If
greedy gets stuck the board data is wrong (bad direction / segmentation).
"""

from __future__ import annotations

import numpy as np

from .config import BotConfig
from .vision import Arrow


def _corridor_slice(a: Arrow, shape: tuple[int, int],
                    factor: float) -> tuple[slice, slice]:
    """(row_slice, col_slice) of the strip in front of the head."""
    h, w = shape
    hx, hy = a.head
    half = max(1, int(round(a.half_width * factor)))
    if a.direction == "U":
        return slice(0, hy + 1), slice(max(0, hx - half), min(w, hx + half + 1))
    if a.direction == "D":
        return slice(hy, h), slice(max(0, hx - half), min(w, hx + half + 1))
    if a.direction == "L":
        return slice(max(0, hy - half), min(h, hy + half + 1)), slice(0, hx + 1)
    # "R"
    return slice(max(0, hy - half), min(h, hy + half + 1)), slice(hx, w)


def can_escape(a: Arrow, labels: np.ndarray, cfg: BotConfig) -> bool:
    """True if nothing but the arrow itself sits in its head corridor."""
    rs, cs = _corridor_slice(a, labels.shape, cfg.corridor_width_factor)
    strip = labels[rs, cs]
    return not np.any((strip != 0) & (strip != a.id))


def remove_arrow(a: Arrow, labels: np.ndarray) -> None:
    x, y, w, h = a.bbox
    sub = labels[y:y + h, x:x + w]
    sub[sub == a.id] = 0


def solve(arrows: list[Arrow], labels: np.ndarray,
          cfg: BotConfig) -> list[Arrow] | None:
    """Return a full tap order, or None if the board can't be fully solved
    (then DON'T tap anything - a blocked tap costs a heart).

    Among currently escapable arrows we pick the one nearest the previous
    tap, which keeps Super Hard scrolling short.  labels is not modified.
    """
    work = labels.copy()
    remaining = list(arrows)
    order: list[Arrow] = []
    last_xy: tuple[int, int] | None = None

    while remaining:
        free = [a for a in remaining if can_escape(a, work, cfg)]
        if not free:
            return None
        if last_xy is None:
            pick = free[0]
        else:
            lx, ly = last_xy
            pick = min(free, key=lambda a: (a.head[0] - lx) ** 2
                                           + (a.head[1] - ly) ** 2)
        remove_arrow(pick, work)
        remaining.remove(pick)
        order.append(pick)
        last_xy = pick.head
    return order
