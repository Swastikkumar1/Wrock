import { GestureType, GestureData } from "../types";
import { LandmarkPoint } from "./hand_tracker";
import { sfx } from "../audio/sound_effects";

export class GestureRecognizer {
  private wasPinching: boolean = false;
  private pinchEngageThreshold: number = 0.085;   // Distance to initiate a pinch
  private pinchReleaseThreshold: number = 0.28;   // Generous release limit allowing wide pinch-out
  private prevPinchDist: number | null = null;
  private prevCursor: { x: number; y: number } | null = null;

  public processLandmarks(landmarks: LandmarkPoint[]): GestureData {
    if (!landmarks || landmarks.length < 21) {
      this.wasPinching = false;
      this.prevPinchDist = null;
      this.prevCursor = null;
      return {
        gesture: "IDLE",
        confidence: 0,
        cursor: { x: 0.5, y: 0.5, z: 0 },
        pointing_ray: [0, 0, -1],
        pinch_distance: 1.0,
      };
    }

    const thumbTip = landmarks[4];
    const indexTip = landmarks[8];
    const indexMcp = landmarks[5];

    // Compute 3D distance between thumb tip and index tip
    const dx = thumbTip.x - indexTip.x;
    const dy = thumbTip.y - indexTip.y;
    const dz = thumbTip.z - indexTip.z;
    const pinchDist = Math.sqrt(dx * dx + dy * dy + dz * dz);

    let gesture: GestureType = "POINT";
    let zoomDelta = 0;
    let panDelta = { dx: 0, dy: 0 };

    if (!this.wasPinching) {
      // Check if fingers are brought together to initiate pinch
      if (pinchDist < this.pinchEngageThreshold) {
        this.wasPinching = true;
        this.prevPinchDist = pinchDist;
        this.prevCursor = { x: indexTip.x, y: indexTip.y };
        gesture = "PINCH_START";
        sfx.playPinchSound();
      } else {
        gesture = "POINT";
        this.prevPinchDist = null;
        this.prevCursor = null;
      }
    } else {
      // Actively in pinch-to-zoom / pan mode
      if (pinchDist > this.pinchReleaseThreshold) {
        // Hand opened wide: release pinch
        this.wasPinching = false;
        this.prevPinchDist = null;
        this.prevCursor = null;
        gesture = "PINCH_RELEASE";
      } else {
        gesture = "PINCH_HOLD";

        // Compute continuous pinch zoom delta (pinch-out -> zoom in, pinch-in -> zoom out)
        if (this.prevPinchDist !== null) {
          const distDiff = pinchDist - this.prevPinchDist;
          // Scale zoom delta proportionally to finger distance change
          zoomDelta = distDiff * 7.5;
        }
        this.prevPinchDist = pinchDist;

        // Compute pan delta
        if (this.prevCursor !== null) {
          panDelta = {
            dx: indexTip.x - this.prevCursor.x,
            dy: indexTip.y - this.prevCursor.y,
          };
        }
        this.prevCursor = { x: indexTip.x, y: indexTip.y };
      }
    }

    // Direction vector from Index MCP to Index Tip
    const rdx = indexTip.x - indexMcp.x;
    const rdy = indexTip.y - indexMcp.y;
    const rdz = indexTip.z - indexMcp.z;
    const mag = Math.sqrt(rdx * rdx + rdy * rdy + rdz * rdz) || 1;

    return {
      gesture,
      confidence: 0.95,
      cursor: { x: indexTip.x, y: indexTip.y, z: indexTip.z },
      pointing_ray: [rdx / mag, rdy / mag, rdz / mag],
      pinch_distance: pinchDist,
      pinch_zoom_delta: zoomDelta,
      pan_delta: panDelta,
    };
  }
}
