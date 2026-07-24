"""All tunables in one place.  Every pixel value is derived from the live
screen resolution so the bot works at 1080x1920, 1900x3840, 2160x3840, ...

Fractions are of screen WIDTH (sw) or HEIGHT (sh) as noted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class BotConfig:
    # ---- ADB ----------------------------------------------------------
    adb_path: str = r"C:\platform-tools\adb.exe"
    adb_serial: str = ""            # empty = default device
    screencap_retries: int = 3

    # ---- ink / segmentation ------------------------------------------
    ink_gray_thresh: int = 140      # gray < thresh  ->  dark (navy) ink
    ink_sat_thresh: int = 70        # max-min channel > this -> colored ink
                                    # (red/orange arrows); 255 = navy only
    min_area_frac: float = 2.0e-4   # min component area = frac * sw**2
    max_area_frac: float = 0.5      # reject blobs bigger than this * sw**2

    # ---- safe capture band (fraction of screen HEIGHT / WIDTH) --------
    # Only this horizontal band of each screenshot is used: below the
    # hearts header, above the floating "#" button.
    band_top_frac: float = 0.14
    band_bottom_frac: float = 0.84
    band_left_frac: float = 0.02
    band_right_frac: float = 0.98

    # ---- solver -------------------------------------------------------
    # Corridor width = head half-width (distance-transform max) * 2 * factor.
    # DELIBERATELY WIDER than the game's real rule: a false BLOCK is safe
    # (greedy taps that arrow later, or refuses the level), while a false
    # FREE is a blocked tap = a lost heart.  The margin also absorbs the
    # +-2-3px of stitching error on Super Hard boards.
    corridor_width_factor: float = 1.2

    # ---- swipes / scrolling -------------------------------------------
    swipe_duration_ms: int = 800    # deliberate drag: no fling, and (with
                                    # min_swipe_frac) never read as a tap.
                                    # Tap-vs-scroll is decided by DISTANCE,
                                    # so this can stay brisk; raise it if
                                    # BlueStacks ever flings/overshoots.
    min_swipe_frac: float = 0.05    # shortest finger travel = frac * band
                                    # width; below OS touch-slop a swipe is
                                    # read as a TAP (flies an arrow, -1 heart)
    swipe_margin_frac: float = 0.06 # keep swipe endpoints inside the band
    swipe_settle_s: float = 0.25    # wait after a swipe before screencap
    scroll_step_frac: float = 0.60  # scroll step = frac * band dimension
    swipe_ratio: float = 1.0        # measured content-px per swipe-px
                                    # (auto-calibrated at runtime)

    # ---- registration (constrained template matching) -----------------
    reg_patch_frac: float = 0.10    # patch size = frac * band width
    reg_tol_frac: float = 0.035     # search tolerance = frac * band width
                                    # (must stay < board cell period!)
    reg_min_score: float = 0.60     # TM_CCOEFF_NORMED acceptance
    reg_single_min_score: float = 0.85  # bar for a LONE agreeing patch
    reg_min_ink_frac: float = 0.015 # patch must contain this much ink
    loc_tol_frac: float = 0.10      # wider window used by localize()

    # ---- edge detection -----------------------------------------------
    changed_pixel_diff: int = 25    # |gray1-gray2| > this  ->  "changed"
    # the changed fraction of a truly static screen is ~0 (1px jitter is
    # eroded away), while a scroll on even a nearly-empty board moves a
    # visible arrow's worth of pixels - so this can be very sensitive:
    moving_frac: float = 0.0005
    # a real full-step scroll changes several % of the pixels; anything
    # under this is at most a few-px jitter shift, so a zero-offset match
    # is tried before the expected-offset one (a jitter-static swipe that
    # dead-reckons a full step is how extents get badly inflated)
    near_static_frac: float = 0.01
    edge_confirm: int = 2           # consecutive no-move swipes = real edge
    max_scroll_steps: int = 60      # sanity bound per axis
    # a wide (0..step) shift search is only alias-safe when the whole
    # window is smaller than the board's repeat period; bigger steps that
    # can't be measured are recovered by backing off one step and creeping
    # to the edge in steps of edge_creep_frac.
    alias_safe_frac: float = 0.12   # of band width
    edge_creep_frac: float = 0.08   # of band width
    canvas_margin_frac: float = 0.25  # slack added to the stitch canvas
                                    # (right/bottom) so a slight sweep
                                    # overshoot can't clip board content

    # ---- play ----------------------------------------------------------
    tap_settle_s: float = 0.45      # wait for the fly-off animation
    verify_taps: bool = True        # confirm ink at tap point before tapping
    verify_gone: bool = True        # confirm arrow left after tapping
    tap_retries: int = 1

    # ---- afk loop -------------------------------------------------------
    # Continue button = big blue blob in the lower part of the home screen.
    blue_hsv_lo: tuple = (95, 110, 110)
    blue_hsv_hi: tuple = (135, 255, 255)
    continue_min_w_frac: float = 0.22   # of screen width
    continue_region_top_frac: float = 0.45
    win_timeout_s: float = 30.0
    level_poll_s: float = 2.0
    skip_levels: tuple = ()

    # ---- ad handling -----------------------------------------------------
    # If the screen is neither the home screen nor a board for this long,
    # assume an interstitial ad and start the dismissal sequence: BACK
    # key presses first (never click into an ad), then taps on the usual
    # X positions in the top corners, and relaunch the game if an ad
    # click-through kicked us into the Play Store / a browser.
    game_package: str = ""          # auto-detected at afk start if empty
    ad_grace_s: float = 12.0        # unknown-screen time before dismissing
    ad_corner_taps: bool = True     # try corner X taps after BACK fails
    ad_max_dismiss_s: float = 90.0  # give up (and stop the loop) after this

    # ---- debug -----------------------------------------------------------
    debug_dir: str = ""             # save intermediate images here if set

    # ------------------------------------------------------------------
    # derived pixel helpers
    # ------------------------------------------------------------------
    def band_rect(self, sw: int, sh: int) -> tuple[int, int, int, int]:
        """(x0, y0, x1, y1) of the safe capture band in screen coords."""
        return (int(sw * self.band_left_frac), int(sh * self.band_top_frac),
                int(sw * self.band_right_frac), int(sh * self.band_bottom_frac))

    def min_area(self, sw: int) -> int:
        return max(20, int(self.min_area_frac * sw * sw))

    def max_area(self, sw: int) -> int:
        return int(self.max_area_frac * sw * sw)

    # ------------------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> BotConfig:
        data = json.loads(Path(path).read_text())
        cfg = cls()
        for k, v in data.items():
            if not hasattr(cfg, k):
                raise KeyError(f"unknown config key: {k}")
            setattr(cfg, k, tuple(v) if isinstance(getattr(cfg, k), tuple) else v)
        return cfg

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))
