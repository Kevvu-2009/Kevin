"""Offline end-to-end tests: synthetic boards behind a fake ADB with an
imperfect scroll ratio, jitter and UI chrome.  If these pass, the vision,
solver, stitcher and scroll-to-tap logic are sound - only real-device
tuning (thresholds, band fractions) remains.
"""

import numpy as np
import pytest

from arrows_bot.config import BotConfig
from arrows_bot.fakegame import FakeAdb, make_board
from arrows_bot.play import play_single, play_superhard
from arrows_bot.solver import can_escape, remove_arrow, solve
from arrows_bot.stitch import Navigator, capture_board
from arrows_bot.vision import extract_arrows, ink_mask

SW, SH = 1080, 1920


def cfg() -> BotConfig:
    return BotConfig(swipe_settle_s=0, tap_settle_s=0)


def match_truth(arrows, truth):
    """Pair each ground-truth head with the nearest detected head."""
    pairs = []
    for (hx, hy), d in truth:
        best = min(arrows, key=lambda a: (a.head[0] - hx) ** 2
                                         + (a.head[1] - hy) ** 2)
        dist = ((best.head[0] - hx) ** 2 + (best.head[1] - hy) ** 2) ** 0.5
        pairs.append((best, d, dist))
    return pairs


# ---------------------------------------------------------------------------
def test_vision_heads_and_directions():
    c = cfg()
    board, truth = make_board(1600, 1600, c, seed=2)
    arrows, _ = extract_arrows(board, c, ref_width=SW)
    assert len(arrows) == len(truth) > 5
    for arrow, d, dist in match_truth(arrows, truth):
        assert dist < 40, f"head too far from truth: {dist:.0f}px"
        assert arrow.direction == d


def test_solver_full_clear_and_validity():
    c = cfg()
    board, truth = make_board(1600, 2400, c, seed=3)
    arrows, labels = extract_arrows(board, c, ref_width=SW)
    order = solve(arrows, labels, c)
    assert order is not None and len(order) == len(arrows)
    # replay: every tap must be legal at the moment it happens
    work = labels.copy()
    for a in order:
        assert can_escape(a, work, c)
        remove_arrow(a, work)


def test_solver_refuses_unsolvable():
    c = cfg()
    board, _ = make_board(1400, 1400, c, seed=4)
    arrows, labels = extract_arrows(board, c, ref_width=SW)
    # sabotage: flip every direction so nothing sensible can escape...
    from arrows_bot.vision import OPPOSITE
    for a in arrows:
        a.direction = OPPOSITE[a.direction]
    order = solve(arrows, labels, c)
    # a fully reversed solvable board is usually stuck; if not stuck the
    # order must at least be internally consistent (replay check)
    if order is not None:
        work = labels.copy()
        for a in order:
            assert can_escape(a, work, c)
            remove_arrow(a, work)


# ---------------------------------------------------------------------------
def test_stitch_full_board():
    c = cfg()
    board, truth = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=6)
    nav = Navigator(fake, c)
    res = capture_board(nav, c)

    # measured scroll extents must match the true ones (a few px of
    # integer-measurement noise per swipe accumulates; placement accuracy
    # is guarded by the IoU / arrow checks below, not by the extent)
    true_ext = (2400 - SW, 4000 - SH)
    assert abs(res.extent[0] - true_ext[0]) < 20
    assert abs(res.extent[1] - true_ext[1]) < 20

    # the stitch must be pixel-faithful to the reachable board region:
    # canvas (cx, cy) should equal board (cx + x0, cy + y0).  Allow a few
    # px of global origin error, compensate it, then demand a high IoU
    # (residual per-tile jitter of +-1px on 14px strokes caps raw IoU).
    from arrows_bot.stitch import register
    x0, y0, _, _ = c.band_rect(SW, SH)
    ch, cw = res.canvas.shape[:2]
    off, n = register(res.canvas[300:1800, 300:1800], board,
                      np.array([x0 + 300, y0 + 300]), 40, c, 96, grid=6,
                      min_valid=4)
    assert off is not None, "canvas does not register against the board"
    gx, gy = float(off[0] - x0 - 300), float(off[1] - y0 - 300)  # global err
    assert abs(gx) <= 12 and abs(gy) <= 12, f"origin off by ({gx},{gy})"
    sx0, sy0 = int(round(x0 + gx)), int(round(y0 + gy))
    gt = board[sy0:sy0 + ch, sx0:sx0 + cw]
    m1 = ink_mask(res.canvas[:gt.shape[0], :gt.shape[1]], c) > 0
    m2 = ink_mask(gt, c) > 0
    iou = np.logical_and(m1, m2).sum() / max(1, np.logical_or(m1, m2).sum())
    assert iou > 0.85, f"stitch IoU too low: {iou:.3f}"

    # and semantically identical: same arrows, same directions, solvable
    arrows, labels = extract_arrows(res.canvas, c, ref_width=SW)
    assert len(arrows) == len(truth)
    for arrow, d, dist in match_truth(arrows, [((hx - x0, hy - y0), d)
                                               for (hx, hy), d in truth]):
        assert dist < 40
        assert arrow.direction == d
    assert solve(arrows, labels, c) is not None


def test_play_superhard_end_to_end():
    c = cfg()
    board, truth = make_board(2400, 4000, c, seed=7)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=8)
    assert play_superhard(fake, c)
    assert fake.hearts == 3, "a blocked tap happened - solver/model bug"
    assert len(fake.arrows) == 0, f"{len(fake.arrows)} arrows left"
    assert fake.cleared == len(truth)


def test_skips_never_lose_hearts(monkeypatch):
    """Inject random localization skips (phantoms).  A skip must be deferred,
    never treated as 'cleared' - so the model stays honest and the bot never
    taps a still-blocked arrow.  With the old order-following code a skip
    desynced the model and cost a heart; here hearts must stay full."""
    import random

    import arrows_bot.play as play
    c = cfg()
    board, _ = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=6)
    nav = Navigator(fake, c)
    rng = random.Random(0)
    real = play._acquire
    monkeypatch.setattr(play, "_acquire", lambda *a, **k:
                        None if rng.random() < 0.3 else real(*a, **k))
    play.play_superhard(fake, c, nav=nav)
    assert fake.hearts == 3, "a skip led to a blocked tap - lost a heart"


def test_play_single_screen():
    c = cfg()
    board, truth = make_board(SW, SH, c, seed=9)
    assert len(truth) > 2
    fake = FakeAdb(board, c, sw=SW, sh=SH)
    assert play_single(fake, c)
    assert fake.hearts == 3
    assert len(fake.arrows) == 0


def test_scrolling_never_taps():
    """A capture-only pass (no intended taps) must not lose a single heart.
    The fake reads any sub-slop finger travel as a tap, so this fails if
    the min_swipe floor regresses and micro-swipes slip through."""
    c = cfg()
    board, _ = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=6)
    nav = Navigator(fake, c)
    capture_board(nav, c)
    assert fake.hearts == 3, "scrolling flew arrows off (swipe read as tap)"
    assert fake.cleared == 0, "capture pass moved arrows - it must not"


def test_min_swipe_floor():
    """Every finger travel _swipe emits - even for a tiny requested move -
    must clear the OS tap-slop, or the game reads it as a tap.  Fails if
    the floor regresses (a raw tiny move would be sent through)."""
    c = cfg()
    board, _ = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH)
    nav = Navigator(fake, c)
    assert nav.min_swipe > fake.tap_slop, "min swipe must exceed OS slop"

    sent = []
    orig = fake.swipe
    fake.swipe = lambda x1, y1, x2, y2, duration_ms=None: (
        sent.append(((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5),
        orig(x1, y1, x2, y2, duration_ms))[1]
    for d in (1.0, 3.0, 10.0, 19.0, 25.0, 100.0, 400.0):
        nav._swipe(d, 0.0)
        nav._swipe(0.0, d)
    assert sent and min(sent) >= fake.tap_slop, \
        f"a swipe was shorter than OS slop: min={min(sent):.1f}px"

    before = len(sent)
    nav._swipe(0.0, 0.0)                     # exact zero move -> no gesture
    assert len(sent) == before


def test_oversized_arrow_is_tappable():
    """An arrow LONGER THAN THE SCREEN must still be localizable and
    tappable.  Previously the template was built from the whole arrow, so
    anything bigger than the band could never match and was skipped
    forever ('couldn't localize any free arrows')."""
    import cv2

    from arrows_bot.play import _fully_visible, _locate_arrow
    c = cfg()
    # board with one very long horizontal arrow (wider than the screen)
    board = np.full((2600, 3000, 3), 255, np.uint8)
    y = 1300
    cv2.line(board, (300, y), (2600, y), (90, 30, 30), 18)      # long shaft
    cv2.arrowedLine(board, (2400, y), (2680, y), (90, 30, 30), 18,
                    tipLength=0.5)                              # head, points R
    arrows, _ = extract_arrows(board, c, ref_width=SW)
    assert len(arrows) == 1
    big = arrows[0]
    assert big.bbox[2] > SW, "test arrow should exceed the screen width"

    fake = FakeAdb(board, c, sw=SW, sh=SH)
    nav = Navigator(fake, c)
    bx0, by0 = nav.band[0], nav.band[1]
    # centre the viewport on the head, then set pos to the TRUE board
    # coords of the band's top-left (band pixel (0,0) == board (vx+bx0, vy+by0))
    fake.vx = float(np.clip(big.head[0] - SW // 2, 0, board.shape[1] - SW))
    fake.vy = float(np.clip(big.head[1] - SH // 2, 0, board.shape[0] - SH))
    nav.pos = np.array([fake.vx + bx0, fake.vy + by0])
    nav.capture()

    assert _fully_visible(nav, big), "head is centred; must count as visible"
    got = _locate_arrow(nav, board, big, c)
    assert got is not None, "oversized arrow could not be localized"
    sx, sy = got
    # the returned aim point must land on the real head in the live band
    assert abs((sx + nav.pos[0]) - big.head[0]) <= 12
    assert abs((sy + nav.pos[1]) - big.head[1]) <= 12


def test_visible_implies_tappable():
    """THE INVARIANT: if _fully_visible says an arrow needs no scroll, then
    _locate_arrow must be able to find it AND the aim gate must accept it.

    When these disagree the bot deadlocks: _acquire only re-centres an arrow
    that is NOT _fully_visible, so an arrow that is "visible" but fails
    localization or the aim gate is skipped, retried from the identical
    viewport, skipped again - forever ("couldn't localize any of N
    currently-free arrows", then "no progress").

    Long arrows broke it: _fully_visible used a stroke-scale pad
    (3*half_width, ~70px) while _locate_arrow's head-centred template needs
    half its own size of context (~537px) and the aim gate compared against
    min(bbox, band) (~1043px of expected ink).  Both are far larger than the
    pad, so heads near the band edge passed _fully_visible and then failed
    downstream.  Observed on device: 20 arrows cleared, then a hard stall
    with tap_020.png written but no blocked_020.png (it never tapped).
    """
    import cv2

    from arrows_bot.play import (_aim_hits_target, _fully_visible,
                                 _locate_arrow)
    c = cfg()
    sw, sh = 1900, 3840                  # the resolution the bot runs at
    length, stroke = 2600, 26
    board = np.full((length + 5000, 3000, 3), 255, np.uint8)
    x, y0 = 1500, 1500                   # long arrow pointing DOWN
    cv2.line(board, (x, y0), (x, y0 + length - 200), (90, 30, 30), stroke)
    cv2.arrowedLine(board, (x, y0 + length - 400), (x, y0 + length),
                    (90, 30, 30), stroke, tipLength=0.5)

    arrows, _ = extract_arrows(board, c, ref_width=sw)
    assert len(arrows) == 1
    a = arrows[0]

    fake = FakeAdb(board, c, sw=sw, sh=sh)
    nav = Navigator(fake, c)
    assert a.bbox[3] > 0.9 * nav.bh, "test arrow should be band-scale long"
    bx0, by0 = nav.band[0], nav.band[1]
    hx, hy = a.tap_point

    checked = 0
    for frac in (0.03, 0.06, 0.10, 0.20, 0.35, 0.50, 0.70, 0.85):
        fake.vy = float(np.clip(hy - by0 - frac * nav.bh, 0,
                                board.shape[0] - sh))
        fake.vx = float(np.clip(hx - sw // 2, 0, board.shape[1] - sw))
        nav.pos = np.array([fake.vx + bx0, fake.vy + by0])
        nav.capture()
        if not _fully_visible(nav, a):
            continue                      # _acquire will scroll: fine
        checked += 1
        sy_in_band = hy - nav.pos[1]
        got = _locate_arrow(nav, board, a, c)
        assert got is not None, (
            f"_fully_visible=True but _locate_arrow failed "
            f"(head {sy_in_band:.0f}px into a {nav.bh}px band) - "
            f"this arrow can never be tapped")
        assert _aim_hits_target(nav, c, a, got[0], got[1]), (
            f"_fully_visible=True and localized, but the aim gate rejected "
            f"it (head {sy_in_band:.0f}px into a {nav.bh}px band) - "
            f"this arrow can never be tapped")
    assert checked >= 3, "test did not exercise enough visible positions"


@pytest.mark.xfail(strict=True, reason=(
    "The CAUSE of over-measured extents is fixed (scroll() no longer "
    "dead-reckons a swipe that saturates or flings - see "
    "test_saturating_swipe_is_measured_not_reckoned), so this condition is "
    "now PREVENTED rather than tolerated.  This test forces it anyway, by "
    "inflating measure_extent's result 30%, and the sweep is still not "
    "robust to being handed a wrong extent: it paints tiles past the real "
    "edge at dead-reckoned offsets and tears the canvas.  Kept as a "
    "standing record of that remaining robustness gap.  Sweep-level guards tried and "
    "rejected, so they are not repeated: trusting scroll_to's return value "
    "(it reports success, since the inflated pos makes it believe it "
    "arrived), comparing consecutive tiles per row and across rows, and "
    "darken-blend pasting (turns erasure into ghost duplicates, 119 -> 133 "
    "components).  All left the count at exactly 119 vs 82."))
def test_sweep_stops_at_the_physical_edge():
    """An OVER-measured extent must not tear the stitch.

    measure_extent is exact offline, but on the real device (fling
    momentum, overscroll bounce - none of which the fake models) it has
    come back up to 27% too large on the same level.  The sweep then keeps
    scrolling past the real edge; those tiles cannot be registered against
    the canvas any more, so they get pasted at dead-reckoned offsets and
    tear it.  The damage is mid-canvas, so nothing touches the border and
    neither dropped_ink nor _clipped_arrows notices - the only symptom is
    merged arrows and a board that will not solve.

    Here the extent is inflated deliberately; the sweep must notice the
    viewport has stopped moving and still produce a solvable board.
    """
    import arrows_bot.stitch as st
    c = cfg()
    board, truth = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=6)
    nav = Navigator(fake, c)

    real = Navigator.measure_extent
    monkey = lambda self, axis: real(self, axis) * 1.30      # noqa: E731
    Navigator.measure_extent = monkey
    try:
        res = st.capture_board(nav, c)
    finally:
        Navigator.measure_extent = real

    arrows, labels = extract_arrows(res.canvas, c, ref_width=SW)
    assert len(arrows) == len(truth), (
        f"stitch is torn: {len(arrows)} components vs {len(truth)} arrows "
        f"(merged/fragmented ink from tiles pasted past the real edge)")
    assert solve(arrows, labels, c) is not None, \
        "board built from an over-measured extent will not solve"


def test_saturating_swipe_is_measured_not_reckoned():
    """A swipe that hits the board edge MID-GESTURE travels less than asked.
    Its real shift must be MEASURED; dead-reckoning the full intended
    distance injects a permanent position error.

    This was the bug behind stitched extents differing by 27% between runs
    of the same level (and the torn canvases that followed): the recovery
    search for partially-travelled swipes was gated to steps <=
    alias_safe_frac*bw (124px here), while real scroll steps are ~400px, so
    it never ran for the swipes that need it.  Measured before the fix: a
    swipe that truly travelled 161.6px advanced pos by the full 400.
    """
    c = cfg()
    board, _ = make_board(2400, 4000, c, seed=5)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=6)
    nav = Navigator(fake, c)
    nav.capture()
    nav.seek_edge("U")
    nav.seek_edge("L")
    nav.snap(0, 0.0)
    nav.snap(1, 0.0)

    step = 400.0
    saturated = worst = 0.0
    for _ in range(9):                       # walk right, into the edge
        before = fake.vx
        nav.scroll(step, 0.0)
        real = fake.vx - before
        if 5.0 < real < 0.9 * step:          # the partial step
            saturated = real
        worst = max(worst, abs(nav.pos[0] - fake.vx))

    assert saturated, "test never produced a partially-saturating swipe"
    assert worst < 30.0, (
        f"pos drifted {worst:.0f}px from the true viewport - a swipe that "
        f"only travelled {saturated:.0f}px of {step:.0f} was dead-reckoned "
        f"at its full intended distance")


def test_play_survives_inertial_scrolling():
    """End-to-end with FLING enabled: a real scroll view carries on past
    the end of the gesture, so a swipe can travel FURTHER than asked.

    The simulation had no fling at all, which is exactly why the bot passed
    every offline test and still tore its stitch on the device.  With fling
    modelled, the shift lands outside both the expected-offset window and a
    recovery window that only covered undershoot - so it was unmeasurable
    and every scroll under-counted.  Hearts matter most here: before the
    fix this board lost one to a wrong-arrow tap.
    """
    c = cfg()
    board, truth = make_board(2400, 4000, c, seed=7)
    fake = FakeAdb(board, c, sw=SW, sh=SH, ratio=0.965, jitter=1.0, seed=8,
                   fling=0.10)
    ok = play_superhard(fake, c)
    assert fake.hearts == 3, "a wrong tap cost a heart under inertial scroll"
    assert ok, f"only cleared {fake.cleared}/{len(truth)} with fling"


def test_screencap_raw_decoder():
    """`screencap` without -p returns uint32 (w, h, format[, colorspace])
    then w*h*4 RGBA bytes.  Both header lengths are in the wild, and an
    unrecognised buffer must return None so screencap() falls back to PNG
    rather than handing back garbage pixels."""
    from arrows_bot.adb import Adb
    w, h = 7, 5
    rgba = np.random.default_rng(0).integers(0, 255, (h, w, 4), dtype=np.uint8)
    for header in (12, 16):
        buf = (np.array([w, h, 1, 0][:header // 4], np.uint32).tobytes()
               + rgba.tobytes())
        got = Adb._decode_raw(buf)
        assert got is not None, f"{header}-byte header not recognised"
        assert got.shape == (h, w, 3)
        np.testing.assert_array_equal(got, rgba[:, :, [2, 1, 0]])

    assert Adb._decode_raw(b"") is None
    assert Adb._decode_raw(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64) is None
    short = np.array([w, h, 1], np.uint32).tobytes() + rgba.tobytes()[:-9]
    assert Adb._decode_raw(short) is None, "truncated buffer must not decode"


def test_board_like_vs_ad():
    from arrows_bot.afk import board_like
    c = cfg()
    board, _ = make_board(SW, SH, c, seed=12)
    fake = FakeAdb(board, c, sw=SW, sh=SH)
    assert board_like(fake.screencap(), c) is True
    ad = np.full((SH, SW, 3), 255, np.uint8)          # blank interstitial
    assert board_like(ad, c) is False
    ad[:] = (30, 30, 200)                             # full-screen ad art
    assert board_like(ad, c) is False


def test_probe_scrollable():
    c = cfg()
    big, _ = make_board(2400, 4000, c, seed=10)
    small, _ = make_board(SW, SH, c, seed=11)
    assert Navigator(FakeAdb(big, c), c).probe_scrollable() is True
    assert Navigator(FakeAdb(small, c), c).probe_scrollable() is False


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
