import { CONFIG } from "../config";
import { SpatialSceneData, VoiceIntentEvent, GestureData, CameraMode } from "../types";
import { LandmarkPoint } from "../gestures/hand_tracker";

export class SpatialWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectInterval: number = 2000;
  private isConnected: boolean = false;

  public onSceneUpdateCallback: ((data: SpatialSceneData) => void) | null = null;
  public onVoiceIntentCallback: ((data: VoiceIntentEvent) => void) | null = null;
  public onGestureEventCallback: ((data: GestureData) => void) | null = null;
  public onConnectionStateChange: ((connected: boolean) => void) | null = null;

  // Lifecycle & Barge-In callbacks
  public onLifecycleStateCallback: ((data: { state: string; is_awake: boolean }) => void) | null = null;
  public onSpeechInterruptedCallback: ((data: { reason: string; timestamp: number }) => void) | null = null;
  public onAssistantSpeechCallback: ((data: { text: string; audio_base64?: string; play_chime?: boolean }) => void) | null = null;
  public onOsGestureCallback: ((data: { gesture: string; payload: any }) => void) | null = null;

  constructor(url: string = CONFIG.WS_URL) {
    this.url = url;
    this.connect();
  }

  private connect() {
    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        this.isConnected = true;
        console.log("Spatial WebSocket Connected to:", this.url);
        if (this.onConnectionStateChange) {
          this.onConnectionStateChange(true);
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const envelope = JSON.parse(event.data);
          const type = envelope.event_type;
          const payload = envelope.payload;

          if (type === "SCENE_UPDATE" && this.onSceneUpdateCallback) {
            this.onSceneUpdateCallback(payload);
          } else if (type === "VOICE_INTENT" && this.onVoiceIntentCallback) {
            this.onVoiceIntentCallback(payload);
          } else if (type === "GESTURE_EVENT" && this.onGestureEventCallback) {
            this.onGestureEventCallback(payload);
          } else if (type === "LIFECYCLE_STATE" && this.onLifecycleStateCallback) {
            this.onLifecycleStateCallback(payload);
          } else if (type === "SPEECH_INTERRUPTED" && this.onSpeechInterruptedCallback) {
            this.onSpeechInterruptedCallback(payload);
          } else if (type === "ASSISTANT_SPEECH" && this.onAssistantSpeechCallback) {
            this.onAssistantSpeechCallback(payload);
          } else if (type === "OS_GESTURE_EVENT" && this.onOsGestureCallback) {
            this.onOsGestureCallback(payload);
          }
        } catch (err) {
          console.warn("Failed to parse WebSocket message:", err);
        }
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        if (this.onConnectionStateChange) {
          this.onConnectionStateChange(false);
        }
        setTimeout(() => this.connect(), this.reconnectInterval);
      };

      this.ws.onerror = (err) => {
        console.warn("WebSocket error:", err);
        this.ws?.close();
      };
    } catch (e) {
      setTimeout(() => this.connect(), this.reconnectInterval);
    }
  }

  public sendHandLandmarks(landmarks: LandmarkPoint[] | LandmarkPoint[][], handedness: any = "Right") {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "HAND_LANDMARKS",
      payload: { landmarks, handedness },
    }));
  }

  public sendHoverUpdate(entityId: string | null) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "HOVER_UPDATE",
      payload: { entity_id: entityId },
    }));
  }

  public sendVoiceTranscript(text: string, isFinal: boolean, forceExec: boolean = false) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "VOICE_TRANSCRIPT",
      payload: { text, is_final: isFinal, force_exec: forceExec },
    }));
  }

  public sendVoiceWake() {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "WAKE",
      payload: {},
    }));
  }

  public sendVoiceDismiss() {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "DISMISS",
      payload: {},
    }));
  }

  public sendSpeechInterrupt(reason: string = "barge_in") {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "SPEECH_INTERRUPT",
      payload: { reason },
    }));
  }

  public sendCommand(text: string) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "COMMAND",
      payload: { text },
    }));
  }

  public sendSetPov(targetId: string) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "SET_POV",
      payload: { target_id: targetId },
    }));
  }

  public sendMapPinchZoom(zoomFactor: number) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "MAP_PINCH_ZOOM",
      payload: { zoom_factor: zoomFactor },
    }));
  }

  public sendCameraMode(mode: CameraMode) {
    if (!this.isConnected || !this.ws) return;
    this.ws.send(JSON.stringify({
      type: "SET_CAMERA_MODE",
      payload: { mode },
    }));
  }

  public getIsConnected(): boolean {
    return this.isConnected;
  }
}
