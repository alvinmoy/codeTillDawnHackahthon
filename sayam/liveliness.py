"""Make Sayam feel alive — idle quirks + smooth face-gaze, one controller.

LivelyRobot owns the Reachy Mini head/antennas via a single ~30 Hz loop so
nothing fights over the motors:
  * No face → gentle "breathing" sway + random quirks (antenna perk, curious
    tilt, glance, nod). Commanding BOTH antennas every frame also overrides the
    daemon's stray single-antenna jitter.
  * Face present → the loop drives the head toward the gaze pose set by the
    face tracker (smoothly low-passed), while antennas keep their lively
    shimmer. Head-moving quirks are suppressed so it keeps eye contact.

Expressive gestures (greet, concerned) pause the loop, play a goto_target
sequence, then the loop resumes.
"""

from __future__ import annotations

import math
import queue
import random
import threading
import time
from typing import Optional

import numpy as np

from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

HEAD_QUIRKS = {"tilt_left", "tilt_right", "glance_left", "glance_right", "nod"}
ANTENNA_QUIRKS = {"perk", "flick"}
ALL_QUIRKS = list(HEAD_QUIRKS | ANTENNA_QUIRKS)

GAZE_TTL_S = 1.0       # face target is "fresh" for this long after an update
GAZE_SMOOTH = 0.25     # low-pass factor toward a new gaze pose (0..1, higher=snappier)


class LivelyRobot:
    def __init__(self, mini: ReachyMini, rate_hz: float = 30.0):
        self.mini = mini
        self._dt = 1.0 / rate_hz
        self._stop = threading.Event()
        self._idle_paused = threading.Event()

        self._quirk: Optional[str] = None
        self._quirk_t0 = 0.0
        self._quirk_dur = 0.0
        self._next_quirk = time.time() + random.uniform(8.0, 16.0)

        self._gaze_lock = threading.Lock()
        self._gaze_target: Optional[np.ndarray] = None  # desired head pose (4x4)
        self._gaze_current: Optional[np.ndarray] = None  # smoothed
        self._gaze_ts = 0.0

        self._gestures: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=1)
        self._idle_thread = threading.Thread(target=self._idle_loop, daemon=True)
        self._gesture_thread = threading.Thread(target=self._gesture_loop, daemon=True)

    # -- lifecycle -----------------------------------------------------------
    def start(self) -> None:
        self._idle_thread.start()
        self._gesture_thread.start()

    def stop(self) -> None:
        self._stop.set()
        try:
            self.mini.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.6)
        except Exception:
            pass

    def request(self, gesture: str) -> None:
        try:
            self._gestures.put_nowait(gesture)
        except queue.Full:
            pass

    # -- face gaze (called by the face tracker) ------------------------------
    def set_gaze(self, head_pose: np.ndarray) -> None:
        with self._gaze_lock:
            self._gaze_target = head_pose
            self._gaze_ts = time.time()

    def clear_gaze(self) -> None:
        with self._gaze_lock:
            self._gaze_target = None

    def _fresh_gaze(self) -> Optional[np.ndarray]:
        with self._gaze_lock:
            if self._gaze_target is None or (time.time() - self._gaze_ts) > GAZE_TTL_S:
                return None
            return self._gaze_target

    # -- idle loop -----------------------------------------------------------
    def _idle_loop(self) -> None:
        t0 = time.time()
        while not self._stop.is_set():
            if self._idle_paused.is_set():
                time.sleep(self._dt)
                continue
            t = time.time() - t0
            now = time.time()

            # Pick a quirk?
            if self._quirk is None and now >= self._next_quirk:
                self._quirk = random.choice(ALL_QUIRKS)
                self._quirk_t0 = now
                self._quirk_dur = 0.5 if self._quirk == "flick" else random.uniform(0.9, 1.5)

            # Antenna shimmer (always) + antenna quirk offset.
            ant = 0.04 * math.sin(2 * math.pi * 0.25 * t)
            ant_l = ant_r = ant
            head_roll = head_pitch = head_yaw = 0.0
            if self._quirk is not None:
                qt = now - self._quirk_t0
                env = math.sin(math.pi * min(qt / self._quirk_dur, 1.0))
                q = self._quirk
                # Subtle on purpose — alive, not distracting.
                if q in ANTENNA_QUIRKS:
                    ant_l += 0.30 * env
                    ant_r += 0.30 * env
                elif q == "tilt_left":
                    head_roll += 6.0 * env
                elif q == "tilt_right":
                    head_roll -= 6.0 * env
                elif q == "glance_left":
                    head_yaw += 9.0 * env
                elif q == "glance_right":
                    head_yaw -= 9.0 * env
                elif q == "nod":
                    head_pitch += 6.0 * env
                if qt >= self._quirk_dur:
                    self._quirk = None
                    self._next_quirk = now + random.uniform(9.0, 20.0)

            gaze = self._fresh_gaze()
            if gaze is not None:
                # Follow the face: low-pass toward the target pose, suppress
                # head quirks (keep eye contact), keep antenna shimmer/perk.
                if self._gaze_current is None:
                    self._gaze_current = gaze.copy()
                else:
                    self._gaze_current = (
                        (1 - GAZE_SMOOTH) * self._gaze_current + GAZE_SMOOTH * gaze
                    )
                head_pose = self._gaze_current
            else:
                self._gaze_current = None
                # Gentle breathing sway + head-quirk offsets.
                pitch = 1.5 * math.sin(2 * math.pi * 0.14 * t) + head_pitch
                roll = 1.2 * math.sin(2 * math.pi * 0.10 * t + 1.0) + head_roll
                yaw = 2.2 * math.sin(2 * math.pi * 0.06 * t + 2.0) + head_yaw
                head_pose = create_head_pose(roll=roll, pitch=pitch, yaw=yaw)

            try:
                self.mini.set_target(head=head_pose, antennas=[ant_l, ant_r])
            except Exception:
                pass
            time.sleep(self._dt)

    # -- gestures ------------------------------------------------------------
    def _gesture_loop(self) -> None:
        while not self._stop.is_set():
            try:
                gesture = self._gestures.get(timeout=0.2)
            except queue.Empty:
                continue
            if gesture is None:
                return
            self._idle_paused.set()
            try:
                getattr(self, f"_gesture_{gesture}", lambda: None)()
            except Exception as exc:
                print(f"[robot] gesture '{gesture}' failed: {exc}")
            finally:
                self._idle_paused.clear()

    def _gesture_greet(self) -> None:
        m = self.mini
        m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.4)
        m.goto_target(head=create_head_pose(pitch=10), antennas=[0.6, -0.6], duration=0.4)
        m.goto_target(head=create_head_pose(pitch=-6), antennas=[-0.6, 0.6], duration=0.4)
        m.goto_target(head=create_head_pose(pitch=8), antennas=[0.5, -0.5], duration=0.4)
        m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.4)

    def _gesture_concerned(self) -> None:
        m = self.mini
        m.goto_target(head=create_head_pose(roll=8, pitch=12), antennas=[-0.4, -0.4], duration=0.8)
        time.sleep(0.5)
        m.goto_target(head=create_head_pose(roll=-6, pitch=10), duration=0.7)
        time.sleep(0.3)
        m.goto_target(create_head_pose(), antennas=[0.0, 0.0], duration=0.7)
