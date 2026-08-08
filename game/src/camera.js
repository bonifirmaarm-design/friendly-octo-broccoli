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

  // Between rounds the camera does what the broadcast does: it sits on one
  // man's face while he drinks and gets wiped down, then cuts to the other
  // corner and does the same. Framing both at once puts them six metres
  // apart on opposite diagonals and shows neither -- you cannot see a man
  // take a bottle from thirty feet.
  //
  // `elapsed` runs from the bell; the cut lands at the halfway mark.
  corners(a, b, elapsed, total, dt) {
    const half = total / 2;
    const first = elapsed < half;
    const subject = first ? a : b;
    const since = first ? elapsed : elapsed - half;

    // In front of him at head height, easing closer over the beat. The
    // camera has to stand *inside* the cage: he sits at 3.3 m from the
    // centre and the fence is at 4.57, so backing away from the middle to
    // frame him puts the lens outside the mesh and shoots him through the
    // chain-link.
    const head = subject.root.position.clone().setY(subject.root.position.y + 1.42);
    const out = subject.root.position.clone().setY(0).normalize();
    const push = Math.min(1, since / half);
    const side = new THREE.Vector3(-out.z, 0, out.x);
    const position = head.clone()
      .addScaledVector(out, -(2.1 - push * 0.6))
      .addScaledVector(side, 0.5 + push * 0.25)
      .setY(head.y + 0.28);
    // Snap on the cut so it reads as a new shot rather than a long swoop.
    this.follow(position, head, dt, since < 0.1 ? 999 : 1.6);
  }

  // The ending is a shot, not an orbit. It cuts to a wide from outside the
  // cage while the three of them find their marks, then pushes in on a
  // straight line to a chest-height two-shot for the belt and the raised
  // arm. Circling them the whole time gave the moment nowhere to go.
  ceremony(centre, elapsed, dt) {
    const push = Math.min(1, Math.max(0, (elapsed - 2.6) / 6.0));
    const eased = push * push * (3 - 2 * push);        // ease in and out
    const distance = 7.4 - eased * 4.5;
    const height = 3.0 - eased * 1.05;

    // The cut: for the first beat the camera is not where it was during the
    // fight, it is somewhere new, and it stays on that axis all the way in.
    const position = new THREE.Vector3(
      centre.x + Math.sin(-0.34) * distance,
      centre.y + height,
      centre.z - Math.cos(-0.34) * distance);
    const look = centre.clone().setY(centre.y + 1.15 + eased * 0.15);
    // Snap on the first frame so it reads as a cut; glide from then on.
    this.follow(position, look, dt, elapsed < 0.08 ? 999 : 1.9);
  }
}
