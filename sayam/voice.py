"""Sayam's voice — ElevenLabs text-to-speech with native macOS playback.

Synthesizes speech with the ElevenLabs API and plays it through `afplay`
(built into macOS, so no ffplay/mpv dependency). Reads credentials from the
environment: ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID.

Quick test:
    SMARTSPECTRA_API_KEY unused here; just need ElevenLabs vars
    python sayam/voice.py "Hey, I'm Sayam."
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Optional

from elevenlabs import ElevenLabs

# eleven_multilingual_v2 is the most broadly available model; swap to
# "eleven_flash_v2_5" for lower latency if your plan supports it.
DEFAULT_MODEL = "eleven_multilingual_v2"
DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


class Voice:
    """Wraps ElevenLabs TTS. Reuses one client/connection across calls."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model_id: str = DEFAULT_MODEL,
    ):
        _load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        self.api_key = api_key or os.environ.get("ELEVENLABS_API_KEY", "")
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "")
        self.model_id = model_id
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY not set (check .env).")
        if not self.voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID not set (check .env).")
        self._client = ElevenLabs(api_key=self.api_key)

    def synthesize(self, text: str, output_format: str = DEFAULT_OUTPUT_FORMAT) -> bytes:
        """Return audio bytes for `text` in the given ElevenLabs output format."""
        chunks = self._client.text_to_speech.convert(
            self.voice_id,
            text=text,
            model_id=self.model_id,
            output_format=output_format,
        )
        return b"".join(chunks)

    def synthesize_to_file(
        self, text: str, output_format: str = DEFAULT_OUTPUT_FORMAT, suffix: str = ".mp3"
    ) -> str:
        """Synthesize `text` to a temp file and return its path (caller deletes)."""
        audio = self.synthesize(text, output_format=output_format)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio)
            return f.name

    def synthesize_to_wav(self, text: str) -> str:
        """Synthesize `text` to a temp WAV and return its path (caller deletes).

        ElevenLabs WAV output is Pro-tier only, so we request MP3 (available on
        all tiers) and transcode to WAV locally with ffmpeg. The robot speaker
        API (`mini.media.play_sound`) wants a WAV it can read frame counts from.
        """
        mp3_path = self.synthesize_to_file(text, output_format=DEFAULT_OUTPUT_FORMAT,
                                            suffix=".mp3")
        wav_path = mp3_path[:-4] + ".wav"
        try:
            # loudnorm normalizes to a loud, broadcast-style target so the
            # robot's small speaker is clearly audible (no clipping). Bump the
            # integrated-loudness target (I=) toward 0 for even louder output.
            subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_path,
                 "-af", "loudnorm=I=-12:TP=-1.0:LRA=11",
                 wav_path],
                check=True, capture_output=True,
            )
        finally:
            try:
                os.unlink(mp3_path)
            except OSError:
                pass
        return wav_path

    def speak(self, text: str, blocking: bool = True) -> None:
        """Synthesize `text` and play it. Set blocking=False to play in a thread."""
        if not blocking:
            threading.Thread(target=self.speak, args=(text,), daemon=True).start()
            return

        audio = self.synthesize(text)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            tmp = f.name
        try:
            subprocess.run(["afplay", tmp], check=True)
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _main() -> None:
    text = " ".join(sys.argv[1:]) or "Hey, I'm Sayam, your study companion."
    print(f"Speaking: {text!r}")
    Voice().speak(text)
    print("Done.")


if __name__ == "__main__":
    _main()
