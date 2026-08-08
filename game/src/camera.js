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

  // Two vantages, chosen by where the fighter is rather than by offsetting
  // from him. Trailing the fighter down the tunnel puts the camera past the
  // tunnel's far end and inside its walls -- the box is 3.2 m wide and 14 m
  // long, so there is simply nowhere behind him to stand.
  walkout(fighter, dt) {
    const p = fighter.root.position;
    let position, look;
    if (p.z < -9.5) {
      // Still inside: watch from outside the mouth, looking in.
      position = new THREE.Vector3(6.4, 3.3, -12.0);
      look = p.clone().setY(p.y + 1.1);
    } else {
      // Out on the floor and climbing: swing round to the side of the stairs.
      position = new THREE.Vector3(6.0, p.y + 2.6, p.z - 3.2);
      look = p.clone().setY(p.y + 1.15);
    }
    this.follow(position, look, dt, 2.2);
  }

  // Between rounds both corners matter at once -- the water, the towel, the
  // coaches leaning through the fence -- and the two men are sitting on
  // opposite diagonals six metres apart. Nothing inside the cage is far
  // enough back to hold both, so the camera goes where the real one goes:
  // outside, on the empty diagonal, just above the top of the fence.
  corners(a, b, dt) {
    const mid = new THREE.Vector3()
      .addVectors(a.root.position, b.root.position).multiplyScalar(0.5);
    const away = new THREE.Vector3()
      .subVectors(b.root.position, a.root.position).normalize();
    const side = new THREE.Vector3(-away.z, 0, away.x);
    this.orbit += dt * 0.08;
    const position = mid.clone()
      .add(side.multiplyScalar(8.6))
      .add(away.clone().multiplyScalar(Math.sin(this.orbit) * 1.2));
    position.y = mid.y + 2.7;
    this.follow(position, mid.clone().setY(mid.y + 0.9), dt, 1.5);
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
