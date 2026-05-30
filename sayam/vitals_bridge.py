"""Bridge between the C++ Presage vitals producer and the Python Sayam brain.

The C++ `sayam_vitals` binary streams line-delimited JSON to stdout. This module
spawns it as a subprocess, parses each line, and surfaces the latest vitals
(pulse rate, breathing rate) plus capture-status hints to a callback. The Sayam
orchestrator (LLM + Reachy Mini SDK + ElevenLabs) consumes `VitalsSample`s and
decides when to speak up ("you look stressed, take a break").

Usage (standalone smoke test):
    SMARTSPECTRA_API_KEY=... python -m sayam.vitals_bridge \
        --binary ../vitals/build/sayam_vitals

Usage (embedded):
    stream = VitalsStream(binary_path, api_key=...)
    stream.on_sample = lambda s: print(s.pulse_rate, s.breathing_rate)
    stream.start()
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class VitalsSample:
    """A single vitals reading distilled from the Presage metrics envelope."""

    ts_us: int
    pulse_rate: Optional[float] = None          # beats per minute
    pulse_confidence: Optional[float] = None
    breathing_rate: Optional[float] = None       # breaths per minute
    breathing_confidence: Optional[float] = None
    hrv_rmssd: Optional[float] = None            # ms — heart-rate variability
    stress_index: Optional[float] = None         # Baevsky stress index (higher = more stress)
    stress_confidence: Optional[float] = None


def _latest(entries: list) -> Optional[dict]:
    """Return the last entry of a repeated measurement list, or None."""
    return entries[-1] if entries else None


def _get(d: dict, *keys: str):
    """Fetch the first present key (handles protobuf camelCase/snake_case)."""
    for k in keys:
        if k in d:
            return d[k]
    return None


def parse_metrics(data: dict, ts_us: int) -> VitalsSample:
    """Turn a Presage `metrics` proto-as-JSON object into a VitalsSample."""
    sample = VitalsSample(ts_us=ts_us)

    cardio = _get(data, "cardio", "cardiac") or {}
    pulse = _latest(_get(cardio, "pulseRate", "pulse_rate") or [])
    if pulse:
        sample.pulse_rate = pulse.get("value")
        sample.pulse_confidence = pulse.get("confidence")

    # HRV carries Baevsky's stress index (higher = more stress).
    hrv = _latest(_get(cardio, "hrv") or [])
    if hrv:
        sample.hrv_rmssd = hrv.get("rmssd")
        sample.stress_index = hrv.get("baevsky")
        sample.stress_confidence = hrv.get("confidence")

    breathing = _get(data, "breathing", "respiration") or {}
    rate = _latest(_get(breathing, "rate") or [])
    if rate:
        sample.breathing_rate = rate.get("value")
        sample.breathing_confidence = rate.get("confidence")

    return sample


class VitalsStream:
    """Spawns the C++ vitals producer and streams parsed samples to callbacks."""

    def __init__(
        self,
        binary_path: str,
        api_key: Optional[str] = None,
        camera_device_index: int = 0,
        input_video_path: Optional[str] = None,
    ):
        self.binary_path = binary_path
        self.api_key = api_key or os.environ.get("SMARTSPECTRA_API_KEY", "")
        self.camera_device_index = camera_device_index
        self.input_video_path = input_video_path

        # Wire these up before calling start().
        self.on_sample: Callable[[VitalsSample], None] = lambda s: None
        self.on_status: Callable[[int, str], None] = lambda code, hint: None
        self.on_error: Callable[[str], None] = lambda msg: None

        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None

    def _build_command(self) -> list[str]:
        cmd = [self.binary_path, f"--api_key={self.api_key}"]
        if self.input_video_path:
            cmd.append(f"--input_video_path={self.input_video_path}")
        else:
            cmd.append(f"--camera_device_index={self.camera_device_index}")
        return cmd

    def start(self) -> None:
        if not self.api_key:
            raise RuntimeError(
                "No API key. Pass api_key=... or set SMARTSPECTRA_API_KEY."
            )
        self._proc = subprocess.Popen(
            self._build_command(),
            stdout=subprocess.PIPE,
            stderr=None,  # let the C++ human logs flow to our stderr
            text=True,
            bufsize=1,  # line-buffered
        )
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            line = line.strip()
            if not line or not line.startswith("{"):
                continue  # skip any non-JSON noise
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue

            kind = msg.get("type")
            if kind == "metrics":
                self.on_sample(parse_metrics(msg.get("data", {}), msg.get("ts", 0)))
            elif kind == "status":
                self.on_status(msg.get("code", -1), msg.get("hint", ""))
            elif kind == "error":
                self.on_error(msg.get("message", "unknown error"))

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()


def _main() -> None:
    parser = argparse.ArgumentParser(description="Sayam vitals bridge smoke test.")
    parser.add_argument(
        "--binary",
        default="../vitals/build/sayam_vitals",
        help="Path to the compiled sayam_vitals binary.",
    )
    parser.add_argument("--api-key", default=os.environ.get("SMARTSPECTRA_API_KEY"))
    parser.add_argument("--camera-device-index", type=int, default=0)
    parser.add_argument("--input-video-path", default=None)
    args = parser.parse_args()

    stream = VitalsStream(
        binary_path=args.binary,
        api_key=args.api_key,
        camera_device_index=args.camera_device_index,
        input_video_path=args.input_video_path,
    )
    stream.on_sample = lambda s: print(
        f"♥ pulse={s.pulse_rate} bpm (conf {s.pulse_confidence})  "
        f"🫁 breathing={s.breathing_rate} brpm (conf {s.breathing_confidence})"
    )
    stream.on_status = lambda code, hint: print(f"[status {code}] {hint}")
    stream.on_error = lambda msg: print(f"[error] {msg}")

    print("Starting vitals stream. Look at the camera. Ctrl+C to stop.")
    stream.start()
    try:
        if stream._thread:
            stream._thread.join()
    except KeyboardInterrupt:
        stream.stop()


if __name__ == "__main__":
    _main()
