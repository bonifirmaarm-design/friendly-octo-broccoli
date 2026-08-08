// The bot. It picks by range first and personality second, because a wrestler
// who shoots from four metres away just looks broken -- the style weights only
// decide between the moves that make sense from where he is standing.

const PUNCHES = ['jab', 'cross', 'hook_L', 'hook_R', 'uppercut_R', 'overhand_R', 'body_hook'];
const CLOSE = ['elbow', 'knee', 'uppercut_L', 'body_hook'];
const KICKS = ['kick_low', 'kick_body', 'kick_high', 'front_kick', 'teep',
  'oblique_kick', 'side_kick', 'spinning_back_kick'];
const TAKEDOWNS = ['takedown_double_leg', 'takedown_single_leg',
  'body_lock_throw', 'trip_throw'];

const pick = (list, has) => {
  const ok = list.filter(has);
  return ok.length ? ok[(Math.random() * ok.length) | 0] : null;
};

export class Bot {
  constructor(fighter, opponent, combat, difficulty = 0.55) {
    this.me = fighter;
    this.foe = opponent;
    this.combat = combat;
    this.difficulty = difficulty;
    this.nextDecision = 0;
    this.approach = 0;
  }

  think(dt) {
    const c = this.combat;
    if (c.phase !== 'fight') return;
    const me = this.me;

    // On the ground the choices are different: hit from the top, work to get
    // out from the bottom. Treating it as "busy, do nothing" is what makes a
    // bot lie there until the referee stands him up.
    if (c.ground) {
      if (c.time < this.nextDecision) return;

      // Caught in a hold, there is exactly one thing to do, and a bot that
      // decides at human speed does it at human speed.
      const held = c.submission;
      if (held) {
        if (held.on === me) {
          c.struggle(me);
          this.nextDecision = c.time + 0.16 + Math.random() * 0.14;
        } else {
          this.nextDecision = c.time + 0.4;
        }
        return;
      }

      const grappling = me.profile.stats.grappling;
      if (c.ground.top === me) {
        // A grappler goes hunting for the neck; a striker just hits him.
        if (Math.random() < grappling / 340 && c.attemptSubmission(me, 'sub_choke')) {
          this.nextDecision = c.time + 1.0;
          return;
        }
        c.groundStrike(me);
        this.nextDecision = c.time + 0.5 + Math.random() * 0.5;
      } else if (c.ground.bottom === me) {
        if (Math.random() < grappling / 380 && c.attemptSubmission(me, 'sub_armbar')) {
          this.nextDecision = c.time + 1.0;
          return;
        }
        c.groundEscape(me, grappling > 80 && Math.random() < 0.45
          ? 'ground_sweep' : 'ground_escape');
        this.nextDecision = c.time + 1.4 + Math.random() * 0.8;
      }
      return;
    }

    if (c.time < me.busyUntil || me.grounded) return;
    if (c.time < this.nextDecision) { this.walk(dt); return; }

    const range = me.distanceTo(this.foe);
    const style = me.profile.style;
    const has = (n) => me.has(n);
    const tired = me.stamina < 28;

    // React to the incoming strike rather than to the hit.
    const incoming = this.foe.pending;
    if (incoming && Math.random() < this.difficulty * 0.75) {
      const kind = Math.random() < 0.45 ? 'block_high'
        : (Math.random() < 0.5 ? 'dodge_left' : 'dodge_right');
      if (c.defend(me, kind)) {
        this.nextDecision = c.time + 0.30;
        return;
      }
    }

    if (tired) {
      c.defend(me, 'block_high');
      this.nextDecision = c.time + 0.8;
      return;
    }

    let move = null;
    if (range > 2.1) {
      this.approach = 1;                       // too far: close the distance
      this.nextDecision = c.time + 0.18;
      this.walk(dt);
      return;
    }
    if (range > 1.55) {
      move = Math.random() < style.kick * 1.6 ? pick(KICKS, has) : pick(PUNCHES, has);
    } else if (range > 1.05) {
      const roll = Math.random();
      if (roll < style.takedown * 1.5) move = pick(TAKEDOWNS, has);
      else if (roll < style.takedown * 1.5 + style.kick) move = pick(KICKS, has);
      else move = pick(PUNCHES, has);
    } else {
      move = Math.random() < style.takedown * 1.8 ? pick(TAKEDOWNS, has) : pick(CLOSE, has);
    }

    this.approach = 0;
    if (move && c.attack(me, this.foe, move)) {
      this.nextDecision = c.time + 0.12 + Math.random() * (1.1 - this.difficulty * 0.7);
    } else {
      this.nextDecision = c.time + 0.25;
    }
  }

  walk(dt) {
    if (!this.approach) return;
    const me = this.me;
    const speed = 1.9 * dt;
    const angle = me.root.rotation.y;
    me.root.position.x += Math.sin(angle) * speed;
    me.root.position.z += Math.cos(angle) * speed;
    if (me.state !== 'walking') {
      me.state = 'walking';
      me.play('walk', { fade: 0.2, restart: false });
      me.busyUntil = 0;
    }
  }
}
