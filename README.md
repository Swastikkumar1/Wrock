# PROJECT WROCK: Unified Spatial-AI & PC Automation Platform

[![Architecture: Multimodal Spatial-AI](https://img.shields.io/badge/Architecture-Spatial--AI-00e5ff.svg)](https://github.com)
[![Status: Operational](https://img.shields.io/badge/Status-Operational-00e676.svg)](https://github.com)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![TypeScript: 5.4+](https://img.shields.io/badge/TypeScript-5.4%2B-blue.svg)](https://www.typescriptlang.org)
[![Engine: Three.js](https://img.shields.io/badge/3D-Three.js-orange.svg)](https://threejs.org)

> **"Project Wrock"** is an end-to-end multimodal spatial computing AI assistant and Windows PC automation platform. It features a sleek **floating middle-bottom Arc-Reactor holographic dock** that stays on your screen, listens to every command, controls your PC, and switches seamlessly into **God's Eye satellite tactical map** with live **Drone/Target POV reconnaissance feeds** and **optical finger pinch-to-zoom/pan tracking**.

---

## 1. Core Architecture & Capabilities

```
                       [ SENSORY & AUTOMATION INPUT ]
                Webcam Feed (MediaPipe)        Microphone & Text Stream
                         │                                │
                         ▼                                ▼
              ┌──────────────────────┐         ┌───────────────────────┐
              │    HOLO-GESTURES     │         │     VOICE ENGINE      │
              │  21-Point Landmarks  │         │ Continuous STT Listen │
              │ Pinch-Zoom & Pan ML  │         │ Neural Speech Synth   │
              └──────────┬───────────┘         └──────────┬────────────┘
                         │ (pinch delta, pan, ray)        │ (user commands)
                         ▼                                ▼
      ┌───────────────────────────────────────────────────────────────┐
      │                 CENTRAL MULTIMODAL SYNCHRONIZER               │
      │        - Deictic Pronoun Resolver ("inspect this", "lock on") │
      │        - Low-Latency (<10ms) Event Bus & WebSocket Dispatcher │
      └───────────────────────────────┬───────────────────────────────┘
                                      │
                 ┌────────────────────┴────────────────────┐
                 ▼                                         ▼
  ┌─────────────────────────────┐           ┌─────────────────────────────┐
  │      PC AUTOMATION CORE     │           │      GOD'S EYE SPATIAL      │
  │ - Screenshot Capture & Open │           │ - 3D Tactical Satellite Map │
  │ - Volume Up / Down / Mute   │           │ - Live Drone/Target POV     │
  │ - CPU / RAM / Battery Stats │           │ - Optical Pinch-to-Zoom/Pan │
  │ - Lock Workstation Screen   │           │ - 360° Radar Sweep & Locks  │
  │ - Launch Apps (Chrome/Code) │           │ - Coordinate Anchors        │
  └──────────────┬──────────────┘           └──────────────┬──────────────┘
                 │                                         │
                 └────────────────────┬────────────────────┘
                                      ▼
             [ FLOATING MIDDLE-BOTTOM HOLOGRAPHIC INTERFACE ]
         ┌───────────────────────────────────────────────────────┐
         │ - Pulsating Arc-Reactor AI Core & Voice Waveform      │
         │ - Live Dialogue Ticker & Command Input                │
         │ - Instant Tactical God's Eye & POV Recon Window       │
         │ - Optical 21-Joint Glowing Finger Skeleton Tracker    │
         │ - Procedural Web Audio SFX & Neural TTS               │
         └───────────────────────────────────────────────────────┘
```

---

## 2. Clean Project Structure

```
WROCK/
├── backend/                               # Python FastAPI, Perception & PC Automation Engine
│   ├── config.py                          # Pydantic configuration & settings
│   ├── main.py                            # ASGI entrypoint & 30Hz telemetry WebSocket loop
│   ├── requirements.txt                   # FastAPI, Uvicorn, PyAutoGUI, Psutil, NumPy
│   ├── Dockerfile                         # Container configuration
│   ├── test_integration.py                # Regression test for Wrock pipelines
│   └── core/
│       ├── perception/
│       │   ├── gestures/                  # 3D hand tracking & gesture parser
│       │   │   ├── landmark_parser.py     # 21-point MediaPipe hand geometry
│       │   │   ├── gesture_classifier.py  # Pinch, grab, swipe, point, push
│       │   │   └── raycaster.py           # 3D spatial ray projection
│       │   └── spatial/                   # Scene localization & God's Eye view
│       │       ├── scene_graph.py         # 3D Spatial Scene Graph & entities
│       │       ├── entity_tracker.py      # Satellites, drones, and kinematics
│       │       └── tactical_observer.py   # EDITH camera modes (God's Eye, Orbital)
│       ├── intelligence/
│       │   └── jarvis/                    # Cognitive Engine (Wrock Persona)
│       │       ├── voice_engine.py        # Wake-word listener & streaming ASR/TTS
│       │       ├── tools.py               # PC automation + spatial tool registry
│       │       ├── memory.py              # Rolling dialogue turns
│       │       └── intent_router.py       # Context fusion, Grok/Claude routing
│       └── fusion/                        # Multimodal Synchronization Engine
│           ├── state_synchronizer.py      # Centralized PerceptionState bus
│           ├── deictic_resolver.py        # Matches voice with pointing reticle
│           └── event_bus.py               # Async WebSocket dispatcher
├── interface/
│   └── hud/                               # Holographic Spatial Frontend Client
│       ├── package.json                   # Vite, TypeScript, Three.js
│       ├── index.html                     # Tactical EDITH layout & screen-space brackets
│       └── src/
│           ├── main.ts                    # Master app coordinator & render loop
│           ├── style.css                  # Middle-bottom dock & holographic styling
│           ├── audio/                     # Sound synthesis & STT/TTS
│           ├── gestures/                  # Hand tracker with optical pinch zoom/pan
│           ├── spatial/                   # 3D tactical scene & entity kinematics
│           ├── hud/
│           │   ├── command_dock.ts        # Floating middle-bottom Arc-Reactor dock
│           │   ├── recon_pov.ts           # Live drone/target cockpit POV feed
│           │   ├── holographic_ui.ts      # Projected screen-space EDITH brackets
│           │   └── telemetry_overlay.ts   # Tactical manifest & diagnostics
│           └── network/
│               └── ws_client.ts           # WebSocket client
├── run.ps1                                # 1-Click launcher (Starts app in borderless window)
├── run.sh                                 # 1-Click launcher for Linux / macOS
├── docker-compose.yml                     # Multi-container deployment
├── requirements.txt                       # Python dependencies
└── .env.example                           # Template environment configuration
```

---

## 3. Quickstart: How to Launch

### On Windows (PowerShell):
```powershell
.\run.ps1
```
This automatically installs any dependencies, boots the backend on `http://localhost:8000`, and opens the holographic interface on `http://localhost:3000` (in a borderless native app window via Chrome or Edge if installed).

---

## 4. Interaction Guide

### 1. Voice & Command Input (Always Listening)
Speak naturally or type commands in the middle-bottom dock. Wrock responds with voice synthesis and executes actions:

#### PC Automation & Web Commands:
- *"Wrock, open reddit on chrome"* / *"open github"* / *"open chatgpt"* &rarr; Instantly launches designated website in Chrome.
- *"Wrock, go to chrome and search latest AI breakthroughs"* &rarr; Opens Google Chrome with active search.
- *"Wrock, in map search Tokyo"* / *"search Paris on map"* &rarr; Locks satellite coordinates on God's Eye 3D map and launches Google Maps recon.
- *"Wrock, search lo-fi beats in youtube"* / *"play interstellar on youtube"* &rarr; Searches and plays videos directly on YouTube.
- *"Wrock, search daft punk in spotify"* / *"play the weeknd on spotify"* &rarr; Launches Spotify search / playback.
- *"Wrock, take screenshot"* &rarr; Captures your full screen, saves to Pictures, and opens it.
- *"Wrock, volume up"* / *"Wrock, volume down"* / *"Wrock, mute"* &rarr; Controls Windows master volume.
- *"Wrock, system status"* / *"Wrock, battery"* &rarr; Reads live CPU load %, RAM %, and battery %.
- *"Wrock, lock PC"* &rarr; Instantly locks your Windows workstation.
- *"Wrock, open calculator"* / *"open notepad"* / *"open terminal"* / *"open cursor"* &rarr; Launches desktop apps.
- *"Wrock, close window"* &rarr; Closes active foreground window (Alt+F4).

#### Spatial & God's Eye POV Commands:
- *"Wrock, show God's eye"* or *"Wrock, open map"* &rarr; Shifts viewport to top-down 90° satellite tactical grid.
- *"Wrock, watch drone POV"* or *"Wrock, show me someone's POV in the map"* &rarr; Opens the live tactical cockpit reconnaissance feed tracking `DRONE-STARK-01` or `UAV-BOGEY-99`!
- *"Wrock, inspect this drone"* &rarr; Deictically inspects whichever entity you point at.
- *"Wrock, lock target"* or *"Wrock, lock bogey"* &rarr; Locks tracking reticles onto hostile signatures.
- *"Wrock, radar sweep"* &rarr; Triggers a 360° sector radar pulse.

---

### 2. Optical Finger Tracking: Pinch-to-Zoom & Pan
Click **`🖐️ PINCH GESTURES`** in the middle-bottom dock to turn on your webcam:
- **Pinch-To-Zoom**: Bring your thumb tip and index tip close together and move fingers closer/farther to zoom the God's Eye map in and out! A live readout `🖐️ PINCH ZOOM: 1.45x` will appear on the dock.
- **Pinch-To-Pan**: Pinch thumb and index together and move your hand across the screen to pan the tactical satellite map in real time!
- **Pointing**: Shoots a laser beam into 3D world space to inspect and lock onto drones and satellites.
- **Mouse Fallback**:
  - Scroll mouse wheel &rarr; Zooms the God's Eye map.
  - Click and drag &rarr; Pans the God's Eye map.
  - Left click &rarr; Pinches to select/lock entities.

---

### 3. Live POV Reconnaissance Feed
Click **`🛰️ GOD'S EYE & POV`** on the dock:
- Displays the top-down satellite map on the main screen.
- Simultaneously opens the **Live Tactical POV Recon Window** in the top-right.
- Features artificial horizon pitch ladder, airspeed/altitude tapes, compass heading, and target acquisition box.
- Switch POV anytime between:
  - `[ DRONE-01 ]` (Friendly Patrol Drone)
  - `[ BOGEY-99 ]` (Hostile Bogey)
  - `[ SAT-EDITH ]` (Orbital Reconnaissance Satellite)
- Switch sensor modes: `CYAN`, `FLIR GREEN`, or `THERMAL AMBER`.

---

## 5. Verification & Smoke Test

You can test all sensory, spatial, and PC automation pipelines anytime:
```powershell
python -m backend.test_integration
```
Output:
```
[1/4] Testing Gesture Pipeline...
 -> Detected Gesture: PINCH_START, pinch_dist=0.014
[2/4] Testing Spatial Scene Graph & Kinematics...
 -> Scene Entities: 5, Threats: 1
[3/4] Testing Deictic Resolver & Tools...
[4/4] Testing Multimodal Intent Routing ('Wrock, inspect this')...
 -> Spoken Response: Inspecting signature DRONE-STARK-01. Diagnostic telemetry streamed to HUD.
 -> Tools Called: ['inspect_entity']

[SUCCESS] All Core Wrock Spatial-AI Pipelines Operational!
```
