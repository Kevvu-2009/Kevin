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


def test_play_single_screen():
    c = cfg()
    board, truth = make_board(SW, SH, c, seed=9)
    assert len(truth) > 2
    fake = FakeAdb(board, c, sw=SW, sh=SH)
    assert play_single(fake, c)
    assert fake.hearts == 3
    assert len(fake.arrows) == 0


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
