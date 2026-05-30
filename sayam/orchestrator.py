"""Sayam orchestrator — ties the Presage vitals stream to a lively Reachy Mini.

Flow:
    Reachy camera (UVC index 1)
        -> sayam_vitals (C++/Presage)  --JSON-->  VitalsStream (Python)
        -> StressMonitor decides when the user looks stressed
        -> Reachy Mini reacts (concerned lean-in) + Sayam speaks (ElevenLabs,
           out the robot's own speaker).

Between events the robot idles with gentle sway + random quirks (LivelyRobot),
so it always feels alive. Uses media_backend="default" so it can speak; Presage
reads the same physical camera directly as UVC index 1 (macOS shares it).

Run (daemon running: `reachy-mini-daemon`, venv active):
    python orchestrator.py --binary ../vitals/build/sayam_vitals
Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import os
import threading
import time
import wave
from pathlib import Path
from typing import Optional

from reachy_mini import ReachyMini

from liveliness import LivelyRobot
from vitals_bridge import VitalsSample, VitalsStream
from voice import Voice

# --- stress thresholds (tune for the demo) ---
PULSE_STRESS_DELTA = 15.0     # bpm above resting baseline → "stressed"
BREATHING_STRESS_BPM = 22.0   # breaths/min above this → "stressed"
BASELINE_SAMPLES = 8
STRESS_COOLDOWN_S = 45.0
MIN_CONFIDENCE = 0.3


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


def make_say(voice: Optional[Voice], mini: ReachyMini):
    """Return `say(text)` that speaks through the ROBOT's speaker (async).

    Falls back to text-only if ElevenLabs is unavailable so the demo still runs.
    """

    def _speak_on_robot(text: str) -> None:
        try:
            wav = voice.synthesize_to_wav(text)
            mini.media.play_sound(wav)
            try:
                with wave.open(wav, "rb") as wf:
                    dur = wf.getnframes() / float(wf.getframerate())
            except Exception:
                dur = 5.0
            time.sleep(dur + 1.0)
            os.unlink(wav)
        except Exception as exc:
            print(f"[voice] TTS failed: {exc}")

    def say(text: str) -> None:
        print(f"\n🗣️  SAYAM: {text}\n")
        if voice is not None:
            threading.Thread(target=_speak_on_robot, args=(text,), daemon=True).start()

    return say


class StressMonitor:
    """Turns a stream of VitalsSamples into stress decisions + robot reactions."""

    def __init__(self, robot: LivelyRobot, say):
        self.robot = robot
        self.say = say
        self._pulse_baseline: Optional[float] = None
        self._baseline_buf: list[float] = []
        self._last_stress_ts = 0.0
        self._last_pulse: Optional[float] = None
        self._last_breathing: Optional[float] = None

    def on_sample(self, s: VitalsSample) -> None:
        if s.pulse_rate and (s.pulse_confidence or 1.0) >= MIN_CONFIDENCE:
            self._last_pulse = s.pulse_rate
            if self._pulse_baseline is None:
                self._baseline_buf.append(s.pulse_rate)
                if len(self._baseline_buf) >= BASELINE_SAMPLES:
                    self._pulse_baseline = sum(self._baseline_buf) / len(self._baseline_buf)
                    print(f"[monitor] resting pulse baseline ≈ {self._pulse_baseline:.0f} bpm")

        if s.breathing_rate and (s.breathing_confidence or 1.0) >= MIN_CONFIDENCE:
            self._last_breathing = s.breathing_rate

        self._evaluate()

    def _evaluate(self) -> None:
        reasons = []
        if (
            self._pulse_baseline is not None
            and self._last_pulse is not None
            and self._last_pulse > self._pulse_baseline + PULSE_STRESS_DELTA
        ):
            reasons.append(
                f"your heart rate is up to {self._last_pulse:.0f} bpm "
                f"(resting ~{self._pulse_baseline:.0f})"
            )
        if self._last_breathing is not None and self._last_breathing > BREATHING_STRESS_BPM:
            reasons.append(f"your breathing has quickened to {self._last_breathing:.0f} per minute")

        if reasons and (time.time() - self._last_stress_ts) > STRESS_COOLDOWN_S:
            self._last_stress_ts = time.time()
            self._trigger_break(reasons[0])

    def _trigger_break(self, reason: str) -> None:
        print(f"[monitor] STRESS detected: {reason}")
        self.robot.request("concerned")
        self.say(f"Hey — {reason}. You've been at it a while. Let's take a five-minute break.")

    def on_status(self, code: int, hint: str) -> None:
        print(f"[capture] ({code}) {hint}")

    def on_error(self, msg: str) -> None:
        print(f"[vitals error] {msg}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sayam vitals→movement orchestrator.")
    parser.add_argument("--binary", default="../vitals/build/sayam_vitals")
    parser.add_argument("--camera-device-index", type=int, default=1,
                        help="Reachy Mini camera is index 1 on this Mac.")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    api_key = os.environ.get("SMARTSPECTRA_API_KEY", "")
    if not api_key:
        raise SystemExit("SMARTSPECTRA_API_KEY not set (check .env).")

    try:
        voice = Voice()
    except Exception as exc:
        print(f"[voice] ElevenLabs unavailable ({exc}); falling back to text.")
        voice = None

    print("Connecting to Reachy Mini (media_backend='default')...")
    with ReachyMini(media_backend="default") as mini:
        robot = LivelyRobot(mini)
        robot.start()  # idle + quirks begin immediately
        say = make_say(voice, mini)

        # Greet: gesture + speak together, then idle keeps it alive.
        robot.request("greet")
        say("Hey, I'm Sayam, your study companion. I'll keep an eye on you while you work.")
        time.sleep(3.0)

        monitor = StressMonitor(robot, say)
        stream = VitalsStream(
            binary_path=args.binary,
            api_key=api_key,
            camera_device_index=args.camera_device_index,
        )
        stream.on_sample = monitor.on_sample
        stream.on_status = monitor.on_status
        stream.on_error = monitor.on_error

        print("Sayam is watching. Study away — Ctrl+C to stop.")
        stream.start()
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            stream.stop()
            robot.stop()
            time.sleep(1.0)


if __name__ == "__main__":
    main()
