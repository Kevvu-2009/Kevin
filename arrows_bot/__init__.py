"""Bot that auto-plays "Arrows - Puzzle Escape" in BlueStacks via ADB.

Modules:
    config   - all tunables, resolution-relative
    adb      - thin ADB wrapper (screencap / tap / swipe)
    vision   - ink mask, arrow segmentation, head + direction detection
    solver   - corridor collision rule + greedy peel
    stitch   - Super Hard scroll-capture: dead-reckoning + constrained
               registration, edge seeking, measure-then-raster stitching
    play     - single-screen play and Super Hard scroll-to-tap play
    afk      - AFK loop (Continue button, win detect, skip list)
    fakegame - offline emulator simulator used by the test-suite
"""

__version__ = "0.1.0"
