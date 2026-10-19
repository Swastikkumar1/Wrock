import * as THREE from "three";
import { LandmarkPoint } from "./hand_tracker";
import { GestureData } from "../types";
import { CONFIG } from "../config";

// Anatomical hand bone connections (pairs of landmark indices)
const BONE_CONNECTIONS: [number, number][] = [
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
  // Palm base cross-links
  [5, 9], [9, 13], [13, 17],
];

export class HandVisualizer {
  public group: THREE.Group;
  private jointMeshes: THREE.Mesh[] = [];
  private boneLines: THREE.LineSegments | null = null;
  private pointerRay: THREE.Line | null = null;
  private reticleMesh: THREE.Group;
  private pinchRippleMesh: THREE.Mesh;
  private camera: THREE.Camera;

  constructor(camera: THREE.Camera) {
    this.camera = camera;
    this.group = new THREE.Group();
    this.group.name = "HolographicHandGroup";

    this.createJoints();
    this.createBones();
    this.createPointerRay();
    this.reticleMesh = this.createReticle();
    this.pinchRippleMesh = this.createPinchRipple();

    this.group.add(this.reticleMesh);
    this.group.add(this.pinchRippleMesh);
  }

  private createJoints() {
    const jointGeo = new THREE.SphereGeometry(0.04, 8, 8);
    const jointMat = new THREE.MeshBasicMaterial({
      color: CONFIG.COLORS.CYAN,
      wireframe: true,
      transparent: true,
      opacity: 0.85,
    });

    for (let i = 0; i < 21; i++) {
      const mesh = new THREE.Mesh(jointGeo, jointMat.clone());
      mesh.visible = false;
      this.jointMeshes.push(mesh);
      this.group.add(mesh);
    }
  }

  private createBones() {
    const lineGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(BONE_CONNECTIONS.length * 2 * 3);
    lineGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));

    const lineMat = new THREE.LineBasicMaterial({
      color: CONFIG.COLORS.CYAN,
      transparent: true,
      opacity: 0.5,
      linewidth: 2,
    });

    this.boneLines = new THREE.LineSegments(lineGeo, lineMat);
    this.group.add(this.boneLines);
  }

  private createPointerRay() {
    const rayGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0, 0),
      new THREE.Vector3(0, 0, -15),
    ]);
    const rayMat = new THREE.LineDashedMaterial({
      color: CONFIG.COLORS.CYAN,
      dashSize: 0.3,
      gapSize: 0.15,
      transparent: true,
      opacity: 0.7,
    });
    this.pointerRay = new THREE.Line(rayGeo, rayMat);
    this.pointerRay.computeLineDistances();
    this.group.add(this.pointerRay);
  }

  private createReticle(): THREE.Group {
    const reticleGroup = new THREE.Group();

    // Outer rotating ring
    const ringGeo = new THREE.RingGeometry(0.12, 0.14, 24);
    const ringMat = new THREE.MeshBasicMaterial({
      color: CONFIG.COLORS.CYAN,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.8,
    });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    ringMesh.name = "OuterRing";
    reticleGroup.add(ringMesh);

    // Center focal dot
    const dotGeo = new THREE.CircleGeometry(0.02, 12);
    const dotMat = new THREE.MeshBasicMaterial({
      color: CONFIG.COLORS.AMBER,
      side: THREE.DoubleSide,
    });
    const dotMesh = new THREE.Mesh(dotGeo, dotMat);
    reticleGroup.add(dotMesh);

    return reticleGroup;
  }

  private createPinchRipple(): THREE.Mesh {
    const rippleGeo = new THREE.RingGeometry(0.05, 0.08, 32);
    const rippleMat = new THREE.MeshBasicMaterial({
      color: CONFIG.COLORS.AMBER,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.0,
    });
    const ripple = new THREE.Mesh(rippleGeo, rippleMat);
    ripple.visible = false;
    return ripple;
  }

  public update(landmarks: LandmarkPoint[], gestureData: GestureData) {
    if (!landmarks || landmarks.length < 21) {
      this.group.visible = false;
      return;
    }
    this.group.visible = true;

    // Convert 2D screen coordinates into 3D camera-relative world coordinates
    const joint3DPositions: THREE.Vector3[] = [];

    for (let i = 0; i < 21; i++) {
      const lm = landmarks[i];
      // NDC coordinates [-1, 1]
      const ndcX = lm.x * 2 - 1;
      const ndcY = -(lm.y * 2 - 1);
      const ndcZ = 0.5 + (lm.z || 0) * 0.5;

      const vec = new THREE.Vector3(ndcX, ndcY, ndcZ);
      vec.unproject(this.camera);

      // Interpolate along camera ray at comfortable tabletop interaction distance (e.g. 3.5 units from camera)
      const ray = vec.sub(this.camera.position).normalize();
      const worldPos = this.camera.position.clone().add(ray.multiplyScalar(3.2));

      joint3DPositions.push(worldPos);

      // Update joint mesh
      const mesh = this.jointMeshes[i];
      mesh.position.copy(worldPos);
      mesh.visible = true;

      // Color thumb and index tips differently if pinching
      if (i === 4 || i === 8) {
        const isPinching = gestureData.gesture.includes("PINCH");
        (mesh.material as THREE.MeshBasicMaterial).color.setHex(
          isPinching ? CONFIG.COLORS.AMBER : CONFIG.COLORS.CYAN
        );
      }
    }

    // Update Bone Lines
    if (this.boneLines) {
      const posAttr = this.boneLines.geometry.attributes.position as THREE.BufferAttribute;
      let ptr = 0;
      for (const [a, b] of BONE_CONNECTIONS) {
        const p1 = joint3DPositions[a];
        const p2 = joint3DPositions[b];
        posAttr.setXYZ(ptr++, p1.x, p1.y, p1.z);
        posAttr.setXYZ(ptr++, p2.x, p2.y, p2.z);
      }
      posAttr.needsUpdate = true;
    }

    // Update Pointer Ray from Index Tip (8)
    const indexTipPos = joint3DPositions[8];
    const indexMcpPos = joint3DPositions[5];
    const pointDir = indexTipPos.clone().sub(indexMcpPos).normalize();

    if (this.pointerRay) {
      this.pointerRay.position.copy(indexTipPos);
      const targetPos = indexTipPos.clone().add(pointDir.clone().multiplyScalar(15));
      this.pointerRay.lookAt(targetPos);
    }

    // Update Reticle Cursor on Index Tip
    this.reticleMesh.position.copy(indexTipPos);
    this.reticleMesh.quaternion.copy(this.camera.quaternion);

    // Scale reticle down when pinching
    const outerRing = this.reticleMesh.getObjectByName("OuterRing");
    if (outerRing) {
      outerRing.rotation.z += 0.05;
      const targetScale = gestureData.gesture.includes("PINCH") ? 0.6 : 1.0;
      this.reticleMesh.scale.lerp(new THREE.Vector3(targetScale, targetScale, targetScale), 0.2);
    }

    // Pinch Confirmation Ripple Animation
    if (gestureData.gesture === "PINCH_START") {
      this.pinchRippleMesh.visible = true;
      this.pinchRippleMesh.position.copy(indexTipPos);
      this.pinchRippleMesh.quaternion.copy(this.camera.quaternion);
      this.pinchRippleMesh.scale.set(0.1, 0.1, 0.1);
      (this.pinchRippleMesh.material as THREE.MeshBasicMaterial).opacity = 1.0;
    }

    if (this.pinchRippleMesh.visible) {
      this.pinchRippleMesh.scale.addScalar(0.08);
      const mat = this.pinchRippleMesh.material as THREE.MeshBasicMaterial;
      mat.opacity -= 0.05;
      if (mat.opacity <= 0) {
        this.pinchRippleMesh.visible = false;
      }
    }
  }
}
