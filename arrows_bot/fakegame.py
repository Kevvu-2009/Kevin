"""Offline emulator simulator so the whole pipeline can be tested without
BlueStacks.

FakeAdb implements the same interface as adb.Adb (screencap / tap / swipe /
sleep) on top of a synthetic board image:
  * the viewport scrolls with an imperfect swipe ratio + per-swipe jitter
    and clamps at the board edges (like a real scroll view),
  * screenshots get a hearts header and a floating "#" button drawn on
    top (they must NOT end up in the stitch),
  * taps obey the real game rule: an arrow whose head corridor is clear
    flies off (its ink is erased), a blocked tap costs a heart.

make_board() generates a guaranteed-solvable board: arrows are inserted
one at a time only where their head corridor is clear of all previously
placed ink, so tapping in reverse insertion order always clears the board
(and greedy therefore succeeds too).
"""

from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np

from .config import BotConfig
from .solver import can_escape, remove_arrow
from .vision import DIRS, extract_arrows

INK_BGR = (90, 30, 30)          # dark navy


# ---------------------------------------------------------------------------
# board generator
# ---------------------------------------------------------------------------
def make_board(bw: int, bh: int, cfg: BotConfig, seed: int = 1,
               cell: int = 190, stroke: int = 14, margin: int = 340,
               fill: float = 0.7) -> tuple[np.ndarray, list]:
    """Returns (board_bgr, truth) where truth = [(head_xy, direction), ...].

    `margin` must be at least as large as the band offsets so every arrow
    is reachable inside the capture band (the real game pads its scroll
    bounds the same way).
    """
    rng = np.random.default_rng(seed)
    board = np.full((bh, bw, 3), 255, np.uint8)
    ink = np.zeros((bh, bw), np.uint8)
    truth: list[tuple[tuple[int, int], str]] = []

    cols = (bw - 2 * margin) // cell
    rows = (bh - 2 * margin) // cell
    cells = [(r, c) for r in range(rows) for c in range(cols)]
    rng.shuffle(cells)
    corridor_hw = 2 * stroke     # generous: wider than any rule we test

    for r, c in cells:
        if rng.random() > fill:
            continue
        pad = 24
        ix0 = margin + c * cell + pad
        iy0 = margin + r * cell + pad
        inner = cell - 2 * pad
        cx, cy = ix0 + inner // 2, iy0 + inner // 2
        L1 = int(inner * rng.uniform(0.45, 0.60))
        L2 = int(inner * rng.uniform(0.25, 0.40)) * int(rng.choice([-1, 1]))
        tri_l, tri_hw = int(2.5 * stroke), int(1.5 * stroke)

        for d in rng.permutation(list(DIRS)):
            dx, dy = DIRS[d]
            if d == "U":
                E = (cx, iy0 + tri_l + 2)
            elif d == "D":
                E = (cx, iy0 + inner - tri_l - 2)
            elif d == "L":
                E = (ix0 + tri_l + 2, cy)
            else:
                E = (ix0 + inner - tri_l - 2, cy)
            C = (E[0] - dx * L1, E[1] - dy * L1)
            T = (C[0] + abs(dy) * L2, C[1] + abs(dx) * L2)  # perpendicular

            # head corridor must be clear of every arrow placed so far ->
            # reverse insertion order clears the board, so it's solvable
            ex, ey = E
            if d == "U":
                strip = ink[:ey, max(0, ex - corridor_hw):ex + corridor_hw]
            elif d == "D":
                strip = ink[ey:, max(0, ex - corridor_hw):ex + corridor_hw]
            elif d == "L":
                strip = ink[max(0, ey - corridor_hw):ey + corridor_hw, :ex]
            else:
                strip = ink[max(0, ey - corridor_hw):ey + corridor_hw, ex:]
            if strip.any():
                continue

            pts = np.array([T, C, E], np.int32)
            for target, color in ((board, INK_BGR), (ink, 255)):
                cv2.polylines(target, [pts], False, color, stroke,
                              cv2.LINE_8)
                tip = (ex + dx * tri_l, ey + dy * tri_l)
                b1 = (ex + abs(dy) * tri_hw, ey + abs(dx) * tri_hw)
                b2 = (ex - abs(dy) * tri_hw, ey - abs(dx) * tri_hw)
                cv2.fillPoly(target, [np.array([tip, b1, b2], np.int32)],
                             color)
            truth.append((E, d))
            break
    return board, truth


# ---------------------------------------------------------------------------
# fake ADB
# ---------------------------------------------------------------------------
class FakeAdb:
    def __init__(self, board: np.ndarray, cfg: BotConfig,
                 sw: int = 1080, sh: int = 1920, ratio: float = 0.965,
                 jitter: float = 1.0, seed: int = 0):
        assert board.shape[0] >= sh and board.shape[1] >= sw
        self.board = board.copy()
        self.cfg = cfg
        # the GAME's collision rule is fixed and independent of whatever
        # the solver is tuned to - the solver must out-margin it
        self.rule_cfg = replace(cfg, corridor_width_factor=0.9)
        self.sw, self.sh = sw, sh
        self.ratio = ratio
        self.jitter = jitter
        self.tap_slop = 20.0            # OS tap-vs-scroll threshold (px)
        self.rng = np.random.default_rng(seed)
        self.vx = (board.shape[1] - sw) / 2.0
        self.vy = (board.shape[0] - sh) / 2.0
        self.hearts = 3
        self.misses = 0
        self.cleared = 0
        self.arrows, self.labels = extract_arrows(self.board, cfg,
                                                  ref_width=sw)
        self._by_id = {a.id: a for a in self.arrows}

    # -- Adb interface ----------------------------------------------------
    def screencap(self) -> np.ndarray:
        x, y = int(round(self.vx)), int(round(self.vy))
        view = self.board[y:y + self.sh, x:x + self.sw].copy()
        # hearts header (must be excluded by the capture band)
        cv2.rectangle(view, (0, 0), (self.sw, int(0.10 * self.sh)),
                      (235, 235, 235), -1)
        for i in range(self.hearts):
            cv2.circle(view, (int(self.sw * (0.40 + 0.08 * i)),
                              int(0.05 * self.sh)), 18, (40, 40, 220), -1)
        # floating "#" button bottom-right (also outside the band)
        cv2.rectangle(view, (int(0.86 * self.sw), int(0.90 * self.sh)),
                      (int(0.96 * self.sw), int(0.96 * self.sh)),
                      (60, 60, 60), -1)
        return view

    def screen_size(self) -> tuple[int, int]:
        return self.sw, self.sh

    def swipe(self, x1, y1, x2, y2, duration_ms=None) -> None:
        # Model the real hazard: a finger travel shorter than the OS touch
        # slop is NOT a scroll - the game reads it as a TAP at that point
        # (and flies an arrow off / costs a heart).  This is exactly the
        # accidental-tap bug the min_swipe floor exists to prevent.
        if ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 < self.tap_slop:
            self.tap((x1 + x2) / 2 - self.vx, (y1 + y2) / 2 - self.vy)
            return
        dx = (x1 - x2) * self.ratio + self.rng.normal(0, self.jitter)
        dy = (y1 - y2) * self.ratio + self.rng.normal(0, self.jitter)
        self.vx = float(np.clip(self.vx + dx, 0, self.board.shape[1] - self.sw))
        self.vy = float(np.clip(self.vy + dy, 0, self.board.shape[0] - self.sh))

    def tap(self, x, y) -> None:
        bx = int(round(self.vx + x))
        by = int(round(self.vy + y))
        if not (0 <= bx < self.board.shape[1] and 0 <= by < self.board.shape[0]):
            self.misses += 1
            return
        lab = int(self.labels[by, bx])
        if lab == 0 or lab not in self._by_id:
            self.misses += 1                      # tapped empty board
            return
        a = self._by_id[lab]
        if can_escape(a, self.labels, self.rule_cfg):
            x0, y0, w, h = a.bbox                 # arrow flies off
            sub = self.board[y0:y0 + h, x0:x0 + w]
            sub[self.labels[y0:y0 + h, x0:x0 + w] == a.id] = 255
            remove_arrow(a, self.labels)
            self.arrows.remove(a)
            del self._by_id[lab]
            self.cleared += 1
        else:
            self.hearts -= 1                      # blocked tap!

    def sleep(self, seconds: float) -> None:      # tests don't wait
        pass

    # ad-handling interface (no ads in the fake)
    def keyevent(self, code) -> None:
        pass

    def foreground_package(self) -> str | None:
        return "com.fake.arrows"

    def launch_app(self, package: str) -> None:
        pass
