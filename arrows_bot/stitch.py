"""Super Hard scroll-capture: build ONE clean image of a board that is
bigger than the screen in both directions.

Why the obvious approaches fail:
  * global template matching     -> boards are repetitive, the overlap
                                    match jumps to the wrong copy
  * "did the screen change" edge -> sparse/blank patches look like the end

What this module does instead:
  1. DEAD-RECKONING PRIOR: BlueStacks scrolls ~1:1 with swipe distance
     (auto-calibrated), so every tile has a predicted position.
  2. CONSTRAINED REGISTRATION: each prediction is refined by template
     matching restricted to a tiny window (± reg_tol) around it - far
     smaller than the board's repeat period, so it cannot jump to the
     wrong copy.  Patches without ink are skipped; when nothing is
     measurable the dead-reckoned value is kept.
  3. STATIC/SATURATION HANDLING: a screen that didn't change at all is a
     zero shift (checked BEFORE registration, so an edge can never
     false-match a periodic copy at the expected offset), and a swipe
     that only partially moved (hit the edge mid-swipe) falls back to a
     wide 0..expected search that must be confirmed by >= 3 agreeing
     patches.
  4. EDGES BY COUNTING changed pixels, needing `edge_confirm`
     consecutive no-move swipes - robust to narrow blank patches.
  5. MEASURE-then-RASTER: measure the scroll extents (height at x=0,
     width at mid-height where the board is widest), then blindly sweep
     the whole rectangle row by row, restarting every row from the left
     edge (an absolute anchor, so horizontal drift cannot accumulate).
  6. PASTE-TIME REFINEMENT: before pasting, each tile is registered
     against the already-painted canvas (the ~40% overlap with the left
     neighbour / the row above), correcting any residual drift.

Only the middle band of each screenshot is used (below the hearts header,
above the floating "#" button) so UI never gets baked into the stitch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .adb import Adb
from .config import BotConfig

AXIS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


# ---------------------------------------------------------------------------
# low-level image measurements
# ---------------------------------------------------------------------------
def _gray(img: np.ndarray) -> np.ndarray:
    return img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def ink_frac(img: np.ndarray, cfg: BotConfig) -> float:
    return float((_gray(img) < cfg.ink_gray_thresh).mean())


def changed_fraction(a: np.ndarray, b: np.ndarray, cfg: BotConfig) -> float:
    """Fraction of genuinely changed pixels.  The eroded mask discards the
    1-2px-wide difference lines that sub-stroke jitter produces, so a
    static screen at an edge never looks like it is still moving."""
    diff = (cv2.absdiff(_gray(a), _gray(b)) > cfg.changed_pixel_diff)
    diff = cv2.erode(diff.astype(np.uint8), np.ones((3, 3), np.uint8))
    return float(np.count_nonzero(diff)) / diff.size


def _patch_centers(sg: np.ndarray, cfg: BotConfig, patch: int,
                   grid: int) -> list[tuple[int, int]]:
    """Patch centers AIMED AT INK: split the image into a grid and use the
    ink centroid of every cell that has ink.  A blind grid goes hungry on
    sparse (late-game / blank-patch) views; this finds a usable patch
    whenever any arrow is visible at all."""
    h, w = sg.shape
    half = patch // 2
    margin = half + 2
    ink = (sg < cfg.ink_gray_thresh).astype(np.uint8)
    centers: list[tuple[int, int]] = []
    for gy in range(grid):
        y0, y1 = h * gy // grid, h * (gy + 1) // grid
        for gx in range(grid):
            x0, x1 = w * gx // grid, w * (gx + 1) // grid
            cell = ink[y0:y1, x0:x1]
            cnt = int(cell.sum())
            if cnt < cfg.reg_min_ink_frac * patch * patch:
                continue
            ys_, xs_ = np.nonzero(cell)
            cx = int(np.clip(x0 + xs_.mean(), margin, w - margin - 1))
            cy = int(np.clip(y0 + ys_.mean(), margin, h - margin - 1))
            centers.append((cx, cy))
    return centers


def register(src: np.ndarray, dst: np.ndarray, expected: np.ndarray,
             tol: tuple[int, int] | int, cfg: BotConfig, patch: int,
             grid: int = 6, min_valid: int = 1,
             min_frac_valid: float = 0.0,
             ) -> tuple[np.ndarray | None, int]:
    """Find offset o (float [ox, oy]) such that content at p in `src`
    appears at p + o in `dst`, searching only within `expected` ± `tol`
    (tol may differ per axis).

    Uses up to grid*grid ink-targeted patches; the median of the agreeing
    patches wins.  Returns (offset, n_valid) or (None, 0) when fewer than
    min_valid patches agree (caller keeps its dead-reckoned estimate).

    min_frac_valid additionally requires that fraction of ALL candidate
    patches to agree - use it for hypotheses that must hold everywhere
    (e.g. "the screen did not move"), where a repetitive board could
    otherwise satisfy a few patches with periodic copies.
    """
    sg, dg = _gray(src), _gray(dst)
    dh, dw = dg.shape
    half = patch // 2
    ex, ey = float(expected[0]), float(expected[1])
    tx, ty = (tol, tol) if isinstance(tol, int) else (int(tol[0]), int(tol[1]))

    offsets = []
    candidates = 0
    for cx, cy in _patch_centers(sg, cfg, patch, grid):
        tpl = sg[cy - half:cy + half, cx - half:cx + half]
        if (tpl < cfg.ink_gray_thresh).mean() < cfg.reg_min_ink_frac:
            continue
        wx0 = int(round(cx + ex)) - half - tx
        wy0 = int(round(cy + ey)) - half - ty
        wx1 = wx0 + patch + 2 * tx
        wy1 = wy0 + patch + 2 * ty
        wx0c, wy0c = max(0, wx0), max(0, wy0)
        wx1c, wy1c = min(dw, wx1), min(dh, wy1)
        if wx1c - wx0c < patch + 4 or wy1c - wy0c < patch + 4:
            continue
        candidates += 1
        win = dg[wy0c:wy1c, wx0c:wx1c]
        res = cv2.matchTemplate(win, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        if score < cfg.reg_min_score:
            continue
        fx = wx0c + loc[0] + half                # found center in dst
        fy = wy0c + loc[1] + half
        offsets.append((fx - cx, fy - cy, score))

    if len(offsets) < min_valid:
        return None, 0
    arr = np.asarray(offsets, dtype=np.float64)
    med = np.median(arr[:, :2], axis=0)
    keep = np.all(np.abs(arr[:, :2] - med) <= 3, axis=1)
    good, scores = arr[keep, :2], arr[keep, 2]
    if len(good) < min_valid:
        return None, 0
    if len(good) == 1 and scores[0] < cfg.reg_single_min_score:
        return None, 0        # one mediocre patch is not evidence enough
    if len(good) < min_frac_valid * candidates:
        return None, 0        # too many visible regions disagree
    return good.mean(axis=0), len(good)


# ---------------------------------------------------------------------------
# navigator: swipes + position tracking
# ---------------------------------------------------------------------------
@dataclass
class ScrollInfo:
    intended: tuple[float, float]
    measured: tuple[float, float] | None    # None = dead-reckoned
    changed: float
    moving: bool


class Navigator:
    """Tracks pos = board coordinates of the capture band's top-left corner.

    Every scroll updates pos by the MEASURED content shift; dead-reckoning
    fills in when a shift isn't measurable (blank patch).  Edges snap pos
    to absolute values, so drift cannot accumulate.
    """

    def __init__(self, adb: Adb, cfg: BotConfig):
        self.adb = adb
        self.cfg = cfg
        img = adb.screencap()
        self.sh, self.sw = img.shape[:2]
        self.band = cfg.band_rect(self.sw, self.sh)     # x0, y0, x1, y1
        x0, y0, x1, y1 = self.band
        self.bw, self.bh = x1 - x0, y1 - y0
        self.ratio = cfg.swipe_ratio
        self.pos = np.zeros(2, dtype=np.float64)
        self.last = img[y0:y1, x0:x1].copy()

    # -- capture ----------------------------------------------------------
    def capture(self) -> np.ndarray:
        x0, y0, x1, y1 = self.band
        self.last = self.adb.screencap()[y0:y1, x0:x1].copy()
        return self.last

    # -- geometry helpers ---------------------------------------------------
    @property
    def _patch(self) -> int:
        return max(24, int(self.cfg.reg_patch_frac * self.bw))

    @property
    def _tol(self) -> int:
        return max(8, int(self.cfg.reg_tol_frac * self.bw))

    @property
    def alias_safe(self) -> float:
        return self.cfg.alias_safe_frac * self.bw

    def max_step(self, axis: int) -> float:
        dim = self.bw if axis == 0 else self.bh
        return dim * (1 - 2 * self.cfg.swipe_margin_frac) * self.ratio * 0.95

    def step(self, axis: int) -> float:
        dim = self.bw if axis == 0 else self.bh
        return min(dim * self.cfg.scroll_step_frac, self.max_step(axis))

    @property
    def min_swipe(self) -> float:
        """Shortest finger travel we will ever send.  A gesture shorter
        than the OS touch-slop is read as a TAP, not a scroll - which on
        this game flies an arrow off and costs a heart.  Kept well above
        slop so every scroll is unambiguously a drag."""
        return max(40.0, self.cfg.min_swipe_frac * self.bw)

    # -- swipes --------------------------------------------------------------
    def _swipe(self, dx: float, dy: float) -> None:
        """One physical swipe intending viewport += (dx, dy).  The finger
        moves opposite to the viewport: content follows the finger.

        A too-short drag would register as a tap, so the finger travel is
        floored at min_swipe (the extra travel is harmless: scroll()
        MEASURES the real shift afterwards, so over-travel self-corrects)."""
        x0, y0, x1, y1 = self.band
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        fx, fy = dx / self.ratio, dy / self.ratio
        length = float(np.hypot(fx, fy))
        if length == 0.0:
            return                               # nothing to do - never tap
        if length < self.min_swipe:
            scale = self.min_swipe / length
            fx, fy = fx * scale, fy * scale
        self.adb.swipe(cx + fx / 2, cy + fy / 2, cx - fx / 2, cy - fy / 2)
        self.adb.sleep(self.cfg.swipe_settle_s)

    def scroll(self, dx: float, dy: float) -> ScrollInfo:
        """Swipe once and update pos from the measured content shift."""
        prev = self.last
        self._swipe(dx, dy)
        new = self.capture()
        changed = changed_fraction(prev, new, self.cfg)
        moving = changed > self.cfg.moving_frac
        measured: tuple[float, float] | None = None

        # content at p in prev shows up at p - actual in new
        exp = np.array([-dx, -dy])
        if not moving:
            # nothing (visibly) changed: confirm the static hypothesis by
            # matching at offset 0.  Never search around the expected
            # offset here - on a repetitive board a static edge would
            # false-match a periodic copy and the seek would never end.
            off, n = register(prev, new, np.zeros(2), self._tol, self.cfg,
                              self._patch)
            if off is not None:
                measured = (-float(off[0]), -float(off[1]))
                self.pos += measured
            elif ink_frac(new, self.cfg) > 0.0015:
                measured = (0.0, 0.0)     # ink visible, nothing changed
            else:
                self.pos += (dx, dy)      # blank band: dead-reckon
        else:
            off = None
            if changed < self.cfg.near_static_frac:
                # so few pixels changed that this can only be a small
                # jitter shift (or a sparse view): check offset ~0 first,
                # otherwise a jitter-static swipe at an edge dead-reckons
                # a whole step and inflates the measured extent.  "Did not
                # move" must hold EVERYWHERE (min_frac_valid) - on a
                # repetitive board a real move of ~k*period would happily
                # match a few twin patches at offset 0
                off, n = register(prev, new, np.zeros(2), self._tol,
                                  self.cfg, self._patch,
                                  min_frac_valid=0.6)
            if off is None:
                off, n = register(prev, new, exp, self._tol, self.cfg,
                                  self._patch)
            if off is None and max(abs(dx), abs(dy)) <= self.alias_safe:
                # a small step that may have saturated (edge hit):
                # searching the whole 0..expected range is safe here, the
                # window being smaller than any board repeat period
                tol2 = (int(abs(dx) / 2) + self._tol,
                        int(abs(dy) / 2) + self._tol)
                off, n = register(prev, new, exp / 2, tol2, self.cfg,
                                  self._patch, min_valid=3)
            if off is not None:
                measured = (-float(off[0]), -float(off[1]))
                self.pos += measured
            else:
                self.pos += (dx, dy)      # moved, unmeasurable: reckon
        return ScrollInfo((dx, dy), measured, changed, moving)

    # -- higher level ----------------------------------------------------------
    def _edge_loop(self, direction: str, step: float) -> float:
        """Scroll toward `direction` in `step`-sized swipes until
        edge_confirm consecutive swipes move nothing.  Returns total
        position change along that axis."""
        ax_dx, ax_dy = AXIS[direction]
        axis = 0 if ax_dx else 1
        start = self.pos[axis]
        no_move = 0
        for _ in range(self.cfg.max_scroll_steps):
            info = self.scroll(ax_dx * step, ax_dy * step)
            if info.measured is not None:
                still = abs(info.measured[axis]) < 3
            else:
                still = not info.moving      # blank band: trust pixel count
            no_move = no_move + 1 if still else 0
            if no_move >= self.cfg.edge_confirm:
                return float(self.pos[axis] - start)
        raise RuntimeError(f"edge seek ({direction}): no edge after "
                           f"{self.cfg.max_scroll_steps} swipes")

    def seek_edge(self, direction: str) -> float:
        """COARSE edge seek with full steps.  The swipe that saturates
        against the edge mid-swipe usually can't be measured (its true
        travel would need an alias-unsafe wide search), so pos may end up
        overshot by up to one step: callers must snap() to an absolute
        value, or use measure_extent() when the edge coordinate itself is
        the quantity of interest."""
        return self._edge_loop(direction, self.step(0 if direction in "LR"
                                                    else 1))

    def creep_to_edge(self, direction: str) -> float:
        """ACCURATE edge approach in small alias-safe steps: every step -
        including the final partial one - is measurable, so pos stays
        exact all the way to the edge."""
        return self._edge_loop(direction,
                               max(24.0, self.cfg.edge_creep_frac * self.bw))

    def measure_extent(self, axis: int) -> float:
        """Distance from the current origin edge (pos[axis] must be 0 and
        the viewport at that edge) to the opposite edge, measured so that
        no swipe can saturate unmeasurably:

          1. coarse seek to the far edge (pos gets contaminated by the
             saturating swipe - only used as an upper bound),
          2. coarse seek back to the origin edge and snap to 0,
          3. free scroll to ~2 steps short of the far edge (never
             saturates, every swipe measured in the tight window),
          4. creep the final stretch.
        """
        fwd, back = ("R", "L") if axis == 0 else ("D", "U")
        self.seek_edge(fwd)
        coarse = float(self.pos[axis])           # >= true extent
        self.seek_edge(back)
        self.snap(axis, 0.0)
        target = max(0.0, coarse - 2 * self.step(axis))
        self.scroll_to(axis, target)
        self.creep_to_edge(fwd)
        return float(self.pos[axis])

    def snap(self, axis: int, value: float) -> None:
        """Anchor pos to an absolute edge coordinate."""
        self.pos[axis] = value

    def scroll_to(self, axis: int, target: float, tol: float = 3.0) -> None:
        """Multi-swipe scroll along one axis until pos[axis] ~= target.
        Stops gracefully if a physical edge is hit first.

        The tolerance is floored at one min_swipe: a residual smaller than
        the shortest safe drag can't be closed without sending a tap-like
        micro-swipe, and it doesn't need to be - localization (tapping) and
        paste-time registration (stitching) both absorb that little slack."""
        tol = max(tol, self.min_swipe)
        stalls = 0
        for _ in range(self.cfg.max_scroll_steps):
            delta = target - self.pos[axis]
            if abs(delta) <= tol:
                return
            step = float(np.clip(delta, -self.max_step(axis),
                                  self.max_step(axis)))
            d = (step, 0.0) if axis == 0 else (0.0, step)
            info = self.scroll(*d)
            got = info.measured[axis] if info.measured is not None else step
            if abs(got) < max(3.0, 0.1 * abs(step)):
                stalls += 1
                if stalls >= self.cfg.edge_confirm:
                    return                    # physical edge: accept
            else:
                stalls = 0
        raise RuntimeError(f"scroll_to(axis={axis}, target={target:.0f}) "
                           f"did not converge (pos={self.pos})")

    def blind_reset(self, w_max: float, h_max: float) -> None:
        """Guaranteed return to the top-left corner: swipe left then up a
        fixed number of full steps with NO measurement - the scroll clamps
        at the true corner no matter how blank the board is, so afterwards
        pos = (0, 0) is exact.  The recovery of last resort when position
        tracking has been starved of ink."""
        for _ in range(int(np.ceil(w_max / self.step(0))) + 2):
            self._swipe(-self.step(0), 0.0)
        for _ in range(int(np.ceil(h_max / self.step(1))) + 2):
            self._swipe(0.0, -self.step(1))
        self.capture()
        self.pos = np.zeros(2, dtype=np.float64)

    def calibrate_ratio(self) -> float:
        """Measure content-px per swipe-px with a down+up scroll pair."""
        step = self.step(1) * 0.8
        meas = []
        for sign in (+1, -1):
            info = self.scroll(0, sign * step)
            if info.measured is not None and abs(info.measured[1]) > 5:
                meas.append(abs(info.measured[1]) / step)
        if meas:
            r = float(np.mean(meas))
            if 0.5 < r < 1.5:                 # sanity: BlueStacks is ~1:1
                self.ratio *= r
        return self.ratio

    def probe_scrollable(self) -> bool:
        """Small down+up wiggle: does the board scroll at all?"""
        step = self.bh * 0.25
        info = self.scroll(0, step)
        scrolled = info.moving or (info.measured is not None
                                   and abs(info.measured[1]) > 5)
        self.scroll(0, -step)                 # scroll back
        return scrolled


# ---------------------------------------------------------------------------
# stitcher
# ---------------------------------------------------------------------------
@dataclass
class StitchResult:
    canvas: np.ndarray                  # BGR, white background
    extent: tuple[float, float]         # (W_max, H_max) max scroll offsets
    nav: Navigator                      # still tracking the live viewport
    tiles: list[tuple[int, int]] = field(default_factory=list)
    dropped_ink: int = 0                # board pixels that fell OFF the
                                        # canvas: >0 means the stitch is
                                        # incomplete (clipped arrows)


def _paste(canvas: np.ndarray, tile: np.ndarray, x: int, y: int,
           cfg: BotConfig | None = None) -> int:
    """Paste a tile at (x, y).  Returns how many INK pixels of the tile
    landed outside the canvas - non-zero means real board content was lost
    (the extent was under-measured), which shows up as arrows clipped at
    the canvas border and a solver that then can't solve."""
    ch, cw = canvas.shape[:2]
    th, tw = tile.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(cw, x + tw), min(ch, y + th)

    dropped = 0
    if cfg is not None and (x0 > x or y0 > y or x1 < x + tw or y1 < y + th):
        ink = _gray(tile) < cfg.ink_gray_thresh
        total = int(ink.sum())
        kept = int(ink[y0 - y:y1 - y, x0 - x:x1 - x].sum()) \
            if (x1 > x0 and y1 > y0) else 0
        dropped = total - kept

    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = tile[y0 - y:y1 - y, x0 - x:x1 - x]
    return dropped


def refine_on_canvas(nav: Navigator, canvas: np.ndarray,
                     cfg: BotConfig) -> bool:
    """Correct nav.pos by registering the current band against the (partly
    painted) canvas, widening the search if needed.  Wider windows demand
    more agreeing patches so a repetitive board can't fool them."""
    for mult, min_n in ((1, 2), (3, 3), (8, 3)):
        off, n = register(nav.last, canvas, expected=nav.pos.copy(),
                          tol=nav._tol * mult, cfg=cfg, patch=nav._patch,
                          min_valid=min_n)
        if off is not None:
            nav.pos = np.array(off)
            return True
    return False


def capture_board(nav: Navigator, cfg: BotConfig,
                  debug_dir: str | Path | None = None) -> StitchResult:
    """Scroll over the whole Super Hard board and stitch one clean image."""
    dbg = Path(debug_dir) if debug_dir else None
    if dbg:
        dbg.mkdir(parents=True, exist_ok=True)

    nav.capture()
    nav.calibrate_ratio()

    # ---- find the top-left corner (absolute origin) ----------------------
    nav.seek_edge("U")
    nav.seek_edge("L")
    nav.seek_edge("U")                    # once more in case L moved us
    nav.snap(0, 0.0)
    nav.snap(1, 0.0)

    # ---- measure extents ----------------------------------------------------
    h_max = max(0.0, nav.measure_extent(1))   # height, measured along x = 0

    nav.scroll_to(1, h_max / 2)           # width is widest at mid-height
    nav.seek_edge("L")
    nav.snap(0, 0.0)
    w_max = max(0.0, nav.measure_extent(0))

    nav.seek_edge("L")
    nav.snap(0, 0.0)
    nav.seek_edge("U")
    nav.snap(1, 0.0)

    # ---- raster sweep ---------------------------------------------------------
    # Margin on the right/bottom: the sweep can overshoot the measured
    # extent slightly (scroll_to residue, paste-time refinement), and
    # without slack that content is clipped off - which shows up as arrows
    # cut at the canvas border and a board the solver then can't solve.
    # The origin stays (0, 0), so no coordinate mapping changes.
    margin = int(round(cfg.canvas_margin_frac * nav.bw))
    canvas = np.full((int(round(h_max)) + nav.bh + margin,
                      int(round(w_max)) + nav.bw + margin, 3), 255, np.uint8)
    sx, sy = nav.step(0), nav.step(1)
    ys = [float(v) for v in np.arange(0.0, h_max, sy)] + [h_max]
    xs = [float(v) for v in np.arange(0.0, w_max, sx)] + [w_max]
    tiles: list[tuple[int, int]] = []
    dropped = 0

    for ri, y in enumerate(ys):
        if ri > 0:
            nav.scroll_to(1, y)
        nav.seek_edge("L")                # absolute anchor every row -
        nav.snap(0, 0.0)                  # jitter drift can't accumulate
        for x in xs:
            nav.scroll_to(0, x)
            if tiles:                     # first tile: pos is exact (0,0)
                refine_on_canvas(nav, canvas, cfg)
            px, py = int(round(nav.pos[0])), int(round(nav.pos[1]))
            dropped += _paste(canvas, nav.last, px, py, cfg)
            tiles.append((px, py))
            if dbg:
                cv2.imwrite(str(dbg / f"tile_r{ri:02d}_x{px}_y{py}.png"),
                            nav.last)

    if dbg:
        cv2.imwrite(str(dbg / "stitched.png"), canvas)
    return StitchResult(canvas=canvas, extent=(w_max, h_max), nav=nav,
                        tiles=tiles, dropped_ink=dropped)


# ---------------------------------------------------------------------------
# live-view localization against the stitched board
# ---------------------------------------------------------------------------
def localize(nav: Navigator, ref_canvas: np.ndarray, cfg: BotConfig) -> bool:
    """Correct nav.pos by registering the live band against the stitched
    board around the dead-reckoned position.  Returns True on success
    (False = blank view, dead-reckoning kept)."""
    nav.capture()
    return refine_on_canvas(nav, ref_canvas, cfg)
