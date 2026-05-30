"""Sayam demo app: live view + face tracking + on-screen control buttons.

A single window shows the robot camera with face box + live Presage vitals
(HR / breathing / stress), and clickable buttons:
    [ Greet ]  [ Fake Stress ]  [ Start/Stop ]  [ Quit ]

The robot stays calm (holds still, recenters on your neck only when you drift
out of frame), greets on startup, and speaks through its own speaker.

Daemon must be running (`reachy-mini-daemon`), venv active:
    python live_view.py                 # full demo (vitals + voice + buttons)
    python live_view.py --no-vitals      # skip Presage overlay
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path

from reachy_mini import ReachyMini

from control import RobotController
from vision import FaceTracker, VitalsState
from vitals_bridge import VitalsStream
from voice import Voice


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Sayam demo app.")
    parser.add_argument("--binary", default="../vitals/build/sayam_vitals")
    parser.add_argument("--camera-device-index", type=int, default=1)
    parser.add_argument("--no-vitals", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("SMARTSPECTRA_API_KEY", "")

    try:
        voice = Voice()
    except Exception as exc:
        print(f"[voice] ElevenLabs unavailable ({exc}); printing lines instead.")
        voice = None

    print("Connecting to Reachy Mini (media_backend='default')...")
    with ReachyMini(media_backend="default") as mini:
        vitals_state = VitalsState()
        controller = RobotController(mini, voice)
        controller.on_stress = vitals_state.set_stressed

        stream = None
        if not args.no_vitals and api_key:
            stream = VitalsStream(
                binary_path=args.binary, api_key=api_key,
                camera_device_index=args.camera_device_index,
            )
            stream.on_sample = lambda s: vitals_state.update_sample(
                s.pulse_rate, s.breathing_rate, s.stress_index)
            stream.on_status = lambda code, hint: vitals_state.update_status(hint)
            stream.on_error = lambda msg: print(f"[vitals error] {msg}")
            stream.start()
        elif not args.no_vitals:
            print("[warn] SMARTSPECTRA_API_KEY missing — no vitals overlay.")

        # Greet on startup (after the window has a moment to come up).
        threading.Timer(1.0, controller.greet).start()

        tracker = FaceTracker(mini, controller, vitals_state)
        try:
            tracker.run()  # blocks on the main thread (cv2 GUI)
        finally:
            if stream is not None:
                stream.stop()


if __name__ == "__main__":
    main()
