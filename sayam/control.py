"""RobotController — the demo's single owner of Reachy Mini movement + voice.

All movement goes through one non-blocking lock so actions never overlap:
  * recenter(u, v) — gentle face/neck recenter (only while `active`, rate-limited)
  * greet()        — greeting gesture + spoken hello
  * fake_stress()  — concerned lean-in + spoken break suggestion (demo cut)
  * toggle_active()/set_active() — start/stop the robot's autonomous movement

Voice plays out the robot's own speaker via mini.media.play_sound (ElevenLabs
MP3 -> WAV). If no Voice is supplied, lines are printed instead.
"""

from __future__ import annotations

import os
import threading
import time
import wave
from typing import Callable, Optional

from reachy_mini.utils import create_head_pose

MIN_MOVE_INTERVAL_S = 0.35   # how often we may issue a recenter (lower = snappier)
MOVE_DURATION_S = 0.28       # per-move smoothing time (lower = faster catch-up)
STRESS_DISPLAY_S = 8.0       # how long the "stressed" overlay stays lit after a trigger

GREET_LINE = "Hey, I'm Sayam, your study companion. Let's get to work!"
STRESS_LINE = ("Hey — your stress is climbing and you've been at it a while. "
               "Let's take a five minute break.")


class RobotController:
    def __init__(self, mini, voice=None):
        self.mini = mini
        self.voice = voice
        self.active = True                      # autonomous movement (face tracking)
        self.on_stress: Optional[Callable[[bool], None]] = None
        self._busy = threading.Lock()
        self._speech = threading.Lock()         # serialize spoken audio
        self._last_move = 0.0

    # -- helpers -------------------------------------------------------------
    def _async(self, fn: Callable[[], None]) -> None:
        threading.Thread(target=fn, daemon=True).start()

    def _exclusive(self, fn: Callable[[], None]) -> None:
        """Run fn only if no other movement action holds the lock."""
        def job():
            if not self._busy.acquire(blocking=False):
                return
            try:
                fn()
            finally:
                self._busy.release()
        self._async(job)

    def _speak(self, text: str) -> None:
        print(f"🗣️  SAYAM: {text}")
        if self.voice is None:
            return
        with self._speech:  # one utterance at a time
            try:
                wav = self.voice.synthesize_to_wav(text)
                self.mini.media.play_sound(wav)
                try:
                    with wave.open(wav, "rb") as wf:
                        dur = wf.getnframes() / float(wf.getframerate())
                except Exception:
                    dur = 4.0
                time.sleep(dur + 1.0)
                os.unlink(wav)
            except Exception as exc:
                print(f"[voice] {exc}")

    def say(self, text: str) -> None:
        """Speak a conversational reply (+ a subtle nod) — used by Q&A."""
        self._async(lambda: self._speak(text))

        def nod():
            self.mini.goto_target(head=create_head_pose(pitch=6), duration=0.4)
            time.sleep(0.2)
            self.mini.goto_target(create_head_pose(), duration=0.4)
        self._exclusive(nod)

    # -- start/stop ----------------------------------------------------------
    def is_speaking(self) -> bool:
        return self._speech.locked()

    def set_active(self, value: bool) -> None:
        self.active = value

    def toggle_active(self) -> bool:
        self.active = not self.active
        return self.active

    # -- movement actions ----------------------------------------------------
    def recenter(self, u: int, v: int) -> bool:
        if not self.active or self._busy.locked():
            return False
        if time.time() - self._last_move < MIN_MOVE_INTERVAL_S:
            return False

        def job():
            try:
                self.mini.look_at_image(u, v, duration=MOVE_DURATION_S, perform_movement=True)
            except Exception:
                pass
            self._last_move = time.time()
        self._exclusive(job)
        return True

    def greet(self) -> None:
        def job():
            self._async(lambda: self._speak(GREET_LINE))
            m = self.mini
            m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.4)
            m.goto_target(head=create_head_pose(pitch=10), antennas=[0.6, -0.6], duration=0.4)
            m.goto_target(head=create_head_pose(pitch=-6), antennas=[-0.6, 0.6], duration=0.4)
            m.goto_target(head=create_head_pose(pitch=8), antennas=[0.5, -0.5], duration=0.4)
            m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.4)
        self._exclusive(job)

    def nudge(self, text: str) -> None:
        """Tutor nudge: a small attention gesture + spoken correction."""
        def job():
            self._async(lambda: self._speak(text))
            m = self.mini
            m.goto_target(head=create_head_pose(pitch=8, yaw=6), antennas=[0.5, 0.5], duration=0.5)
            time.sleep(0.25)
            m.goto_target(head=create_head_pose(yaw=-6), duration=0.4)
            time.sleep(0.2)
            m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.5)
        self._exclusive(job)

    def fake_stress(self) -> None:
        if self.on_stress:
            self.on_stress(True)
            # auto-clear the overlay flag after a bit
            self._async(lambda: (time.sleep(STRESS_DISPLAY_S),
                                 self.on_stress and self.on_stress(False)))

        def job():
            self._async(lambda: self._speak(STRESS_LINE))
            m = self.mini
            m.goto_target(head=create_head_pose(roll=8, pitch=12), antennas=[-0.4, -0.4], duration=0.8)
            time.sleep(0.5)
            m.goto_target(head=create_head_pose(roll=-6, pitch=10), duration=0.7)
            time.sleep(0.3)
            m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.7)
        self._exclusive(job)
