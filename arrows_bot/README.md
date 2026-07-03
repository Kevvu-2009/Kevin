# arrows_bot

Auto-player for **"Arrows – Puzzle Escape"** running in BlueStacks on Windows,
controlled over ADB.  Handles normal/Hard single-screen levels and
**Super Hard levels that scroll in both directions** (scroll-capture →
stitch → solve → scroll-to-tap), inside an AFK loop.

## Install / run (Windows)

```bat
pip install opencv-python numpy
:: optional, only for the skip-list "Level N" reading:
pip install pytesseract   & rem + install the Tesseract binary

python -m arrows_bot probe                 :: ADB sanity: saves probe.png
python -m arrows_bot solve --dry-run       :: detect+solve, saves overlay, no taps
python -m arrows_bot solve                 :: play the on-screen board
python -m arrows_bot stitch -o board.png   :: Super Hard capture only + overlay
python -m arrows_bot superhard             :: stitch + solve + scroll-to-tap
python -m arrows_bot afk --skip 12,34      :: the full loop; skip-list levels are
                                           ::   left for you to play yourself
```

Common flags: `--adb C:\platform-tools\adb.exe`, `--serial <device>`,
`--debug debug_out\` (saves stitched board, numbered overlay, tiles,
failure snapshots), `--config bot.json`.

Generate a config file to tweak: `python -c "from arrows_bot.config import
BotConfig; BotConfig().save('bot.json')"` — every knob is documented in
`config.py`, and **all pixel values are fractions of the live screen
resolution**.

## First run on your device — what to check

1. `probe`: confirm the printed band rectangle sits **below the hearts
   header and above the floating “#” button** on probe.png.  Adjust
   `band_top_frac` / `band_bottom_frac` if not.
2. `solve --dry-run` on a normal level: check solve_overlay.png — every
   arrow boxed, red arrows pointing the right way, numbers = tap order.
   If small arrows are missed, lower `min_area_frac`; if noise is picked
   up, raise it.  If ink isn't detected at all, raise `ink_gray_thresh`.
3. `stitch --debug dbg\` on a Super Hard level: inspect `stitched.png` +
   `board_overlay.png` for duplicated / cut-off arrows.
4. `superhard`, then `afk`.

## How the Super Hard capture works (design notes)

The two failure modes of naive stitching are **repetitive boards** (template
matching jumps to the wrong copy) and **sparse/blank patches** (nothing to
match, and "did the screen change" thinks a blank patch is the board edge).
Every mechanism below exists to kill one of those:

* **Dead-reckoning prior + constrained registration.**  BlueStacks scrolls
  ~1:1 with swipe distance (auto-calibrated), so every tile has a predicted
  position; template matching only *refines* it inside a window far smaller
  than the board's repeat period, so it can never lock onto the wrong copy.
  Patches are **aimed at ink** (per-cell centroids), so even a view with a
  single arrow in it is measurable.
* **Static means proven static.**  A screen is only treated as "didn't
  move" if registration at offset 0 is confirmed by a **supermajority** of
  visible regions — on a repetitive board a real move of ~1 cell period
  happily matches a few twin patches at offset 0, and a naive pixel-count
  check is fooled by 1-3px jitter (handled by eroding the diff mask).
* **Edges**: coarse seek = counting changed pixels with `edge_confirm`
  consecutive no-move swipes (robust to narrow blank patches).  The swipe
  that saturates against an edge mid-swipe is unmeasurable on a repetitive
  board, so extents are measured in **two passes**: coarse seek for an
  upper bound, then return to the anchored origin edge and re-approach,
  stopping 2 steps short and **creeping** the rest in small alias-safe
  steps that are always measurable.
* **Measure-then-raster**: height measured at x=0, width at mid-height
  (board is widest there), then a blind row-by-row sweep of the whole
  rectangle.  Every row restarts from the left edge (an absolute anchor,
  so drift cannot accumulate), and each tile is registered against the
  already-painted canvas overlap before pasting.
* Only the middle **band** of each screenshot is used, so the hearts
  header and the floating "#" button never enter the stitch.

## Scroll-to-tap (Super Hard play)

For each arrow in solve order: scroll it to band center, **confirm the
viewport position** against the stitched board (supermajority again — a
view off by exactly one period matches the target's identical twin but not
the twin's differing neighbours), then find the arrow by template-matching
it *with context* across the whole band and taking the strong peak nearest
the expected position.  A head-centred sub-template is verified separately
(a match that slid along a self-similar shaft scores well overall but puts
shaft where the head belongs).  If anything cannot be vouched for, a
**blind corner reset** (a fixed number of unmeasured full swipes — the
scroll clamps at the true corner no matter how blank the board is)
re-anchors position exactly, which also disambiguates identical twins.

Safety invariants:

* If the solver can't clear the whole board model, **nothing is tapped**.
* Every tap point is template-verified before tapping; unverifiable
  arrows are *skipped* (a phantom costs nothing), never guessed at.
* After each tap the arrow must actually be gone, else the bot stops
  rather than risk hearts on a wrong board model.
* The solver's corridor is deliberately **wider** than the game's rule
  (`corridor_width_factor`): a false BLOCK is safe, a false FREE costs a
  heart.
* Tapped arrows are erased from the reference canvas, so localization
  stays in sync with the live board all the way to an empty screen.

## Offline test-suite

`arrows_bot/tests/test_bot.py` runs the whole pipeline against a **fake
emulator** (`fakegame.py`): synthetic solvable boards, imperfect swipe
ratio, per-swipe jitter, UI chrome drawn on top, and the real tap rule
(blocked tap costs a heart, with the game's corridor width fixed
independently of the solver's).  `pytest arrows_bot/tests -q` — plus the
same harness has been soak-tested over 50+ random boards, screen sizes up
to 1900x3840 and swipe ratios 0.95–0.98 with zero heart losses.

## Known caveats

* If the real game lets board content hide *under* the header / "#"
  button at extreme scroll positions (i.e. scroll bounds without padding),
  the outermost strip of the board would be invisible to the band.  If a
  Super Hard stitch is missing its outer rim, shrink the band margins.
* `read_level` needs pytesseract; without it the skip-list is inactive
  (everything else works).
* An interstitial ad that covers the screen mid-level will stall the
  AFK loop until dismissed (the loop just polls; it never taps blindly).
