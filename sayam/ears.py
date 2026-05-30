"""Conversation — Sayam listens and answers when you talk to it.

Pipeline (all on the Reachy Mini mic):
    mic audio --VAD--> utterance --Groq Whisper--> transcript
      -> if it contains the wake word ("sayam") OR a Talk-button trigger,
         strip the wake word and send the question (+ a snapshot of your notes)
         to Groq's Llama-4 Scout vision model -> spoken reply via the robot.

To avoid Sayam hearing itself, listening is suspended while it speaks.
"""

from __future__ import annotations

import base64
import re
import tempfile
import threading
import time
import wave
from typing import Callable, Optional

import cv2
import numpy as np
import requests

GROQ_BASE = "https://api.groq.com/openai/v1"
STT_MODEL = "whisper-large-v3-turbo"
CHAT_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # vision: can see the notes

# Match how Whisper tends to hear "Sayam" (sayam/siam/sam/...), punctuation-proof.
WAKE_RE = re.compile(
    r"\b(sa+yam|sa+yem|saiyam|saiam|siam|salaam|psalm|sayyam|sam)\b", re.IGNORECASE)


def detect_wake(text: str):
    """Return (matched, query_after_wake)."""
    m = WAKE_RE.search(text)
    if not m:
        return False, text
    return True, text[m.end():].lstrip(" ,.!?:-")

# Voice-activity thresholds (float32 audio in [-1, 1]) — calibrated to the
# Reachy mic (silence ~0.0005, speech peaks ~0.13).
START_RMS = 0.040
END_RMS = 0.020
SILENCE_END_S = 0.8     # trailing silence that ends an utterance
MIN_SPEECH_S = 0.4
MAX_SPEECH_S = 8.0

SYSTEM_PROMPT = (
    "You are Sayam, a warm, encouraging study-companion robot sitting on the "
    "student's desk. They are talking to you out loud. Answer in 1-2 short, "
    "spoken-style sentences. If they refer to 'this', 'the problem', or their "
    "work, use the attached image of their notes to help. Don't read the wake "
    "word back. Be concise and friendly."
)


class Conversation:
    def __init__(self, mini, controller, api_key: str,
                 get_notes_image: Optional[Callable[[], np.ndarray]] = None,
                 on_state: Optional[Callable[[str, str], None]] = None):
        self.mini = mini
        self.controller = controller
        self.api_key = api_key
        self.get_notes_image = get_notes_image
        self.on_state = on_state or (lambda state, text: None)
        self._stop = threading.Event()
        self._listen_now = threading.Event()   # Talk button: capture next utterance w/o wake word
        self._suspend_until = 0.0
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def trigger_listen(self) -> None:
        """Talk button: answer my next utterance without needing the wake word."""
        self._listen_now.set()
        self.on_state("listening", "Listening...")

    # -- audio helpers -------------------------------------------------------
    def _headers(self):
        return {"Authorization": f"Bearer {self.api_key}", "User-Agent": "sayam/1.0"}

    @staticmethod
    def _to_mono(chunk: np.ndarray) -> np.ndarray:
        return chunk if chunk.ndim == 1 else chunk.mean(axis=1)

    def _write_wav(self, samples: np.ndarray, sr: int) -> str:
        pcm = np.clip(samples, -1.0, 1.0)
        pcm = (pcm * 32767.0).astype(np.int16)
        path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(pcm.tobytes())
        return path

    def _transcribe(self, wav_path: str) -> str:
        with open(wav_path, "rb") as f:
            r = requests.post(f"{GROQ_BASE}/audio/transcriptions", headers=self._headers(),
                              files={"file": ("a.wav", f, "audio/wav")},
                              data={"model": STT_MODEL}, timeout=30)
        r.raise_for_status()
        return r.json().get("text", "").strip()

    def _answer(self, query: str) -> str:
        content = [{"type": "text", "text": query}]
        if self.get_notes_image is not None:
            try:
                img = self.get_notes_image()
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                if float((gray < 200).mean()) > 0.004:  # only attach if there's ink
                    b64 = base64.b64encode(cv2.imencode(".png", img)[1]).decode()
                    content.append({"type": "image_url",
                                    "image_url": {"url": f"data:image/png;base64,{b64}"}})
            except Exception:
                pass
        body = {"model": CHAT_MODEL, "temperature": 0.4, "max_tokens": 160,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": content}]}
        r = requests.post(f"{GROQ_BASE}/chat/completions", json=body,
                          headers=self._headers(), timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    # -- main loop -----------------------------------------------------------
    def _loop(self) -> None:
        try:
            sr = self.mini.media.get_input_audio_samplerate()
            self.mini.media.start_recording()
        except Exception as exc:
            print(f"[ears] mic unavailable: {exc}")
            return

        print(f"[ears] listening on mic (sr={sr}). Say 'Sayam ...' or use the Talk button.")
        buf = []
        in_speech = False
        speech_s = 0.0
        silence_s = 0.0
        dbg_peak = 0.0
        dbg_t = time.time()
        while not self._stop.is_set():
            chunk = self.mini.media.get_audio_sample()
            if chunk is None:
                time.sleep(0.01)
                continue
            mono = self._to_mono(np.asarray(chunk, dtype=np.float32))
            if mono.size == 0:
                continue
            frame_s = mono.size / float(sr)

            # Periodic mic-level debug so we can see audio is flowing / tune VAD.
            _rms = float(np.sqrt(np.mean(mono ** 2)))
            dbg_peak = max(dbg_peak, _rms)
            if time.time() - dbg_t > 3.0:
                print(f"[ears] mic peak RMS (3s) = {dbg_peak:.3f}  (START={START_RMS})")
                dbg_peak = 0.0
                dbg_t = time.time()

            # Ignore audio while Sayam is speaking (anti-feedback) — covers
            # greet/nudge/stress/answer, so it never hears its own "I'm Sayam".
            if time.time() < self._suspend_until or self.controller.is_speaking():
                buf, in_speech, speech_s, silence_s = [], False, 0.0, 0.0
                if self.controller.is_speaking():
                    self._suspend_until = time.time() + 0.6  # short tail
                continue

            rms = float(np.sqrt(np.mean(mono ** 2)))
            if rms > START_RMS:
                in_speech = True
                silence_s = 0.0
            if in_speech:
                buf.append(mono)
                speech_s += frame_s
                silence_s = silence_s + frame_s if rms < END_RMS else 0.0
                ended = silence_s > SILENCE_END_S and speech_s > MIN_SPEECH_S
                if ended or speech_s > MAX_SPEECH_S:
                    utterance = np.concatenate(buf)
                    buf, in_speech, sdur, speech_s, silence_s = [], False, speech_s, 0.0, 0.0
                    self._handle(utterance, sr)

    def _handle(self, samples: np.ndarray, sr: int) -> None:
        forced = self._listen_now.is_set()
        wav = self._write_wav(samples, sr)
        try:
            text = self._transcribe(wav)
        except Exception as exc:
            print(f"[ears] STT failed: {exc}")
            return
        finally:
            try:
                import os
                os.unlink(wav)
            except OSError:
                pass

        if not text:
            return
        has_wake, stripped = detect_wake(text)
        print(f"[ears] heard: {text!r}  (wake={has_wake} armed={forced})")
        if not (forced or has_wake):
            return  # not addressed to Sayam

        query = stripped if has_wake else text

        # Bare wake word ("Sayam") with no question yet → arm for the next sentence.
        if not forced and len(query) < 2:
            self._listen_now.set()
            self.on_state("listening", "Listening - go ahead")
            print("[ears] wake word heard; listening for your question...")
            return

        self._listen_now.clear()
        if len(query) < 2:
            query = "The student said hi to you — greet them back in one short sentence."
        print(f"[ears] query: {query!r}")
        self.on_state("thinking", f"You: {text}")

        try:
            reply = self._answer(query)
        except Exception as exc:
            print(f"[ears] answer failed: {exc}")
            self.on_state("idle", "")
            return

        print(f"[ears] reply: {reply!r}")
        self.on_state("speaking", f"Sayam: {reply}")
        # suspend listening for the spoken duration (rough estimate) + buffer
        self._suspend_until = time.time() + 2.0 + 0.075 * len(reply)
        self.controller.say(reply)
