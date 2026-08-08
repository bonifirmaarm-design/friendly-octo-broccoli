import * as THREE from '../vendor/three.module.js';

// Three cameras, because a fight and a walkout want different things: the
// broadcast rig frames both men, the close rig sits low on the fence for
// exchanges, and the follow rig walks a fighter out of the tunnel.

const MODES = ['broadcast', 'close', 'corner'];

export class FightCamera {
  constructor(camera) {
    this.camera = camera;
    this.mode = 0;
    this.shake = 0;
    this.slowmo = 0;
    this.target = new THREE.Vector3();
    this.wanted = new THREE.Vector3();
    this.orbit = 0;
  }

  cycle() { this.mode = (this.mode + 1) % MODES.length; }

  kick(amount = 0.4) { this.shake = Math.min(1.2, this.shake + amount); }

  follow(position, lookAt, dt, lerp = 3.2) {
    this.wanted.copy(position);
    this.camera.position.lerp(this.wanted, Math.min(1, lerp * dt));
    this.target.lerp(lookAt, Math.min(1, lerp * dt));
    this.applyShake(dt);
    this.camera.lookAt(this.target);
  }

  applyShake(dt) {
    if (this.shake <= 0) return;
    this.shake = Math.max(0, this.shake - dt * 2.4);
    const s = this.shake * 0.07;
    this.camera.position.x += (Math.random() - 0.5) * s;
    this.camera.position.y += (Math.random() - 0.5) * s;
    this.camera.position.z += (Math.random() - 0.5) * s;
  }

  fight(a, b, dt) {
    const mid = new THREE.Vector3()
      .addVectors(a.root.position, b.root.position).multiplyScalar(0.5);
    const away = new THREE.Vector3()
      .subVectors(b.root.position, a.root.position);
    const spread = Math.max(1.2, away.length());
    away.normalize();
    // Sit off to the side of the line between them, so both are in frame and
    // neither hides the other.
    const side = new THREE.Vector3(-away.z, 0, away.x);
    this.orbit += dt * 0.05;

    let position, look;
    if (MODES[this.mode] === 'broadcast') {
      position = mid.clone()
        .add(side.clone().multiplyScalar(Math.cos(this.orbit) * 5.6))
        .add(away.clone().multiplyScalar(Math.sin(this.orbit) * 1.6));
      position.y = mid.y + 2.5;
      look = mid.clone().setY(mid.y + 1.25);
    } else if (MODES[this.mode] === 'close') {
      position = mid.clone().add(side.clone().multiplyScalar(3.1 + spread * 0.25));
      position.y = mid.y + 1.45;
      look = mid.clone().setY(mid.y + 1.15);
    } else {
      position = a.root.position.clone()
        .add(away.clone().multiplyScalar(-2.4))
        .add(side.clone().multiplyScalar(1.1));
      position.y = mid.y + 1.9;
      look = b.root.position.clone().setY(mid.y + 1.2);
    }
    this.follow(position, look, dt);
  }

  walkout(fighter, dt) {
    const angle = fighter.root.rotation.y;
    const forward = new THREE.Vector3(Math.sin(angle), 0, Math.cos(angle));
    const position = fighter.root.position.clone()
      .add(forward.clone().multiplyScalar(-3.6))
      .add(new THREE.Vector3(1.5, 1.85, 0));
    const look = fighter.root.position.clone()
      .add(forward.clone().multiplyScalar(1.5))
      .setY(fighter.root.position.y + 1.3);
    this.follow(position, look, dt, 2.4);
  }

  ceremony(centre, dt) {
    this.orbit += dt * 0.22;
    const position = new THREE.Vector3(
      centre.x + Math.cos(this.orbit) * 4.4,
      centre.y + 2.2,
      centre.z + Math.sin(this.orbit) * 4.4);
    this.follow(position, centre.clone().setY(centre.y + 1.2), dt, 2.0);
  }
}
