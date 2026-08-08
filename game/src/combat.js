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
    this.ground = null;          // { top, bottom, since, lastAction }
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
      this.toGround(attacker, defender);
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

  // -- the ground -----------------------------------------------------------
  //
  // A takedown that ends the exchange is not MMA. What follows is a position:
  // one man on top, the other working to stand or reverse, and a referee who
  // stands them both up if nothing happens for long enough.

  toGround(top, bottom) {
    this.ground = { top, bottom, since: this.time, lastAction: this.time };
    for (const f of [top, bottom]) { f.grounded = true; f.pending = null; }
    top.play('ground_top', { fade: 0.15 });
    bottom.play('ground_bottom', { fade: 0.15 });
    top.state = 'ground-top';
    bottom.state = 'ground-bottom';
    top.busyUntil = bottom.busyUntil = this.time + 0.9;
    this.emit('ground', { top: top.profile.id, bottom: bottom.profile.id });
  }

  groundStrike(fighter) {
    const g = this.ground;
    if (!g || g.top !== fighter || this.time < fighter.busyUntil) return false;
    if (fighter.stamina < 5) return false;
    fighter.stamina -= 5;
    fighter.play('ground_pound', { fade: 0.08 });
    fighter.busyUntil = this.time + 0.42;
    g.lastAction = this.time;

    const power = fighter.profile.stats.power / 100;
    const chin = g.bottom.profile.stats.chin / 100;
    const damage = 7 * (0.75 + power * 0.5) / (0.7 + chin * 0.45);
    g.bottom.health = Math.max(0, g.bottom.health - damage);
    this.emit('hit', { by: fighter.profile.id, move: 'ground_pound', damage, ground: true });
    if (g.bottom.health <= 0) {
      g.bottom.play('knockdown', { fade: 0.06 });
      this.emit('knockdown', { by: fighter.profile.id, move: 'ground_pound' });
      this.finish(fighter, g.bottom, 'остановка в партере');
    }
    return true;
  }

  groundEscape(fighter, kind = 'ground_escape') {
    const g = this.ground;
    if (!g || g.bottom !== fighter || this.time < fighter.busyUntil) return false;
    const cost = kind === 'ground_sweep' ? 22 : 16;
    if (fighter.stamina < cost) return false;
    fighter.stamina -= cost;
    g.lastAction = this.time;

    // Grappling decides it. A wrestler holds the man underneath down; a
    // striker on top gets reversed.
    const mine = fighter.profile.stats.grappling;
    const theirs = g.top.profile.stats.grappling;
    const chance = 0.28 + (mine - theirs) / 220;
    fighter.play(kind, { fade: 0.1 });
    fighter.busyUntil = this.time + fighter.clipLength(kind);

    if (Math.random() < chance) {
      if (kind === 'ground_sweep') {
        const wasTop = g.top;
        this.toGround(fighter, wasTop);
        this.emit('sweep', { by: fighter.profile.id });
      } else {
        this.standUp('встал');
      }
      return true;
    }
    this.emit('escape-failed', { by: fighter.profile.id });
    return true;
  }

  standUp(reason) {
    const g = this.ground;
    if (!g) return;
    for (const f of [g.top, g.bottom]) {
      f.grounded = false;
      f.state = 'idle';
      f.play(f.has('stand_up') ? 'stand_up' : 'get_up', { fade: 0.15 });
      f.busyUntil = this.time + 0.9;
    }
    this.ground = null;
    this.emit('stand-up', { reason });
  }

  updateGround(dt) {
    const g = this.ground;
    if (!g) return;
    // The referee steps in when the position has gone nowhere. Twelve seconds
    // is short for a real fight and about right for a game.
    if (this.time - g.lastAction > 12) {
      this.emit('referee-break', {});
      this.standUp('судья поднял');
    }
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
        if (this.ground) this.standUp('конец раунда');
        this.phase = 'between';
        this.breakClock = 14;
        this.emit('round-end', { round: this.round });
      }
      return;
    }

    this.updateGround(dt);

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
      if (this.time < f.busyUntil) continue;
      if (this.ground && (f === this.ground.top || f === this.ground.bottom)) {
        // Hold the position rather than standing him up: on the ground the
        // loop *is* the state, and only an escape, a sweep or the referee
        // ends it.
        const clip = f === this.ground.top ? 'ground_top' : 'ground_bottom';
        f.state = f === this.ground.top ? 'ground-top' : 'ground-bottom';
        f.play(clip, { fade: 0.25, restart: false });
        continue;
      }
      if (f.state !== 'idle') {
        f.state = 'idle';
        f.grounded = false;
        f.play('idle', { fade: 0.22, restart: false });
      }
    }
    this.player.faceTowards(this.bot, 0.12);
    this.bot.faceTowards(this.player, 0.12);
    this.separate();
  }

  separate() {
    if (this.ground) return;
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
