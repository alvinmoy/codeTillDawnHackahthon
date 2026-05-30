"""Sayam greets us THROUGH THE ROBOT, then stays lively.

ElevenLabs voice out the robot's speaker + an antenna/head greeting, then a
continuous "alive" idle (gentle sway + random quirks) until you Ctrl+C.

Requires the daemon running (`reachy-mini-daemon`) and the venv active:
    python sayam/greet.py
    python sayam/greet.py "Good morning! Ready to study?"
"""

from __future__ import annotations

import os
import sys
import time
import wave

from reachy_mini import ReachyMini

from liveliness import LivelyRobot
from voice import Voice

GREETING = "Hey, I'm Sayam, your study companion. Let's get to work!"


def wav_duration_s(path: str) -> float:
    with wave.open(path, "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def main() -> None:
    text = " ".join(sys.argv[1:]) or GREETING
    voice = Voice()

    print(f"Synthesizing greeting with ElevenLabs: {text!r}")
    wav_path = voice.synthesize_to_wav(text)
    duration = wav_duration_s(wav_path)
    print(f"Got {duration:.1f}s of audio.")

    print("Connecting to Reachy Mini (media_backend='default' for speaker)...")
    with ReachyMini(media_backend="default") as mini:
        robot = LivelyRobot(mini)
        robot.start()  # idle/quirks begin immediately
        time.sleep(0.3)

        print("Sayam is greeting you — listen to the robot!")
        robot.request("greet")            # greeting gesture (pauses idle briefly)
        mini.media.play_sound(wav_path)   # voice out the robot's speaker
        time.sleep(duration + 0.3)

        print("Sayam is now idling with little quirks. Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            robot.stop()
            time.sleep(0.8)

    try:
        os.unlink(wav_path)
    except OSError:
        pass


if __name__ == "__main__":
    main()
