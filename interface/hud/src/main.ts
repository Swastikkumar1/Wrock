import * as THREE from "three";
import { GodsEyeScene } from "./spatial/gods_eye_scene";
import { WrockOrbVisualizer } from "./hud/wrock_orb";
import { HandTracker, LandmarkPoint } from "./gestures/hand_tracker";
import { GestureRecognizer } from "./gestures/gesture_recognizer";
import { VoiceController } from "./audio/voice_controller";
import { CommandDockManager } from "./hud/command_dock";
import { SpatialWebSocketClient } from "./network/ws_client";
import { sfx } from "./audio/sound_effects";
import { GestureData, CameraMode } from "./types";
import { CONFIG } from "./config";

class WrockApp {
  private canvas: HTMLCanvasElement;
  private scene: GodsEyeScene;
  private orbVisualizer: WrockOrbVisualizer;

  private handTracker: HandTracker;
  private gestureRecognizer: GestureRecognizer;
  private voiceController: VoiceController;
  private commandDock: CommandDockManager;
  private wsClient: SpatialWebSocketClient;

  // State
  private lastLandmarks: LandmarkPoint[] = [];
  private lastGestureData: GestureData = {
    gesture: "IDLE",
    confidence: 0,
    cursor: { x: 0.5, y: 0.5, z: 0 },
    pointing_ray: [0, 0, -1],
    pinch_distance: 1.0,
  };

  // Conversational Lifecycle State (Start active in LISTENING mode)
  private isAwake: boolean = true;
  private prevTwoHandDist: number | null = null;
  private clock: THREE.Clock;

  constructor() {
    this.canvas = document.getElementById("viewport-canvas") as HTMLCanvasElement;
    this.clock = new THREE.Clock();

    // 1. Initialize 3D Map Scene
    this.scene = new GodsEyeScene(this.canvas);
    this.scene.setCameraMode("GODS_EYE");

    this.orbVisualizer = new WrockOrbVisualizer();
    this.scene.scene.add(this.orbVisualizer.group);

    // 2. Initialize Interaction Subsystems
    this.handTracker = new HandTracker();
    this.gestureRecognizer = new GestureRecognizer();
    this.voiceController = new VoiceController();
    this.commandDock = new CommandDockManager();
    this.wsClient = new SpatialWebSocketClient();

    // Set initial ready state
    this.commandDock.setVoiceState("LISTENING");

    this.bindEvents();
    this.initWakeControls();

    // Automatically start webcam hand tracking for instant OS & map control
    this.autoStartHandTracking();

    // Automatically initialize voice listener
    this.autoStartVoice();

    // Global one-time interaction to unblock audio autoplay
    const triggerMicOnGesture = async () => {
      if (!this.voiceController.getListeningState() && this.voiceController.permissionState !== "denied") {
        await this.voiceController.startListening();
        this.commandDock.setMicButtonState(this.voiceController.getListeningState() ? "LISTENING" : "MUTED");
      }
      window.removeEventListener("click", triggerMicOnGesture);
      window.removeEventListener("keydown", triggerMicOnGesture);
    };
    window.addEventListener("click", triggerMicOnGesture);
    window.addEventListener("keydown", triggerMicOnGesture);

    // Start Master Render Loop
    this.renderLoop();
  }

  private async autoStartHandTracking() {
    try {
      await this.handTracker.startWebcam();
      const btnCam = document.getElementById("btn-toggle-cam");
      if (btnCam) btnCam.classList.add("glow-cyan");
    } catch (e) {
      console.log("Webcam ready for user trigger.");
    }
  }

  private async autoStartVoice() {
    try {
      const active = await this.voiceController.startListening();
      if (active) {
        this.commandDock.setMicButtonState("LISTENING");
      } else {
        this.commandDock.setMicButtonState(this.voiceController.permissionState === "denied" ? "BLOCKED" : "MUTED");
      }
    } catch (e) {
      console.log("Voice ready for user interaction.");
      this.commandDock.setMicButtonState("MUTED");
    }
  }


  private bindEvents() {
    // 1. Real Multi-Hand Tracking (Forward to OS Gesture Engine & 3D Scene)
    this.handTracker.onLandmarksCallback = (
      landmarks: LandmarkPoint[],
      multiHands?: LandmarkPoint[][],
      handedness?: string[]
    ) => {
      this.lastLandmarks = landmarks;
      this.lastGestureData = this.gestureRecognizer.processLandmarks(landmarks);

      // A. Multi-Hand Zoom (when two hands are detected in camera frame)
      let handledZoom = false;
      if (multiHands && multiHands.length >= 2 && multiHands[0].length > 8 && multiHands[1].length > 8) {
        const h1 = multiHands[0][8];
        const h2 = multiHands[1][8];
        const twoHandDist = Math.hypot(h1.x - h2.x, h1.y - h2.y);

        if (this.prevTwoHandDist !== null) {
          const delta = twoHandDist - this.prevTwoHandDist;
          if (Math.abs(delta) > 0.003) {
            const factor = 1.0 + delta * 2.2;
            const currentZoom = this.scene.adjustZoom(factor);
            this.commandDock.setPinchZoomIndicator(currentZoom, true);
            handledZoom = true;
          }
        }
        this.prevTwoHandDist = twoHandDist;
      } else {
        this.prevTwoHandDist = null;
      }

      // B. Single-Hand Continuous Pinch-To-Zoom (pinch-out -> zoom in, pinch-in -> zoom out)
      const isPinch =
        this.lastGestureData.gesture === "PINCH_HOLD" ||
        this.lastGestureData.gesture === "PINCH_START";

      if (isPinch) {
        if (!handledZoom && this.lastGestureData.pinch_zoom_delta && Math.abs(this.lastGestureData.pinch_zoom_delta) > 0.002) {
          const factor = 1.0 + this.lastGestureData.pinch_zoom_delta * 0.32;
          const currentZoom = this.scene.adjustZoom(factor);
          this.commandDock.setPinchZoomIndicator(currentZoom, true);
          handledZoom = true;
        } else if (!handledZoom) {
          this.commandDock.setPinchZoomIndicator(this.scene.zoomLevel, true);
        }

        // Optical pinch-to-pan for map
        if (this.lastGestureData.pan_delta) {
          const { dx, dy } = this.lastGestureData.pan_delta;
          if (Math.abs(dx) > 0.001 || Math.abs(dy) > 0.001) {
            this.scene.adjustPan(dx, dy);
          }
        }
      } else if (!handledZoom) {
        this.commandDock.setPinchZoomIndicator(this.scene.zoomLevel, false);
      }

      // Stream landmarks (multi-hand if present, else primary) to backend OS gesture controller
      if (multiHands && multiHands.length > 0) {
        this.wsClient.sendHandLandmarks(multiHands, handedness || ["Right", "Left"]);
      } else {
        this.wsClient.sendHandLandmarks(landmarks, handedness?.[0] || "Right");
      }
    };

    // Wheel zoom as shortcut
    this.handTracker.onWheelZoomCallback = (factor: number) => {
      const z = this.scene.adjustZoom(factor);
      this.commandDock.setPinchZoomIndicator(z, true);
      setTimeout(() => this.commandDock.setPinchZoomIndicator(z, false), 1200);
    };

    // 2. Voice Controller Callbacks
    this.voiceController.onTranscriptCallback = (transcript: string, isFinal: boolean) => {
      this.commandDock.setUserTranscript(transcript, !isFinal);

      if (isFinal) {
        const text = transcript.trim();
        if (!text) return;

        // Process directly through handleCommand so both voice & typed directives
        // execute identical high-speed command routing, auto-wake, and instant interrupt logic
        this.handleCommand(text);
      } else {
        // Stream interim transcript for visual feedback
        this.wsClient.sendVoiceTranscript(transcript, false, false);
      }
    };

    // INSTANT SPEECH INTERRUPTION ("BARGE-IN"):
    this.voiceController.onBargeInCallback = (spokenInterruption: string) => {
      console.log("Barge-in on client:", spokenInterruption);
      this.wsClient.sendSpeechInterrupt("client_barge_in");
      this.commandDock.setVoiceState("LISTENING");
    };

    this.voiceController.onStateChangeCallback = (isListening: boolean, isSpeaking: boolean) => {
      this.orbVisualizer.setVoiceState(isListening, isSpeaking);
      const state = isSpeaking
        ? "SPEAKING"
        : isListening
        ? this.isAwake
          ? "LISTENING"
          : "SLEEPING"
        : "IDLE";
      this.commandDock.setVoiceState(state);
      this.commandDock.setMicButtonState(isListening ? "LISTENING" : "MUTED");
    };

    this.voiceController.onAudioLevelCallback = (volume: number, freqData: any) => {
      this.commandDock.updateAudioBarsWithFrequency(freqData, volume);
    };

    this.voiceController.onErrorCallback = (errorMsg: string, isPermissionError: boolean) => {
      if (isPermissionError) {
        this.commandDock.setMicButtonState("BLOCKED");
        this.commandDock.setVoiceState("BLOCKED");
        this.commandDock.setWrockResponse(errorMsg);
      } else {
        console.warn("Voice controller warning:", errorMsg);
      }
    };

    // 3. Command Dock Actions
    this.commandDock.onCommandSubmit = (cmd: string) => {
      this.commandDock.setUserTranscript(cmd, false);
      if (!this.isAwake) {
        this.wakeUpWrock();
      }
      this.handleCommand(cmd);
    };

    this.commandDock.onToggleGodsEye = () => {
      this.scene.resetPanAndZoom();
      this.scene.setCameraMode("GODS_EYE");
      this.speak("God's Eye map centered.");
    };

    this.commandDock.onToggleCam = async () => {
      const active = await this.handTracker.toggleWebcam();
      const btnCam = document.getElementById("btn-toggle-cam");
      if (btnCam) btnCam.classList.toggle("glow-cyan", active);
      sfx.playHoverSound();
    };

    this.commandDock.onToggleMic = async () => {
      const active = await this.voiceController.toggleListening();
      this.commandDock.setMicButtonState(
        active ? "LISTENING" : this.voiceController.permissionState === "denied" ? "BLOCKED" : "MUTED"
      );
      sfx.playSelectSound();
    };

    // 4. WebSocket Backend Events
    this.wsClient.onConnectionStateChange = (online: boolean) => {
      const statusPill = document.getElementById("hud-conn-status");
      if (statusPill) {
        statusPill.className = online ? "status-indicator-pill" : "status-indicator-pill reconnecting";
        statusPill.querySelector(".status-label")!.textContent = online ? "ONLINE" : "OFFLINE";
      }
    };

    this.wsClient.onVoiceIntentCallback = (event) => {
      if (event.spoken_text) {
        this.commandDock.setWrockResponse(event.spoken_text);
      }
      if (event.camera_mode) {
        this.scene.setCameraMode(event.camera_mode);
      }
    };

    // ElevenLabs High-Quality Speech & Audio Delivery
    this.wsClient.onAssistantSpeechCallback = (payload) => {
      if (payload.text) {
        this.commandDock.setWrockResponse(payload.text);
      }
      if (payload.play_chime) {
        sfx.playWakeChime();
      }
      if (payload.audio_base64) {
        this.voiceController.playBase64Audio(payload.audio_base64);
      } else if (payload.text) {
        this.voiceController.speak(payload.text);
      }
    };

    this.wsClient.onSpeechInterruptedCallback = () => {
      this.voiceController.abortSpeech();
      this.commandDock.setVoiceState(this.isAwake ? "LISTENING" : "SLEEPING");
    };

    this.wsClient.onLifecycleStateCallback = (payload) => {
      this.isAwake = payload.is_awake;
      if (payload.state) {
        this.commandDock.setVoiceState(payload.state as any);
      }
    };

    this.wsClient.onOsGestureCallback = (payload) => {
      console.log("OS Gesture Executed:", payload.gesture);
      const indicator = document.getElementById("dock-pinch-indicator");
      if (indicator && payload.gesture) {
        indicator.classList.add("active");
        indicator.innerHTML = `🖐️ OS ACTION: <strong>${payload.gesture}</strong>`;
        setTimeout(() => indicator.classList.remove("active"), 1500);
      }
    };

    // PC Controls Close Button
    const btnClosePc = document.getElementById("btn-close-pc-menu");
    const pcMenu = document.getElementById("pc-controls-menu");
    if (btnClosePc && pcMenu) {
      btnClosePc.addEventListener("click", () => pcMenu.classList.remove("open"));
    }
  }

  private initWakeControls() {
    const wakeAction = () => {
      this.wakeUpWrock();
    };

    const wakeBtn = document.getElementById("btn-wake-toggle");
    if (wakeBtn) wakeBtn.addEventListener("click", wakeAction);

    const reactorWrapper = document.getElementById("reactor-trigger-wrapper");
    if (reactorWrapper) reactorWrapper.addEventListener("click", wakeAction);
  }

  public async wakeUpWrock() {
    this.isAwake = true;
    sfx.playWakeChime();
    this.commandDock.setVoiceState("LISTENING");
    const wakeMsg = "Yes, I am online. What's your command, Swastik?";
    this.commandDock.setWrockResponse(wakeMsg);

    // Notify backend WebSocket that assistant is awake
    if (this.wsClient.getIsConnected()) {
      this.wsClient.sendVoiceWake();
    } else {
      this.voiceController.speak(wakeMsg);
    }

    const active = await this.voiceController.startListening();
    this.commandDock.setMicButtonState(active ? "LISTENING" : "MUTED");
  }

  public putToSleep() {
    this.isAwake = false;
    this.commandDock.setVoiceState("SLEEPING");
    const dismissMsg = "Standing by.";
    this.commandDock.setWrockResponse(dismissMsg);
    this.voiceController.speak(dismissMsg);

    // Notify backend WebSocket that assistant is asleep
    this.wsClient.sendVoiceDismiss();
  }

  private handleCommand(cmd: string) {
    const raw = cmd.trim();
    if (!raw) return;
    const u = raw.toLowerCase();

    // Check for explicit dismiss / sleep commands
    if (
      u.includes("go to sleep") ||
      u === "sleep" ||
      u.includes("dismiss") ||
      u.includes("stand by") ||
      u.includes("stop listening")
    ) {
      this.putToSleep();
      if (this.wsClient.getIsConnected()) {
        this.wsClient.sendCommand("dismiss");
      }
      return;
    }

    // -------------------------------------------------------------
    // WAKE-WORD & AUTO-WAKE DETECTION
    // Matches variations like "wake up", "wake up block", "wake up wrock", "hey wrock"
    // -------------------------------------------------------------
    const isWakePhrase =
      /\bwake\s+up\b/i.test(u) ||
      /\b(?:hey|hi|hello|ok|okay)\s+(?:wrock|rock|brok|block|lock|jarvis)\b/i.test(u) ||
      /\b(?:wrock|rock|brok|block|jarvis)\s+wake\s+up\b/i.test(u) ||
      /\b(wrock|jarvis)\b/i.test(u);

    const hasActionableIntent =
      /\b(how|what|who|why|where|hello|hi|hey|open|launch|start|screenshot|status|laptop|battery|cpu|gpu|temp|temperature|volume|mute|unmute|lock|spotify|youtube|chrome|cursor|vscode|reddit|search|find|locate|close|kill|turn\s+off|yes|do it|sure|zoom|map|maps|google|inspect|look\s+at)\b/i.test(u) ||
      /\b(?:i\s+(?:said|told|asked))\b/i.test(u);

    // Instant stop check even if asleep or thinking
    const isStopWord = /^\s*(?:please\s+)?(?:stop(?:\s+it|\s+that|\s+talking|\s+now)?|shut\s+up|silence|quiet|cancel|hold\s+on|pause|ruk\s+jao|bas\s+karo)\s*$/i.test(u);
    if (isStopWord) {
      this.voiceController.abortSpeech();
      this.wsClient.sendSpeechInterrupt("user_command");
      this.commandDock.setVoiceState("LISTENING");
      this.commandDock.setWrockResponse("Stopped.");
      return;
    }

    if (!this.isAwake) {
      if (isWakePhrase || hasActionableIntent) {
        this.wakeUpWrock();
        const commandAfterWake = u
          .replace(/^.*?\b(?:wake\s+up(?:\s+(?:wrock|rock|brok|block|lock|jarvis))?|(?:hey|hi|hello|ok|okay)\s+(?:wrock|rock|brok|block|jarvis))\b[,:\s]*/i, "")
          .trim();
        const finalCmd = commandAfterWake || (hasActionableIntent ? u : "");
        if (finalCmd) {
          this.handleCommand(finalCmd);
        }
      }
      return;
    }

    // Assistant is awake: process command directly without needing repeat wake-words
    this.commandDock.setVoiceState("THINKING");

    // Clean optional wake-word prefixes
    const cleaned = u.replace(/^(hey\s+)?(wake\s+up\s+)?(wrock|rock|brok|block|jarvis)\b[,:\s]*/i, "").trim();
    const targetCmd = cleaned || u;

    // Handle instant interrupt words
    if (/^\s*(?:please\s+)?(?:stop(?:\s+it|\s+that|\s+talking|\s+now)?|shut\s+up|silence|quiet|cancel|hold\s+on|pause|ruk\s+jao|bas\s+karo)\s*$/i.test(targetCmd)) {
      this.voiceController.abortSpeech();
      this.wsClient.sendSpeechInterrupt("user_command");
      this.commandDock.setVoiceState("LISTENING");
      this.commandDock.setWrockResponse("Stopped.");
      return;
    }

    // 1. Direct Map Controls (instant client viewport update + notify backend)
    if (targetCmd.includes("zoom in") || targetCmd.includes("closer")) {
      const z = this.scene.adjustZoom(1.3);
      this.speak(`Zooming in. Scale is ${z.toFixed(2)}x.`);
      if (this.wsClient.getIsConnected()) this.wsClient.sendMapPinchZoom(1.3);
      return;
    }
    if (targetCmd.includes("zoom out") || targetCmd.includes("wider")) {
      const z = this.scene.adjustZoom(0.75);
      this.speak(`Zooming out. Scale is ${z.toFixed(2)}x.`);
      if (this.wsClient.getIsConnected()) this.wsClient.sendMapPinchZoom(0.75);
      return;
    }
    if (targetCmd.includes("reset map") || targetCmd.includes("center map")) {
      this.scene.resetPanAndZoom();
      this.speak("Map centered.");
      return;
    }

    // 2. Send to Backend Asynchronously (Backend handles intent routing & voice output without duplicate client synthesis)
    if (this.wsClient.getIsConnected()) {
      this.wsClient.sendCommand(targetCmd);
      this.wsClient.sendVoiceTranscript(targetCmd, true, true);
    } else {
      this.executeFallback(targetCmd);
    }
  }

  private async executeFallback(cmd: string) {
    const u = cmd.toLowerCase();

    // 1. Try REST HTTP endpoint
    try {
      const res = await fetch(`${CONFIG.HTTP_API_URL}/api/voice/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd, is_final: true }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data && (data.reply || data.spoken_text)) {
          this.speak(data.reply || data.spoken_text);
          return;
        }
      }
    } catch (e) {
      // Backend HTTP endpoint not yet reachable
    }

    // 2. Instant Local Intelligent Persona Fallback
    if (u.includes("how are you") || u.includes("how are u") || u.includes("how r u") || u.includes("kese ho") || u.includes("kaise ho")) {
      this.speak("All systems online and ready, Swastik. What would you like to do?");
    } else if (u.includes("who are you") || u.includes("what is your name") || u.includes("tum kaun")) {
      this.speak("I am Wrock, your autonomous Spatial-AI assistant, Swastik.");
    } else if (u.includes("what can you do") || u.includes("features") || u.includes("help")) {
      this.speak("I control applications, monitor system health, take screenshots, manage volume, and navigate the 3D map. What shall we do, Swastik?");
    } else if (u.includes("hello") || u.includes("hey") || u.includes("hi") || u.includes("namaste")) {
      this.speak("Hello Swastik! Standing by for your directive.");
    } else if (u.includes("thank you") || u.includes("thanks")) {
      this.speak("Always at your service, Swastik.");
    } else {
      this.speak("Reconnecting to backend intelligence core... Standing by.");
    }
  }

  private speak(text: string) {
    this.commandDock.setWrockResponse(text);
    this.voiceController.speak(text);
  }

  private renderLoop = () => {
    requestAnimationFrame(this.renderLoop);

    const dt = this.clock.getDelta();
    const elapsedTime = this.clock.getElapsedTime();

    // Update 3D Map
    this.scene.update(dt);
    this.orbVisualizer.update(elapsedTime);

    // Render Scene
    this.scene.render();
  };
}

// Start app on DOM load
window.addEventListener("DOMContentLoaded", () => {
  new WrockApp();
});
