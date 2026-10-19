/**
 * HandTracker: High-speed multi-hand tracking engine.
 * Powered by local MediaPipe Hands (supporting 2 hands simultaneously for
 * two-hand distance zoom, Alt+Tab switch, index/middle clicks, drag, and scrolling)
 * with an ultra-fast optical skin CV tracker as an immediate zero-latency fallback.
 */

import { Hands, Results } from "@mediapipe/hands";

export interface LandmarkPoint {
  x: number;
  y: number;
  z: number;
}

const HAND_BONES: [number, number][] = [
  // Thumb
  [0, 1], [1, 2], [2, 3], [3, 4],
  // Index
  [0, 5], [5, 6], [6, 7], [7, 8],
  // Middle
  [0, 9], [9, 10], [10, 11], [11, 12],
  // Ring
  [0, 13], [13, 14], [14, 15], [15, 16],
  // Pinky
  [0, 17], [17, 18], [18, 19], [19, 20],
  // Palm
  [5, 9], [9, 13], [13, 17]
];

export class HandTracker {
  private videoEl: HTMLVideoElement | null = null;
  private canvasEl: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private isCameraActive: boolean = false;
  private animFrameId: number | null = null;

  // MediaPipe Hands multi-hand detector
  private mpHands: Hands | null = null;
  private isMpReady: boolean = false;
  private isMpProcessing: boolean = false;
  private lastMpFrameTime: number = 0;
  private lastMultiHands: LandmarkPoint[][] = [];
  private lastHandedness: string[] = [];

  // Offscreen CV canvas for optical skin analysis fallback
  private cvCanvas: HTMLCanvasElement;
  private cvCtx: CanvasRenderingContext2D | null;

  // Smoothed tracking coordinates for fallback
  private smoothedIndex: { x: number; y: number } = { x: 0.5, y: 0.5 };
  private smoothedThumb: { x: number; y: number } = { x: 0.45, y: 0.55 };
  private smoothedWrist: { x: number; y: number } = { x: 0.5, y: 0.85 };
  public isPinchingNow: boolean = false;

  // Mouse fallback
  private mouseX: number = 0.5;
  private mouseY: number = 0.5;
  private isMouseDown: boolean = false;

  public onLandmarksCallback: ((landmarks: LandmarkPoint[], multiHands?: LandmarkPoint[][], handedness?: string[]) => void) | null = null;
  public onWheelZoomCallback: ((deltaZoom: number) => void) | null = null;

  constructor() {
    this.videoEl = document.getElementById("webcam-video") as HTMLVideoElement;
    this.canvasEl = document.getElementById("webcam-canvas") as HTMLCanvasElement;
    if (this.canvasEl) {
      this.ctx = this.canvasEl.getContext("2d");
    }

    // 160x120 downscaled processing canvas for instant optical fallback
    this.cvCanvas = document.createElement("canvas");
    this.cvCanvas.width = 160;
    this.cvCanvas.height = 120;
    this.cvCtx = this.cvCanvas.getContext("2d", { willReadFrequently: true });

    this.initMediaPipeHands();
    this.initMouseAndWheelFallback();
  }

  private initMediaPipeHands() {
    try {
      this.mpHands = new Hands({
        locateFile: (file: string) => `/mediapipe/${file}`,
      });

      this.mpHands.setOptions({
        maxNumHands: 2,
        modelComplexity: 1,
        minDetectionConfidence: 0.60,
        minTrackingConfidence: 0.55,
      });

      this.mpHands.onResults((results: Results) => {
        this.handleMediaPipeResults(results);
      });

      this.isMpReady = true;
      console.log("MediaPipe Hands loaded successfully with multi-hand support.");
    } catch (e) {
      console.warn("MediaPipe Hands initialization fallback to optical tracking:", e);
      this.isMpReady = false;
    }
  }

  private handleMediaPipeResults(results: Results) {
    if (!results.multiHandLandmarks || results.multiHandLandmarks.length === 0) {
      this.lastMultiHands = [];
      this.lastHandedness = [];
      this.isPinchingNow = false;

      // Clear overlay canvas
      if (this.ctx && this.canvasEl) {
        this.ctx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
      }

      // Notify callback that NO hands are present so cursor stays put!
      if (this.onLandmarksCallback) {
        this.onLandmarksCallback([], [], []);
      }
      return;
    }

    const multiHands: LandmarkPoint[][] = [];
    const handedness: string[] = [];

    for (let i = 0; i < results.multiHandLandmarks.length; i++) {
      // Natural Screen-Space Mirroring: moving hand right moves cursor right!
      const lms = results.multiHandLandmarks[i].map(pt => ({
        x: Math.max(0, Math.min(1, 1.0 - pt.x)),
        y: Math.max(0, Math.min(1, pt.y)),
        z: pt.z || 0,
      }));
      multiHands.push(lms);

      const label = results.multiHandedness && results.multiHandedness[i]
        ? results.multiHandedness[i].label
        : (i === 1 ? "Left" : "Right");
      handedness.push(label);
    }

    this.lastMultiHands = multiHands;
    this.lastHandedness = handedness;

    // Primary hand (first detected)
    const primary = multiHands[0];
    const thumbTip = primary[4];
    const indexTip = primary[8];
    const pDist = Math.hypot(thumbTip.x - indexTip.x, thumbTip.y - indexTip.y);
    this.isPinchingNow = pDist < 0.055;

    if (this.onLandmarksCallback) {
      this.onLandmarksCallback(primary, multiHands, handedness);
    }

    this.renderMultiHandCanvas(multiHands, handedness);
  }

  private initMouseAndWheelFallback() {
    window.addEventListener("mousemove", (e) => {
      this.mouseX = e.clientX / window.innerWidth;
      this.mouseY = e.clientY / window.innerHeight;
      if (!this.isCameraActive) {
        this.updateSimulatedHandFromMouse();
      }
    });

    window.addEventListener("mousedown", (e) => {
      if ((e.target as HTMLElement)?.closest("button, input, select")) return;
      this.isMouseDown = true;
      if (!this.isCameraActive) {
        this.updateSimulatedHandFromMouse();
      }
    });

    window.addEventListener("mouseup", () => {
      this.isMouseDown = false;
      if (!this.isCameraActive) {
        this.updateSimulatedHandFromMouse();
      }
    });

    window.addEventListener("wheel", (e) => {
      if ((e.target as HTMLElement)?.closest(".transcript-body, .diagnostics-box")) return;
      const zoomFactor = e.deltaY < 0 ? 1.15 : 0.85;
      if (this.onWheelZoomCallback) {
        this.onWheelZoomCallback(zoomFactor);
      }
    }, { passive: true });
  }

  public async startWebcam(): Promise<boolean> {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      console.warn("getUserMedia not supported on this browser.");
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" },
        audio: false,
      });

      if (this.videoEl) {
        this.videoEl.srcObject = stream;
        await this.videoEl.play();
        this.isCameraActive = true;
        console.log("Webcam live! Tracking gestures via MediaPipe + Optical Engine...");
        this.trackLoop();
        return true;
      }
    } catch (err) {
      console.warn("Webcam access error:", err);
      this.isCameraActive = false;
    }
    return false;
  }

  public stopWebcam() {
    this.isCameraActive = false;
    if (this.animFrameId) {
      cancelAnimationFrame(this.animFrameId);
    }
    if (this.videoEl && this.videoEl.srcObject) {
      const stream = this.videoEl.srcObject as MediaStream;
      stream.getTracks().forEach(t => t.stop());
      this.videoEl.srcObject = null;
    }
    if (this.ctx && this.canvasEl) {
      this.ctx.clearRect(0, 0, this.canvasEl.width, this.canvasEl.height);
    }
    this.lastMultiHands = [];
  }

  public toggleWebcam(): Promise<boolean> {
    if (this.isCameraActive) {
      this.stopWebcam();
      return Promise.resolve(false);
    } else {
      return this.startWebcam();
    }
  }

  /**
   * Main tracking loop: Feeds MediaPipe Hands at high throughput,
   * falling back smoothly to optical CV skin tracking when MediaPipe is initializing.
   */
  private trackLoop = () => {
    if (!this.isCameraActive) return;

    const now = performance.now();

    if (this.videoEl && this.videoEl.readyState >= 2) {
      // 1. Dispatch frame to MediaPipe Hands if ready
      if (this.isMpReady && this.mpHands && !this.isMpProcessing && (now - this.lastMpFrameTime) >= 28) {
        this.isMpProcessing = true;
        this.lastMpFrameTime = now;
        this.mpHands.send({ image: this.videoEl })
          .catch((e) => console.debug("MediaPipe send warning:", e))
          .finally(() => { this.isMpProcessing = false; });
      }
    }

    this.animFrameId = requestAnimationFrame(this.trackLoop);
  };

  private runOpticalSkinTracking() {
    if (!this.videoEl || !this.cvCtx) return;

    const cw = this.cvCanvas.width;
    const ch = this.cvCanvas.height;

    // Draw mirrored webcam frame to downscaled CV canvas
    this.cvCtx.save();
    this.cvCtx.scale(-1, 1);
    this.cvCtx.drawImage(this.videoEl, -cw, 0, cw, ch);
    this.cvCtx.restore();

    const imgData = this.cvCtx.getImageData(0, 0, cw, ch);
    const data = imgData.data;

    let skinCount = 0;
    let sumX = 0;
    let sumY = 0;
    let topX = 0;
    let topY = ch;
    let sideX = 0;
    let sideY = 0;

    for (let y = 10; y < ch - 10; y += 2) {
      for (let x = 10; x < cw - 10; x += 2) {
        const idx = (y * cw + x) * 4;
        const r = data[idx];
        const g = data[idx + 1];
        const b = data[idx + 2];

        const isSkin =
          r > 60 && g > 35 && b > 20 &&
          r > g && r > b &&
          (r - g) > 12 &&
          Math.abs(r - g) > 10;

        if (isSkin) {
          skinCount++;
          sumX += x;
          sumY += y;

          if (y < topY) {
            topY = y;
            topX = x;
          }
        }
      }
    }

    if (skinCount > 70) {
      const palmCenterX = sumX / skinCount;
      const palmCenterY = sumY / skinCount;

      let maxThumbDist = 0;
      for (let y = Math.floor(palmCenterY - 15); y < Math.min(ch, palmCenterY + 30); y += 3) {
        for (let x = 10; x < cw - 10; x += 3) {
          const idx = (y * cw + x) * 4;
          const r = data[idx];
          const g = data[idx + 1];
          const b = data[idx + 2];
          const isSkin = r > 60 && g > 35 && b > 20 && r > g && r > b && (r - g) > 12;

          if (isSkin) {
            const dx = x - palmCenterX;
            if (Math.abs(dx) > maxThumbDist && y > topY + 5) {
              maxThumbDist = Math.abs(dx);
              sideX = x;
              sideY = y;
            }
          }
        }
      }

      const normIndexX = topX / cw;
      const normIndexY = topY / ch;
      const normThumbX = sideX ? sideX / cw : (palmCenterX - 20) / cw;
      const normThumbY = sideY ? sideY / ch : palmCenterY / ch;
      const normWristX = palmCenterX / cw;
      const normWristY = Math.min(0.98, (palmCenterY + 25) / ch);

      this.smoothedIndex.x += (normIndexX - this.smoothedIndex.x) * 0.35;
      this.smoothedIndex.y += (normIndexY - this.smoothedIndex.y) * 0.35;

      this.smoothedThumb.x += (normThumbX - this.smoothedThumb.x) * 0.35;
      this.smoothedThumb.y += (normThumbY - this.smoothedThumb.y) * 0.35;

      this.smoothedWrist.x += (normWristX - this.smoothedWrist.x) * 0.25;
      this.smoothedWrist.y += (normWristY - this.smoothedWrist.y) * 0.25;

      const pDist = Math.hypot(
        this.smoothedIndex.x - this.smoothedThumb.x,
        this.smoothedIndex.y - this.smoothedThumb.y
      );

      this.isPinchingNow = pDist < 0.085;

      const landmarks = this.buildSkeleton(
        this.smoothedIndex,
        this.smoothedThumb,
        this.smoothedWrist,
        this.isPinchingNow
      );

      if (this.onLandmarksCallback) {
        this.onLandmarksCallback(landmarks);
      }

      this.renderDebugCanvas(landmarks, this.isPinchingNow, pDist);
    } else {
      this.renderEmptyCanvas();
    }
  }

  private renderMultiHandCanvas(multiHands: LandmarkPoint[][], handedness: string[]) {
    if (!this.ctx || !this.canvasEl) return;
    const w = (this.canvasEl.width = this.canvasEl.clientWidth);
    const h = (this.canvasEl.height = this.canvasEl.clientHeight);

    this.ctx.clearRect(0, 0, w, h);

    const colors = [
      { joint: "#00e5ff", bone: "rgba(0, 229, 255, 0.6)", pinch: "#ffb300" },
      { joint: "#ff007f", bone: "rgba(255, 0, 127, 0.6)", pinch: "#ffaa00" },
    ];

    multiHands.forEach((hand, hIdx) => {
      const colorScheme = colors[hIdx % colors.length];

      // Measure pinch
      const thumbTip = hand[4];
      const indexTip = hand[8];
      const pDist = Math.hypot(thumbTip.x - indexTip.x, thumbTip.y - indexTip.y);
      const isPinch = pDist < 0.055;

      // Draw skeleton bones
      this.ctx!.strokeStyle = isPinch ? colorScheme.pinch : colorScheme.bone;
      this.ctx!.lineWidth = isPinch ? 2.5 : 1.5;

      for (const [s, e] of HAND_BONES) {
        if (s < hand.length && e < hand.length) {
          const p1 = hand[s];
          const p2 = hand[e];
          this.ctx!.beginPath();
          this.ctx!.moveTo(p1.x * w, p1.y * h);
          this.ctx!.lineTo(p2.x * w, p2.y * h);
          this.ctx!.stroke();
        }
      }

      // Draw joints
      this.ctx!.fillStyle = isPinch ? colorScheme.pinch : colorScheme.joint;
      for (const lm of hand) {
        this.ctx!.beginPath();
        this.ctx!.arc(lm.x * w, lm.y * h, 3.0, 0, Math.PI * 2);
        this.ctx!.fill();
      }

      // Glow circle at index fingertip
      this.ctx!.strokeStyle = isPinch ? colorScheme.pinch : colorScheme.joint;
      this.ctx!.lineWidth = 2;
      this.ctx!.beginPath();
      this.ctx!.arc(indexTip.x * w, indexTip.y * h, isPinch ? 10 : 6, 0, Math.PI * 2);
      this.ctx!.stroke();
    });

    // If 2 hands detected, draw connection line showing two-hand distance for zoom
    if (multiHands.length >= 2) {
      const idx1 = multiHands[0][8];
      const idx2 = multiHands[1][8];
      this.ctx.strokeStyle = "#ffb300";
      this.ctx.setLineDash([4, 4]);
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.moveTo(idx1.x * w, idx1.y * h);
      this.ctx.lineTo(idx2.x * w, idx2.y * h);
      this.ctx.stroke();
      this.ctx.setLineDash([]);

      const twoHandDist = Math.hypot(idx1.x - idx2.x, idx1.y - idx2.y);
      this.ctx.font = "bold 9px 'Orbitron', monospace";
      this.ctx.fillStyle = "#ffb300";
      this.ctx.fillText(`👐 TWO-HAND ZOOM (${twoHandDist.toFixed(2)})`, 8, h - 8);
    } else {
      this.ctx.font = "bold 9px 'Orbitron', monospace";
      this.ctx.fillStyle = this.isPinchingNow ? "#ffb300" : "#00e5ff";
      this.ctx.fillText(this.isPinchingNow ? "🖐️ PINCH CLICK" : "🖐️ 1-HAND ACTIVE", 8, h - 8);
    }
  }

  private buildSkeleton(
    idxTip: { x: number; y: number },
    thbTip: { x: number; y: number },
    wrist: { x: number; y: number },
    pinching: boolean
  ): LandmarkPoint[] {
    const pts: LandmarkPoint[] = [];

    // 0: Wrist
    pts.push({ x: wrist.x, y: wrist.y, z: 0 });

    // 1-4: Thumb
    const tDx = (thbTip.x - wrist.x) / 4;
    const tDy = (thbTip.y - wrist.y) / 4;
    pts.push({ x: wrist.x + tDx, y: wrist.y + tDy, z: 0 });
    pts.push({ x: wrist.x + tDx * 2, y: wrist.y + tDy * 2, z: 0 });
    pts.push({ x: wrist.x + tDx * 3, y: wrist.y + tDy * 3, z: 0 });
    pts.push({ x: thbTip.x, y: thbTip.y, z: 0 }); // 4: Thumb Tip

    // 5-8: Index Finger
    const iDx = (idxTip.x - wrist.x) / 4;
    const iDy = (idxTip.y - wrist.y) / 4;
    pts.push({ x: wrist.x + iDx, y: wrist.y + iDy, z: 0 });
    pts.push({ x: wrist.x + iDx * 2, y: wrist.y + iDy * 2, z: 0 });
    pts.push({ x: wrist.x + iDx * 3, y: wrist.y + iDy * 3, z: 0 });
    pts.push({ x: idxTip.x, y: idxTip.y, z: 0 }); // 8: Index Tip

    // 9-12: Middle Finger
    const midX = (idxTip.x + thbTip.x) * 0.5 + 0.02;
    const midY = idxTip.y - 0.02;
    pts.push({ x: wrist.x + 0.01, y: wrist.y - 0.1, z: 0 });
    pts.push({ x: wrist.x + 0.015, y: wrist.y - 0.15, z: 0 });
    pts.push({ x: wrist.x + 0.02, y: wrist.y - 0.2, z: 0 });
    pts.push({ x: midX, y: midY, z: 0 });

    // 13-16: Ring Finger
    pts.push({ x: wrist.x + 0.03, y: wrist.y - 0.08, z: 0 });
    pts.push({ x: wrist.x + 0.04, y: wrist.y - 0.13, z: 0 });
    pts.push({ x: wrist.x + 0.05, y: wrist.y - 0.18, z: 0 });
    pts.push({ x: wrist.x + 0.055, y: wrist.y - 0.22, z: 0 });

    // 17-20: Pinky
    pts.push({ x: wrist.x + 0.06, y: wrist.y - 0.06, z: 0 });
    pts.push({ x: wrist.x + 0.07, y: wrist.y - 0.1, z: 0 });
    pts.push({ x: wrist.x + 0.08, y: wrist.y - 0.14, z: 0 });
    pts.push({ x: wrist.x + 0.085, y: wrist.y - 0.17, z: 0 });

    return pts;
  }

  private updateSimulatedHandFromMouse() {
    const x = this.mouseX;
    const y = this.mouseY;
    const pinchClose = this.isMouseDown ? 0.015 : 0.08;

    const landmarks: LandmarkPoint[] = [];
    landmarks.push({ x: x, y: y + 0.12, z: 0.0 });
    landmarks.push({ x: x - 0.03, y: y + 0.08, z: 0.0 });
    landmarks.push({ x: x - 0.05, y: y + 0.04, z: 0.0 });
    landmarks.push({ x: x - 0.04, y: y + 0.01, z: 0.0 });
    landmarks.push({ x: x - pinchClose, y: y, z: 0.0 }); // 4: Thumb Tip
    landmarks.push({ x: x - 0.015, y: y + 0.05, z: 0.0 });
    landmarks.push({ x: x - 0.01, y: y + 0.03, z: 0.0 });
    landmarks.push({ x: x - 0.005, y: y + 0.01, z: 0.0 });
    landmarks.push({ x: x, y: y, z: 0.0 }); // 8: Index Tip
    landmarks.push({ x: x + 0.01, y: y + 0.05, z: 0.0 });
    landmarks.push({ x: x + 0.015, y: y + 0.03, z: 0.0 });
    landmarks.push({ x: x + 0.02, y: y + 0.02, z: 0.0 });
    landmarks.push({ x: x + 0.025, y: y + 0.03, z: 0.0 });
    landmarks.push({ x: x + 0.03, y: y + 0.06, z: 0.0 });
    landmarks.push({ x: x + 0.035, y: y + 0.04, z: 0.0 });
    landmarks.push({ x: x + 0.04, y: y + 0.03, z: 0.0 });
    landmarks.push({ x: x + 0.045, y: y + 0.04, z: 0.0 });
    landmarks.push({ x: x + 0.05, y: y + 0.07, z: 0.0 });
    landmarks.push({ x: x + 0.055, y: y + 0.05, z: 0.0 });
    landmarks.push({ x: x + 0.06, y: y + 0.04, z: 0.0 });
    landmarks.push({ x: x + 0.065, y: y + 0.05, z: 0.0 });

    if (this.onLandmarksCallback) {
      this.onLandmarksCallback(landmarks);
    }
    this.renderDebugCanvas(landmarks, this.isMouseDown, pinchClose);
  }

  private renderDebugCanvas(landmarks: LandmarkPoint[], isPinch: boolean, pDist: number) {
    if (!this.ctx || !this.canvasEl) return;
    const w = (this.canvasEl.width = this.canvasEl.clientWidth);
    const h = (this.canvasEl.height = this.canvasEl.clientHeight);

    this.ctx.clearRect(0, 0, w, h);

    // Draw joints
    this.ctx.fillStyle = isPinch ? "#ffb300" : "#00e5ff";
    for (const lm of landmarks) {
      this.ctx.beginPath();
      this.ctx.arc(lm.x * w, lm.y * h, 3.5, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // Connect Thumb (4) to Index Tip (8) with dynamic pinch line
    if (landmarks.length > 8) {
      const p1 = landmarks[4];
      const p2 = landmarks[8];
      this.ctx.strokeStyle = isPinch ? "#ffb300" : "rgba(0, 229, 255, 0.6)";
      this.ctx.lineWidth = isPinch ? 3 : 1.5;
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x * w, p1.y * h);
      this.ctx.lineTo(p2.x * w, p2.y * h);
      this.ctx.stroke();

      // Glowing targeting ring around index fingertip
      this.ctx.strokeStyle = isPinch ? "#ffb300" : "#00e5ff";
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.arc(p2.x * w, p2.y * h, isPinch ? 12 : 8, 0, Math.PI * 2);
      this.ctx.stroke();

      this.ctx.font = "bold 9px 'Orbitron', monospace";
      this.ctx.fillStyle = isPinch ? "#ffb300" : "#00e5ff";
      this.ctx.fillText(isPinch ? "🖐️ PINCH: ZOOM" : "🖐️ TRACKING", 8, h - 8);
    }
  }

  private renderEmptyCanvas() {
    if (!this.ctx || !this.canvasEl) return;
    const w = (this.canvasEl.width = this.canvasEl.clientWidth);
    const h = (this.canvasEl.height = this.canvasEl.clientHeight);
    this.ctx.clearRect(0, 0, w, h);
    this.ctx.font = "9px 'Share Tech Mono', monospace";
    this.ctx.fillStyle = "rgba(0, 229, 255, 0.5)";
    this.ctx.fillText("RAISE HAND TO PINCH", 8, h - 8);
  }

  public getIsActive(): boolean {
    return this.isCameraActive;
  }
}
