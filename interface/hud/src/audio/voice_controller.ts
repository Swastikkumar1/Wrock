import { sfx } from "./sound_effects";
import { CONFIG } from "../config";

export class VoiceController {
  private recognition: any = null;
  private isListening: boolean = false;
  private isSpeaking: boolean = false;
  private isStarting: boolean = false;
  private synth: SpeechSynthesis | null = null;
  private preferredVoice: SpeechSynthesisVoice | null = null;
  private currentAudioElement: HTMLAudioElement | null = null;
  private lastSpokenText: string = "";
  private currentUtterance: SpeechSynthesisUtterance | null = null;
  private speechSafetyTimer: any = null;

  // Real Web Audio API microphone stream & frequency analyser
  private audioStream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private freqData: any = null;
  private audioLoopId: number | null = null;
  private restartTimer: any = null;

  public permissionState: "prompt" | "granted" | "denied" | "unsupported" = "prompt";

  // Public Callbacks
  public onTranscriptCallback: ((transcript: string, isFinal: boolean) => void) | null = null;
  public onStateChangeCallback: ((isListening: boolean, isSpeaking: boolean) => void) | null = null;
  public onAudioLevelCallback: ((volume: number, freqData: any) => void) | null = null;
  public onErrorCallback: ((errorMsg: string, isPermissionError: boolean) => void) | null = null;
  public onBargeInCallback: ((spokenInterruption: string) => void) | null = null;

  constructor() {
    this.synth = window.speechSynthesis || null;
    this.initVoices();
    this.initSpeechRecognition();
  }

  private initVoices() {
    if (!this.synth) return;
    const updateVoices = () => {
      const voices = this.synth!.getVoices();
      if (!voices || voices.length === 0) return;

      const isExplicitFemale = (v: SpeechSynthesisVoice) => {
        const n = v.name.toLowerCase();
        return (
          n.includes("female") ||
          n.includes("zira") ||
          n.includes("jenny") ||
          n.includes("aria") ||
          n.includes("susan") ||
          n.includes("hazel") ||
          n.includes("heera") ||
          n.includes("victoria") ||
          n.includes("samantha") ||
          n.includes("karen") ||
          n.includes("catherine") ||
          n.includes("linda")
        );
      };

      const isMaleVoice = (v: SpeechSynthesisVoice) => {
        if (isExplicitFemale(v)) return false;
        const n = v.name.toLowerCase();
        return (
          n.includes("male") ||
          n.includes("george") ||
          n.includes("ryan") ||
          n.includes("guy") ||
          n.includes("david") ||
          n.includes("mark") ||
          n.includes("daniel") ||
          n.includes("oliver") ||
          n.includes("arthur") ||
          n.includes("james") ||
          n.includes("christopher") ||
          n.includes("eric") ||
          n.includes("brian") ||
          n.includes("alex") ||
          n.includes("uk english male")
        );
      };

      // Priority ranking: British/American Natural Male Voice (Jarvis style)
      this.preferredVoice =
        voices.find(v => isMaleVoice(v) && v.name.includes("Natural") && v.lang.includes("en-GB")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("George")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("UK English Male")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("Daniel")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("Ryan")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("Guy")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("David")) ||
        voices.find(v => isMaleVoice(v) && v.name.includes("Mark")) ||
        voices.find(v => isMaleVoice(v) && v.lang.startsWith("en")) ||
        voices.find(v => isMaleVoice(v)) ||
        voices.find(v => v.lang.startsWith("en") && !isExplicitFemale(v)) ||
        voices[0] ||
        null;

      if (this.preferredVoice) {
        console.log(`[WROCK-VOICE] Selected male persona voice: ${this.preferredVoice.name} (${this.preferredVoice.lang})`);
      }
    };
    updateVoices();
    if (this.synth.onvoiceschanged !== undefined) {
      this.synth.onvoiceschanged = updateVoices;
    }
  }

  private initSpeechRecognition() {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      console.warn("SpeechRecognition API not available in this browser. Falling back to text/manual commands.");
      this.permissionState = "unsupported";
      return;
    }

    try {
      this.recognition = new SpeechRecognition();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = "en-US";
      this.recognition.maxAlternatives = 3;

      this.recognition.onstart = () => {
        this.isListening = true;
        this.isStarting = false;
        this.notifyState();
      };

      this.recognition.onresult = (event: any) => {
        let interimTranscript = "";
        let finalTranscript = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const item = event.results[i];
          if (item.isFinal) {
            finalTranscript += item[0].transcript;
          } else {
            interimTranscript += item[0].transcript;
          }
        }

        const rawText = (finalTranscript || interimTranscript).trim();
        const isFinal = Boolean(finalTranscript);

        if (!rawText) return;

        // INSTANT SPEECH INTERRUPTION ("BARGE-IN"):
        // Only abort speech if user gives an explicit interrupt keyword or distinct command,
        // and ignore acoustic echo of Wrock's own utterance from the laptop speakers.
        if (this.isSpeaking) {
          const lower = rawText.toLowerCase();
          // Echo is ONLY true if transcript is virtually identical to what was just spoken
          const isEcho = Boolean(
            this.lastSpokenText &&
            (lower === this.lastSpokenText ||
             (this.lastSpokenText.length > 8 && lower.length > 8 && this.lastSpokenText.startsWith(lower)))
          );

          const isInterruptKeyword = /\b(stop|cancel|quiet|hold\s+on|shut\s+up|silence|wait|pause|ruk\s+jao|bas\s+karo)\b/i.test(lower);

          if (!isEcho && (isInterruptKeyword || isFinal)) {
            console.log("Barge-In detected! Aborting active speech for user input:", rawText);
            this.abortSpeech();
            if (this.onBargeInCallback) {
              this.onBargeInCallback(rawText);
            }
          } else if (isEcho) {
            // Drop speaker acoustic echo
            return;
          }
        }

        if (this.onTranscriptCallback) {
          this.onTranscriptCallback(rawText, isFinal);
        }
      };

      this.recognition.onerror = (event: any) => {
        console.warn("Speech recognition error:", event.error);
        this.isStarting = false;

        if (event.error === "no-speech") {
          return;
        }

        if (event.error === "not-allowed" || event.error === "service-not-allowed") {
          this.permissionState = "denied";
          this.isListening = false;
          this.notifyState();
          if (this.onErrorCallback) {
            this.onErrorCallback("Microphone permission required. Click the Mic button or camera icon to allow.", true);
          }
          return;
        }

        if (event.error === "network") {
          console.warn("Speech recognition network glitch. Will auto-retry listener...");
          if (this.isListening) {
            setTimeout(() => {
              if (this.isListening && this.recognition) {
                try {
                  this.recognition.abort();
                  this.recognition.start();
                } catch (e) {
                  // ignore
                }
              }
            }, 1000);
          }
        }
      };

      this.recognition.onend = () => {
        this.isStarting = false;
        if (this.isListening) {
          if (this.restartTimer) clearTimeout(this.restartTimer);
          this.restartTimer = setTimeout(() => {
            if (this.isListening && this.recognition) {
              try {
                this.isStarting = true;
                this.recognition.start();
              } catch (e: any) {
                this.isStarting = false;
                // If InvalidStateError, recognition is already running
              }
            }
          }, 250);
        } else {
          this.notifyState();
        }
      };
    } catch (e) {
      console.warn("Could not instantiate SpeechRecognition:", e);
      this.permissionState = "unsupported";
    }
  }

  public async requestMicrophoneAccess(forcePrompt: boolean = false): Promise<boolean> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.permissionState = "unsupported";
      if (this.onErrorCallback) {
        this.onErrorCallback("getUserMedia is not supported on this browser context.", false);
      }
      return false;
    }

    try {
      if (this.audioStream && !forcePrompt) {
        const activeTracks = this.audioStream.getAudioTracks().filter(t => t.readyState === "live");
        if (activeTracks.length > 0) {
          return true;
        }
      }

      this.audioStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
        video: false,
      });

      this.permissionState = "granted";
      this.initAudioAnalyser(this.audioStream);
      return true;
    } catch (err: any) {
      console.warn("Microphone access prompt:", err);
      // Only permanently mark denied if explicitly blocked by user
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        this.permissionState = "denied";
      }
      if (this.onErrorCallback) {
        this.onErrorCallback("Click the Mic button to allow microphone access.", true);
      }
      return false;
    }
  }

  private initAudioAnalyser(stream: MediaStream) {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (!AudioCtx) return;

      this.audioCtx = new AudioCtx();
      const source = this.audioCtx.createMediaStreamSource(stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 64; // 32 frequency bins
      this.analyser.smoothingTimeConstant = 0.8;
      source.connect(this.analyser);

      this.freqData = new Uint8Array(this.analyser.frequencyBinCount);
      this.startAudioAnalysisLoop();
    } catch (e) {
      console.warn("Web Audio Analyser setup error:", e);
    }
  }

  private startAudioAnalysisLoop() {
    if (this.audioLoopId) {
      cancelAnimationFrame(this.audioLoopId);
    }

    const processAudio = () => {
      if (this.analyser && this.freqData && this.onAudioLevelCallback) {
        this.analyser.getByteFrequencyData(this.freqData);

        // Compute volume level (RMS)
        let sum = 0;
        for (let i = 0; i < this.freqData.length; i++) {
          sum += this.freqData[i];
        }
        const avg = sum / this.freqData.length;
        this.onAudioLevelCallback(avg, this.freqData);
      }

      this.audioLoopId = requestAnimationFrame(processAudio);
    };

    this.audioLoopId = requestAnimationFrame(processAudio);
  }

  public async startListening(): Promise<boolean> {
    const hasMic = await this.requestMicrophoneAccess();
    if (!hasMic) {
      return false;
    }

    if (this.audioCtx && this.audioCtx.state === "suspended") {
      try {
        await this.audioCtx.resume();
      } catch (e) {
        // ignore
      }
    }

    if (!this.recognition) {
      this.initSpeechRecognition();
    }

    if (!this.recognition) {
      return false;
    }

    if (this.isListening) {
      return true;
    }

    try {
      this.isListening = true;
      this.isStarting = true;
      this.recognition.start();
      this.notifyState();
      return true;
    } catch (e: any) {
      this.isStarting = false;
      if (e.name !== "InvalidStateError") {
        console.warn("Could not start speech recognition:", e);
      }
      return false;
    }
  }

  public stopListening(): void {
    this.isListening = false;
    this.isStarting = false;

    if (this.restartTimer) {
      clearTimeout(this.restartTimer);
      this.restartTimer = null;
    }

    if (this.recognition) {
      try {
        this.recognition.stop();
      } catch (e) {
        // ignore
      }
    }

    this.notifyState();
  }

  public async toggleListening(): Promise<boolean> {
    if (this.isListening) {
      this.stopListening();
      return false;
    } else {
      return await this.startListening();
    }
  }

  /**
   * Instantly aborts any active speech output (browser synthesis or audio element)
   */
  public abortSpeech(): void {
    if (this.speechSafetyTimer) {
      clearTimeout(this.speechSafetyTimer);
      this.speechSafetyTimer = null;
    }

    if (this.synth) {
      try {
        this.synth.cancel();
      } catch (e) {
        // ignore
      }
    }

    if (this.currentAudioElement) {
      try {
        this.currentAudioElement.pause();
        this.currentAudioElement.currentTime = 0;
        this.currentAudioElement = null;
      } catch (e) {
        // ignore
      }
    }

    this.currentUtterance = null;
    this.lastSpokenText = "";
    this.isSpeaking = false;
    this.notifyState(false);
  }

  /**
   * Plays MP3 audio from base64 (e.g. ElevenLabs output) with barge-in support.
   */
  public playBase64Audio(base64Mp3: string): Promise<void> {
    return new Promise((resolve) => {
      this.abortSpeech(); // Abort previous speech if any

      const audio = new Audio(`data:audio/mp3;base64,${base64Mp3}`);
      this.currentAudioElement = audio;
      this.isSpeaking = true;
      this.notifyState(true);

      const finish = () => {
        this.isSpeaking = false;
        this.currentAudioElement = null;
        this.lastSpokenText = "";
        this.notifyState(false);
        resolve();
      };

      audio.onended = finish;
      audio.onerror = finish;

      audio.play().catch(() => {
        finish();
      });
    });
  }

  public speak(text: string): void {
    if (!text) return;

    this.abortSpeech(); // Clear any ongoing speech
    if (!this.synth) return;

    this.lastSpokenText = text.toLowerCase().trim();
    this.isSpeaking = true;
    this.notifyState(true);

    const utterance = new SpeechSynthesisUtterance(text);
    this.currentUtterance = utterance; // Retain reference to prevent Chromium GC bug
    if (this.preferredVoice) {
      utterance.voice = this.preferredVoice;
    }
    utterance.pitch = 0.92; // Deep, commanding resonant tone
    utterance.rate = 1.02;  // Articulate, confident cadence

    const cleanup = () => {
      if (this.speechSafetyTimer) {
        clearTimeout(this.speechSafetyTimer);
        this.speechSafetyTimer = null;
      }
      this.currentUtterance = null;
      this.lastSpokenText = "";
      this.isSpeaking = false;
      this.notifyState(false);
    };

    utterance.onstart = () => {
      this.isSpeaking = true;
      this.notifyState(true);
    };

    utterance.onend = cleanup;
    utterance.onerror = cleanup;

    // Safety watchdog timer: Chromium SpeechSynthesisUtterance occasionally never fires onend
    const estDurationMs = Math.max(1500, (text.split(" ").length * 360) + 1000);
    this.speechSafetyTimer = setTimeout(() => {
      if (this.isSpeaking && this.currentUtterance === utterance) {
        console.warn("Speech synthesis safety watchdog triggered. Resetting speaking state.");
        cleanup();
      }
    }, estDurationMs);

    this.synth.speak(utterance);
  }

  private notifyState(isSpeaking: boolean = this.isSpeaking) {
    if (this.onStateChangeCallback) {
      this.onStateChangeCallback(this.isListening, isSpeaking);
    }
  }

  public getListeningState(): boolean {
    return this.isListening;
  }

  public getSpeakingState(): boolean {
    return this.isSpeaking;
  }
}
