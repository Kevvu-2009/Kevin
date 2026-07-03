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
from .vision import extract_arrows


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
# ad handling
# ---------------------------------------------------------------------------
def board_like(img_bgr: np.ndarray, cfg: BotConfig) -> bool:
    """Does the capture band contain something that segments like arrows?
    Used to tell 'level in progress' apart from 'interstitial ad'."""
    sh, sw = img_bgr.shape[:2]
    x0, y0, x1, y1 = cfg.band_rect(sw, sh)
    arrows, _ = extract_arrows(img_bgr[y0:y1, x0:x1], cfg, ref_width=sw)
    return len(arrows) > 0


def dismiss_ad(adb: Adb, cfg: BotConfig) -> bool:
    """Try to get back to the game from an interstitial ad.  Order of
    escalation is chosen to never click INTO the ad:

      1. if an earlier click-through kicked us out of the game (Play
         Store / browser in the foreground), relaunch the game;
      2. BACK key presses (close most interstitials, click nothing);
      3. taps on the standard X positions in the two top corners.

    Returns True as soon as the home screen or a board is visible."""
    print("ad watchdog: unknown screen - trying to dismiss")
    t0 = time.time()
    backs = 0
    while time.time() - t0 < cfg.ad_max_dismiss_s:
        pkg = adb.foreground_package()
        if cfg.game_package and pkg and cfg.game_package != pkg:
            print(f"ad watchdog: foreground is {pkg} - relaunching game")
            adb.launch_app(cfg.game_package)
            adb.sleep(5.0)
        elif backs < 3:
            adb.keyevent(4)                   # BACK
            backs += 1
            adb.sleep(2.5)
        elif cfg.ad_corner_taps:
            img = adb.screencap()
            h, w = img.shape[:2]
            for fx, fy in ((0.964, 0.036), (0.036, 0.036)):
                adb.tap(int(w * fx), int(h * fy))
                adb.sleep(2.0)
            backs = 0                         # alternate corners and BACK
        else:
            adb.sleep(2.5)
        img = adb.screencap()
        if find_continue(img, cfg) is not None or board_like(img, cfg):
            print("ad watchdog: back in the game")
            return True
    return False


# ---------------------------------------------------------------------------
# the loop
# ---------------------------------------------------------------------------
def afk_loop(adb: Adb, cfg: BotConfig) -> None:
    skip = {int(x) for x in cfg.skip_levels}
    print(f"AFK loop started (skip list: {sorted(skip) or 'empty'})")
    if not cfg.game_package:
        cfg.game_package = adb.foreground_package() or ""
        if cfg.game_package:
            print(f"game package: {cfg.game_package}")

    unknown_since: float | None = None
    while True:
        img = adb.screencap()
        btn = find_continue(img, cfg)
        if btn is None:
            # in a level / loading / ad.  A board on screen is fine (the
            # user may be playing a skip-level); a screen that is neither
            # home nor board for ad_grace_s is treated as an ad.
            if board_like(img, cfg):
                unknown_since = None
            elif unknown_since is None:
                unknown_since = time.time()
            elif time.time() - unknown_since > cfg.ad_grace_s:
                if not dismiss_ad(adb, cfg):
                    print("could not get past the ad/popup - stopping")
                    return
                unknown_since = None
            time.sleep(cfg.level_poll_s)
            continue
        unknown_since = None

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
            img = adb.screencap()
            if find_continue(img, cfg) is None and not board_like(img, cfg):
                # play was interrupted by something that is neither the
                # board nor the home screen: almost certainly an ad/popup.
                # Dismiss it and re-enter the loop (the level restarts
                # from its current state).
                if dismiss_ad(adb, cfg):
                    continue
            print("could not fully solve this board - stopping the loop so "
                  "no hearts are risked. Check the debug images.")
            return

        if not _wait_for_home(adb, cfg):
            print("win screen never appeared - check the game, stopping")
            return
        print("level cleared!")


def _wait_for_home(adb: Adb, cfg: BotConfig) -> bool:
    """Wait for the Continue button; a post-level interstitial that covers
    the win screen is dismissed on the way."""
    t0 = time.time()
    unknown_since: float | None = None
    while time.time() - t0 < cfg.win_timeout_s + cfg.ad_max_dismiss_s:
        img = adb.screencap()
        if find_continue(img, cfg) is not None:
            return True
        if board_like(img, cfg):
            unknown_since = None              # fly-off animation / loading
        elif unknown_since is None:
            unknown_since = time.time()
        elif time.time() - unknown_since > cfg.ad_grace_s:
            if not dismiss_ad(adb, cfg):
                return False
            unknown_since = None
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
