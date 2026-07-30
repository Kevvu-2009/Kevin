# arrows_bot — project handoff

Everything a fresh session needs to continue. **All code is in this repo**
(branch `claude/arrows-puzzle-bot-yg7p6c`) — read the files, don't rewrite them.

## What this is

A Python bot that auto-plays the mobile puzzle game **"Arrows – Puzzle Escape"**
in **BlueStacks** on Windows, driven over **ADB**. It handles normal levels and
**"Super Hard" levels whose board is bigger than the screen in both directions**
(scroll → stitch → solve → scroll-to-tap), inside an AFK loop.

## The game

- A board of arrows: each is a bent/L-shaped/spiral line, dark navy on white,
  with ONE arrowhead pointing U/D/L/R. Some boards also have **red/orange
  arrows** (behaviour still unconfirmed — see Open questions).
- Arrows never touch (thin white gap), so connected components on a dark-pixel
  mask segment them cleanly.
- Tap an arrow → it flies off in its arrowhead's direction. Clear all to win.
- **3 hearts; a blocked tap costs a heart.** This drives every design decision.

## THE COLLISION RULE (critical — get this right)

An arrow escapes **iff the corridor directly in front of its ARROWHEAD is clear**
— a strip as wide as the arrow, shot straight out from the head to the board
edge. It is **not** the whole bent body sweeping sideways, and **not** the
leading edge of the whole shape. (A big frame-shaped arrow whose head points
down escapes straight down even though its body is up above.)

**Greedy peel is complete and optimal**: repeatedly tap any arrow that can
currently escape — removing one never blocks another. If greedy gets stuck, the
board *data* is wrong (bad direction/segmentation), not the strategy.

## Environment

- Windows + PowerShell, repo at `C:\Users\kevin\kevin`
- ADB at `C:\platform-tools\adb.exe`; BlueStacks on `127.0.0.1:5555`
- Set the device once per terminal: `$env:ANDROID_SERIAL="127.0.0.1:5555"`
- **Emulator resolution 1900x3840 works. 1080x1920 broke the solve** (see
  Open questions).
- Deps: `pip install opencv-python numpy` (`pytesseract` optional, skip-list only)

## Commands

```powershell
python -m arrows_bot probe                    # ADB sanity, saves probe.png
python -m arrows_bot solve --dry-run          # single screen, no taps
python -m arrows_bot solve                    # play a single-screen level
python -m arrows_bot stitch --debug dbg -o board.png   # Super Hard capture only
python -m arrows_bot superhard --debug dbg    # Super Hard: stitch+solve+tap
python -m arrows_bot afk --skip 12,34         # full loop
```
Global flags (`--serial --adb --config --debug`) work in any position.

## Files (all under `arrows_bot/`)

| File | Purpose |
|---|---|
| `config.py` | Every tunable, **all resolution-relative** (fractions of screen w/h) |
| `adb.py` | ADB wrapper: screencap/tap/swipe/keyevent + auto-reconnect on dropped TCP |
| `vision.py` | Ink mask (navy **and** colored arrows), segmentation, head + direction |
| `solver.py` | Corridor rule, greedy peel, `stuck_set()` diagnostic |
| `stitch.py` | Scroll-capture + stitching + `Navigator` (viewport tracking) |
| `play.py` | `play_single`, `play_superhard` (scroll-to-tap), all safety gates |
| `afk.py` | AFK loop, Continue-button detection, ad watchdog |
| `fakegame.py` | Offline emulator sim: synthetic boards, jitter, hearts, tap rule |
| `tests/test_bot.py` | 12 tests, full pipeline offline (`pytest arrows_bot/tests -q`) |
| `README.md` | Design notes + on-device tuning guide |

## How detection works

- **Head** = argmax of the distance transform (arrowhead is the fattest part).
- **Direction** = OPPOSITE of the longest straight ink run from the head (the
  shaft behind the head is longer than the tip in front).
- **Ink** = dark pixels **OR** high-saturation pixels (catches red/orange arrows;
  `ink_sat_thresh=255` reverts to navy-only).

## How Super Hard capture works

Two failure modes drove the design: boards are **very repetitive** (naive template
matching jumps to the wrong copy) and have **sparse/blank patches** (nothing to
match; naive "did the screen change" thinks a blank patch is the board edge).

- **Dead-reckoning prior + constrained registration**: BlueStacks scrolls ~1:1
  with swipe distance (auto-calibrated); matching only *refines* within a window
  far smaller than the board's repeat period, so it can't lock onto a wrong copy.
  Patches are **aimed at ink** so sparse views are still measurable.
- **"Static" must be proven** by a zero-offset match confirmed by a
  **supermajority** of regions — a real move of ~one cell period would satisfy a
  few twin patches at offset 0, and pixel-counting is fooled by jitter.
- **Extents measured in two passes**: coarse seek for an upper bound, then
  re-approach from the anchored origin and **creep** the last stretch in small
  always-measurable steps (the swipe that saturates against an edge is
  unmeasurable on a repetitive board).
- **Measure-then-raster**: height at x=0, width at mid-height; every row restarts
  from the left edge (absolute anchor, so drift can't accumulate); each tile is
  registered against the painted canvas before pasting.
- Only the **middle band** of each screenshot is used, so the hearts header and
  floating "#" button never enter the stitch.
- Canvas gets right/bottom **margin** so a slight overshoot can't clip content;
  `StitchResult.dropped_ink` reports any content lost.

## Scroll-to-tap and the safety model

`play_superhard` **re-decides every step from the true remaining board**. It only
taps an arrow that `can_escape()` says is free *right now*, and an arrow leaves
the model **only when confirmed gone**.

Safety invariants (all learned from real heart losses):
1. **Solver can't clear the model → tap nothing.**
2. **Swipes are floored at ~5% of band width** (`min_swipe_frac`). A shorter drag
   is read by Android as a **tap** and flies an arrow off. Tap-vs-scroll is
   decided by **distance, not duration**.
3. **A skip is never treated as cleared.** Pretending a skipped arrow was gone
   invalidated the rest of the plan and caused a delayed blocked tap (cost a
   heart several taps later). Skips are deferred and retried.
4. **Aim gate**: before tapping, re-segment the live view; the arrow under the
   finger must match the target's direction and (band-clamped) size.
5. **Miss vs block**: if an arrow is still there after a tap, re-localize — a
   moved head means the tap *missed* (empty space, no heart) → re-aim; an unmoved
   head means genuinely **blocked** → stop instead of tapping again.
6. **Corridor is deliberately wider than the game's rule**
   (`corridor_width_factor=1.2`): a false BLOCK is safe, a false FREE costs a heart.
7. **Never taps Hint** (that plays an ad).

## Status

**Working on the real device**: probe, single-screen solve, full Super Hard
stitch (clean, verified by eye), solve of the stitched board, and scroll-to-tap
clearing many arrows in a row with hearts intact.

**Fixed along the way** (each was a real, observed bug):
- scroll swipes registering as taps (heart loss)
- skipped arrows marked "cleared" → delayed blocked tap (heart loss)
- wrong-arrow taps → added the aim gate
- incomplete stitch clipping arrows → canvas margin + clip detection
- **arrows longer than the screen were permanently un-tappable** — the match
  template was built from the whole arrow and couldn't fit the band (measured:
  2399px arrow → 2501px template vs a 1037px band). Now the template is
  **head-centred and capped at 40% of the band**. This was the cause of the last
  failure ("couldn't localize any of N free arrows").

**Performance**: ~5s/arrow (was ~15s) after skipping needless scrolls/screenshots.
The stitch phase is ~3 min before tapping starts (inherent — the board must be
mapped).

**NOT yet verified on device**: the oversized-arrow fix (last change; user was
about to test it). Simulation: 20/20 boards clear with all 3 hearts.

## Open questions (need the user / a device run)

1. **What do the RED/orange arrows do?** Normal but colored, or special (locked,
   move twice, immovable)? This gates whether tapping them is ever safe. If the
   bot ever stops with *"free in the model but won't leave in-game"* and saves
   `dbg\blocked_NNN.png`, that's the confirmation they're special.
2. **Why did 1080x1920 break the solve** (49 of 71 arrows unsolvable, stitch was
   complete)? Hypothesis: thin white gaps blur at low res and arrows merge into
   one component — **not confirmed**; downscaling the synthetic test boards did
   *not* reproduce it. `dbg\ink_mask.png` from a 1080 run would settle it.
   Workaround: use 1900x3840.
3. **Ads**: watchdog exists (BACK → corner X taps → relaunch) but has never been
   exercised by a real ad. Best fix is prevention (offline/no-ads).

## How to debug (this workflow works — keep using it)

Run with `--debug dbg`, then read `dbg\`:
- `board.png` — the raw stitch (is it complete and correctly aligned?)
- `board_overlay.png` — green boxes, red direction arrows, tap order;
  **MAGENTA = the arrows jamming the solve**
- `ink_mask.png` — exactly what the detector sees (are red arrows white? are
  neighbours fused?)
- `tap_NNN.png` — red crosshair on the exact aim point of every tap
- `blocked_NNN.png`, `skip_NNN.png`, `fail_*.png` — failure snapshots

Every stop prints **why**, and the three messages mean different things:
*"couldn't localize any of N free arrows"* (localization gap, harmless) /
*"free in the model but won't leave in-game"* (a real game rule we don't model) /
*"N left but none can escape in the model"* (a misread direction).

## Working agreements

- Ask for the actual **image files** (not screenshots of the terminal) — they've
  diagnosed nearly every bug here.
- Prefer a **safe stop over a guess**: skipping costs nothing, a wrong tap costs
  a heart.
- Keep every pixel constant **resolution-relative**.
- Reproduce each bug in `fakegame.py` and add a regression test; several fixes
  were verified by confirming the test fails without them.
- Commit and push to `claude/arrows-puzzle-bot-yg7p6c`.
