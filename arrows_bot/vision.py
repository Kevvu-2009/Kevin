"""Arrow segmentation and per-arrow geometry.

The board is dark-navy ink on white.  Arrows never touch, so connected
components on the ink mask are exactly the individual arrows.

Per arrow we find:
  * head       - argmax of the distance transform (the arrowhead triangle
                 is the fattest part of the shape)
  * direction  - OPPOSITE of the longest straight ink run leaving the head
                 (the shaft behind the head is longer than the tip in front)
  * half_width - distance-transform value at the head = half the head width,
                 used as the corridor half-width by the solver
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import BotConfig

# direction -> (dx, dy)
DIRS: dict[str, tuple[int, int]] = {
    "U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0),
}
OPPOSITE = {"U": "D", "D": "U", "L": "R", "R": "L"}


def ink_mask(img_bgr: np.ndarray, cfg: BotConfig) -> np.ndarray:
    """uint8 {0,255} mask of arrow ink (dark pixels on white)."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    return ((gray < cfg.ink_gray_thresh) * 255).astype(np.uint8)


@dataclass
class Arrow:
    id: int                      # label in the labels image
    bbox: tuple[int, int, int, int]   # x, y, w, h
    area: int
    head: tuple[int, int]        # (x, y) in image coords
    direction: str               # U / D / L / R
    half_width: float            # corridor half-width in px

    @property
    def tap_point(self) -> tuple[int, int]:
        return self.head


def _run_length(mask: np.ndarray, x: int, y: int, dx: int, dy: int) -> int:
    """Consecutive ink pixels from (x, y) walking (dx, dy), inclusive."""
    h, w = mask.shape
    n = 0
    while 0 <= x < w and 0 <= y < h and mask[y, x]:
        n += 1
        x += dx
        y += dy
    return n


def _head_and_direction(comp_mask: np.ndarray) -> tuple[tuple[int, int], str, float]:
    """comp_mask: uint8 {0,255} of one component (full-image size or bbox crop)."""
    dist = cv2.distanceTransform(comp_mask, cv2.DIST_L2, 5)
    _, half_width, _, head = cv2.minMaxLoc(dist)  # head = (x, y)
    hx, hy = int(head[0]), int(head[1])

    runs = {d: _run_length(comp_mask, hx, hy, dx, dy)
            for d, (dx, dy) in DIRS.items()}
    shaft_dir = max(runs, key=runs.get)           # longest run = backwards
    return (hx, hy), OPPOSITE[shaft_dir], float(half_width)


def extract_arrows(img_bgr: np.ndarray, cfg: BotConfig,
                   ref_width: int | None = None
                   ) -> tuple[list[Arrow], np.ndarray]:
    """Segment a board image into arrows.

    ref_width: width used to scale min/max area (defaults to image width;
    pass the SCREEN width when segmenting a stitched canvas so the
    thresholds match what a single screen would use).

    Returns (arrows, labels) where labels is the int32 component-label image
    (0 = background); arrow.id indexes into it.
    """
    mask = ink_mask(img_bgr, cfg)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)

    rw = ref_width if ref_width is not None else img_bgr.shape[1]
    lo, hi = cfg.min_area(rw), cfg.max_area(rw)

    arrows: list[Arrow] = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (lo <= area <= hi):
            sub = labels[y:y + h, x:x + w]     # drop noise from labels too
            sub[sub == i] = 0
            continue
        crop = (labels[y:y + h, x:x + w] == i).astype(np.uint8) * 255
        # pad so the distance transform isn't clipped at the bbox border
        crop = cv2.copyMakeBorder(crop, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=0)
        (hx, hy), direction, half_w = _head_and_direction(crop)
        arrows.append(Arrow(
            id=i, bbox=(int(x), int(y), int(w), int(h)), area=int(area),
            head=(int(x + hx - 2), int(y + hy - 2)),
            direction=direction, half_width=half_w,
        ))
    return arrows, labels


def draw_overlay(img_bgr: np.ndarray, arrows: list[Arrow],
                 order: list[Arrow] | None = None) -> np.ndarray:
    """Debug overlay: heads, directions, and (optionally) the tap order."""
    out = img_bgr.copy()
    rank = {a.id: k for k, a in enumerate(order)} if order else {}
    for a in arrows:
        x, y, w, h = a.bbox
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 200, 0), 2)
        hx, hy = a.head
        dx, dy = DIRS[a.direction]
        cv2.arrowedLine(out, (hx, hy), (hx + dx * 60, hy + dy * 60),
                        (0, 0, 255), 4, tipLength=0.4)
        label = str(rank.get(a.id, a.id) + 1) if order else a.direction
        cv2.putText(out, label, (x + 4, y + 26), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (255, 0, 0), 2)
    return out
