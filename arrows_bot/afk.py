"""AFK loop: home screen -> Continue -> classify board -> play -> detect
win -> repeat.  Supports a skip-list of levels the user wants to play
personally (the bot waits until the level number changes).
"""

from __future__ import annotations

import re
import time

import cv2
import numpy as np

from .adb import Adb
from .config import BotConfig
from .play import play_single, play_superhard
from .stitch import Navigator


# ---------------------------------------------------------------------------
# home-screen detection
# ---------------------------------------------------------------------------
def find_continue(img_bgr: np.ndarray, cfg: BotConfig
                  ) -> tuple[int, int] | None:
    """Center of the big blue Continue button, or None."""
    sh, sw = img_bgr.shape[:2]
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(cfg.blue_hsv_lo, np.uint8),
                       np.array(cfg.blue_hsv_hi, np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask)
    best = None
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        cy = cents[i][1]
        if (w >= cfg.continue_min_w_frac * sw
                and cy >= cfg.continue_region_top_frac * sh
                and w > 2 * h):                       # wide pill shape
            if best is None or area > stats[best][4]:
                best = i
    if best is None:
        return None
    return int(cents[best][0]), int(cents[best][1])


def read_level(img_bgr: np.ndarray) -> int | None:
    """Read the 'Level N' number via pytesseract if it's installed."""
    try:
        import pytesseract
    except ImportError:
        return None
    top = img_bgr[: img_bgr.shape[0] // 2]
    gray = cv2.cvtColor(top, cv2.COLOR_BGR2GRAY)
    text = pytesseract.image_to_string(gray)
    m = re.search(r"level\s*(\d+)", text, re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------
def afk_loop(adb: Adb, cfg: BotConfig) -> None:
    skip = {int(x) for x in cfg.skip_levels}
    print(f"AFK loop started (skip list: {sorted(skip) or 'empty'})")

    while True:
        img = adb.screencap()
        btn = find_continue(img, cfg)
        if btn is None:
            time.sleep(cfg.level_poll_s)      # in a level / ad / loading
            continue

        level = read_level(img)
        print(f"home screen, level {level if level is not None else '?'}")
        if level is not None and level in skip:
            print(f"level {level} is on your skip list - your turn! "
                  f"waiting for the level to change...")
            _wait_level_change(adb, cfg, level)
            continue

        adb.tap(*btn)
        adb.sleep(2.5)                        # board load

        nav = Navigator(adb, cfg)
        if nav.probe_scrollable():
            print("scrollable board detected -> Super Hard pipeline")
            ok = play_superhard(adb, cfg, nav=nav)
        else:
            ok = play_single(adb, cfg)
        if not ok:
            print("could not fully solve this board - stopping the loop so "
                  "no hearts are risked. Check the debug images.")
            return

        if not _wait_for_home(adb, cfg):
            print("win screen never appeared - check the game, stopping")
            return
        print("level cleared!")


def _wait_for_home(adb: Adb, cfg: BotConfig) -> bool:
    t0 = time.time()
    while time.time() - t0 < cfg.win_timeout_s:
        img = adb.screencap()
        if find_continue(img, cfg) is not None:
            return True
        time.sleep(cfg.level_poll_s)
    return False


def _wait_level_change(adb: Adb, cfg: BotConfig, level: int) -> None:
    while True:
        time.sleep(cfg.level_poll_s * 2)
        img = adb.screencap()
        if find_continue(img, cfg) is None:
            continue                          # user is mid-level
        now = read_level(img)
        if now is not None and now != level:
            return
