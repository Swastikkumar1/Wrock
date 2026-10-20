import * as THREE from "three";
import { CameraMode } from "../types";
import { CONFIG } from "../config";

export class GodsEyeScene {
  public scene: THREE.Scene;
  public camera: THREE.PerspectiveCamera;
  public renderer: THREE.WebGLRenderer;
  private canvas: HTMLCanvasElement;

  public currentMode: CameraMode = "ORBITAL";
  private targetCameraPos: THREE.Vector3 = new THREE.Vector3(13, 13, 13);
  private targetLookAt: THREE.Vector3 = new THREE.Vector3(0, 1.4, 0);
  private currentLookAt: THREE.Vector3 = new THREE.Vector3(0, 1.4, 0);

  // Optical Pinch Zoom & Pan State
  public zoomLevel: number = 1.0;
  public panOffset: THREE.Vector2 = new THREE.Vector2(0, 0);

  // Ground Tactical Grid & Radar Rings
  private gridHelper: THREE.GridHelper | null = null;
  private radarRingsGroup: THREE.Group;
  private sensorConeGroup: THREE.Group;

  constructor(canvas: HTMLCanvasElement) {
    this.canvas = canvas;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(CONFIG.COLORS.BG);
    this.scene.fog = new THREE.FogExp2(CONFIG.COLORS.BG, 0.015);

    // Camera setup
    const aspect = window.innerWidth / window.innerHeight;
    this.camera = new THREE.PerspectiveCamera(CONFIG.CAMERA.FOV, aspect, CONFIG.CAMERA.NEAR, CONFIG.CAMERA.FAR);
    this.camera.position.set(13, 13, 13);

    // WebGL Renderer setup
    this.renderer = new THREE.WebGLRenderer({
      canvas: this.canvas,
      antialias: true,
      alpha: true,
      powerPreference: "high-performance",
    });
    this.renderer.setSize(window.innerWidth, window.innerHeight);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    this.radarRingsGroup = new THREE.Group();
    this.scene.add(this.radarRingsGroup);

    this.sensorConeGroup = new THREE.Group();
    this.scene.add(this.sensorConeGroup);

    this.initLighting();
    this.initTacticalGrid();
    this.initStars();
    this.initWindowResize();
    this.setCameraMode("ORBITAL");
  }

  private initLighting() {
    const ambientLight = new THREE.AmbientLight(0x102030, 1.5);
    this.scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(CONFIG.COLORS.CYAN, 2.0);
    dirLight.position.set(20, 40, 20);
    this.scene.add(dirLight);

    const bluePoint = new THREE.PointLight(CONFIG.COLORS.CYAN, 3.0, 50);
    bluePoint.position.set(0, 5, 0);
    this.scene.add(bluePoint);
  }

  private initTacticalGrid() {
    // 3D Tactical Plane Grid
    this.gridHelper = new THREE.GridHelper(70, 70, CONFIG.COLORS.CYAN, CONFIG.COLORS.GRID);
    this.gridHelper.position.y = 0;
    this.scene.add(this.gridHelper);

    // Concentric Radar Distance Rings (5km, 10km, 15km, 20km, 25km scale)
    [5, 10, 15, 20, 25].forEach((r) => {
      const ringGeo = new THREE.RingGeometry(r - 0.04, r, 64);
      const ringMat = new THREE.MeshBasicMaterial({
        color: CONFIG.COLORS.CYAN,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.25,
      });
      const ringMesh = new THREE.Mesh(ringGeo, ringMat);
      ringMesh.rotation.x = Math.PI / 2;
      ringMesh.position.y = 0.02;
      this.radarRingsGroup.add(ringMesh);
    });

    // Central Tactical Earth / Map Projection Sphere
    const earthGeo = new THREE.SphereGeometry(3.0, 32, 32);
    const earthMat = new THREE.MeshStandardMaterial({
      color: 0x071b2d,
      wireframe: true,
      roughness: 0.6,
      metalness: 0.8,
      emissive: 0x003344,
      emissiveIntensity: 0.4,
    });
    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthMesh.name = "TacticalGlobe";
    earthMesh.position.set(0, -2.0, 0);
    this.scene.add(earthMesh);
  }

  private initStars() {
    const starCount = 600;
    const starGeo = new THREE.BufferGeometry();
    const starPos = new Float32Array(starCount * 3);

    for (let i = 0; i < starCount * 3; i += 3) {
      starPos[i] = (Math.random() - 0.5) * 160;
      starPos[i + 1] = Math.random() * 80 + 10;
      starPos[i + 2] = (Math.random() - 0.5) * 160;
    }

    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    const starMat = new THREE.PointsMaterial({
      color: CONFIG.COLORS.CYAN,
      size: 0.35,
      transparent: true,
      opacity: 0.7,
    });

    const starField = new THREE.Points(starGeo, starMat);
    this.scene.add(starField);
  }

  private initWindowResize() {
    window.addEventListener("resize", () => {
      this.camera.aspect = window.innerWidth / window.innerHeight;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(window.innerWidth, window.innerHeight);
    });
  }

  public setCameraMode(mode: CameraMode, targetEntityPos?: THREE.Vector3) {
    this.currentMode = mode;

    switch (mode) {
      case "GODS_EYE":
        // Direct top-down 90-degree satellite view (EDITH mode) with zoom and pan
        const alt = 28.0 / this.zoomLevel;
        this.targetCameraPos.set(this.panOffset.x + 0.01, alt, this.panOffset.y + 0.01);
        this.targetLookAt.set(this.panOffset.x, 0, this.panOffset.y);
        break;

      case "ORBITAL":
        // 45-degree angled tactical isometric view
        this.targetCameraPos.set(13.0, 13.0, 13.0);
        this.targetLookAt.set(0, 1.4, 0);
        break;

      case "TACTICAL_DRONE":
        // Chase camera following active drone
        if (targetEntityPos) {
          this.targetCameraPos.copy(targetEntityPos).add(new THREE.Vector3(-2.5, 2.0, 3.5));
          this.targetLookAt.copy(targetEntityPos);
        } else {
          this.targetCameraPos.set(-4.5, 5.0, 5.0);
          this.targetLookAt.set(-4.5, 3.2, 2.0);
        }
        break;

      case "HOLOGRAM":
        // Front-facing Arc-Reactor workspace view
        this.targetCameraPos.set(0, 5.0, 9.0);
        this.targetLookAt.set(0, 1.0, 0);
        break;
    }
  }

  // Optical Pinch-To-Zoom Handler
  public adjustZoom(factor: number) {
    this.zoomLevel = Math.max(0.35, Math.min(4.5, this.zoomLevel * factor));
    if (this.currentMode === "GODS_EYE") {
      this.targetCameraPos.y = 28.0 / this.zoomLevel;
    }
    return this.zoomLevel;
  }

  // Optical Pinch-To-Pan Handler
  public adjustPan(dx: number, dy: number) {
    const scale = (this.targetCameraPos.y / 28.0) * 15.0;
    this.panOffset.x += dx * scale;
    this.panOffset.y += dy * scale;

    if (this.currentMode === "GODS_EYE") {
      this.targetCameraPos.x = this.panOffset.x + 0.01;
      this.targetCameraPos.z = this.panOffset.y + 0.01;
      this.targetLookAt.x = this.panOffset.x;
      this.targetLookAt.z = this.panOffset.y;
    }
  }

  public resetPanAndZoom() {
    this.zoomLevel = 1.0;
    this.panOffset.set(0, 0);
    if (this.currentMode === "GODS_EYE") {
      this.setCameraMode("GODS_EYE");
    }
  }

  public focusOnEntity(pos: THREE.Vector3) {
    this.panOffset.set(pos.x, pos.z);
    if (this.currentMode === "GODS_EYE") {
      this.targetCameraPos.x = pos.x + 0.01;
      this.targetCameraPos.z = pos.z + 0.01;
      this.targetLookAt.set(pos.x, 0, pos.z);
    }
  }

  public update(dt: number) {
    // Smooth camera position damping
    this.camera.position.lerp(this.targetCameraPos, 0.08);
    this.currentLookAt.lerp(this.targetLookAt, 0.08);
    this.camera.lookAt(this.currentLookAt);

    // Rotate tactical globe slowly
    const globe = this.scene.getObjectByName("TacticalGlobe");
    if (globe) {
      globe.rotation.y += 0.002;
    }
  }

  public render() {
    this.renderer.render(this.scene, this.camera);
  }
}
