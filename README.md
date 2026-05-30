# Sayam, Your Study Companion on Reachy Mini

A vitals-aware desktop robot that watches how you are doing while you study, not just what you are doing, and tells you when to take a break.

Built for the Presage Technologies Hackathon.

## Inspiration

We are still college students, and we still have to study. Those late-night grind sessions are real: three hours deep, heart racing, shoulders at your ears, and you do not even notice you stopped absorbing anything an hour ago. Timers and to-do apps track tasks, but they are blind to the person doing them.

We wanted a companion that could tell the difference between focused flow and quiet panic. Presage's video-to-vitals technology meant we did not need a watch or a chest strap, just a camera. Reachy Mini gave that camera a face, a voice, and a personality, so the readings feel like a friend nudging you to breathe.

## What It Does and How We Use It

Sayam runs on a Reachy Mini robot and combines contactless vitals sensing, face tracking, expressive movement, and voice.

- **Reads your body, no wearables.** The Reachy Mini camera feed runs through the Presage SmartSpectra SDK to get live heart rate, breathing rate, and a heart-rate-variability stress index.
- **Learns your baseline.** It builds your resting heart rate over the first few readings, then flags stress when your heart rate climbs above that, your breathing quickens, or your stress index spikes.
- **Reacts physically and out loud.** On stress, it leans in with a concerned gesture and speaks through its own speaker (ElevenLabs voice): "Hey, your heart rate is up and you have been at it a while. Let's take a five-minute break." A cooldown keeps it from nagging.
- **Stays alive.** It tracks your face to keep you in frame, and between events idles with a gentle breathing sway and small quirks (tilt, glance, nod, antenna perk).

Run it two ways (both need the Reachy Mini daemon running and a Presage key in `.env`):

- `live_view.py`: a window with the camera, a face box, a live vitals overlay, and buttons (greet, demo stress, start/stop, quit). The main demo.
- `orchestrator.py`: headless. Greets you, then monitors vitals and reacts on its own.

ElevenLabs credentials enable voice; without them, Sayam prints its lines instead so the demo still runs.

## How It Was Built

A C++ vitals producer feeds a Python brain that drives the robot.

- **`vitals/` (C++):** a thin wrapper around the Presage SmartSpectra C++ SDK. It opens the camera by device index, runs the pipeline, and streams metrics to stdout as line-delimited JSON. Built with CMake and C++20.
- **`sayam/vitals_bridge.py`:** spawns the C++ binary, parses each JSON line into a `VitalsSample` (pulse, breathing, stress index, confidences).
- **`sayam/vision.py`:** OpenCV Haar-cascade face detection, the live overlay, and face aiming with a center deadzone so the robot only moves when you drift.
- **`sayam/liveliness.py`:** one roughly 30 Hz loop owns the head and antennas so nothing fights over the motors. Idle sway, quirks, smooth face-follow, and gestures (greet, concerned).
- **`sayam/control.py`:** serializes movement and voice behind one lock so actions never overlap.
- **`sayam/voice.py`:** ElevenLabs text-to-speech. WAV output is a paid tier, so we request MP3, transcode to WAV with ffmpeg (loudness-normalized), and play it through the robot speaker.
- **`sayam/orchestrator.py` / `live_view.py`:** the two entry points above.

## Tech Stack

| Component | Technology |
|---|---|
| Robot and movement | Reachy Mini, Reachy Mini Python SDK |
| Vitals and stress | Presage SmartSpectra C++ SDK (video to vitals) |
| Face detection | OpenCV Haar cascade |
| Voice | ElevenLabs text-to-speech, transcoded with ffmpeg |
| Brain | Python, with a C++20 vitals producer |

## Status

Built during the Presage Technologies Hackathon and actively in development.
