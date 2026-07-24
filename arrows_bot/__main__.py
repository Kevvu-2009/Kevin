"""CLI entry points.

    python -m arrows_bot probe                # ADB sanity: size + screenshot
    python -m arrows_bot solve [--dry-run]    # single-screen board
    python -m arrows_bot stitch -o board.png  # Super Hard capture only
    python -m arrows_bot superhard            # stitch + solve + tap
    python -m arrows_bot afk [--skip 12,34]   # the full AFK loop

Common flags: --config bot.json  --adb PATH  --serial SERIAL  --debug DIR
"""

from __future__ import annotations

import argparse
import sys

import cv2

from .adb import Adb
from .afk import afk_loop
from .config import BotConfig
from .play import play_single, play_superhard
from .solver import solve
from .stitch import Navigator, capture_board
from .vision import draw_overlay, extract_arrows


def _report_board(board_bgr, cfg: BotConfig, overlay_name: str,
                  ref_width: int):
    """Segment + solve a board image, save the overlay (STUCK arrows boxed
    in magenta), dump the ink mask when --debug is set, and print a
    diagnosis.  Returns the solve order (None if stuck)."""
    from pathlib import Path

    from .solver import stuck_set
    from .vision import ink_mask

    arrows, labels = extract_arrows(board_bgr, cfg, ref_width=ref_width)
    order = solve(arrows, labels, cfg)
    stuck = [] if order else stuck_set(arrows, labels, cfg)
    overlay = draw_overlay(board_bgr, arrows, order,
                           highlight={a.id for a in stuck})
    cv2.imwrite(overlay_name, overlay)
    if cfg.debug_dir:
        d = Path(cfg.debug_dir)
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / "ink_mask.png"), ink_mask(board_bgr, cfg))

    if order:
        print(f"{len(arrows)} arrows, solver: OK -> {overlay_name}")
    else:
        pts = ", ".join(f"({a.head[0]},{a.head[1]}) {a.direction}"
                        for a in stuck[:8])
        print(f"{len(arrows)} arrows, solver: STUCK on {len(stuck)} of them "
              f"-> see the MAGENTA boxes in {overlay_name}\n"
              f"  first stuck heads: {pts}"
              + ("" if not cfg.debug_dir else
                 "\n  ink_mask.png dumped - check the red arrows show up "
                 "white in it"))
    return order


def build_cfg(args) -> BotConfig:
    cfg = (BotConfig.load(args.config) if getattr(args, "config", None)
           else BotConfig())
    if getattr(args, "adb", None):
        cfg.adb_path = args.adb
    if getattr(args, "serial", None):
        cfg.adb_serial = args.serial
    if getattr(args, "debug", None):
        cfg.debug_dir = args.debug
    return cfg


def main(argv=None) -> int:
    # Global flags live on a parent parser added to every subparser too,
    # so they work in EITHER position (`--serial X probe` and
    # `probe --serial X` both parse).  SUPPRESS defaults stop the
    # subparser copy from clobbering a value the main parser already set.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default=argparse.SUPPRESS,
                        help="JSON config file (see BotConfig)")
    common.add_argument("--adb", default=argparse.SUPPRESS,
                        help="path to adb.exe")
    common.add_argument("--serial", default=argparse.SUPPRESS,
                        help="adb device serial (or set $env:ANDROID_SERIAL)")
    common.add_argument("--debug", default=argparse.SUPPRESS,
                        help="directory for debug images")

    p = argparse.ArgumentParser(
        prog="arrows_bot", description=__doc__, parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", parents=[common])
    sp = sub.add_parser("solve", parents=[common])
    sp.add_argument("--dry-run", action="store_true",
                    help="detect + solve + save overlay, but don't tap")
    st = sub.add_parser("stitch", parents=[common])
    st.add_argument("-o", "--out", default="board.png")
    sub.add_parser("superhard", parents=[common])
    ak = sub.add_parser("afk", parents=[common])
    ak.add_argument("--skip", default="",
                    help="comma-separated level numbers to play yourself")

    args = p.parse_args(argv)
    cfg = build_cfg(args)
    adb = Adb(cfg)
    adb.reconnect()          # re-establish a dropped BlueStacks TCP link

    if args.cmd == "probe":
        w, h = adb.screen_size()
        img = adb.screencap()
        cv2.imwrite("probe.png", img)
        print(f"screen {w}x{h}, band {cfg.band_rect(w, h)}, "
              f"min_area {cfg.min_area(w)} -> saved probe.png")
        return 0

    if args.cmd == "solve":
        if args.dry_run:
            img = adb.screencap()
            x0, y0, x1, y1 = cfg.band_rect(img.shape[1], img.shape[0])
            band = img[y0:y1, x0:x1]
            _report_board(band, cfg, "solve_overlay.png", img.shape[1])
            arrows, labels = extract_arrows(band, cfg, ref_width=img.shape[1])
            return 0 if solve(arrows, labels, cfg) else 1
        return 0 if play_single(adb, cfg) else 1

    if args.cmd == "stitch":
        nav = Navigator(adb, cfg)
        res = capture_board(nav, cfg, cfg.debug_dir or None)
        cv2.imwrite(args.out, res.canvas)
        print(f"stitched {res.canvas.shape[1]}x{res.canvas.shape[0]} "
              f"(extent {res.extent[0]:.0f},{res.extent[1]:.0f}) -> {args.out}")
        order = _report_board(res.canvas, cfg, "board_overlay.png", nav.sw)
        return 0 if order else 1

    if args.cmd == "superhard":
        return 0 if play_superhard(adb, cfg) else 1

    if args.cmd == "afk":
        if args.skip:
            cfg.skip_levels = tuple(int(x) for x in args.skip.split(","))
        afk_loop(adb, cfg)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
