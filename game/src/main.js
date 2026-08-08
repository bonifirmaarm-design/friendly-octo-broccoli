import * as THREE from '../vendor/three.module.js';
import { ROSTER, byId } from './roster.js';
import { Fighter, FIGHTER_SCALE, STRIKES } from './fighter.js';
import { Combat, SUBMISSIONS } from './combat.js';
import { Bot } from './ai.js';
import { BINDINGS, MAC_NOTES, Input } from './controls.js';
import { FightCamera } from './camera.js';
import { load, ASSETS, makeRenderer, lightArena, Flashes, Blood } from './scene.js';
import { Audio as Sound } from './audio.js';

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
const WALK_LEG = 5.2;      // seconds per fighter: tunnel, stairs, corner

const renderer = makeRenderer($('view'));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(52, innerWidth / innerHeight, 0.1, 200);
const rig = new FightCamera(camera);
const input = new Input();
lightArena(scene);

// Browsers will not start audio until the page has been touched, so the
// context is built on whatever the first click or keypress happens to be.
const sound = new Sound();
const wake = () => sound.start();
addEventListener('pointerdown', wake);
addEventListener('keydown', wake);

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
  cast: {},        // role -> loaded node (referee, coaches, belt)
  refHome: null,
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
      <div class="shot" style="background-image:url('./assets/portraits/${f.id}.jpg')"></div>
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

// The referee and the corner coaches are rigged now, so they load like a
// fighter -- mesh plus mixer plus clips -- rather than as scenery. Everyone
// else cageside is still a static prop, which is all they need to be.
const STAFF = { referee: 'official_referee', coach: 'official_coach' };

function makeStaff(gltf, role) {
  const s = new Fighter({ scene: gltf.scene, animations: gltf.animations },
    { id: role, stats: {}, style: {} });
  s.root.scale.setScalar(1);
  scene.add(s.root);
  return s;
}

async function placeCageside() {
  let manifest;
  try {
    manifest = await (await fetch(`${ASSETS}/arena/placements.json`)).json();
  } catch { return; }

  const flashPoints = [];
  for (const entry of [...manifest.cageside, ...manifest.props]) {
    const staffModel = STAFF[entry.role];
    if (staffModel) {
      try {
        const gltf = await load(`${ASSETS}/animated/${staffModel}.glb`);
        const person = makeStaff(gltf, entry.role);
        person.root.position.set(...entry.position);
        person.root.rotation.y = entry.yaw;
        person.play(entry.role === 'referee' ? 'ref_watch' : 'coach_watch',
          { fade: 0 });
        if (entry.role === 'referee') {
          state.cast.referee = person;
          state.refHome = person.root.position.clone();
        } else {
          (state.cast.coaches ||= []).push(person);
        }
        continue;
      } catch (e) { console.warn('нет модели', staffModel, e.message); }
    }
    if (entry.model) {
      try {
        const gltf = await load(`${ASSETS}/glb/${entry.model}.glb`);
        const node = gltf.scene;
        node.position.set(...entry.position);
        node.rotation.y = entry.yaw;
        node.traverse((o) => { if (o.isMesh) o.castShadow = true; });
        scene.add(node);
        // The referee walks in, the coaches get shown during the walkout and
        // the belt is handed over at the end, so keep hold of them.
        if (entry.role === 'belt') { state.cast.belt = node; node.visible = false; }
        // The towel and the bottle live in the corner until a hand reaches
        // for them between rounds; remember where "the corner" is so they can
        // be put back.
        if (entry.role === 'towel' || entry.role === 'water') {
          node.userData.rest = node.position.clone();
          node.userData.restYaw = entry.yaw || 0;
          const corner = (state.cast.corner ||= {});
          (corner[entry.corner] ||= {})[entry.role] = node;
        }
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
  if (state.cast.belt) state.cast.belt.visible = false;
  if (state.cast.referee && state.refHome) state.cast.referee.root.position.copy(state.refHome);
  for (const set of Object.values(state.cast.corner || {})) {
    for (const node of Object.values(set)) restProp(node);
  }
  state.refBreakUntil = 0;
  state.crowdActions.crowd_ovation?.stop();
  state.crowdActions.crowd_murmur?.play();
}

// Both men come out of the tunnel and climb into the cage, one after the
// other, because that is the order it happens in and it gives the camera
// something to do before the fight.
function updateWalkout(dt) {
  const w = state.walk;
  w.t += dt;
  const lead = w.t < WALK_LEG ? state.player : state.enemy;
  const other = lead === state.player ? state.enemy : state.player;
  const local = w.t < WALK_LEG ? w.t : w.t - WALK_LEG;

  const march = (f, t, laneX) => {
    if (t < 2.8) {
      const z = TUNNEL_START + t * 4.0;
      f.root.position.set(laneX, 0, Math.min(z, STAIR_BOTTOM));
      f.root.rotation.y = 0;
      if (f.state !== 'walkout') { f.state = 'walkout'; f.play('walkout', { fade: 0.3 }); }
    } else if (t < 4.7) {
      const u = Math.min((t - 2.8) / 1.9, 1);
      f.root.position.set(laneX * (1 - u), 1.26 * u,
        STAIR_BOTTOM + (STAIR_TOP - STAIR_BOTTOM) * u);
      if (f.state !== 'climb') { f.state = 'climb'; f.play('climb', { fade: 0.3 }); }
    } else {
      f.root.position.set(0, 1.26, STAIR_TOP + 1.2);
      if (f.state !== 'idle') { f.state = 'idle'; f.play('idle', { fade: 0.35 }); }
    }
  };

  (state.cast.coaches || []).forEach((coach, i) => {
    const angle = i === 0 ? Math.PI * 0.25 : Math.PI * 1.25;
    coach.root.position.set(Math.cos(angle) * 6.3, 0, Math.sin(angle) * 6.3);
    coach.root.rotation.y = Math.atan2(-coach.root.position.x, -coach.root.position.z);
    coach.mixer.update(dt);
  });

  march(lead, local, lead === state.player ? -1.1 : 1.1);
  if (w.t >= WALK_LEG) {
    // The first man is already inside, waiting in his corner.
    other.root.position.set(-1.6, 1.26, -1.9);
    if (other.state !== 'idle') { other.state = 'idle'; other.play('idle', { fade: 0.3 }); }
  }

  rig.walkout(lead, dt);
  lead.mixer.update(dt);
  other.mixer.update(dt);

  if (w.t > WALK_LEG * 2) {
    state.player.root.position.set(0, 1.26, -1.7);
    state.enemy.root.position.set(0, 1.26, 1.7);
    state.player.root.rotation.y = 0;
    state.enemy.root.rotation.y = Math.PI;
    state.phase = 'fight';
    state.crowdActions.crowd_murmur?.play();
    sound.bell(1);
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

  // On the ground the same keys mean different things, which is how it has to
  // be: there is no punching from your back and no standing up from on top.
  if (c.ground) {
    // Caught in a hold, every key means the same thing: get out. Mashing is
    // the mechanic, so it reads taps rather than a held key.
    const held = c.submission;
    if (held) {
      if (held.on === me && (input.tapped('Space') || input.tapped('KeyJ')
        || input.tapped('KeyK') || input.tapped('KeyG'))) c.struggle(me);
      return;
    }
    if (c.ground.top === me) {
      if (input.tapped('KeyJ') || input.tapped('KeyK')) c.groundStrike(me);
      if (input.tapped('KeyI')) c.attemptSubmission(me, 'sub_choke');
    } else if (c.ground.bottom === me) {
      if (input.tapped('KeyG')) c.groundEscape(me, 'ground_escape');
      if (input.tapped('KeyU')) c.groundEscape(me, 'ground_sweep');
      if (input.tapped('KeyI')) c.attemptSubmission(me, 'sub_armbar');
    }
    return;
  }

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

// The referee circles the action at a polite distance and steps between the
// two of them when he breaks a stalled position up. He has no rig, so he is
// moved rather than animated -- at cageside distance that reads fine.
function updateReferee(dt) {
  const referee = state.cast.referee;
  if (!referee) return;
  const c = state.combat;
  referee.mixer.update(dt);
  const mid = state.player.root.position.clone()
    .add(state.enemy.root.position).multiplyScalar(0.5);

  const breaking = c.time < (state.refBreakUntil || 0);
  let wanted;
  if (breaking) {
    wanted = mid.clone().setY(1.26);                  // in between them
  } else {
    const away = new THREE.Vector3()
      .subVectors(state.enemy.root.position, state.player.root.position);
    const side = new THREE.Vector3(-away.z, 0, away.x).normalize();
    wanted = mid.clone().add(side.multiplyScalar(2.1)).setY(1.26);
  }
  const r = Math.hypot(wanted.x, wanted.z);
  if (r > 3.9) { wanted.x *= 3.9 / r; wanted.z *= 3.9 / r; }
  referee.root.position.lerp(wanted, Math.min(1, dt * 1.7));
  referee.root.rotation.y = Math.atan2(mid.x - referee.root.position.x,
    mid.z - referee.root.position.z);

  // He watches from a crouch, breaks with both arms and counts a man down.
  const clip = breaking ? 'ref_break'
    : (c.ground ? 'ref_count' : 'ref_watch');
  if (referee.state !== clip) { referee.state = clip; referee.play(clip, { fade: 0.25 }); }
}

function updateCoaches(dt, shouting) {
  for (const coach of state.cast.coaches || []) {
    coach.mixer.update(dt);
    const clip = shouting ? 'coach_shout' : 'coach_watch';
    if (coach.state !== clip) { coach.state = clip; coach.play(clip, { fade: 0.3 }); }
  }
}

// ---------------------------------------------------------------------------
// HUD
// ---------------------------------------------------------------------------

// The crowd bed sits at a level per phase: a murmur in the menu, a wall of
// noise during the walkout, a working hum through the round. A roar overrides
// it for a few seconds and then the phase level is re-asserted.
const ROOM = { boot: 0.10, menu: 0.12, walkout: 0.55, fight: 0.40,
  ceremony: 0.75, result: 0.20 };
let roomLevel = -1;
let roarTimer = 0;
let soundOn = true;

function roar(strength) {
  sound.roar(strength);
  clearTimeout(roarTimer);
  roarTimer = setTimeout(() => { roomLevel = -1; }, 3600);
}

function updateRoom() {
  let want = ROOM[state.phase] ?? 0.20;
  if (state.phase === 'fight' && state.combat?.phase === 'between') want = 0.22;
  if (want !== roomLevel) { roomLevel = want; sound.crowdLevel(want, 1.6); }
}

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

  // The grip meter. It fills as the hold tightens and empties as the man in
  // it works loose, and it is the only readout during a submission that says
  // whether mashing is achieving anything.
  const s = c.submission;
  $('grip').classList.toggle('on', !!s);
  if (s) {
    const mine = s.by === p;
    $('grip-name').textContent = SUBMISSIONS[s.kind].name.toUpperCase();
    $('grip-fill').style.width = `${Math.round(s.tight * 100)}%`;
    $('grip').classList.toggle('theirs', !mine);
    $('grip-tip').textContent = mine ? 'Держит' : 'Space — вырываться';
  }

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
      if (ev.type === 'hit') {
        if (ev.move?.startsWith('kick') || ev.move === 'knee' || ev.move === 'teep') {
          sound.kick(ev.damage);
        } else sound.punch(ev.damage);
        if (ev.damage > 12) roar(ev.damage / 22);
      }
      if (ev.type === 'knockdown') {
        state.flashes?.burst(c.time, 22);
        sound.thud();
        roar(1);
        state.crowdActions.crowd_murmur?.stop();
        state.crowdActions.crowd_ovation?.reset().play();
      }
    }
    if (ev.type === 'blocked') sound.block();
    if (ev.type === 'takedown') {
      rig.kick(0.6);
      sound.thud();
      roar(0.7);
      state.crowdActions.crowd_ovation?.reset().play();
      setTimeout(() => {
        state.crowdActions.crowd_ovation?.stop();
        state.crowdActions.crowd_murmur?.play();
      }, 2600);
    }
    if (ev.type === 'ground') {
      hint('Партер: сверху J бьёт и I душит, снизу G встать, U переворот, I рычаг');
    }
    if (ev.type === 'sweep') { toast('ПЕРЕВОРОТ', 1.4); roar(0.6); }
    if (ev.type === 'submission-start') {
      toast(ev.name.toUpperCase(), 1.6);
      roar(0.8);
      const mine = ev.by === state.player.profile.id;
      hint(mine ? 'Держи!' : 'Тебя ловят — жми Space, вырывайся');
    }
    if (ev.type === 'submission-end') { toast('ВЫРВАЛСЯ', 1.4); roar(0.5); hint(''); }
    if (ev.type === 'tap') { toast('СДАЁТСЯ', 2.4); roar(1); }
    if (ev.type === 'referee-break') {
      toast('СУДЬЯ ПОДНИМАЕТ', 1.8);
      sound.whistle();
      state.refBreakUntil = c.time + 2.4;
    }
    if (ev.type === 'stand-up') { hint(''); }
    if (ev.type === 'round-end') {
      toast('КОНЕЦ РАУНДА', 2); hint('Перерыв: угол, вода, полотенце'); sound.bell(1);
    }
    if (ev.type === 'round-start') { toast(`РАУНД ${ev.round}`, 1.6); hint(''); sound.bell(1); }
    if (ev.type === 'finish') {
      state.flashes?.burst(c.time, 26);
      sound.bell(3);
      roar(1);
      state.crowdActions.crowd_ovation?.reset().play();
      state.phase = 'ceremony';
      state.ceremonyClock = 0;
      toast(ev.how.toUpperCase(), 2.6);
    }
  }
}

// The corner between rounds.
//
// The bottle does not appear in the fighter's hand out of nowhere: the coach
// picks it up, holds it out through the fence, the fighter takes it, drinks,
// and gives it back. That handover is the whole reason the routine is a
// table of beats rather than two clips -- each beat says what the fighter is
// doing, which prop is in play, and whose hand is holding it.
const CORNER_ROUTINE = [
  [0.0, 'corner_sit', null, null],
  [1.3, 'corner_sit', 'water', 'coach'],     // the coach reaches through
  [2.4, 'drink', 'water', 'fighter'],        // taken, and drunk from
  [4.6, 'corner_sit', 'water', 'coach'],     // handed back
  [5.6, 'corner_sit', 'towel', 'coach'],
  [6.4, 'towel', 'towel', 'fighter'],
  [8.6, 'corner_sit', null, null],
];

function cornerBeat(elapsed) {
  let beat = CORNER_ROUTINE[0];
  for (const b of CORNER_ROUTINE) if (elapsed >= b[0]) beat = b;
  return { clip: beat[1], prop: beat[2], holder: beat[3] };
}

// Putting the bottle and the towel in somebody's hands rather than miming them.
//
// They are not parented to the hand bone: the fighter's whole model carries a
// 0.93 scale, and a child of one of his bones inherits it along with whatever
// the skinning has done to that bone's transform. Reading the bone's world
// matrix each frame and moving the prop to it keeps the props in the scene's
// own space, at their own size -- and it works the same whether the hand
// belongs to the fighter or to the coach on the other side of the fence.
const HAND_SLOT = { water: 'Hand_R', towel: 'Hand_L' };
const COACH_SLOT = { water: 'Hand_R', towel: 'Hand_R' };
const BONE_SCALE = new THREE.Vector3();

function carry(node, person, bone) {
  const joint = person?.model.getObjectByName(bone);
  if (!joint) return false;
  joint.updateWorldMatrix(true, false);
  joint.matrixWorld.decompose(node.position, node.quaternion, BONE_SCALE);
  node.scale.setScalar(1);
  return true;
}

function updateCornerProps(beat) {
  const corners = state.cast.corner;
  if (!corners) return;
  for (const [i, fighter] of [state.player, state.enemy].entries()) {
    const set = corners[i === 0 ? 'blue' : 'red'];
    if (!set) continue;
    const coach = (state.cast.coaches || [])[i];
    for (const [role, node] of Object.entries(set)) {
      if (role === beat.prop) {
        const held = beat.holder === 'coach'
          ? carry(node, coach, COACH_SLOT[role])
          : carry(node, fighter, HAND_SLOT[role]);
        if (held) continue;
      }
      restProp(node);
    }
  }
}

function restProp(node) {
  if (!node.userData.rest) return;
  node.position.copy(node.userData.rest);
  node.quaternion.set(0, 0, 0, 1);
  node.rotation.y = node.userData.restYaw;
}

const CORNER_ANGLE = [Math.PI * 0.25, Math.PI * 1.25];

function updateBreak(dt) {
  const c = state.combat;
  const beat = cornerBeat(14 - c.breakClock);

  for (const [i, f] of [state.player, state.enemy].entries()) {
    // Each man goes to his own corner and sits facing outward -- his coach is
    // on the other side of that fence, and a fighter with his back to his own
    // corner cannot be handed anything.
    const angle = CORNER_ANGLE[i];
    f.root.position.set(Math.cos(angle) * 3.3, 1.26, Math.sin(angle) * 3.3);
    f.root.rotation.y = Math.atan2(f.root.position.x, f.root.position.z);
    const clip = f.has(beat.clip) ? beat.clip : 'idle';
    if (f.cornerClip !== clip) { f.cornerClip = clip; f.play(clip, { fade: 0.35 }); }
    f.state = 'corner';
  }
  // The coaches step up to the fence beside their man, and the one whose turn
  // it is holds the bottle or the towel through it.
  (state.cast.coaches || []).forEach((coach, i) => {
    const angle = CORNER_ANGLE[i];
    coach.root.position.set(Math.cos(angle) * 6.3, 0, Math.sin(angle) * 6.3);
    coach.root.rotation.y = Math.atan2(-coach.root.position.x, -coach.root.position.z);
    coach.mixer.update(dt);
    const clip = beat.prop ? 'coach_hand' : 'coach_shout';
    if (coach.state !== clip) { coach.state = clip; coach.play(clip, { fade: 0.3 }); }
  });
  // Props last: the hands they hang off have to be posed for this frame first.
  updateCornerProps(beat);

  rig.corners(state.player, state.enemy, dt);
}

function updateCeremony(dt) {
  state.ceremonyClock += dt;
  const winner = state.combat.winner;
  const loser = state.combat.loser;

  // The referee runs the whole ending: waves it off, fetches the belt,
  // fastens it and lifts the winner's hand. Same order as a real card.
  const referee = state.cast.referee;
  if (referee) {
    referee.mixer.update(dt);
    const beside = winner.root.position.clone()
      .add(new THREE.Vector3(0.78, 0, 0.42));
    referee.root.position.lerp(beside, Math.min(1, dt * 1.6));
    referee.root.rotation.y = Math.atan2(
      winner.root.position.x - referee.root.position.x,
      winner.root.position.z - referee.root.position.z);

    const t = state.ceremonyClock;
    const clip = t < 1.8 ? 'ref_wave_off' : (t < 6.4 ? 'ref_belt' : 'ref_raise_hand');
    if (referee.state !== clip) { referee.state = clip; referee.play(clip, { fade: 0.3 }); }
  }
  // His man just won. One coach comes off the floor; the other keeps his
  // arms folded, which is the difference the moment is made of.
  const winningCorner = winner === state.player ? 0 : 1;
  (state.cast.coaches || []).forEach((coach, i) => {
    coach.mixer.update(dt);
    const clip = i === winningCorner && coach.has('coach_jump')
      ? 'coach_jump' : 'coach_watch';
    if (coach.state !== clip) { coach.state = clip; coach.play(clip, { fade: 0.3 }); }
  });

  const belt = state.cast.belt;
  if (belt && state.ceremonyClock > 1.8) {
    belt.visible = true;
    if (state.ceremonyClock < 3.4 && referee) {
      // Carried over in the referee's hand, so it arrives rather than
      // materialising round the champion's waist.
      carry(belt, referee, 'Hand_R');
    } else {
      // Round the waist: the belt model is a metre long, so it sits at hip
      // height and turns with him.
      belt.quaternion.set(0, 0, 0, 1);
      belt.position.set(winner.root.position.x, winner.root.position.y + 0.95,
        winner.root.position.z);
      belt.rotation.y = winner.root.rotation.y;
    }
  }

  // Arms out for the belt, then the one arm the referee is holding.
  const stage = state.ceremonyClock < 6.4 ? 'belt_receive' : 'hand_raised';
  const clip = winner.has(stage) ? stage : (winner.has('walkoff') ? 'walkoff' : 'idle');
  if (winner.state !== clip) {
    winner.state = clip;
    winner.play(clip, { fade: 0.4 });
  }
  if (loser && !loser.grounded && loser.state !== 'idle') {
    loser.state = 'idle'; loser.play('idle', { fade: 0.4 });
  }
  winner.mixer.update(dt);
  loser?.mixer.update(dt);
  rig.ceremony(winner.root.position.clone().setY(winner.root.position.y + 0.4), dt);

  if (state.ceremonyClock > 11) {
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
  if (input.tapped('KeyO')) {
    soundOn = !soundOn;
    sound.setEnabled(soundOn);
    toast(soundOn ? 'ЗВУК ВКЛ' : 'ЗВУК ВЫКЛ', 1.2);
  }
  updateRoom();

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
    updateReferee(dt);
    // The break drives the coaches itself -- they have a bottle to pass --
    // so only the round proper goes through updateCoaches.
    if (state.combat.phase === 'between') updateBreak(dt);
    else {
      updateCoaches(dt, false);
      rig.fight(state.player, state.enemy, dt);
    }
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
  window.__walk = state.walk;
  window.__game = state;   // the automated check drives this directly
  input.endFrame();
  renderer.render(scene, camera);
}

boot().then(frame).catch((e) => {
  $('loading').textContent = `ОШИБКА: ${e.message}`;
  console.error(e);
});
