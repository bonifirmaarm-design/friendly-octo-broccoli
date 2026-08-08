import * as THREE from '../vendor/three.module.js';

// The mesh is authored ~2 units tall; the arena is in metres.
export const FIGHTER_SCALE = 1.85 / 1.994;

// How long after a strike starts its damage window opens and closes, and how
// hard it lands. Timings are read off the clips: every strike fires on its
// third keyframe, roughly 40% of the way in.
export const STRIKES = {
  jab:          { window: [0.16, 0.26], damage: 5,  cost: 4,  reach: 1.35, recover: 0.30 },
  cross:        { window: [0.20, 0.32], damage: 9,  cost: 7,  reach: 1.40, recover: 0.38 },
  hook_L:       { window: [0.22, 0.34], damage: 10, cost: 8,  reach: 1.25, recover: 0.40 },
  hook_R:       { window: [0.22, 0.34], damage: 10, cost: 8,  reach: 1.25, recover: 0.40 },
  uppercut_L:   { window: [0.23, 0.35], damage: 12, cost: 9,  reach: 1.15, recover: 0.42 },
  uppercut_R:   { window: [0.23, 0.35], damage: 12, cost: 9,  reach: 1.15, recover: 0.42 },
  overhand_R:   { window: [0.25, 0.38], damage: 14, cost: 11, reach: 1.35, recover: 0.46 },
  body_hook:    { window: [0.22, 0.34], damage: 8,  cost: 7,  reach: 1.20, recover: 0.40 },
  elbow:        { window: [0.17, 0.27], damage: 11, cost: 7,  reach: 1.05, recover: 0.32 },
  spinning_elbow: { window: [0.26, 0.40], damage: 18, cost: 15, reach: 1.20, recover: 0.60 },
  spinning_back_kick: { window: [0.28, 0.44], damage: 19, cost: 16, reach: 1.70, recover: 0.62 },
  kick_low:     { window: [0.24, 0.38], damage: 8,  cost: 8,  reach: 1.55, recover: 0.44 },
  kick_body:    { window: [0.27, 0.42], damage: 12, cost: 10, reach: 1.60, recover: 0.50 },
  kick_high:    { window: [0.30, 0.46], damage: 17, cost: 13, reach: 1.65, recover: 0.56 },
  front_kick:   { window: [0.22, 0.36], damage: 9,  cost: 8,  reach: 1.70, recover: 0.42 },
  teep:         { window: [0.18, 0.30], damage: 6,  cost: 6,  reach: 1.75, recover: 0.34 },
  oblique_kick: { window: [0.19, 0.31], damage: 7,  cost: 6,  reach: 1.65, recover: 0.36 },
  side_kick:    { window: [0.26, 0.40], damage: 13, cost: 11, reach: 1.80, recover: 0.50 },
  knee:         { window: [0.22, 0.34], damage: 13, cost: 10, reach: 1.05, recover: 0.42 },
  flying_knee:  { window: [0.26, 0.40], damage: 20, cost: 18, reach: 1.50, recover: 0.66 },
  superman_punch: { window: [0.25, 0.38], damage: 16, cost: 14, reach: 1.60, recover: 0.58 },
  takedown_double_leg: { window: [0.34, 0.62], damage: 10, cost: 20, reach: 1.30,
                         recover: 1.00, takedown: true },
  takedown_single_leg: { window: [0.36, 0.66], damage: 9,  cost: 20, reach: 1.30,
                         recover: 1.05, takedown: true },
  body_lock_throw:     { window: [0.40, 0.70], damage: 12, cost: 22, reach: 1.10,
                         recover: 1.06, takedown: true },
  trip_throw:          { window: [0.38, 0.68], damage: 11, cost: 20, reach: 1.10,
                         recover: 1.02, takedown: true },
  ground_pound: { window: [0.10, 0.20], damage: 7, cost: 5, reach: 1.30, recover: 0.24 },
};

// What each signature combination is made of, in order. Kept in step with
// the `combos` tables in tools/moves.py, which is what the clips were baked
// from -- the game needs the move list to know what damage to queue, and the
// clip alone cannot tell it.
export const COMBOS = {
  combo_chain_wrestle: ['jab', 'overhand_R', 'level_change'],
  combo_smash: ['cross', 'knee', 'takedown_double_leg'],
  combo_ground_and_pound: ['takedown_double_leg', 'ground_pound'],
  combo_range: ['oblique_kick', 'jab', 'side_kick'],
  combo_elbows: ['jab', 'elbow', 'spinning_elbow'],
  combo_grind: ['jab', 'cross', 'trip_throw'],
  combo_strike_takedown: ['kick_low', 'cross', 'takedown_double_leg'],
  combo_left_hand: ['jab', 'cross', 'hook_L'],
  combo_switch: ['teep', 'cross', 'spinning_back_kick'],
};

// What each key means, per fighter.
//
// Nobody owns every strike: Conor has no wrestling at all, Khabib has no head
// kick, Jones has no uppercut. A key wired straight to one move therefore
// does nothing at all for some of the roster -- silently, with no animation
// and no sound, which does not read as "this fighter cannot do that" but as
// "this game is broken". So a key names a slot, and the slot lists what to
// try in order until it finds something the man actually has.
const SLOT_ORTHODOX = {
  jab: ['jab', 'cross'],
  cross: ['cross', 'overhand_R', 'jab'],
  hook: ['hook_L', 'hook_R', 'body_hook', 'overhand_R', 'elbow'],
  uppercut: ['uppercut_R', 'uppercut_L', 'elbow', 'knee', 'hook_R', 'hook_L'],
  kick_low: ['kick_low', 'oblique_kick', 'teep', 'front_kick', 'kick_body'],
  kick_body: ['kick_body', 'front_kick', 'teep', 'side_kick', 'knee', 'kick_low'],
  kick_high: ['kick_high', 'spinning_back_kick', 'side_kick', 'kick_body', 'knee'],
  takedown: ['takedown_double_leg', 'takedown_single_leg', 'body_lock_throw',
    'trip_throw', 'level_change', 'knee'],
};

// A southpaw leads with the other hand, so the pairs swap. Everything else is
// the same list.
const SLOT_SOUTHPAW = {
  ...SLOT_ORTHODOX,
  hook: ['hook_R', 'hook_L', 'body_hook', 'overhand_R', 'elbow'],
  uppercut: ['uppercut_L', 'uppercut_R', 'elbow', 'knee', 'hook_L', 'hook_R'],
};

export const SLOTS = Object.keys(SLOT_ORTHODOX);

export const DEFENCE = {
  block_high: { clip: 'block_high', hold: 0.34, cost: 2 },
  block_body: { clip: 'block_body', hold: 0.34, cost: 2 },
  dodge_left: { clip: 'dodge_left', hold: 0.26, cost: 6, evade: true, shift: 0.55 },
  dodge_right: { clip: 'dodge_right', hold: 0.26, cost: 6, evade: true, shift: -0.55 },
  weave: { clip: 'weave', hold: 0.30, cost: 7, evade: true },
};

// Positions rather than motions: these are authored as loops with the first
// and last keyframe the same, and they are held until something ends them.
// A submission left on LoopOnce freezes on its last frame, which reads as the
// hold going slack at exactly the moment it should be at its tightest.
// The staff clips are the same idea: the referee watches and counts and the
// coach shouts, holds something out or jumps for as long as the game needs
// him to, so those loop too. Only his one-shots -- the break, the wave-off,
// the belt, the raised hand -- play once and stop.
const HELD = new Set(['ground_top', 'ground_bottom', 'corner_sit', 'hand_raised',
  'sub_choke', 'sub_choke_victim', 'sub_armbar', 'sub_armbar_victim',
  'stand', 'ref_watch', 'ref_count',
  'coach_watch', 'coach_shout', 'coach_hand', 'coach_jump']);

export class Fighter {
  constructor(gltf, profile) {
    this.profile = profile;
    this.root = new THREE.Group();
    this.model = gltf.scene;
    this.model.scale.setScalar(FIGHTER_SCALE);
    this.model.traverse((o) => {
      if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; o.frustumCulled = false; }
    });
    this.root.add(this.model);

    this.mixer = new THREE.AnimationMixer(this.model);
    this.actions = new Map();
    for (const clip of gltf.animations) {
      const action = this.mixer.clipAction(clip);
      const loops = clip.name === 'idle' || clip.name.startsWith('walk')
        || clip.name === 'climb' || clip.name === 'ground_pound'
        || HELD.has(clip.name);
      action.loop = loops ? THREE.LoopRepeat : THREE.LoopOnce;
      action.clampWhenFinished = !loops;
      this.actions.set(clip.name, action);
    }

    this.current = null;
    this.health = 100;
    this.stamina = 100;
    this.state = 'idle';
    this.busyUntil = 0;
    this.pending = null;       // strike awaiting its damage window
    this.guardUntil = 0;
    this.evadeUntil = 0;
    this.grounded = false;
    this.knockdowns = 0;
    // Damage per target, shown on the HUD the way a broadcast shows it: a
    // man whose lead leg is gone is a different problem from one whose head
    // is gone, and the health bar alone cannot say which.
    this.parts = { head: 100, leg: 100 };
  }

  has(name) { return this.actions.has(name); }

  // The move this fighter throws for a given key. Null only if he has nothing
  // in that family at all, which the caller can then say out loud.
  pick(slot) {
    const table = this.profile.stance === 'southpaw' ? SLOT_SOUTHPAW : SLOT_ORTHODOX;
    return (table[slot] || []).find((n) => this.has(n) && STRIKES[n]) || null;
  }

  play(name, { fade = 0.18, restart = true } = {}) {
    const action = this.actions.get(name);
    if (!action) return null;
    if (this.current === action && !restart) return action;
    action.reset();
    action.enabled = true;
    action.setEffectiveWeight(1);
    if (this.current && this.current !== action) {
      this.current.crossFadeTo(action, fade, false);
      action.play();
    } else {
      action.fadeIn(fade).play();
    }
    this.current = action;
    return action;
  }

  clipLength(name) {
    const action = this.actions.get(name);
    return action ? action.getClip().duration : 0;
  }

  faceTowards(target, lerp = 0.18) {
    const dx = target.root.position.x - this.root.position.x;
    const dz = target.root.position.z - this.root.position.z;
    const wanted = Math.atan2(dx, dz);
    let delta = wanted - this.root.rotation.y;
    while (delta > Math.PI) delta -= Math.PI * 2;
    while (delta < -Math.PI) delta += Math.PI * 2;
    this.root.rotation.y += delta * lerp;
  }

  distanceTo(other) {
    return this.root.position.distanceTo(other.root.position);
  }

  update(dt) {
    this.mixer.update(dt);
    // Stamina comes back slowly, and only when not mid-move.
    if (this.state === 'idle') {
      this.stamina = Math.min(100, this.stamina + dt * 11);
    } else {
      this.stamina = Math.min(100, this.stamina + dt * 3);
    }
  }
}
