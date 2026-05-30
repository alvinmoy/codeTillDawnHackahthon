"""NotesCanvas — a little freehand drawing window for the user's study notes.

Draw with the mouse (left-button drag). A top bar has a Clear button and shows
the brain's status / Sayam's latest nudge. The brain periodically snapshots
get_image() to check the work.

Created and serviced on the main thread alongside the camera window (one shared
cv2.waitKey in the app loop).
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

BAR_H = 46
PEN_THICKNESS = 3


class NotesCanvas:
    def __init__(self, window: str = "Sayam - Notes", width: int = 760, height: int = 560):
        self.window = window
        self.w = width
        self.h = height
        self.canvas = np.full((height, width, 3), 255, np.uint8)
        self._lock = threading.Lock()
        self._drawing = False
        self._last = None
        self.status_text = "Draw your notes here"
        self.status_color = (150, 150, 150)

    def attach(self) -> None:
        cv2.namedWindow(self.window, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window, self._on_mouse)

    def _on_mouse(self, event, x, y, flags, param) -> None:
        # Top bar: Clear button.
        if y < BAR_H:
            if event == cv2.EVENT_LBUTTONDOWN and x < 96:
                self.clear()
            return
        dy = y - BAR_H  # drawing-area coords
        if event == cv2.EVENT_LBUTTONDOWN:
            self._drawing = True
            self._last = (x, dy)
        elif event == cv2.EVENT_MOUSEMOVE and self._drawing:
            with self._lock:
                if self._last is not None:
                    cv2.line(self.canvas, self._last, (x, dy), (0, 0, 0), PEN_THICKNESS)
            self._last = (x, dy)
        elif event == cv2.EVENT_LBUTTONUP:
            self._drawing = False
            self._last = None

    def clear(self) -> None:
        with self._lock:
            self.canvas[:] = 255
        self.status_text = "Cleared"
        self.status_color = (150, 150, 150)

    def get_image(self) -> np.ndarray:
        with self._lock:
            return self.canvas.copy()

    def step(self) -> None:
        with self._lock:
            draw = self.canvas.copy()
        bar = np.full((BAR_H, self.w, 3), 35, np.uint8)
        cv2.rectangle(bar, (6, 7), (90, BAR_H - 7), (80, 80, 80), -1)
        cv2.rectangle(bar, (6, 7), (90, BAR_H - 7), (220, 220, 220), 1)
        cv2.putText(bar, "Clear", (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(bar, self.status_text[:60], (108, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.6, self.status_color, 2, cv2.LINE_AA)
        cv2.imshow(self.window, np.vstack([bar, draw]))
