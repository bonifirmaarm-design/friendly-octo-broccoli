import { STRIKES, DEFENCE } from './fighter.js';

// A strike is resolved once, in the middle of its animation, not on the frame
// the button is pressed. That gap is the whole game: it is what makes a jab
// beat a hook to the punch, and what gives the defender time to block after
// the wind-up has started.

export class Combat {
  constructor(player, bot, opts = {}) {
    this.player = player;
    this.bot = bot;
    this.time = 0;
    this.round = 1;
    this.rounds = opts.rounds ?? 3;
    this.roundLength = opts.roundLength ?? 90;
    this.roundClock = this.roundLength;
    this.phase = 'fight';        // fight | between | over
    this.breakClock = 0;
    this.events = [];            // consumed by the HUD and the camera
    this.winner = null;
  }

  emit(type, data = {}) { this.events.push({ type, ...data, at: this.time }); }

  attack(attacker, defender, move) {
    const spec = STRIKES[move];
    if (!spec || !attacker.has(move)) return false;
    if (this.time < attacker.busyUntil || attacker.grounded) return false;
    if (attacker.stamina < spec.cost) return false;

    attacker.stamina -= spec.cost;
    attacker.state = 'attack';
    attacker.play(move, { fade: 0.10 });
    attacker.busyUntil = this.time + spec.recover;
    attacker.pending = {
      move, defender,
      resolveAt: this.time + (spec.window[0] + spec.window[1]) / 2,
    };
    this.emit('strike-start', { by: attacker.profile.id, move });
    return true;
  }

  defend(fighter, kind) {
    const spec = DEFENCE[kind];
    if (!spec || !fighter.has(spec.clip)) return false;
    if (this.time < fighter.busyUntil || fighter.grounded) return false;
    if (fighter.stamina < spec.cost) return false;

    fighter.stamina -= spec.cost;
    fighter.state = spec.evade ? 'evade' : 'block';
    fighter.play(spec.clip, { fade: 0.08 });
    fighter.busyUntil = this.time + spec.hold;
    if (spec.evade) fighter.evadeUntil = this.time + spec.hold * 0.8;
    else fighter.guardUntil = this.time + spec.hold;
    if (spec.shift) {
      // Side-steps move him; that is what makes a dodge cost ground as well
      // as stamina, and why you can be walked into the fence.
      const angle = fighter.root.rotation.y;
      fighter.root.position.x += Math.cos(angle) * spec.shift;
      fighter.root.position.z -= Math.sin(angle) * spec.shift;
    }
    return true;
  }

  resolve(attacker, defender, move) {
    const spec = STRIKES[move];
    const range = attacker.distanceTo(defender);
    if (range > spec.reach) {
      this.emit('miss', { by: attacker.profile.id, move, reason: 'range' });
      return;
    }
    if (this.time < defender.evadeUntil) {
      this.emit('evaded', { by: defender.profile.id, move });
      return;
    }

    const blocking = this.time < defender.guardUntil;
    const chin = defender.profile.stats.chin / 100;
    const power = attacker.profile.stats.power / 100;
    let damage = spec.damage * (0.75 + power * 0.5) / (0.7 + chin * 0.45);
    if (blocking) damage *= 0.22;

    defender.health = Math.max(0, defender.health - damage);

    if (spec.takedown && !blocking) {
      defender.grounded = true;
      attacker.grounded = true;
      defender.play('takedown_double_leg_victim', { fade: 0.08 });
      defender.busyUntil = this.time + 1.4;
      attacker.busyUntil = this.time + 1.2;
      this.emit('takedown', { by: attacker.profile.id, move, damage });
      return;
    }

    if (blocking) {
      defender.play('block_high', { fade: 0.06 });
      this.emit('blocked', { by: defender.profile.id, move, damage });
      return;
    }

    if (defender.health <= 0) {
      defender.grounded = true;
      defender.knockdowns += 1;
      defender.play('knockdown', { fade: 0.06 });
      defender.busyUntil = this.time + 2.2;
      this.emit('knockdown', { by: attacker.profile.id, move });
      this.finish(attacker, defender, 'нокаут');
      return;
    }

    defender.state = 'hurt';
    defender.play(spec.reach > 1.4 || move.includes('body') ? 'hit_body' : 'hit_head',
      { fade: 0.05 });
    defender.busyUntil = this.time + 0.26;
    this.emit('hit', { by: attacker.profile.id, move, damage });
  }

  finish(winner, loser, how) {
    this.phase = 'over';
    this.winner = winner;
    this.loser = loser;
    this.emit('finish', { winner: winner.profile.id, how });
  }

  update(dt) {
    if (this.phase === 'over') { this.time += dt; this.stepFighters(dt); return; }
    this.time += dt;

    if (this.phase === 'between') {
      this.breakClock -= dt;
      if (this.breakClock <= 0) {
        this.round += 1;
        this.phase = 'fight';
        this.roundClock = this.roundLength;
        for (const f of [this.player, this.bot]) {
          f.stamina = Math.min(100, f.stamina + 45);
          f.health = Math.min(100, f.health + 6);
          f.grounded = false;
          f.state = 'idle';
        }
        this.emit('round-start', { round: this.round });
      }
      this.stepFighters(dt);
      return;
    }

    this.roundClock -= dt;
    if (this.roundClock <= 0) {
      if (this.round >= this.rounds) {
        const winner = this.player.health >= this.bot.health ? this.player : this.bot;
        const loser = winner === this.player ? this.bot : this.player;
        this.finish(winner, loser, 'решение судей');
      } else {
        this.phase = 'between';
        this.breakClock = 14;
        this.emit('round-end', { round: this.round });
      }
      return;
    }

    for (const attacker of [this.player, this.bot]) {
      const pending = attacker.pending;
      if (pending && this.time >= pending.resolveAt) {
        attacker.pending = null;
        this.resolve(attacker, pending.defender, pending.move);
      }
    }
    this.stepFighters(dt);
  }

  stepFighters(dt) {
    for (const f of [this.player, this.bot]) {
      f.update(dt);
      if (this.time >= f.busyUntil && f.state !== 'idle') {
        f.state = 'idle';
        if (f.grounded && this.phase !== 'over') {
          f.grounded = false;
          f.play('get_up', { fade: 0.12 });
          f.busyUntil = this.time + f.clipLength('get_up');
          f.state = 'getting-up';
        } else if (!f.grounded) {
          f.play('idle', { fade: 0.22, restart: false });
        }
      }
    }
    this.player.faceTowards(this.bot, 0.12);
    this.bot.faceTowards(this.player, 0.12);
    this.separate();
  }

  separate() {
    const a = this.player.root.position;
    const b = this.bot.root.position;
    const dx = b.x - a.x, dz = b.z - a.z;
    const d = Math.hypot(dx, dz);
    const minimum = 0.78;
    if (d > 1e-4 && d < minimum) {
      const push = (minimum - d) / 2;
      a.x -= (dx / d) * push; a.z -= (dz / d) * push;
      b.x += (dx / d) * push; b.z += (dz / d) * push;
    }
    // Keep both inside the cage: the apothem is 4.57, minus a body's width.
    for (const p of [a, b]) {
      const r = Math.hypot(p.x, p.z);
      if (r > 4.15) { p.x *= 4.15 / r; p.z *= 4.15 / r; }
    }
  }
}
