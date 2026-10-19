export type EntityType = "DRONE" | "SATELLITE" | "VEHICLE" | "INFRASTRUCTURE" | "POI" | "PERSONNEL";
export type ThreatLevel = "FRIENDLY" | "NEUTRAL" | "UNKNOWN" | "HOSTILE";
export type CameraMode = "GODS_EYE" | "ORBITAL" | "TACTICAL_DRONE" | "HOLOGRAM";

export interface SpatialPosition {
  x: number;
  y: number;
  z: number;
}

export interface SpatialEntity {
  id: string;
  name: string;
  type: EntityType;
  position: SpatialPosition;
  heading_deg: number;
  altitude_m: number;
  threat_level: ThreatLevel;
  is_locked: boolean;
  is_inspected: boolean;
  bounding_radius: number;
  spatial_anchor_id?: string;
  telemetry: Record<string, any>;
}

export interface SpatialAnchor {
  id: string;
  label: string;
  x: number;
  y: number;
  z: number;
}

export interface SpatialSceneData {
  entities: SpatialEntity[];
  anchors: SpatialAnchor[];
  summary: {
    total_entities: number;
    threats_count: number;
    locked_entity_id: string | null;
    entity_ids: string[];
    anchors_count: number;
  };
  observer: {
    mode: CameraMode;
    position: [number, number, number];
    target: [number, number, number];
    fov: number;
  };
}

export type GestureType =
  | "IDLE"
  | "POINT"
  | "PINCH_START"
  | "PINCH_HOLD"
  | "PINCH_RELEASE"
  | "GRAB"
  | "OPEN_PALM"
  | "PUSH"
  | "SWIPE_LEFT"
  | "SWIPE_RIGHT"
  | "SWIPE_UP"
  | "SWIPE_DOWN"
  | "WRIST_ROLL";

export interface GestureData {
  gesture: GestureType;
  confidence: number;
  cursor: { x: number; y: number; z: number };
  pointing_ray: [number, number, number];
  pinch_distance: number;
  pinch_zoom_delta?: number;
  pan_delta?: { dx: number; dy: number };
  action_triggered?: {
    action: string;
    target_id?: string;
    reason: string;
  };
}

export interface VoiceIntentEvent {
  spoken_text: string;
  hud_alert?: string;
  target_entity_id?: string;
  camera_mode?: CameraMode;
  pov_entity_id?: string;
  action_type?: string;
  tools_called?: string[];
}
