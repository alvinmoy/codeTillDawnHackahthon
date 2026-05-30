"""Sayam demo app: live camera view + face tracking + notes canvas + brain.

Two windows, one main loop:
  * "Sayam"        — robot cam, face tracking, vitals (HR/BR/stress), buttons
                     (Greet / Fake Stress / Start-Stop / Quit)
  * "Sayam - Notes" — freehand drawing canvas for your work; the Groq brain
                     watches it and Sayam cuts in (voice + gesture) if you go
                     astray (e.g. you write 1+1=3).

Daemon must be running (`reachy-mini-daemon`), venv active:
    python live_view.py
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path

import cv2
from reachy_mini import ReachyMini

from brain import NotesBrain
from control import RobotController
from ears import Conversation
from notes import NotesCanvas
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
    parser.add_argument("--no-notes", action="store_true")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("SMARTSPECTRA_API_KEY", "")
    groq_key = os.environ.get("GROQ_API_KEY", "")

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

        # Vitals stream
        stream = None
        if not args.no_vitals and api_key:
            stream = VitalsStream(binary_path=args.binary, api_key=api_key,
                                  camera_device_index=args.camera_device_index)
            stream.on_sample = lambda s: vitals_state.update_sample(
                s.pulse_rate, s.breathing_rate, s.stress_index)
            stream.on_status = lambda code, hint: vitals_state.update_status(hint)
            stream.on_error = lambda msg: print(f"[vitals error] {msg}")
            stream.start()

        # Notes canvas + brain
        notes = None
        brain = None
        nudge_until = [0.0]
        if not args.no_notes and groq_key:
            notes = NotesCanvas()

            def on_nudge(text: str) -> None:
                print(f"[brain] NUDGE: {text}")
                notes.status_text = text
                notes.status_color = (0, 0, 255)
                nudge_until[0] = time.time() + 8.0
                controller.nudge(text)

            brain = NotesBrain(groq_key, notes.get_image, on_nudge, interval=4.0)
        elif not args.no_notes:
            print("[warn] GROQ_API_KEY missing — notes brain disabled.")

        tracker = FaceTracker(mini, controller, vitals_state)

        # Voice conversation: "hey sayam ..." or the Talk button.
        convo = None
        convo_clear = [0.0]
        if groq_key:
            def on_convo_state(state: str, text: str) -> None:
                tracker.convo_status = text
                convo_clear[0] = time.time() + (10.0 if state == "speaking" else 5.0)
            convo = Conversation(mini=mini, controller=controller, api_key=groq_key,
                                 get_notes_image=(notes.get_image if notes else None),
                                 on_state=on_convo_state)
            tracker.on_talk = convo.trigger_listen

        tracker.attach()
        if notes is not None:
            notes.attach()
        if brain is not None:
            brain.start()
        if convo is not None:
            convo.start()

        threading.Timer(1.0, controller.greet).start()
        print("Running. Draw in the Notes window; use the buttons on the camera view.")

        try:
            while not tracker.quit:
                tracker.step()
                if convo is not None and time.time() > convo_clear[0]:
                    tracker.convo_status = ""
                if notes is not None:
                    # Reflect brain status unless a nudge is currently showing.
                    if brain is not None and time.time() > nudge_until[0]:
                        st = brain.status
                        if st == "checking":
                            notes.status_text, notes.status_color = "Sayam is checking...", (0, 180, 220)
                        elif st == "ok":
                            notes.status_text, notes.status_color = "Looks good", (0, 200, 0)
                        elif st == "idle":
                            notes.status_text, notes.status_color = "Draw your notes here", (150, 150, 150)
                    notes.step()
                cv2.waitKey(1)
        except KeyboardInterrupt:
            pass
        finally:
            if convo is not None:
                convo.stop()
            if brain is not None:
                brain.stop()
            if stream is not None:
                stream.stop()
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
