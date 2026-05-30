# Sayam — Your Study Companion on Reachy Mini

> A physical, vitals-aware study assistant that watches *how* you're doing — not just *what* you're doing — and steps in before burnout does.

Built for the **Presage Technologies Hackathon**.

---

## ✨ Inspiration

Everyone has a study setup. Almost no one has something watching out for *them* while they use it.

We've all had those late-night grind sessions where you're three hours deep, your heart is racing, your shoulders are at your ears, and you don't even notice you stopped absorbing anything an hour ago. Timers and to-do apps track tasks, but they're blind to the person doing them. They can't tell the difference between focused flow and quiet panic.

We wanted to build a companion that could — one that lives on your desk, *sees* you, *reads your body*, and actually cares when you're spiraling. The breakthrough was realizing that **Presage's video-to-vitals technology** meant we didn't need wearables or chest straps. A camera is enough. And **Reachy Mini** gave that camera a face, a voice, and a personality — turning a stream of biometric data into something that feels like a friend nudging you to breathe.

So we made **Sayam**: a robot that studies *with* you, notices when you're stressed, and knows when to tell you to take a break — or help you push through the problem in front of you.

---

## 🎯 What It Does

Sayam is a desktop study companion that combines **real-time vitals sensing**, **screen awareness**, and **conversational AI** into a single physical robot.

### 1. It reads how you're feeling — without any wearables
The **Reachy Mini camera** continuously streams video of you while you study. That feed is piped into the **Presage SDK**, which converts plain video into live vitals (e.g. heart rate) and signals of physiological stress.

When Sayam detects that your heart rate is climbing or that you look visibly stressed, it speaks up:

> *"Hey, your heart rate's been climbing for a while — you've earned a 5-minute break. Step away for a sec."*

It's proactive wellness, driven by your actual body, not a fixed Pomodoro clock.

### 2. It understands what you're working on
A companion **desktop app** monitors your screen and feeds that context into an LLM. So Sayam isn't guessing — it knows you're stuck on a calculus integral or a failing unit test.

### 3. It helps you when you ask
Say the wake word and ask for help. Sayam routes your screen context + question to the LLM and answers out loud, guiding you through the problem.

> **You:** *"Hey Sayam, I can't figure out why this function keeps returning undefined."*
> **Sayam:** *"Looks like you're returning inside the loop on line 12 — move it after..."*

### 4. It feels alive
All of Sayam's movement — head turns, nods, expressive gestures — runs through the **Reachy Mini SDK**, so check-ins land as a physical presence on your desk rather than a notification you'll ignore. Its voice is generated with **ElevenLabs** TTS for natural, warm speech.

---

## 🗣️ Talking to Sayam

Wake Sayam by saying:

- **"Hey Sayam"**
- **"Sayam"**

From there you can ask for help with whatever's on your screen, ask how you're doing, or just talk it through.

---

## 🧩 How It Works

```
┌─────────────────┐      video       ┌──────────────────┐     vitals/stress
│  Reachy Mini    │ ───────────────▶ │   Presage SDK    │ ──────────────────┐
│  Camera         │                  │ (video → vitals) │                   │
└─────────────────┘                  └──────────────────┘                   ▼
                                                                   ┌───────────────────┐
┌─────────────────┐   screen context                              │   Decision / LLM  │
│  Desktop App    │ ────────────────────────────────────────────▶ │   "Thinking"      │
│  (screen watch) │                                                │   layer           │
└─────────────────┘                                                └─────────┬─────────┘
                                                                              │
┌─────────────────┐   "Hey Sayam" / question                                 │ response
│  Voice / Wake   │ ─────────────────────────────────────────────────────────┤
│  Word           │                                                           ▼
└─────────────────┘                                              ┌─────────────────────────┐
                                                                 │  Reachy Mini SDK  +     │
                                                                 │  ElevenLabs TTS         │
                                                                 │  (movement + speech)    │
                                                                 └─────────────────────────┘
```

**The loop:**
1. Reachy Mini's camera captures the user studying.
2. The Presage SDK turns that video into live vitals and stress signals.
3. The desktop app captures on-screen context.
4. Vitals + screen context + voice requests flow into the LLM "thinking" layer.
5. Sayam responds — speaking through ElevenLabs and moving through the Reachy Mini SDK — either proactively (*"take a break"*) or on request (*"here's how to solve that"*).

---

## 🛠️ Tech Stack

| Component | Technology |
|---|---|
| **Robot platform & movement** | [Reachy Mini](https://www.pollen-robotics.com/) + Reachy Mini SDK |
| **Vitals & stress sensing** | [Presage Technologies](https://www.presagetech.com/) SDK (video → vitals) |
| **Camera input** | Reachy Mini onboard camera |
| **Screen awareness** | Desktop monitoring app |
| **Reasoning** | LLM-based "thinking" layer (screen context + vitals + voice) |
| **Voice (TTS)** | [ElevenLabs](https://elevenlabs.io/) |
| **Wake word** | "Hey Sayam" / "Sayam" |

---

## 🚀 Why It Matters

Productivity tools optimize output. Sayam optimizes *you*. By fusing contactless biometrics with screen context and a genuinely present physical companion, it closes the gap between "I'm working hard" and "I'm working well" — catching stress early, encouraging real breaks, and offering help exactly when you're stuck.

Healthier study sessions. Better focus. A companion that actually has your back.

---

## 📋 Status

🚧 Built during the Presage Technologies Hackathon — actively in development.
