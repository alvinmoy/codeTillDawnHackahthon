"""Calm face tracking + live view with an on-screen BUTTON panel.

The robot holds still and only recenters on your neck when you drift out of a
center deadzone (keeps your chest in frame for breathing). The OpenCV window
shows the robot cam + face box + live Presage vitals (HR / breathing / stress),
and a row of clickable buttons:

    [ Greet ]  [ Fake Stress ]  [ Start/Stop ]  [ Quit ]

Buttons are drawn in the window and handled via an OpenCV mouse callback — no
keyboard, no extra GUI toolkit. Call run() from the main thread (macOS).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional

import cv2

# Recenter when the aim point drifts past this fraction of half-frame
# (smaller = follows sooner / less lag, but don't go so small it jitters).
DEADZONE_X = 0.26
DEADZONE_Y = 0.24
# Aim a bit below the face center (in face-height units) — on the lower face,
# not all the way to the neck. Keeps the face prominent (good for HR) while
# nudging the chest into frame.
NECK_OFFSET_FACES = 0.35
# Downscale factor for face detection (smaller = faster detection = less lag).
DETECT_SCALE = 0.5

BAR_H = 76  # button bar height (px)

# Baevsky stress index bands (tunable; SI rises as HRV drops).
STRESS_MODERATE = 150.0
STRESS_HIGH = 500.0


def stress_label(si: Optional[float]) -> str:
    if si is None:
        return "--"
    if si >= STRESS_HIGH:
        return "HIGH"
    if si >= STRESS_MODERATE:
        return "moderate"
    return "low"


@dataclass
class VitalsState:
    pulse: Optional[float] = None
    breathing: Optional[float] = None
    stress_index: Optional[float] = None
    status_hint: str = ""
    stressed: bool = False     # demo override OR computed high stress
    samples: int = 0
    _lock: threading.Lock = None  # type: ignore

    def __post_init__(self):
        self._lock = threading.Lock()

    def update_sample(self, pulse, breathing, stress=None):
        with self._lock:
            self.samples += 1
            if pulse is not None:
                self.pulse = pulse
            if breathing is not None:
                self.breathing = breathing
            if stress is not None:
                self.stress_index = stress

    def update_status(self, hint: str):
        with self._lock:
            self.status_hint = hint

    def set_stressed(self, value: bool):
        with self._lock:
            self.stressed = value

    def snapshot(self):
        with self._lock:
            return (self.pulse, self.breathing, self.stress_index,
                    self.status_hint, self.stressed, self.samples)


class FaceTracker:
    def __init__(self, mini, controller, vitals: Optional[VitalsState] = None,
                 window_name: str = "Sayam"):
        self.mini = mini
        self.controller = controller
        self.vitals = vitals
        self.window_name = window_name
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        self._buttons = []      # list of dicts: {label, rect, action, color}
        self.quit = False
        self.on_talk = None     # set by app -> conversation.trigger_listen
        self.convo_status = ""  # "You: ..." / "Sayam: ..." / "Listening..."
        self._flash = (None, 0.0)  # (action, until_ts) for click feedback
        self._hover = None         # action under the cursor (for hover highlight)
        self._last_t = time.time()
        self._fps = 0.0

    # -- buttons -------------------------------------------------------------
    def _hit(self, x, y):
        for b in self._buttons:
            x1, y1, x2, y2 = b["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return b
        return None

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            b = self._hit(x, y)
            self._hover = b["action"] if b else None
        elif event == cv2.EVENT_LBUTTONDOWN:
            b = self._hit(x, y)
            if b:
                self._flash = (b["action"], time.time() + 0.2)
                self._do(b["action"])

    def _do(self, action: str) -> None:
        print(f"[button] {action}")
        if action == "greet":
            self.controller.greet()
        elif action == "stress":
            self.controller.fake_stress()
        elif action == "toggle":
            self.controller.toggle_active()
        elif action == "talk":
            if self.on_talk:
                self.on_talk()
        elif action == "quit":
            self.quit = True

    def _draw_buttons(self, canvas, video_h, w) -> None:
        active = self.controller.active
        specs = [
            ("Greet", "greet", (60, 140, 60)),
            ("Talk", "talk", (150, 90, 30)),
            ("Stress", "stress", (40, 40, 200)),
            ("Stop" if active else "Start", "toggle",
             (140, 110, 40) if active else (40, 110, 140)),
            ("Quit", "quit", (70, 70, 70)),
        ]
        self._buttons = []
        n = len(specs)
        bw = w // n
        y1, y2 = video_h, video_h + BAR_H
        for i, (label, action, color) in enumerate(specs):
            x1 = i * bw + 6
            x2 = (i + 1) * bw - 6
            flashing = self._flash[0] == action and time.time() < self._flash[1]
            c = tuple(min(255, v + 70) for v in color) if flashing else color
            cv2.rectangle(canvas, (x1, y1 + 8), (x2, y2 - 8), c, -1)
            cv2.rectangle(canvas, (x1, y1 + 8), (x2, y2 - 8), (230, 230, 230), 1)
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            tx = x1 + (x2 - x1 - tw) // 2
            ty = y1 + (BAR_H + th) // 2
            cv2.putText(canvas, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        (255, 255, 255), 2, cv2.LINE_AA)
            self._buttons.append({"label": label, "rect": (x1, y1, x2, y2),
                                  "action": action})

    # -- overlay on the video region ----------------------------------------
    def _overlay(self, bgr, face, neck, tracking_now, fps) -> None:
        h, w = bgr.shape[:2]
        dz_x = int((w / 2) * DEADZONE_X)
        dz_y = int((h / 2) * DEADZONE_Y)
        cv2.rectangle(bgr, (w // 2 - dz_x, h // 2 - dz_y),
                      (w // 2 + dz_x, h // 2 + dz_y), (90, 90, 90), 1)

        cv2.rectangle(bgr, (0, 0), (w, 70), (0, 0, 0), -1)
        cv2.putText(bgr, "SAYAM", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (0, 200, 255), 2, cv2.LINE_AA)
        state = "tracking" if self.controller.active else "STOPPED"
        cv2.putText(bgr, f"{state}  {fps:4.1f}fps", (w - 210, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

        if self.vitals is not None:
            pulse, breathing, si, hint, stressed, samples = self.vitals.snapshot()
            hr = f"{pulse:.0f}" if pulse else "--"
            br = f"{breathing:.0f}" if breathing else "--"
            slab = stress_label(si)
            scol = (0, 0, 255) if (stressed or slab == "HIGH") else (0, 220, 0)
            cv2.putText(bgr, f"HR {hr} bpm   BR {br}/min   Stress {slab}",
                        (10, 58), cv2.FONT_HERSHEY_SIMPLEX, 0.6, scol, 2, cv2.LINE_AA)
            cv2.putText(bgr, f"rx {samples}", (w - 90, 58), cv2.FONT_HERSHEY_SIMPLEX,
                        0.45, (150, 150, 150), 1, cv2.LINE_AA)
            if pulse is None and breathing is None:
                msg = ("Reading vitals... face camera, hold still, good light"
                       if samples else "Waiting for camera/face...")
                cv2.putText(bgr, msg, (10, h - 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 220, 255), 2, cv2.LINE_AA)
            if hint:
                cv2.putText(bgr, f"capture: {hint}", (10, h - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 220, 0), 1, cv2.LINE_AA)
            if stressed:
                cv2.putText(bgr, "STRESSED - take a break", (10, h - 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2, cv2.LINE_AA)

        if self.convo_status:
            cv2.putText(bgr, self.convo_status[:64], (10, h - 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 80), 2, cv2.LINE_AA)

        if face is not None:
            x, y, fw, fh = face
            box_color = (0, 200, 255) if tracking_now else (0, 220, 0)
            cv2.rectangle(bgr, (x, y), (x + fw, y + fh), box_color, 2)
            cv2.putText(bgr, "recentering" if tracking_now else "centered",
                        (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1, cv2.LINE_AA)
        if neck is not None:
            cv2.drawMarker(bgr, neck, (255, 150, 0), cv2.MARKER_CROSS, 16, 2)

    def attach(self) -> None:
        cv2.namedWindow(self.window_name, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(self.window_name, self._on_mouse)

    def step(self, display_width: int = 960) -> None:
        """Render one camera frame (no waitKey — the app loop owns that)."""
        frame = self.mini.media.get_frame()
        if frame is None:
            return

        bgr_full = frame[:, :, ::-1]
        full_h, full_w = bgr_full.shape[:2]
        scale = display_width / float(full_w)
        bgr = cv2.resize(bgr_full, (display_width, int(full_h * scale)))
        dh, dw = bgr.shape[:2]
        sx, sy = full_w / float(dw), full_h / float(dh)

        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (0, 0), fx=DETECT_SCALE, fy=DETECT_SCALE)
        dets = self._cascade.detectMultiScale(small, scaleFactor=1.2,
                                              minNeighbors=5, minSize=(40, 40))
        faces = [(int(x / DETECT_SCALE), int(y / DETECT_SCALE),
                  int(fw / DETECT_SCALE), int(fh / DETECT_SCALE))
                 for (x, y, fw, fh) in dets]
        face = None
        neck = None
        issued = False
        if len(faces) > 0:
            face = max(faces, key=lambda f: f[2] * f[3])
            x, y, fw, fh = face
            neck = (int(x + fw / 2),
                    min(int(y + fh / 2 + NECK_OFFSET_FACES * fh), dh - 1))
            ndx = (neck[0] - dw / 2) / (dw / 2)
            ndy = (neck[1] - dh / 2) / (dh / 2)
            if abs(ndx) > DEADZONE_X or abs(ndy) > DEADZONE_Y:
                issued = self.controller.recenter(int(neck[0] * sx), int(neck[1] * sy))

        now = time.time()
        self._fps = 0.9 * self._fps + 0.1 * (1.0 / max(now - self._last_t, 1e-3))
        self._last_t = now
        self._overlay(bgr, face, neck, issued, self._fps)

        canvas = cv2.copyMakeBorder(bgr, 0, BAR_H, 0, 0, cv2.BORDER_CONSTANT,
                                    value=(20, 20, 20))
        self._draw_buttons(canvas, dh, dw)
        cv2.imshow(self.window_name, canvas)
        if cv2.getWindowProperty(self.window_name, cv2.WND_PROP_VISIBLE) < 1:
            self.quit = True

    def run(self, display_width: int = 960) -> None:
        """Standalone loop (camera only)."""
        self.attach()
        print("Live view up. Use the on-screen buttons. (Quit button to exit.)")
        while not self.quit:
            self.step(display_width)
            cv2.waitKey(1)
        cv2.destroyAllWindows()
