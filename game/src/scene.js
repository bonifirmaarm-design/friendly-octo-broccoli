import * as THREE from '../vendor/three.module.js';
import { GLTFLoader } from '../vendor/jsm/loaders/GLTFLoader.js';

const loader = new GLTFLoader();
export const load = (url) => new Promise((res, rej) => loader.load(url, res, undefined, rej));

export const ASSETS = '../build';

export function makeRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  return renderer;
}

export function lightArena(scene) {
  scene.background = new THREE.Color(0x05060a);
  scene.fog = new THREE.Fog(0x05060a, 34, 95);

  // three.js is physically correct since r155: spot intensity is candela and
  // illuminance falls as I/d². Every lamp below is therefore sized from its
  // own throw, I = E·d² with E ≈ 3.6 for a mid-grey surface -- which is why
  // the key at 15 m wants ~800 while the little lamp two metres off the
  // stairs wants ~20. Guessing one number for all of them is what produced
  // first a black arena and then a white one.
  scene.add(new THREE.HemisphereLight(0x44557a, 0x0d0f16, 0.22));
  scene.add(new THREE.AmbientLight(0x2a3244, 0.14));

  const key = new THREE.SpotLight(0xfff3e0, 820, 46, Math.PI / 4.4, 0.5, 1.15);   // d≈15 m
  key.position.set(0, 15, 0);
  key.target.position.set(0, 1.2, 0);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  key.shadow.camera.near = 4;
  key.shadow.camera.far = 30;
  key.shadow.bias = -0.0009;
  scene.add(key, key.target);

  for (const [x, z, colour] of [[8, 8, 0xbcd2ff], [-8, -8, 0xffd9b0]]) {
    const rake = new THREE.SpotLight(colour, 300, 50, Math.PI / 5, 0.65, 1.25);   // d≈14 m
    rake.position.set(x, 11, z);
    rake.target.position.set(0, 1.4, 0);
    scene.add(rake, rake.target);
  }

  // The tunnel gets its own light, otherwise the walkout happens in the dark:
  // every other lamp is aimed at the cage.
  const tunnel = new THREE.SpotLight(0xcfd8ee, 190, 30, Math.PI / 3.4, 0.7, 1.2);   // d≈7 m
  tunnel.position.set(0, 4.2, -16);
  tunnel.target.position.set(0, 0.8, -9);
  scene.add(tunnel, tunnel.target);

  const ramp = new THREE.PointLight(0xffe6c4, 22, 18, 1.2);   // d≈2.5 m
  ramp.position.set(0, 3.4, -7.4);
  scene.add(ramp);
  return key;
}

// Photographers' flashes. Sprites rather than lights: a few dozen real lights
// would cost more than the rest of the scene, and at this distance a flash is
// a bright dot and a momentary lift in ambience, nothing more.
export class Flashes {
  constructor(scene, positions) {
    this.scene = scene;
    const texture = flashTexture();
    this.sprites = positions.map((p) => {
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
        map: texture, color: 0xffffff, transparent: true,
        opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending,
      }));
      sprite.position.set(p[0], p[1], p[2]);
      sprite.scale.setScalar(1.6);
      scene.add(sprite);
      return { sprite, until: 0 };
    });
    this.rate = 0.55;      // flashes per second, per photographer
  }

  update(dt, time, excitement = 1) {
    for (const f of this.sprites) {
      if (time < f.until) {
        f.sprite.material.opacity = Math.max(0, (f.until - time) / 0.09);
      } else {
        f.sprite.material.opacity = 0;
        if (Math.random() < this.rate * excitement * dt) f.until = time + 0.09;
      }
    }
  }

  burst(time, count = 14) {
    const shuffled = [...this.sprites].sort(() => Math.random() - 0.5);
    shuffled.slice(0, count).forEach((f, i) => { f.until = time + 0.09 + i * 0.03; });
  }
}

function flashTexture() {
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext('2d');
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.25, 'rgba(255,250,235,0.75)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, size, size);
  return new THREE.CanvasTexture(canvas);
}

// Blood: a short-lived spray at the point of impact. Cheap points, no physics
// beyond gravity, because it is on screen for a third of a second.
export class Blood {
  constructor(scene, count = 160) {
    this.count = count;
    const geometry = new THREE.BufferGeometry();
    this.positions = new Float32Array(count * 3);
    this.velocity = new Float32Array(count * 3);
    this.life = new Float32Array(count);
    geometry.setAttribute('position', new THREE.BufferAttribute(this.positions, 3));
    this.points = new THREE.Points(geometry, new THREE.PointsMaterial({
      color: 0x8e1114, size: 0.045, transparent: true, opacity: 0.95,
      depthWrite: false,
    }));
    this.points.frustumCulled = false;
    scene.add(this.points);
    this.cursor = 0;
  }

  spray(at, strength = 1) {
    const n = Math.min(this.count, 12 + Math.round(strength * 14));
    for (let i = 0; i < n; i++) {
      const k = this.cursor = (this.cursor + 1) % this.count;
      this.positions[k * 3] = at.x;
      this.positions[k * 3 + 1] = at.y;
      this.positions[k * 3 + 2] = at.z;
      this.velocity[k * 3] = (Math.random() - 0.5) * 2.6 * strength;
      this.velocity[k * 3 + 1] = Math.random() * 2.2 * strength;
      this.velocity[k * 3 + 2] = (Math.random() - 0.5) * 2.6 * strength;
      this.life[k] = 0.55 + Math.random() * 0.35;
    }
  }

  update(dt) {
    for (let i = 0; i < this.count; i++) {
      if (this.life[i] <= 0) continue;
      this.life[i] -= dt;
      this.velocity[i * 3 + 1] -= 9.8 * dt;
      this.positions[i * 3] += this.velocity[i * 3] * dt;
      this.positions[i * 3 + 1] += this.velocity[i * 3 + 1] * dt;
      this.positions[i * 3 + 2] += this.velocity[i * 3 + 2] * dt;
      if (this.positions[i * 3 + 1] < 1.26) { this.life[i] = 0; }
      if (this.life[i] <= 0) {
        this.positions[i * 3 + 1] = -100;   // park it out of sight
      }
    }
    this.points.geometry.attributes.position.needsUpdate = true;
  }
}
