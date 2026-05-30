# Sayam Vitals Producer (C++)

A thin wrapper around the **Presage SmartSpectra C++ SDK** that turns a camera
feed into vitals and streams them as **line-delimited JSON on stdout**, so the
Python Sayam brain can read them from a subprocess pipe.

```
camera ──▶ sayam_vitals (C++ / SmartSpectra) ──JSON lines──▶ vitals_bridge.py ──▶ Sayam brain
```

## Output format (stdout)

One JSON object per line:

```json
{"type":"metrics","ts":1717000000000,"data":{ ...full Presage metrics... }}
{"type":"status","ts":1717000000000,"code":0,"hint":"Face detected"}
{"type":"error","message":"see stderr"}
```

Human-readable logs go to **stderr** and can be ignored by the parser.

## Prerequisites

- macOS Apple Silicon 14.0+ (this machine)
- SmartSpectra SDK installed via Homebrew (see repo root setup)
- CMake 3.22.1+ and a C++20 compiler (provided by the Command Line Tools)
- A Presage API key: https://physiology.presagetech.com/auth/login

## Build

```bash
cd vitals
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

## Run

```bash
# key via flag
./build/sayam_vitals --api_key=YOUR_KEY

# key via env
export SMARTSPECTRA_API_KEY=YOUR_KEY
./build/sayam_vitals

# pick a non-default camera (e.g. the Reachy Mini camera)
./build/sayam_vitals --camera_device_index=1

# test offline from a recorded clip
./build/sayam_vitals --input_video_path=clip.mp4
```

Then point the Python bridge at the binary:

```bash
cd ../sayam
SMARTSPECTRA_API_KEY=YOUR_KEY python -m sayam.vitals_bridge --binary ../vitals/build/sayam_vitals
```
