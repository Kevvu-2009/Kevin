"""Playing a level: single-screen boards and Super Hard scrolling boards.

Safety rule everywhere: if the solver can't fully clear the board model,
tap NOTHING (a blocked tap costs a heart).  During Super Hard play every
tap is verified: ink must actually be present at the tap point (phantoms
from a bad stitch are skipped, they cost nothing) and must be gone
afterwards (if it isn't, the board model is wrong and we stop).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from .adb import Adb
from .config import BotConfig
from .solver import solve
from .stitch import Navigator, capture_board, register
from .vision import Arrow, draw_overlay, extract_arrows


def _ink_frac_at(img_bgr: np.ndarray, x: int, y: int, r: int,
                 cfg: BotConfig) -> float:
    h, w = img_bgr.shape[:2]
    x0, y0 = max(0, x - r), max(0, y - r)
    x1, y1 = min(w, x + r + 1), min(h, y + r + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    patch = cv2.cvtColor(img_bgr[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    return float((patch < cfg.ink_gray_thresh).mean())


def _save_debug(cfg: BotConfig, name: str, img: np.ndarray) -> None:
    if cfg.debug_dir:
        d = Path(cfg.debug_dir)
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / name), img)


# ---------------------------------------------------------------------------
# single-screen levels
# ---------------------------------------------------------------------------
def play_single(adb: Adb, cfg: BotConfig) -> bool:
    """Solve and tap a board that fits on one screen.  Returns True when
    every arrow was tapped, False if the solver refused (no taps sent)."""
    img = adb.screencap()
    sw = img.shape[1]
    x0, y0, x1, y1 = cfg.band_rect(sw, img.shape[0])
    band = img[y0:y1, x0:x1]

    arrows, labels = extract_arrows(band, cfg, ref_width=sw)
    if not arrows:
        print("play_single: no arrows found")
        return False
    order = solve(arrows, labels, cfg)
    _save_debug(cfg, "single_overlay.png", draw_overlay(band, arrows, order))
    if order is None:
        print("play_single: solver stuck - NOT tapping (check debug overlay)")
        return False

    for k, a in enumerate(order):
        if cfg.verify_taps:
            # re-capture and confirm ink at the tap point: if an ad or
            # popup covered the board mid-level, stop instead of tapping
            # blindly into it
            live = adb.screencap()[y0:y1, x0:x1]
            r = max(4, int(round(a.half_width)))
            if _ink_frac_at(live, a.tap_point[0], a.tap_point[1],
                            r, cfg) < 0.15:
                print(f"play_single: tap {k + 1}/{len(order)}: board "
                      f"changed (ad/popup?) - stopping taps")
                _save_debug(cfg, "single_interrupted.png", live)
                return False
        adb.tap(x0 + a.tap_point[0], y0 + a.tap_point[1])
        adb.sleep(cfg.tap_settle_s)
    return True


# ---------------------------------------------------------------------------
# Super Hard levels
# ---------------------------------------------------------------------------
def play_superhard(adb: Adb, cfg: BotConfig,
                   nav: Navigator | None = None) -> bool:
    """Stitch the scrolling board, solve it, then scroll-to-tap each arrow
    in solve order.  Returns True when the whole order was executed."""
    nav = nav or Navigator(adb, cfg)
    result = capture_board(nav, cfg, cfg.debug_dir or None)
    canvas = result.canvas
    w_max, h_max = result.extent

    arrows, labels = extract_arrows(canvas, cfg, ref_width=nav.sw)
    if not arrows:
        print("play_superhard: no arrows in stitched board")
        _save_debug(cfg, "board_empty.png", canvas)
        return False
    order = solve(arrows, labels, cfg)
    _save_debug(cfg, "board_overlay.png", draw_overlay(canvas, arrows, order))
    if order is None:
        print("play_superhard: solver stuck - NOT tapping "
              "(see board_overlay.png)")
        return False

    # ref = live board model; every tapped arrow is erased from it so
    # localization stays in sync with the real screen
    ref = canvas.copy()
    bx0, by0, _, _ = nav.band

    for k, a in enumerate(order):
        got = _acquire(nav, ref, cfg, a, w_max, h_max)
        if got is None:
            # phantom from a bad stitch (or the arrow already flew off):
            # skipping costs nothing - keep the model honest and move on
            print(f"tap {k + 1}/{len(order)}: arrow not found on screen, "
                  f"skipping (phantom?)")
            _save_debug(cfg, f"skip_phantom_{k}.png", nav.last)
            _erase(ref, labels, a)
            continue
        sx, sy = got
        r = max(4, int(round(a.half_width)))

        if cfg.debug_dir:                       # show exactly where it aims
            _save_debug(cfg, f"tap_{k:02d}.png",
                        _mark(nav.last, sx, sy, k + 1, a.direction))

        # FINAL identity gate: the arrow actually under the finger, in a
        # fresh segmentation of the live view, must be the target (same
        # direction).  A mis-aimed lock lands on a neighbour pointing some
        # other way - refuse rather than fly the wrong arrow off.
        if cfg.verify_taps and not _aim_hits_target(nav, cfg, a, sx, sy):
            print(f"tap {k + 1}/{len(order)}: the arrow under the aim point "
                  f"is not the target ({a.direction}); stopping so it can't "
                  f"tap the wrong arrow. See tap_{k:02d}.png / board_overlay.png")
            _save_debug(cfg, f"fail_wrongaim_{k:02d}.png",
                        _mark(nav.last, sx, sy, k + 1, a.direction))
            return False

        ok = False
        for attempt in range(1 + cfg.tap_retries):
            adb.tap(bx0 + sx, by0 + sy)
            adb.sleep(cfg.tap_settle_s)
            if not cfg.verify_gone:
                ok = True
                break
            live = nav.capture()
            if _ink_frac_at(live, sx, sy, r, cfg) < 0.15:
                ok = True
                break
            print(f"tap {k + 1}/{len(order)}: arrow still there "
                  f"(attempt {attempt + 1})")
        if not ok:
            print(f"tap {k + 1}/{len(order)}: arrow did not leave - board "
                  f"model is wrong, stopping to protect hearts")
            _save_debug(cfg, f"fail_stuck_{k}.png", nav.last)
            return False

        _erase(ref, labels, a)
        nav.capture()          # refresh after the fly-off animation
    return True


def _mark(band: np.ndarray, sx: int, sy: int, num: int, d: str) -> np.ndarray:
    """Copy of the live band with a crosshair at the intended tap point."""
    out = band.copy()
    cv2.drawMarker(out, (int(sx), int(sy)), (0, 0, 255),
                   cv2.MARKER_CROSS, 70, 4)
    cv2.circle(out, (int(sx), int(sy)), 40, (0, 0, 255), 3)
    cv2.putText(out, f"{num}:{d}", (max(0, int(sx) - 40), max(24, int(sy) - 46)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)
    return out


def _aim_hits_target(nav, cfg: BotConfig, a: Arrow, sx: int, sy: int) -> bool:
    """Re-segment the live band and confirm the arrow at the aim point is
    the target: same direction, comparable size.  Catches a lock that
    slid onto a differently-pointing neighbour (skipping/stopping is free;
    a wrong tap costs a heart).  It cannot tell identical twins apart -
    that's the viewport-position confirmation's job, upstream."""
    live_arrows, live_labels = extract_arrows(nav.last, cfg, ref_width=nav.sw)
    if not live_arrows:
        return False
    h, w = live_labels.shape
    match = None
    if 0 <= sy < h and 0 <= sx < w and live_labels[sy, sx]:
        lab = int(live_labels[sy, sx])
        match = next((la for la in live_arrows if la.id == lab), None)
    if match is None:                            # aim just off the ink
        near = min(live_arrows, key=lambda la: (la.head[0] - sx) ** 2
                                               + (la.head[1] - sy) ** 2)
        if (near.head[0] - sx) ** 2 + (near.head[1] - sy) ** 2 > \
                (2 * max(6, a.half_width)) ** 2:
            return False
        match = near
    if match.direction != a.direction:
        return False
    aw, ah = a.bbox[2], a.bbox[3]
    mw, mh = match.bbox[2], match.bbox[3]        # loose size sanity
    return (0.5 * aw - 8 <= mw <= 1.8 * aw + 8
            and 0.5 * ah - 8 <= mh <= 1.8 * ah + 8)


def _erase(ref: np.ndarray, labels: np.ndarray, a: Arrow) -> None:
    x, y, w, h = a.bbox
    sub = ref[y:y + h, x:x + w]
    sub[labels[y:y + h, x:x + w] == a.id] = 255


def _acquire(nav, ref: np.ndarray, cfg: BotConfig, a: Arrow,
             w_max: float, h_max: float,
             attempts: int = 3) -> tuple[int, int] | None:
    """Scroll the arrow into the safe band and return VERIFIED screen-band
    coordinates of its tap point, or None if it truly isn't there.

    The tap point comes from template-matching the arrow itself (plus
    context) from the ref canvas - already-tapped arrows are erased from
    ref, so it matches the live screen exactly.  Before any peak is
    trusted, the viewport position must be CONFIRMED against ref by a
    supermajority of visible regions (a view off by one board period
    matches the target's identical twin but not the twin's differing
    neighbours); when it can't be, a blind corner reset re-anchors the
    position exactly.  Every success re-anchors nav.pos, so drift can't
    accumulate across taps."""
    hx, hy = a.tap_point
    did_reset = False
    for _attempt in range(attempts):
        nav.scroll_to(1, float(np.clip(hy - nav.bh / 2, 0, h_max)))
        nav.scroll_to(0, float(np.clip(hx - nav.bw / 2, 0, w_max)))
        nav.capture()
        # confirm pos against the ref canvas.  The supermajority demand
        # (min_frac_valid) is what makes this a real identity check: with
        # pos off by a whole board period, the target's twin still
        # matches, but its DIFFERING neighbours don't.
        off, n = register(nav.last, ref, expected=nav.pos.copy(),
                          tol=nav._tol, cfg=cfg, patch=nav._patch,
                          min_valid=2, min_frac_valid=0.6)
        confirmed = off is not None
        if confirmed:
            nav.pos = np.array(off)
        if not (confirmed or did_reset):
            # position cannot be vouched for and might be off by exactly
            # one period (identical twins would fool the peak gate!).
            # Measured edge seeks are unreliable on a nearly-cleared
            # (blank) board, so use the unmeasured, clamp-guaranteed
            # corner reset: afterwards dead-reckoning error is far below
            # one period and the nearest-peak choice is unambiguous.
            nav.blind_reset(w_max, h_max)
            did_reset = True
            continue

        if not cfg.verify_taps:
            sx = int(round(hx - nav.pos[0]))
            sy = int(round(hy - nav.pos[1]))
            if 0 <= sx < nav.bw and 0 <= sy < nav.bh:
                return sx, sy
            continue

        got = _locate_arrow(nav, ref, a, cfg)
        if got is not None:
            sx, sy = got
            if 2 <= sx < nav.bw - 2 and 2 <= sy < nav.bh - 2:
                return sx, sy
            # found near the border: pos was re-anchored, loop re-centers
        elif not did_reset:
            nav.blind_reset(w_max, h_max)
            did_reset = True
    return None


def _locate_arrow(nav, ref: np.ndarray, a: Arrow,
                  cfg: BotConfig) -> tuple[int, int] | None:
    """Template-match the arrow (with surrounding context) from the ref
    canvas against the WHOLE live band, then accept only a strong peak
    close to the dead-reckoned position.  On a repetitive board several
    identical copies can be on screen at once - distance to the expected
    position is the only safe disambiguator, and the caller guarantees it
    is meaningful (blind corner reset when in doubt).  On success
    re-anchors nav.pos and returns the tap point in band coordinates."""
    x, y, w, h = a.bbox
    m = nav._patch // 2
    x0, y0 = max(0, x - m), max(0, y - m)
    x1 = min(ref.shape[1], x + w + m)
    y1 = min(ref.shape[0], y + h + m)
    tpl = cv2.cvtColor(ref[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    band = cv2.cvtColor(nav.last, cv2.COLOR_BGR2GRAY)
    th, tw = tpl.shape
    if th >= band.shape[0] or tw >= band.shape[1]:
        return None

    res = cv2.matchTemplate(band, tpl, cv2.TM_CCOEFF_NORMED)
    _, s1, _, _ = cv2.minMaxLoc(res)
    if s1 < 0.75:
        return None
    peaks = []
    work = res.copy()
    for _ in range(6):
        _, s, _, lp = cv2.minMaxLoc(work)
        if s < max(0.72, s1 - 0.06):
            break
        peaks.append(lp)
        work[max(0, lp[1] - th // 2):lp[1] + th // 2 + 1,
             max(0, lp[0] - tw // 2):lp[0] + tw // 2 + 1] = -1.0

    ex = x0 - nav.pos[0]                  # expected template position
    ey = y0 - nav.pos[1]
    loc = min(peaks, key=lambda p: (p[0] - ex) ** 2 + (p[1] - ey) ** 2)
    gate = max(48.0, 0.06 * nav.bw)
    if ((loc[0] - ex) ** 2 + (loc[1] - ey) ** 2) ** 0.5 > gate:
        return None                       # nearest copy is too far to trust

    sx = loc[0] + a.tap_point[0] - x0
    sy = loc[1] + a.tap_point[1] - y0
    # verify the HEAD specifically: a match that slid along a self-similar
    # shaft scores decently overall but puts shaft/white where the head
    # belongs - tapping there hits the wrong spot (or the wrong arrow)
    hs = max(12, int(round(4 * a.half_width)))
    hx0 = int(np.clip(a.tap_point[0] - hs, 0, ref.shape[1] - 1))
    hy0 = int(np.clip(a.tap_point[1] - hs, 0, ref.shape[0] - 1))
    head_tpl = cv2.cvtColor(ref[hy0:a.tap_point[1] + hs,
                                hx0:a.tap_point[0] + hs],
                            cv2.COLOR_BGR2GRAY)
    ex, ey = sx - (a.tap_point[0] - hx0), sy - (a.tap_point[1] - hy0)
    pad = 6
    wx0, wy0 = max(0, ex - pad), max(0, ey - pad)
    wx1 = min(band.shape[1], ex + head_tpl.shape[1] + pad)
    wy1 = min(band.shape[0], ey + head_tpl.shape[0] + pad)
    if (wx1 - wx0 < head_tpl.shape[1] + 2
            or wy1 - wy0 < head_tpl.shape[0] + 2):
        return None
    hres = cv2.matchTemplate(band[wy0:wy1, wx0:wx1], head_tpl,
                             cv2.TM_CCOEFF_NORMED)
    _, hscore, _, _ = cv2.minMaxLoc(hres)
    if hscore < 0.80:
        return None

    nav.pos = np.array([float(x0 - loc[0]), float(y0 - loc[1])])
    return (sx, sy)
