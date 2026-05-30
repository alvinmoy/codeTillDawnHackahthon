"""NotesBrain — watches the notes canvas and nudges when the user goes astray.

Every few seconds it snapshots the canvas, and if it changed since the last
check (and isn't blank), sends it to Groq's Llama-4 Scout vision model asking
for a mistake. If the model returns a correction (not "OK"), it fires on_nudge
with a short spoken sentence. Corrections are de-duplicated + cooled down so
Sayam doesn't nag.
"""

from __future__ import annotations

import base64
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np
import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # fastest vision Llama on Groq

SYSTEM_PROMPT = (
    "You are Sayam, a friendly study companion watching a student's handwritten "
    "notes through a small drawing canvas. Look at the image. If there is a CLEAR "
    "factual or math mistake, reply with ONE short, spoken-style sentence that "
    "gently corrects it and nudges them back on track "
    "(e.g. \"Hey, careful — one plus one is two, not three.\"). "
    "If the work looks correct, or the page is blank or unreadable, reply with "
    "exactly: OK"
)

NUDGE_COOLDOWN_S = 18.0   # don't repeat the same nudge within this window


class NotesBrain:
    def __init__(self, api_key: str, get_image: Callable[[], np.ndarray],
                 on_nudge: Callable[[str], None], interval: float = 4.0):
        self.api_key = api_key
        self.get_image = get_image
        self.on_nudge = on_nudge
        self.interval = interval
        self.status = "idle"          # idle | checking | ok | nudge  (for the UI)
        self.last_nudge = ""
        self._last_nudge_ts = 0.0
        self._last_hash = None
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @staticmethod
    def _is_blank(img: np.ndarray) -> bool:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return float((gray < 200).mean()) < 0.004   # <0.4% ink

    def _ask_groq(self, img: np.ndarray) -> str:
        b64 = base64.b64encode(cv2.imencode(".png", img)[1]).decode()
        body = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Check my notes for a mistake."},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64}"}},
                ]},
            ],
            "temperature": 0.2,
            "max_tokens": 80,
        }
        r = requests.post(GROQ_URL, json=body, timeout=20,
                          headers={"Authorization": f"Bearer {self.api_key}",
                                   "User-Agent": "sayam/1.0"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                img = self.get_image()
            except Exception:
                continue
            if img is None:
                continue
            h = hash(img.tobytes())
            if h == self._last_hash:
                continue                      # nothing new drawn since last check
            self._last_hash = h
            if self._is_blank(img):
                self.status = "idle"
                continue

            self.status = "checking"
            try:
                reply = self._ask_groq(img)
            except Exception as exc:
                print(f"[brain] {exc}")
                self.status = "idle"
                continue

            if reply.upper().startswith("OK") or len(reply) < 3:
                self.status = "ok"
                continue

            self.status = "nudge"
            now = time.time()
            if reply != self.last_nudge or (now - self._last_nudge_ts) > NUDGE_COOLDOWN_S:
                self.last_nudge = reply
                self._last_nudge_ts = now
                try:
                    self.on_nudge(reply)
                except Exception as exc:
                    print(f"[brain] nudge failed: {exc}")
