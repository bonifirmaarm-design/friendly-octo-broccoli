import * as THREE from '../vendor/three.module.js';
import { ROSTER, byId } from './roster.js';
import { Fighter, FIGHTER_SCALE, STRIKES } from './fighter.js';
import { Combat } from './combat.js';
import { Bot } from './ai.js';
import { BINDINGS, MAC_NOTES, Input } from './controls.js';
import { FightCamera } from './camera.js';
import { load, ASSETS, makeRenderer, lightArena, Flashes, Blood } from './scene.js';

const $ = (id) => document.getElementById(id);
const screens = ['menu', 'controls', 'about', 'select', 'result'];
const show = (name) => {
  screens.forEach((s) => $(s).classList.toggle('on', s === name));
  $('hud').classList.toggle('on', name === null);
};

const CAGE_CENTRE = new THREE.Vector3(0, 1.26, 0);   // canvas surface
const TUNNEL_START = -19.5;
const STAIR_BOTTOM = -8.3;
const STAIR_TOP = -5.3;

const renderer = makeRenderer($('view'));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.1, 200);
const rig = new FightCamera(camera);
const input = new Input();
lightArena(scene);

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
renderer.setSize(innerWidth, innerHeight);

const state = {
  phase: 'boot',
  chosen: null,
  fighters: new Map(),      // id -> loaded gltf, cloned per match
  crowdMixer: null,
  crowdActions: {},
  combat: null,
  bot: null,
  player: null,
  enemy: null,
  walk: null,
  flashes: null,
  blood: null,
};

// ---------------------------------------------------------------------------
// Menus
// ---------------------------------------------------------------------------

function buildControlsScreen() {
  $('bind-table').innerHTML = BINDINGS
    .map((b) => `<tr><td><kbd>${b.label}</kbd></td><td>${b.text}</td></tr>`).join('');
  $('mac-table').innerHTML = MAC_NOTES
    .map(([k, t]) => `<tr><td><kbd>${k}</kbd></td><td>${t}</td></tr>`).join('');
}

function buildRoster() {
  $('roster').innerHTML = ROSTER.map((f) => `
    <div class="card" data-id="${f.id}">
      <div class="tag">${f.tag}</div>
      <h3>${f.name}</h3>
      <p>${f.blurb}</p>
      ${Object.entries({ Сила: f.stats.power, Скорость: f.stats.speed,
        Борьба: f.stats.grappling, Челюсть: f.stats.chin })
        .map(([k, v]) => `<div class="stat"><b>${k}</b>
          <span class="bar"><i style="width:${v}%"></i></span></div>`).join('')}
    </div>`).join('');
  $('roster').querySelectorAll('.card').forEach((card) => {
    card.onclick = () => {
      $('roster').querySelectorAll('.card').forEach((c) => c.classList.remove('sel'));
      card.classList.add('sel');
      state.chosen = card.dataset.id;
      $('btn-fight').disabled = false;
    };
  });
}

$('btn-play').onclick = () => show('select');
$('btn-controls').onclick = () => show('controls');
$('btn-about').onclick = () => show('about');
document.querySelectorAll('[data-back]').forEach((b) => { b.onclick = () => show('menu'); });
$('btn-menu').onclick = () => { teardown(); show('menu'); };
$('btn-again').onclick = () => { teardown(); show('select'); };
$('btn-fight').onclick = () => startMatch();

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

async function boot() {
  const arena = await load(`${ASSETS}/arena/arena.glb`);
  arena.scene.traverse((o) => { if (o.isMesh) o.receiveShadow = true; });
  scene.add(arena.scene);

  try {
    const crowd = await load(`${ASSETS}/arena/crowd.glb`);
    scene.add(crowd.scene);
    state.crowdMixer = new THREE.AnimationMixer(crowd.scene);
    for (const clip of crowd.animations) {
      const action = state.crowdMixer.clipAction(clip);
      action.loop = THREE.LoopRepeat;
      state.crowdActions[clip.name] = action;
    }
    state.crowdActions.crowd_murmur?.play();
  } catch (e) { console.warn('нет толпы:', e.message); }

  await placeCageside();

  for (const f of ROSTER) {
    state.fighters.set(f.id, await load(`${ASSETS}/animated/${f.file}.glb`));
  }

  buildControlsScreen();
  buildRoster();
  $('loading').classList.add('off');
  state.phase = 'menu';
  camera.position.set(0, 6.5, 14);
  camera.lookAt(CAGE_CENTRE);
}

async function placeCageside() {
  let manifest;
  try {
    manifest = await (await fetch(`${ASSETS}/arena/placements.json`)).json();
  } catch { return; }

  const flashPoints = [];
  for (const entry of [...manifest.cageside, ...manifest.props]) {
    if (entry.model) {
      try {
        const gltf = await load(`${ASSETS}/glb/${entry.model}.glb`);
        const node = gltf.scene;
        node.position.set(...entry.position);
        node.rotation.y = entry.yaw;
        node.traverse((o) => { if (o.isMesh) o.castShadow = true; });
        scene.add(node);
      } catch { /* a missing NPC should not stop the show */ }
    }
    if (entry.flash) {
      flashPoints.push([entry.position[0] * 0.94, 1.62, entry.position[2] * 0.94]);
    }
  }
  // Press row flashes too, from further back.
  for (let i = 0; i < 26; i++) {
    const a = -Math.PI / 2 + (i / 26) * Math.PI * 2;
    flashPoints.push([Math.cos(a) * 9.5, 1.5, Math.sin(a) * 9.5]);
  }
  state.flashes = new Flashes(scene, flashPoints);
  state.blood = new Blood(scene);
}

// ---------------------------------------------------------------------------
// Match
// ---------------------------------------------------------------------------

function spawn(profile) {
  const source = state.fighters.get(profile.id);
  // Reuse the loaded gltf directly: only one match runs at a time, and
  // SkeletonUtils-free cloning of a skinned mesh is not worth the risk here.
  const fighter = new Fighter({ scene: source.scene, animations: source.animations },
    profile);
  scene.add(fighter.root);
  return fighter;
}

function startMatch() {
  const playerProfile = byId(state.chosen);
  const others = ROSTER.filter((f) => f.id !== playerProfile.id);
  const enemyProfile = others[(Math.random() * others.length) | 0];

  state.player = spawn(playerProfile);
  state.enemy = spawn(enemyProfile);

  state.player.root.position.set(-1.1, 1.26, TUNNEL_START);
  state.enemy.root.position.set(1.1, 1.26, TUNNEL_START - 6);
  state.player.root.position.y = 0;
  state.enemy.root.position.y = 0;

  $('n-l').textContent = playerProfile.name;
  $('n-r').textContent = enemyProfile.name;

  state.combat = new Combat(state.player, state.enemy);
  state.bot = new Bot(state.enemy, state.player, state.combat, 0.55);
  state.walk = { t: 0, stage: 0 };
  state.phase = 'walkout';
  show(null);
  hint('Выход бойцов');
}

function teardown() {
  for (const f of [state.player, state.enemy]) {
    if (f) scene.remove(f.root);
  }
  state.player = state.enemy = state.combat = state.bot = null;
  state.phase = 'menu';
  state.crowdActions.crowd_ovation?.stop();
  state.crowdActions.crowd_murmur?.play();
}

// Both men come out of the tunnel and climb into the cage, one after the
// other, because that is the order it happens in and it gives the camera
// something to do before the fight.
function updateWalkout(dt) {
  const w = state.walk;
  w.t += dt;
  const lead = w.t < 7.5 ? state.player : state.enemy;
  const other = lead === state.player ? state.enemy : state.player;
  const local = w.t < 7.5 ? w.t : w.t - 7.5;

  const march = (f, t, laneX) => {
    if (t < 4.2) {
      const z = TUNNEL_START + t * 2.5;
      f.root.position.set(laneX, 0, Math.min(z, STAIR_BOTTOM));
      f.root.rotation.y = 0;
      if (f.state !== 'walkout') { f.state = 'walkout'; f.play('walkout', { fade: 0.3 }); }
    } else if (t < 7.0) {
      const u = Math.min((t - 4.2) / 2.4, 1);
      f.root.position.set(laneX * (1 - u), 1.26 * u,
        STAIR_BOTTOM + (STAIR_TOP - STAIR_BOTTOM) * u);
      if (f.state !== 'climb') { f.state = 'climb'; f.play('climb', { fade: 0.3 }); }
    } else {
      f.root.position.set(0, 1.26, STAIR_TOP + 1.2);
      if (f.state !== 'idle') { f.state = 'idle'; f.play('idle', { fade: 0.35 }); }
    }
  };

  march(lead, local, lead === state.player ? -1.1 : 1.1);
  if (w.t >= 7.5) {
    // The first man is already inside, waiting in his corner.
    other.root.position.set(-1.6, 1.26, -1.9);
    if (other.state !== 'idle') { other.state = 'idle'; other.play('idle', { fade: 0.3 }); }
  }

  rig.walkout(lead, dt);
  lead.mixer.update(dt);
  other.mixer.update(dt);

  if (w.t > 14.5) {
    state.player.root.position.set(0, 1.26, -1.7);
    state.enemy.root.position.set(0, 1.26, 1.7);
    state.player.root.rotation.y = 0;
    state.enemy.root.rotation.y = Math.PI;
    state.phase = 'fight';
    state.crowdActions.crowd_murmur?.play();
    hint('Бой!');
    toast('РАУНД 1', 1.4);
  }
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function playerActions(dt) {
  const c = state.combat, me = state.player;
  if (c.phase !== 'fight') return;

  if (input.tapped('KeyR')) rig.cycle();

  const speed = 2.3 * dt;
  const yaw = me.root.rotation.y;
  const fwd = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
  const side = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
  let moving = false;
  if (c.time >= me.busyUntil && !me.grounded) {
    if (input.held('KeyW')) { me.root.position.addScaledVector(fwd, speed); moving = true; }
    if (input.held('KeyS')) { me.root.position.addScaledVector(fwd, -speed * 0.8); moving = true; }
    if (input.held('KeyA')) { me.root.position.addScaledVector(side, speed * 0.8); moving = true; }
    if (input.held('KeyD')) { me.root.position.addScaledVector(side, -speed * 0.8); moving = true; }
  }
  if (moving && me.state === 'idle') { me.state = 'walking'; me.play('walk', { fade: 0.2, restart: false }); }
  if (!moving && me.state === 'walking') { me.state = 'idle'; me.play('idle', { fade: 0.2 }); }

  const lead = me.profile.stance === 'southpaw' ? 'hand_R' : 'hand_L';
  const map = {
    KeyJ: 'jab', KeyK: 'cross',
    KeyU: lead === 'hand_L' ? 'hook_L' : 'hook_R',
    KeyI: lead === 'hand_L' ? 'uppercut_R' : 'uppercut_L',
    KeyH: 'kick_low', KeyN: 'kick_body', KeyM: 'kick_high',
  };
  for (const [code, move] of Object.entries(map)) {
    if (input.tapped(code)) { c.attack(me, state.enemy, move); return; }
  }
  if (input.tapped('KeyG')) {
    const shot = ['takedown_double_leg', 'takedown_single_leg', 'body_lock_throw',
      'trip_throw'].find((m) => me.has(m));
    if (shot) c.attack(me, state.enemy, shot);
    return;
  }
  if (input.tapped('KeyL') && me.has(me.profile.combo)) {
    me.play(me.profile.combo, { fade: 0.1 });
    me.state = 'attack';
    me.busyUntil = c.time + me.clipLength(me.profile.combo);
    me.stamina = Math.max(0, me.stamina - 22);
    return;
  }
  if (input.tapped('KeyQ')) return void c.defend(me, 'dodge_left');
  if (input.tapped('KeyE')) return void c.defend(me, 'dodge_right');
  if (input.tapped('KeyC')) return void c.defend(me, 'weave');
  if (input.held('Space')) c.defend(me, 'block_high');
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------

let toastTimer = 0;
function toast(text, seconds = 1.6) {
  $('toast').textContent = text;
  $('toast').classList.add('on');
  toastTimer = seconds;
}
function hint(text) { $('hint').textContent = text; }

function updateHud(dt) {
  const c = state.combat;
  if (!c) return;
  const [p, e] = [state.player, state.enemy];
  $('hp-l').style.width = `${p.health}%`;
  $('hp-r').style.width = `${e.health}%`;
  $('st-l').style.width = `${p.stamina}%`;
  $('st-r').style.width = `${e.stamina}%`;
  $('h-l').textContent = Math.round(p.health);
  $('h-r').textContent = Math.round(e.health);
  const clock = Math.max(0, c.phase === 'between' ? c.breakClock : c.roundClock);
  $('clock').textContent =
    `${Math.floor(clock / 60)}:${String(Math.floor(clock % 60)).padStart(2, '0')}`;
  $('round').textContent = c.phase === 'between' ? 'ПЕРЕРЫВ' : `РАУНД ${c.round}`;

  if (toastTimer > 0) {
    toastTimer -= dt;
    if (toastTimer <= 0) $('toast').classList.remove('on');
  }
}

function drainEvents() {
  const c = state.combat;
  for (const ev of c.events.splice(0)) {
    if (ev.type === 'hit' || ev.type === 'knockdown') {
      rig.kick(ev.type === 'knockdown' ? 1.0 : 0.25 + ev.damage / 40);
      const victim = ev.by === state.player.profile.id ? state.enemy : state.player;
      const at = victim.root.position.clone().setY(victim.root.position.y + 1.55);
      if (ev.damage > 9 || ev.type === 'knockdown') {
        state.blood?.spray(at, Math.min(1.6, ev.damage / 12));
      }
      if (ev.type === 'knockdown') {
        state.flashes?.burst(c.time, 22);
        state.crowdActions.crowd_murmur?.stop();
        state.crowdActions.crowd_ovation?.reset().play();
      }
    }
    if (ev.type === 'takedown') {
      rig.kick(0.6);
      state.crowdActions.crowd_ovation?.reset().play();
      setTimeout(() => {
        state.crowdActions.crowd_ovation?.stop();
        state.crowdActions.crowd_murmur?.play();
      }, 2600);
    }
    if (ev.type === 'round-end') { toast('КОНЕЦ РАУНДА', 2); hint('Перерыв: угол, вода, полотенце'); }
    if (ev.type === 'round-start') { toast(`РАУНД ${ev.round}`, 1.6); hint(''); }
    if (ev.type === 'finish') {
      state.flashes?.burst(c.time, 26);
      state.crowdActions.crowd_ovation?.reset().play();
      state.phase = 'ceremony';
      state.ceremonyClock = 0;
      toast(ev.how.toUpperCase(), 2.6);
    }
  }
}

// The corner between rounds: the fighter sits, the coach talks, the towel and
// the bottle come out. The props already sit in the corner from placements.
function updateBreak(dt) {
  for (const f of [state.player, state.enemy]) {
    if (f.state !== 'corner') {
      f.state = 'corner';
      f.play(f.has('block_body') ? 'block_body' : 'idle', { fade: 0.4 });
    }
  }
  const corner = state.player.root.position.clone().setY(1.9);
  rig.follow(corner.clone().add(new THREE.Vector3(2.4, 0.6, 2.4)), corner, dt, 1.8);
}

function updateCeremony(dt) {
  state.ceremonyClock += dt;
  const winner = state.combat.winner;
  const loser = state.combat.loser;
  if (winner.state !== 'walkoff') {
    winner.state = 'walkoff';
    winner.play(winner.has('walkoff') ? 'walkoff' : 'idle', { fade: 0.4 });
  }
  if (loser && !loser.grounded && loser.state !== 'idle') {
    loser.state = 'idle'; loser.play('idle', { fade: 0.4 });
  }
  winner.mixer.update(dt);
  loser?.mixer.update(dt);
  rig.ceremony(winner.root.position.clone().setY(winner.root.position.y + 0.4), dt);

  if (state.ceremonyClock > 7) {
    const same = winner === state.player;
    $('result-title').textContent = same ? 'ПОБЕДА' : 'ПОРАЖЕНИЕ';
    $('result-sub').textContent = same
      ? `${winner.profile.name} забирает пояс.`
      : `${winner.profile.name} побеждает. Пояс уходит ему.`;
    state.phase = 'result';
    show('result');
  }
}

// ---------------------------------------------------------------------------
// Loop
// ---------------------------------------------------------------------------

const clock = new THREE.Clock();
function frame() {
  requestAnimationFrame(frame);
  const dt = Math.min(clock.getDelta(), 0.05);

  if (input.tapped('Escape') && state.phase !== 'menu') { teardown(); show('menu'); }

  state.crowdMixer?.update(dt);
  const excitement = state.phase === 'fight' ? 1 : 0.35;
  state.flashes?.update(dt, performance.now() / 1000, excitement);
  state.blood?.update(dt);

  if (state.phase === 'walkout') {
    updateWalkout(dt);
  } else if (state.phase === 'fight') {
    playerActions(dt);
    state.bot.think(dt);
    state.combat.update(dt);
    drainEvents();
    if (state.combat.phase === 'between') updateBreak(dt);
    else rig.fight(state.player, state.enemy, dt);
    updateHud(dt);
  } else if (state.phase === 'ceremony') {
    state.combat.update(dt);
    drainEvents();
    updateCeremony(dt);
    updateHud(dt);
  } else {
    // Menu: slow orbit of the empty cage.
    const t = performance.now() / 6000;
    camera.position.set(Math.cos(t) * 13, 6.2, Math.sin(t) * 13);
    camera.lookAt(CAGE_CENTRE);
  }

  window.__phase = state.phase;   // read by the automated playthrough
  input.endFrame();
  renderer.render(scene, camera);
}

boot().then(frame).catch((e) => {
  $('loading').textContent = `ОШИБКА: ${e.message}`;
  console.error(e);
});
