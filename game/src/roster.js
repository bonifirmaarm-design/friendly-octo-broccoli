// Who is in the game, and what each one is good at.
//
// The bot reads `style` to decide what to throw, so the numbers are gameplay
// weights, not decoration: a wrestler shoots often and kicks rarely.

export const ROSTER = [
  {
    id: 'khabib',
    file: 'fighter_apose_01',
    name: 'Хабиб',
    tag: 'Борец',
    stance: 'orthodox',
    blurb: 'Проходы в ноги, обхват, добивание сверху.',
    stats: { power: 78, speed: 72, grappling: 96, chin: 88 },
    style: { punch: 0.42, kick: 0.10, takedown: 0.36, defend: 0.12 },
    combo: 'combo_ground_and_pound',
  },
  {
    id: 'jones',
    file: 'fighter_apose_02',
    name: 'Джонс',
    tag: 'Длинная дистанция',
    stance: 'orthodox',
    blurb: 'Боковой в колено, вертушки локтем, летящее колено.',
    stats: { power: 88, speed: 80, grappling: 82, chin: 90 },
    style: { punch: 0.38, kick: 0.34, takedown: 0.12, defend: 0.16 },
    combo: 'combo_range',
  },
  {
    id: 'islam',
    file: 'fighter_apose_03',
    name: 'Ислам',
    tag: 'Ударка и перевод',
    stance: 'orthodox',
    blurb: 'Бьёт в стойке, переводит в партер, добивает.',
    stats: { power: 82, speed: 84, grappling: 90, chin: 86 },
    style: { punch: 0.40, kick: 0.22, takedown: 0.24, defend: 0.14 },
    combo: 'combo_strike_takedown',
  },
  {
    id: 'conor',
    file: 'fighter_apose_04',
    name: 'Конор',
    tag: 'Левша, нокаутёр',
    stance: 'southpaw',
    blurb: 'Левый прямой, вертушка с ноги, тип.',
    stats: { power: 96, speed: 86, grappling: 62, chin: 74 },
    style: { punch: 0.50, kick: 0.28, takedown: 0.04, defend: 0.18 },
    combo: 'combo_left_hand',
  },
];

export const byId = (id) => ROSTER.find((f) => f.id === id) || ROSTER[0];
