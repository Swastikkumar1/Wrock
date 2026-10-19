import * as THREE from "three";
import { CONFIG } from "../config";

export class WrockOrbVisualizer {
  public group: THREE.Group;
  private coreMesh: THREE.Mesh;
  private ring1: THREE.Mesh;
  private ring2: THREE.Mesh;
  private ring3: THREE.Mesh;
  private isSpeaking: boolean = false;
  private isListening: boolean = false;

  constructor() {
    this.group = new THREE.Group();
    this.group.name = "WrockOrbGroup";
    this.group.position.set(0, 1.8, 0);

    // Glowing Inner Energy Sphere
    const coreGeo = new THREE.SphereGeometry(0.5, 24, 24);
    const coreMat = new THREE.MeshStandardMaterial({
      color: CONFIG.COLORS.CYAN,
      emissive: CONFIG.COLORS.CYAN,
      emissiveIntensity: 1.2,
      wireframe: true,
      transparent: true,
      opacity: 0.85,
    });
    this.coreMesh = new THREE.Mesh(coreGeo, coreMat);
    this.group.add(this.coreMesh);

    // Gyroscope Ring 1
    const ring1Geo = new THREE.TorusGeometry(0.85, 0.02, 16, 64);
    const ring1Mat = new THREE.MeshBasicMaterial({ color: CONFIG.COLORS.CYAN });
    this.ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
    this.group.add(this.ring1);

    // Gyroscope Ring 2
    const ring2Geo = new THREE.TorusGeometry(1.1, 0.02, 16, 64);
    const ring2Mat = new THREE.MeshBasicMaterial({ color: CONFIG.COLORS.AMBER, transparent: true, opacity: 0.7 });
    this.ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
    this.ring2.rotation.x = Math.PI / 3;
    this.group.add(this.ring2);

    // Gyroscope Ring 3
    const ring3Geo = new THREE.TorusGeometry(1.35, 0.015, 16, 64);
    const ring3Mat = new THREE.MeshBasicMaterial({ color: CONFIG.COLORS.CYAN, transparent: true, opacity: 0.5 });
    this.ring3 = new THREE.Mesh(ring3Geo, ring3Mat);
    this.ring3.rotation.y = Math.PI / 4;
    this.group.add(this.ring3);
  }

  public setVoiceState(isListening: boolean, isSpeaking: boolean) {
    this.isListening = isListening;
    this.isSpeaking = isSpeaking;

    const coreMat = this.coreMesh.material as THREE.MeshStandardMaterial;
    if (isSpeaking) {
      coreMat.color.setHex(CONFIG.COLORS.AMBER);
      coreMat.emissive.setHex(CONFIG.COLORS.AMBER);
    } else if (isListening) {
      coreMat.color.setHex(CONFIG.COLORS.EMERALD);
      coreMat.emissive.setHex(CONFIG.COLORS.EMERALD);
    } else {
      coreMat.color.setHex(CONFIG.COLORS.CYAN);
      coreMat.emissive.setHex(CONFIG.COLORS.CYAN);
    }
  }

  public update(time: number) {
    const speed = this.isSpeaking ? 3.0 : this.isListening ? 2.0 : 1.0;

    this.ring1.rotation.x += 0.015 * speed;
    this.ring1.rotation.y += 0.02 * speed;

    this.ring2.rotation.y -= 0.018 * speed;
    this.ring2.rotation.z += 0.012 * speed;

    this.ring3.rotation.x += 0.008 * speed;
    this.ring3.rotation.z -= 0.015 * speed;

    // Breath / pulse scale
    const pulse = 1.0 + Math.sin(time * (this.isSpeaking ? 8.0 : 3.0)) * (this.isSpeaking ? 0.15 : 0.06);
    this.coreMesh.scale.set(pulse, pulse, pulse);
  }
}

// Alias for backward compatibility
export const JarvisOrbVisualizer = WrockOrbVisualizer;
