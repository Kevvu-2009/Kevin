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
from .solver import can_escape, remove_arrow, solve, stuck_set
from .stitch import Navigator, capture_board, register
from .vision import Arrow, draw_overlay, extract_arrows, ink_mask


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
    """Stitch the scrolling board, then clear it by RE-DECIDING every step
    from the true remaining board - only ever tapping an arrow the current,
    accurate model says can escape right now.  Returns True iff every arrow
    was confirmed gone.

    Why not just follow the one-shot solve order: if an arrow can't be
    localized (a "phantom" skip), the rest of that order is invalid - it
    assumed the skip was cleared, so a later arrow that needed it gone gets
    tapped while still blocked, and a blocked tap costs a heart.  So the
    model here loses an arrow ONLY when that arrow is confirmed gone; a
    skip is deferred, never pretended-cleared.
    """
    nav = nav or Navigator(adb, cfg)
    result = capture_board(nav, cfg, cfg.debug_dir or None)
    canvas = result.canvas
    w_max, h_max = result.extent

    print(f"stitched {canvas.shape[1]}x{canvas.shape[0]} "
          f"(extent {w_max:.0f},{h_max:.0f})")
    _save_debug(cfg, "board.png", canvas)

    arrows, labels = extract_arrows(canvas, cfg, ref_width=nav.sw)
    if not arrows:
        print("play_superhard: no arrows in stitched board")
        _save_debug(cfg, "board_empty.png", canvas)
        return False

    order = solve(arrows, labels, cfg)
    stuck = [] if order else stuck_set(arrows, labels, cfg)
    _save_debug(cfg, "board_overlay.png",
                draw_overlay(canvas, arrows, order, {a.id for a in stuck}))
    if order is None:
        clipped = _clipped_arrows(arrows, canvas.shape)
        print(f"play_superhard: solver STUCK on {len(stuck)} of "
              f"{len(arrows)} arrows - NOT tapping (no hearts risked).\n"
              f"  see the MAGENTA boxes in board_overlay.png\n"
              f"  first stuck heads: "
              + ", ".join(f"({a.head[0]},{a.head[1]}) {a.direction}"
                          for a in stuck[:8]))
        if result.dropped_ink > 500 or clipped:
            print(f"  LIKELY CAUSE: the stitch is INCOMPLETE - "
                  f"{len(clipped)} arrows are cut off at the canvas border"
                  f" and {result.dropped_ink} ink px fell outside it.\n"
                  f"  Clipped arrows get a wrong head/direction, which jams "
                  f"the solve. Re-run; if it repeats, the board edge wasn't "
                  f"found (a blank strip at an edge can stop the search "
                  f"early).")
        _report_merges(arrows, cfg, nav.sw)
        if cfg.debug_dir:
            _save_debug(cfg, "ink_mask.png", ink_mask(canvas, cfg))
        return False

    ref = canvas.copy()          # image model; whitened as arrows leave
    work = labels.copy()         # label model; an id -> 0 only when CONFIRMED gone
    by_id = {a.id: a for a in arrows}
    remaining = set(by_id)
    last: tuple[int, int] | None = None
    step = 0
    stalls = 0

    while remaining:
        free = [by_id[i] for i in remaining if can_escape(by_id[i], work, cfg)]
        if not free:
            # accurate model, yet nothing can escape: a direction is wrong
            # or the board really is unsolvable - never happens on good data
            print(f"play_superhard: {len(remaining)} arrows left but none can "
                  f"escape in the model - stopping (bad direction?).")
            _save_debug(cfg, "board_stuck.png",
                        draw_overlay(canvas, [by_id[i] for i in remaining], None))
            return False
        # Clear everything reachable without scrolling first (scrolling
        # dominates runtime, so this is ~one scroll per screenful rather
        # than one per arrow).  But when we DO have to move, go where the
        # ink is, not merely to the nearest arrow.
        #
        # The bot locates itself by matching ink between the live screen and
        # the stitched board, so every arrow it clears removes some of the
        # evidence it needs.  Nearest-first empties one neighbourhood at a
        # time and then creeps along its own blank trail: measured, viewport
        # confirmation went from 100% (13-20 agreeing patches) while the
        # board was full to 40% (1.5 patches) once it had been hollowed out,
        # and a failed confirmation is exactly what surfaces as "couldn't
        # localize any of N free arrows".  Preferring a destination that
        # still has neighbours keeps landmarks on screen; the board then
        # thins out roughly evenly instead of developing a hole.
        ref_xy = last if last is not None else (nav.pos[0] + nav.bw / 2,
                                                nav.pos[1] + nav.bh / 2)
        near2 = (0.5 * min(nav.bw, nav.bh)) ** 2

        def _company(a: Arrow) -> int:
            return sum(1 for i in remaining
                       if (by_id[i].head[0] - a.head[0]) ** 2
                       + (by_id[i].head[1] - a.head[1]) ** 2 <= near2)

        free.sort(key=lambda a: (not _fully_visible(nav, a),
                                 -_company(a),
                                 (a.head[0] - ref_xy[0]) ** 2
                                 + (a.head[1] - ref_xy[1]) ** 2))

        progressed = False
        for a in free:
            res = _try_tap(nav, adb, cfg, a, w_max, h_max, ref, step)
            if res == "ok":
                _erase(ref, labels, a)          # whiten image (orig labels)
                remove_arrow(a, work)           # remove from live model
                remaining.discard(a.id)
                last = a.head
                progressed = True
                step += 1
                break                           # _try_tap already re-captured
            if res == "blocked":
                print(f"play_superhard: arrow at {a.head} ({a.direction}) is "
                      f"free in the model but won't leave in-game - stopping to "
                      f"protect hearts (a special/red arrow?). "
                      f"See blocked_{step:03d}.png")
                return False
            # "skip": couldn't confirm this one now - try the next free arrow

        if not progressed:
            stalls += 1
            print(f"play_superhard: couldn't localize any of {len(free)} "
                  f"currently-free arrows ({len(remaining)} remain, "
                  f"try {stalls}).")
            if stalls >= 2:
                print("play_superhard: no progress - stopping. Re-run to "
                      "re-stitch, or check the debug images.")
                _save_debug(cfg, "board_noprogress.png",
                            draw_overlay(canvas, [by_id[i] for i in remaining],
                                         None))
                return False
        else:
            stalls = 0

    print("play_superhard: board cleared!")
    return True


def _try_tap(nav, adb: Adb, cfg: BotConfig, a: Arrow, w_max: float,
             h_max: float, ref: np.ndarray, step: int) -> str:
    """Localize, aim-gate, tap, and verify one free arrow.  Returns:
        "ok"      - the arrow is confirmed gone
        "skip"    - couldn't confidently localize/aim (defer, costs nothing)
        "blocked" - aimed correctly but the arrow won't leave (protect hearts)

    Miss vs block: after a tap that leaves the arrow present, re-localize.
    If the arrow's head moved, the tap MISSED (empty space, no heart) - re-aim
    and try once more.  If it's exactly where we tapped, it's genuinely
    blocked - report without a second heart-costing tap."""
    bx0, by0, _, _ = nav.band
    got = _acquire(nav, ref, cfg, a, w_max, h_max)
    if got is None:
        _save_debug(cfg, f"skip_{step:03d}.png", nav.last)
        return "skip"
    sx, sy = got
    if cfg.debug_dir:
        _save_debug(cfg, f"tap_{step:03d}.png", _mark(nav.last, sx, sy,
                                                      step + 1, a.direction))
    if cfg.verify_taps and not _aim_hits_target(nav, cfg, a, sx, sy):
        return "skip"                           # not confidently the target
    r = max(4, int(round(a.half_width)))

    for _attempt in range(2):
        adb.tap(bx0 + sx, by0 + sy)
        adb.sleep(cfg.tap_settle_s)
        if not cfg.verify_gone:
            return "ok"
        if _ink_frac_at(nav.capture(), sx, sy, r, cfg) < 0.15:
            return "ok"
        got2 = _acquire(nav, ref, cfg, a, w_max, h_max)   # miss or block?
        if got2 is None:
            return "skip"
        sx2, sy2 = got2
        if (sx2 - sx) ** 2 + (sy2 - sy) ** 2 <= (1.5 * r) ** 2:
            _save_debug(cfg, f"blocked_{step:03d}.png",
                        _mark(nav.last, sx2, sy2, step + 1, a.direction))
            return "blocked"                    # unmoved & aimed right
        sx, sy = sx2, sy2                        # missed: re-aim, tap once more
    return "blocked"


def _tpl_size(nav, a: Arrow) -> tuple[int, int]:
    """Size of the head-centred template _locate_arrow will build for `a`.
    Kept here so _fully_visible and _locate_arrow can never disagree about
    how much context the match needs."""
    m = nav._patch // 2
    return (int(min(a.bbox[2] + 2 * m, nav.bw * 0.40)),
            int(min(a.bbox[3] + 2 * m, nav.bh * 0.40)))


def _fully_visible(nav, a: Arrow) -> bool:
    """Is the target's HEAD - plus the context needed to MATCH it - already
    well inside the band?  Only the head must be on screen to tap it
    (requiring the whole bbox is unsatisfiable for arrows longer than the
    screen, which are common on Super Hard boards).

    But "the head" alone is not enough to localize: _locate_arrow matches a
    head-centred template that extends half its size around the head, so
    that much must be on screen too.  A stroke-scale pad (3*half_width,
    ~70px) let the head sit right at the band edge, where the template has
    almost nothing to match against - localization then either found no
    strong peak, or found one whose live fragment was too small for the aim
    gate.  Either way the arrow was skipped, and because this said "visible"
    _acquire never re-centred it, so the stall repeated forever.
    """
    cx, cy = a.tap_point
    sx, sy = cx - nav.pos[0], cy - nav.pos[1]
    tw, th = _tpl_size(nav, a)
    # half the template, floored at the old stroke-scale pad.  Templates are
    # capped at 40% of the band, so this is at most 20% - always satisfiable.
    px = max(24.0, 3.0 * a.half_width, tw / 2.0)
    py = max(24.0, 3.0 * a.half_width, th / 2.0)
    return (px <= sx <= nav.bw - px) and (py <= sy <= nav.bh - py)


def _report_merges(arrows: list[Arrow], cfg: BotConfig, sw: int) -> None:
    """Warn when components look like MERGED arrows.

    Segmentation relies on the thin white gap between arrows.  Lower the
    emulator resolution far enough and that gap blurs away, so two or more
    arrows join into one component - which then gets a nonsense head and
    direction, and jams the solve.  A merged blob is far larger than a
    typical arrow, so a heavy upper tail in the area distribution is the
    tell."""
    if len(arrows) < 8:
        return
    areas = sorted(a.area for a in arrows)
    med = areas[len(areas) // 2]
    big = [a for a in arrows if a.area > 4 * med]
    stroke = min(a.half_width for a in arrows) * 2
    if big:
        print(f"  POSSIBLE MERGED ARROWS: {len(big)} components are >4x the "
              f"median size ({med} px) - at this resolution the white gaps "
              f"between arrows may be too thin to separate them.")
    if stroke < 10:
        print(f"  Arrow strokes are only ~{stroke:.0f}px wide. If the board "
              f"won't solve, RAISE the emulator resolution (BlueStacks "
              f"Settings > Display) - bigger arrows means clearer gaps.")


def _clipped_arrows(arrows: list[Arrow], shape, tol: int = 2) -> list[Arrow]:
    """Arrows whose bbox touches the canvas border - i.e. shapes cut off by
    an incomplete stitch.  Their head/direction is read from a fragment, so
    they are the usual reason a stitched board won't solve."""
    h, w = shape[:2]
    out = []
    for a in arrows:
        x, y, bw, bh = a.bbox
        if (x <= tol or y <= tol
                or x + bw >= w - tol or y + bh >= h - tol):
            out.append(a)
    return out


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
    # Loose size sanity against the fragment we EXPECT to see: the part of
    # the arrow that actually intersects the band at the current viewport.
    # An arrow longer than the screen only ever appears as a fragment, and
    # which fragment depends on where the viewport sits - clamping to the
    # whole band instead (min(bbox, band)) demanded ~40% of a screenful of
    # ink even when the head sat near the band edge, so every big arrow was
    # rejected there and skipped forever.
    bx, by, bw_, bh_ = a.bbox
    aw = max(0.0, min(bx + bw_, nav.pos[0] + nav.bw) - max(bx, nav.pos[0]))
    ah = max(0.0, min(by + bh_, nav.pos[1] + nav.bh) - max(by, nav.pos[1]))
    mw, mh = match.bbox[2], match.bbox[3]
    return (0.4 * aw - 8 <= mw <= 1.8 * aw + 8
            and 0.4 * ah - 8 <= mh <= 1.8 * ah + 8)


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
        # Only scroll when the arrow isn't already comfortably on screen.
        # Re-centering every arrow is what made play crawl: each swipe
        # costs ~2s, and after a tap the next (nearest-first) target is
        # usually already visible.
        if not _fully_visible(nav, a):
            nav.scroll_to(1, float(np.clip(hy - nav.bh / 2, 0, h_max)))
            nav.scroll_to(0, float(np.clip(hx - nav.bw / 2, 0, w_max)))
        nav.capture_if_stale()      # reuse the post-tap frame when unmoved
        confirmed = _pos_confirmed(nav, ref, cfg)
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
                # NEVER tap on an unconfirmed viewport.  _locate_arrow
                # matches the arrow's own template, which cannot tell the
                # target from an identical twin - that is the viewport
                # confirmation's job.  After a blind_reset this loop used to
                # fall straight through to here with `confirmed` still
                # False, so a position that was wrong (e.g. drifted by a
                # flung swipe) put the finger on a DIFFERENT arrow that
                # happened to share a direction and size, which sails
                # through the aim gate and costs a heart.  _locate_arrow has
                # just re-anchored pos from its match, so re-check it here:
                # if the match was honest this now confirms cheaply.
                # Trustworthy by construction: blind_reset drives into the
                # corner against the scroll clamp, so pos is EXACT there,
                # and if every swipe since was measured then pos is still
                # exact.  This is the endgame case - once only a few arrows
                # remain there is too little ink left to confirm anything by
                # matching, so demanding a match would strand the last
                # arrows on every board.  A dead-reckoned swipe in between
                # voids it: that is precisely when pos becomes a guess.
                exact = did_reset and nav.reckoned == 0
                if confirmed or exact or _pos_confirmed(nav, ref, cfg):
                    return sx, sy
                continue            # unverifiable: defer.  A skip is free.
            # found near the border: pos was re-anchored, loop re-centers
        elif not did_reset:
            nav.blind_reset(w_max, h_max)
            did_reset = True
    return None


def _pos_confirmed(nav, ref: np.ndarray, cfg: BotConfig) -> bool:
    """Confirm nav.pos against the ref canvas, re-anchoring it on success.

    The supermajority demand (min_frac_valid) is what makes this a real
    identity check rather than a similarity check: with pos off by a whole
    board period the target's twin still matches, but the twin's DIFFERING
    neighbours do not, so most visible regions disagree."""
    off, _n = register(nav.last, ref, expected=nav.pos.copy(),
                       tol=nav._tol, cfg=cfg, patch=nav._patch,
                       min_valid=2, min_frac_valid=0.6)
    if off is not None:
        nav.pos = np.array(off)
        nav.reckoned = 0            # re-anchored against real ink
    return off is not None


def _locate_arrow(nav, ref: np.ndarray, a: Arrow,
                  cfg: BotConfig) -> tuple[int, int] | None:
    """Template-match the arrow (with surrounding context) from the ref
    canvas against the WHOLE live band, then accept only a strong peak
    close to the dead-reckoned position.  On a repetitive board several
    identical copies can be on screen at once - distance to the expected
    position is the only safe disambiguator, and the caller guarantees it
    is meaningful (blind corner reset when in doubt).  On success
    re-anchors nav.pos and returns the tap point in band coordinates."""
    # Template: a region CENTRED ON THE HEAD, capped so it always fits in
    # the band with room to search.  Using the whole arrow made every arrow
    # longer than the screen permanently un-tappable (its template couldn't
    # fit, so it was skipped forever) - and only the head must be on screen
    # to tap it anyway.
    x, y, w, h = a.bbox
    m = nav._patch // 2
    cx, cy = a.tap_point
    rw = int(min(w + 2 * m, nav.bw * 0.40))
    rh = int(min(h + 2 * m, nav.bh * 0.40))
    x0 = int(np.clip(cx - rw // 2, 0, max(0, ref.shape[1] - rw)))
    y0 = int(np.clip(cy - rh // 2, 0, max(0, ref.shape[0] - rh)))
    tpl = cv2.cvtColor(ref[y0:y0 + rh, x0:x0 + rw], cv2.COLOR_BGR2GRAY)
    band = cv2.cvtColor(nav.last, cv2.COLOR_BGR2GRAY)
    th, tw = tpl.shape
    if th >= band.shape[0] or tw >= band.shape[1] or th < 8 or tw < 8:
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
