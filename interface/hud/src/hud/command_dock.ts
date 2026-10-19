import { sfx } from "../audio/sound_effects";

export class CommandDockManager {
  private dockEl: HTMLElement | null = null;
  private reactorCanvas: HTMLCanvasElement | null = null;
  private reactorCtx: CanvasRenderingContext2D | null = null;
  private statusBadge: HTMLElement | null = null;
  private userTranscriptEl: HTMLElement | null = null;
  private wrockResponseEl: HTMLElement | null = null;
  private audioBarsContainer: HTMLElement | null = null;
  private pcMenuEl: HTMLElement | null = null;
  private cmdInput: HTMLInputElement | null = null;
  private btnMic: HTMLElement | null = null;

  public onCommandSubmit: ((cmd: string) => void) | null = null;
  public onToggleGodsEye: (() => void) | null = null;
  public onToggleCam: (() => void) | null = null;
  public onToggleMic: (() => void) | null = null;
  public onToggleFullscreen: (() => void) | null = null;

  private animStep: number = 0;
  private isSpeaking: boolean = false;
  private isListening: boolean = false;
  private currentState: "IDLE" | "LISTENING" | "THINKING" | "SPEAKING" | "BLOCKED" = "IDLE";
  private lastLiveVolume: number = 0;
  private lastFreqData: any = null;

  constructor() {
    this.dockEl = document.getElementById("middle-bottom-dock");
    this.reactorCanvas = document.getElementById("dock-arc-reactor") as HTMLCanvasElement;
    if (this.reactorCanvas) {
      this.reactorCtx = this.reactorCanvas.getContext("2d");
    }
    this.statusBadge = document.getElementById("dock-voice-status");
    this.userTranscriptEl = document.getElementById("dock-user-transcript");
    this.wrockResponseEl = document.getElementById("dock-wrock-response");
    this.audioBarsContainer = document.getElementById("dock-audio-bars");
    this.pcMenuEl = document.getElementById("pc-controls-menu");
    this.cmdInput = document.getElementById("dock-cmd-input") as HTMLInputElement;
    this.btnMic = document.getElementById("btn-dock-mic");

    this.initEventListeners();
    this.initAudioBars();
    this.startReactorAnimation();
  }

  private initEventListeners() {
    // Quick Trigger: God's Eye & POV Map
    const btnGodsEye = document.getElementById("btn-toggle-gods-eye");
    if (btnGodsEye) {
      btnGodsEye.addEventListener("click", () => {
        sfx.playSelectSound();
        if (this.onToggleGodsEye) this.onToggleGodsEye();
      });
    }

    // Quick Trigger: Hand Cam
    const btnCam = document.getElementById("btn-toggle-cam");
    if (btnCam) {
      btnCam.addEventListener("click", () => {
        sfx.playSelectSound();
        if (this.onToggleCam) this.onToggleCam();
      });
    }

    // Quick Trigger: Mic
    if (this.btnMic) {
      this.btnMic.addEventListener("click", () => {
        sfx.playSelectSound();
        if (this.onToggleMic) this.onToggleMic();
      });
    }

    // Quick Trigger: Cockpit / Fullscreen toggle
    const btnCockpit = document.getElementById("btn-toggle-cockpit");
    if (btnCockpit) {
      btnCockpit.addEventListener("click", () => {
        sfx.playSelectSound();
        if (this.onToggleFullscreen) this.onToggleFullscreen();
      });
    }

    // PC Controls Menu Toggle
    const btnPc = document.getElementById("btn-toggle-pc-menu");
    if (btnPc && this.pcMenuEl) {
      btnPc.addEventListener("click", () => {
        sfx.playHoverSound();
        this.pcMenuEl!.classList.toggle("open");
      });
    }

    // PC Action Buttons inside popup
    document.querySelectorAll(".pc-action-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const cmd = (e.currentTarget as HTMLElement).dataset.cmd;
        if (cmd && this.onCommandSubmit) {
          sfx.playSelectSound();
          this.onCommandSubmit(cmd);
          if (this.pcMenuEl) this.pcMenuEl.classList.remove("open");
        }
      });
    });

    // Command Input Submission (Enter key or Send button)
    const btnSend = document.getElementById("btn-dock-send");
    const handleSend = () => {
      if (this.cmdInput && this.cmdInput.value.trim()) {
        const text = this.cmdInput.value.trim();
        this.cmdInput.value = "";
        sfx.playSelectSound();
        if (this.onCommandSubmit) {
          this.onCommandSubmit(text);
        }
      }
    };

    if (btnSend) {
      btnSend.addEventListener("click", handleSend);
    }
    if (this.cmdInput) {
      this.cmdInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          handleSend();
        }
      });
    }
  }

  private initAudioBars() {
    if (!this.audioBarsContainer) return;
    this.audioBarsContainer.innerHTML = "";
    for (let i = 0; i < 12; i++) {
      const bar = document.createElement("div");
      bar.className = "equalizer-bar";
      bar.style.height = "6px";
      this.audioBarsContainer.appendChild(bar);
    }
  }

  public updateAudioBarsWithFrequency(freqData: any, volume: number) {
    this.lastLiveVolume = volume;
    this.lastFreqData = freqData;
  }

  public setMicButtonState(status: "LISTENING" | "MUTED" | "BLOCKED" | "STARTING" | "UNSUPPORTED") {
    if (!this.btnMic) return;

    this.btnMic.className = "dock-action-pill";
    if (status === "LISTENING") {
      this.btnMic.classList.add("glow-cyan");
      this.btnMic.innerHTML = `<span class="pill-icon">🎙️</span> <span class="pill-text">MIC ACTIVE</span>`;
      this.btnMic.title = "Microphone listening. Click to mute.";
      this.isListening = true;
    } else if (status === "MUTED") {
      this.btnMic.innerHTML = `<span class="pill-icon">🎙️</span> <span class="pill-text">ENABLE MIC</span>`;
      this.btnMic.title = "Click to turn on microphone & voice commands.";
      this.isListening = false;
    } else if (status === "BLOCKED") {
      this.btnMic.classList.add("glow-crimson");
      this.btnMic.innerHTML = `<span class="pill-icon">⚠️</span> <span class="pill-text">ALLOW MIC</span>`;
      this.btnMic.title = "Microphone blocked in browser. Click to retry or allow in browser settings.";
      this.isListening = false;
    } else if (status === "STARTING") {
      this.btnMic.classList.add("glow-amber");
      this.btnMic.innerHTML = `<span class="pill-icon">🎙️</span> <span class="pill-text">CONNECTING...</span>`;
    } else {
      this.btnMic.innerHTML = `<span class="pill-icon">🎙️</span> <span class="pill-text">NO SPEECH API</span>`;
      this.btnMic.title = "Speech recognition not supported in this browser. Please use Chrome or Edge.";
      this.isListening = false;
    }
  }

  public setVoiceState(state: "IDLE" | "SLEEPING" | "LISTENING" | "THINKING" | "SPEAKING" | "BLOCKED") {
    this.currentState = state === "SLEEPING" ? "IDLE" : state;
    if (this.statusBadge) {
      this.statusBadge.className = `voice-status-pill status-${state.toLowerCase()}`;
      if (state === "LISTENING") {
        this.statusBadge.innerHTML = `<span class="pulse-dot"></span> LIVE // LISTENING`;
      } else if (state === "THINKING") {
        this.statusBadge.innerHTML = `<span class="pulse-dot amber"></span> EXECUTING TASK...`;
      } else if (state === "SPEAKING") {
        this.statusBadge.innerHTML = `<span class="pulse-dot emerald"></span> SPEAKING (BARGE-IN READY)`;
      } else if (state === "BLOCKED") {
        this.statusBadge.innerHTML = `<span class="pulse-dot crimson"></span> MIC PERMISSION NEEDED`;
      } else {
        this.statusBadge.innerHTML = `<span class="pulse-dot idle"></span> ASLEEP (SAY "WAKE UP WROCK")`;
      }
    }
  }

  public setUserTranscript(text: string, isInterim: boolean = false) {
    if (this.userTranscriptEl) {
      if (text) {
        if (isInterim) {
          this.userTranscriptEl.innerHTML = `<span style="color:#00e5ff; font-weight:700;">🎙️ Hearing:</span> "${text}..."`;
        } else {
          this.userTranscriptEl.innerHTML = `<strong>Swastik:</strong> "${text}"`;
        }
      } else {
        this.userTranscriptEl.innerText = 'Listening for your command (e.g. "Take screenshot", "Show Gods eye")...';
      }
    }
  }

  public setWrockResponse(text: string) {
    if (this.wrockResponseEl) {
      this.wrockResponseEl.innerText = text ? `Wrock: "${text}"` : "Standing by for Swastik's command.";
    }
  }

  public setPinchZoomIndicator(zoomLevel: number, isPinching: boolean) {
    const indicator = document.getElementById("dock-pinch-indicator");
    if (indicator) {
      if (isPinching) {
        indicator.classList.add("active");
        indicator.innerHTML = `🖐️ PINCH ZOOM: <strong>${zoomLevel.toFixed(2)}x</strong>`;
      } else {
        indicator.classList.remove("active");
      }
    }
  }

  private startReactorAnimation() {
    const animate = () => {
      this.animStep += 0.05;

      // Draw Arc-Reactor core
      if (this.reactorCtx && this.reactorCanvas) {
        const ctx = this.reactorCtx;
        const w = (this.reactorCanvas.width = 64);
        const h = (this.reactorCanvas.height = 64);
        ctx.clearRect(0, 0, w, h);

        const cx = w * 0.5;
        const cy = h * 0.5;

        // Outer rotating segmented ring
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(this.animStep);

        const isAmber = this.currentState === "THINKING";
        const ringColor = isAmber ? "#ffb300" : "#00e5ff";
        ctx.strokeStyle = ringColor;
        ctx.lineWidth = 2.5;

        for (let i = 0; i < 6; i++) {
          const angle = (i * Math.PI) / 3;
          ctx.beginPath();
          ctx.arc(0, 0, 26, angle, angle + Math.PI / 4.5);
          ctx.stroke();
        }
        ctx.restore();

        // Inner reverse rotating core
        ctx.save();
        ctx.translate(cx, cy);
        ctx.rotate(-this.animStep * 1.5);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.7)";
        ctx.lineWidth = 1.5;
        for (let i = 0; i < 4; i++) {
          const angle = (i * Math.PI) / 2;
          ctx.beginPath();
          ctx.arc(0, 0, 16, angle, angle + Math.PI / 3);
          ctx.stroke();
        }
        ctx.restore();

        // Central pulsating energy core
        const pulse = Math.sin(this.animStep * 3) * 3;
        const coreRad = Math.max(4, 9 + pulse);
        const grad = ctx.createRadialGradient(cx, cy, 2, cx, cy, coreRad + 6);
        grad.addColorStop(0, "#ffffff");
        grad.addColorStop(0.5, ringColor);
        grad.addColorStop(1, "transparent");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(cx, cy, coreRad + 6, 0, Math.PI * 2);
        ctx.fill();
      }

      // Animate audio equalizer bars with REAL frequency analysis or TTS rhythm
      if (this.audioBarsContainer) {
        const bars = this.audioBarsContainer.children;
        const isSpeaking = this.currentState === "SPEAKING";
        const isListening = this.currentState === "LISTENING";

        for (let i = 0; i < bars.length; i++) {
          const bar = bars[i] as HTMLElement;

          if (isSpeaking) {
            // Speaking rhythm
            const h = Math.floor(Math.sin(this.animStep * 6 + i * 0.8) * 11 + 14);
            bar.style.height = `${Math.max(5, h)}px`;
            bar.style.background = "#00e676";
            bar.style.boxShadow = "0 0 8px rgba(0, 230, 118, 0.6)";
          } else if (isListening && this.lastFreqData && this.lastLiveVolume > 4) {
            // Real physical microphone frequencies!
            const binIdx = Math.min(Math.floor((i / bars.length) * this.lastFreqData.length), this.lastFreqData.length - 1);
            const amp = this.lastFreqData[binIdx];
            const liveH = Math.max(5, Math.floor((amp / 255) * 30) + 5);
            bar.style.height = `${liveH}px`;
            bar.style.background = amp > 90 ? "#00e5ff" : "rgba(0, 229, 255, 0.7)";
            bar.style.boxShadow = amp > 90 ? "0 0 8px rgba(0, 229, 255, 0.7)" : "none";
          } else if (isListening) {
            // Calm resting listener wave
            const restingH = Math.floor(Math.sin(this.animStep * 2 + i * 0.4) * 2 + 6);
            bar.style.height = `${Math.max(4, restingH)}px`;
            bar.style.background = "rgba(0, 229, 255, 0.45)";
            bar.style.boxShadow = "none";
          } else {
            // Idle / Muted
            bar.style.height = "4px";
            bar.style.background = "rgba(0, 229, 255, 0.2)";
            bar.style.boxShadow = "none";
          }
        }
      }

      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }
}
