"""Thin ADB wrapper.  Everything the bot needs from the emulator:
screenshots, taps, swipes, and the screen size.

The same interface is implemented by fakegame.FakeAdb so the whole
pipeline can be tested offline.
"""

from __future__ import annotations

import os
import subprocess
import time

import cv2
import numpy as np

from .config import BotConfig


class AdbError(RuntimeError):
    pass


class Adb:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self._base = [cfg.adb_path]
        if cfg.adb_serial:
            self._base += ["-s", cfg.adb_serial]

    # -- raw helpers ----------------------------------------------------
    def _tcp_serial(self) -> str | None:
        """The device serial if it's a TCP endpoint (host:port) - the kind
        that can be re-established with `adb connect`.  Falls back to
        $ANDROID_SERIAL so the env-var workflow self-heals too."""
        serial = self.cfg.adb_serial or os.environ.get("ANDROID_SERIAL", "")
        return serial if ":" in serial else None

    def reconnect(self) -> bool:
        """Best-effort `adb connect <host:port>`.  Idempotent - a no-op if
        already connected.  Returns False for non-TCP serials (e.g.
        emulator-5554, which adb re-detects on its own)."""
        serial = self._tcp_serial()
        if not serial:
            return False
        try:
            subprocess.run([self.cfg.adb_path, "connect", serial],
                           capture_output=True, timeout=15)
            return True
        except Exception:                               # noqa: BLE001
            return False

    def _run(self, *args: str, binary: bool = False) -> bytes:
        proc = subprocess.run(self._base + list(args), capture_output=True,
                              timeout=30)
        if proc.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} failed: "
                           f"{proc.stderr.decode(errors='replace')[:400]}")
        return proc.stdout if binary else proc.stdout

    # -- public interface -------------------------------------------------
    def screencap(self) -> np.ndarray:
        """Full-screen BGR screenshot.  BlueStacks' TCP ADB link drops
        periodically, so a failed capture triggers one reconnect attempt
        before the next retry (harmless for emulator-* serials)."""
        last_err: Exception | None = None
        for _attempt in range(self.cfg.screencap_retries):
            try:
                raw = self._run("exec-out", "screencap", "-p", binary=True)
                img = cv2.imdecode(np.frombuffer(raw, np.uint8),
                                   cv2.IMREAD_COLOR)
                if img is None:
                    # old adb mangles \n -> \r\n on 'shell'; exec-out is
                    # normally binary-safe, but try the fix as a fallback
                    raw = raw.replace(b"\r\n", b"\n")
                    img = cv2.imdecode(np.frombuffer(raw, np.uint8),
                                       cv2.IMREAD_COLOR)
                if img is not None:
                    return img
                last_err = AdbError("screencap: could not decode PNG")
            except Exception as e:                      # noqa: BLE001
                last_err = e
                self.reconnect()                        # link may have dropped
            time.sleep(0.5)
        hint = ""
        if self._tcp_serial():
            hint = (f"  (tried reconnecting to {self._tcp_serial()}; is "
                    f"BlueStacks running with ADB enabled?)")
        raise AdbError(f"screencap failed: {last_err}{hint}")

    def screen_size(self) -> tuple[int, int]:
        """(width, height) of the screen."""
        img = self.screencap()
        return img.shape[1], img.shape[0]

    def tap(self, x: int, y: int) -> None:
        self._run("shell", "input", "tap", str(int(x)), str(int(y)))

    def swipe(self, x1: int, y1: int, x2: int, y2: int,
              duration_ms: int | None = None) -> None:
        d = duration_ms if duration_ms is not None else self.cfg.swipe_duration_ms
        self._run("shell", "input", "swipe",
                  str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)),
                  str(int(d)))

    def keyevent(self, code: int | str) -> None:
        """e.g. keyevent(4) = BACK - closes most interstitial ads safely."""
        self._run("shell", "input", "keyevent", str(code))

    def foreground_package(self) -> str | None:
        """Package name of the app in the foreground (None if unknown).
        Used to notice when an ad click-through kicked us into the Play
        Store or a browser."""
        try:
            out = self._run("shell", "dumpsys", "activity",
                            "activities").decode(errors="replace")
        except AdbError:
            return None
        for key in ("topResumedActivity", "mResumedActivity",
                    "mFocusedActivity"):
            for line in out.splitlines():
                if key in line and "/" in line:
                    frag = line.split("/")[0]
                    return frag.rsplit(" ", 1)[-1].strip("{ ")
        return None

    def launch_app(self, package: str) -> None:
        self._run("shell", "monkey", "-p", package,
                  "-c", "android.intent.category.LAUNCHER", "1")

    def sleep(self, seconds: float) -> None:
        """Overridable so the fake emulator can skip real waiting."""
        time.sleep(seconds)
