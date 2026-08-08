// Exercise the ground phase without a browser. combat.js only touches the
// fighter through a small surface -- play, has, clipLength, position -- so a
// stub stands in for the rigged model and the logic can be checked in
// milliseconds instead of the minutes a software-rendered walkout costs.
import { Combat } from '../src/combat.js';

const clips = new Set(['idle', 'ground_top', 'ground_bottom', 'ground_pound',
  'ground_escape', 'ground_sweep', 'stand_up', 'knockdown', 'get_up',
  'block_high', 'hit_head', 'hit_body', 'jab', 'takedown_double_leg']);

function stub(id, stats) {
  return {
    profile: { id, stats, style: {} },
    root: { position: { x: 0, y: 0, z: 0,
      distanceTo() { return 0; },
      copy() {}, lerp() {} }, rotation: { y: 0 } },
    health: 100, stamina: 100, state: 'idle', busyUntil: 0, pending: null,
    guardUntil: 0, evadeUntil: 0, grounded: false, knockdowns: 0,
    played: [],
    has(n) { return clips.has(n); },
    play(n) { this.played.push(n); },
    clipLength() { return 1.2; },
    faceTowards() {},
    distanceTo() { return 1.0; },
    update() {},
  };
}

let failures = 0;
const check = (name, ok, extra = '') => {
  console.log(`${ok ? ' ok ' : 'FAIL'}  ${name}${extra ? '  — ' + extra : ''}`);
  if (!ok) failures++;
};

// --- a takedown opens a position, it does not end the exchange -------------
{
  const a = stub('wrestler', { power: 80, chin: 85, grappling: 95 });
  const b = stub('striker', { power: 90, chin: 80, grappling: 60 });
  const c = new Combat(a, b);
  c.resolve(a, b, 'takedown_double_leg');
  check('перевод открывает партер', !!c.ground);
  check('сверху атакующий', c.ground?.top === a);
  check('снизу защищающийся', c.ground?.bottom === b);
  check('оба помечены как в партере', a.grounded && b.grounded);
}

// --- the top man can hit, the bottom man cannot ---------------------------
{
  const a = stub('top', { power: 85, chin: 85, grappling: 90 });
  const b = stub('bottom', { power: 85, chin: 85, grappling: 70 });
  const c = new Combat(a, b);
  c.toGround(a, b);
  c.time = 1.0;
  const before = b.health;
  check('сверху бьёт', c.groundStrike(a) === true);
  check('урон прошёл', b.health < before, `${(before - b.health).toFixed(1)}`);
  c.time = 2.0;
  check('снизу бить нельзя', c.groundStrike(b) === false);
  check('сверху вставать нельзя', c.groundEscape(a) === false);
}

// --- grappling decides escapes -------------------------------------------
{
  let escapes = 0;
  for (let i = 0; i < 400; i++) {
    const strong = stub('grappler', { power: 80, chin: 85, grappling: 98 });
    const weak = stub('striker', { power: 80, chin: 85, grappling: 55 });
    const c = new Combat(weak, strong);
    c.toGround(weak, strong);          // the grappler is underneath
    c.time = 1.0;
    c.groundEscape(strong, 'ground_escape');
    if (!c.ground) escapes++;
  }
  const rate = escapes / 400;
  check('борец снизу встаёт чаще', rate > 0.35 && rate < 0.75,
    `${(rate * 100).toFixed(0)}%`);

  let weakEscapes = 0;
  for (let i = 0; i < 400; i++) {
    const strong = stub('grappler', { power: 80, chin: 85, grappling: 98 });
    const weak = stub('striker', { power: 80, chin: 85, grappling: 55 });
    const c = new Combat(strong, weak);
    c.toGround(strong, weak);          // the striker is underneath
    c.time = 1.0;
    c.groundEscape(weak, 'ground_escape');
    if (!c.ground) weakEscapes++;
  }
  check('ударник снизу встаёт реже борца', weakEscapes < escapes,
    `${(weakEscapes / 4).toFixed(0)}% против ${(rate * 100).toFixed(0)}%`);
}

// --- a sweep swaps the roles ----------------------------------------------
{
  let swept = 0;
  for (let i = 0; i < 300; i++) {
    const a = stub('top', { power: 80, chin: 85, grappling: 60 });
    const b = stub('bottom', { power: 80, chin: 85, grappling: 98 });
    const c = new Combat(a, b);
    c.toGround(a, b);
    c.time = 1.0;
    c.groundEscape(b, 'ground_sweep');
    if (c.ground && c.ground.top === b && c.ground.bottom === a) swept++;
  }
  check('переворот меняет позиции', swept > 60, `${swept} из 300`);
}

// --- the referee stands a stalled position up -----------------------------
{
  const a = stub('top', { power: 80, chin: 85, grappling: 90 });
  const b = stub('bottom', { power: 80, chin: 85, grappling: 70 });
  const c = new Combat(a, b);
  c.toGround(a, b);
  c.time = 5;
  c.updateGround(0.016);
  check('через 5 с судья не вмешивается', !!c.ground);
  c.time = 14;
  c.updateGround(0.016);
  check('через 12 с судья поднимает', !c.ground);
  check('событие судьи отправлено',
    c.events.some((e) => e.type === 'referee-break'));
  check('оба больше не в партере', !a.grounded && !b.grounded);
}

// --- ground strikes can finish the fight ----------------------------------
{
  const a = stub('top', { power: 99, chin: 85, grappling: 90 });
  const b = stub('bottom', { power: 80, chin: 60, grappling: 70 });
  b.health = 6;
  const c = new Combat(a, b);
  c.toGround(a, b);
  c.time = 1.0;
  c.groundStrike(a);
  check('добивание завершает бой', c.phase === 'over' && c.winner === a);
}

// --- the round bell clears the position -----------------------------------
{
  const a = stub('top', { power: 80, chin: 85, grappling: 90 });
  const b = stub('bottom', { power: 80, chin: 85, grappling: 70 });
  const c = new Combat(a, b, { rounds: 3, roundLength: 1 });
  c.toGround(a, b);
  c.update(1.2);
  check('гонг поднимает из партера', !c.ground && c.phase === 'between');
}

console.log(failures ? `\n${failures} провалов` : '\nвсе проверки прошли');
process.exit(failures ? 1 : 0);
