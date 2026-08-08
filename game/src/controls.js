// Keyboard map. Listed here once so the menu can print it and the game can
// read it, rather than the two drifting apart.
//
// Codes, not characters: KeyW is the same physical key on a Russian layout,
// `key` would be Ц.

export const BINDINGS = [
  { code: 'KeyW', label: 'W', action: 'forward', text: 'Вперёд' },
  { code: 'KeyS', label: 'S', action: 'back', text: 'Назад' },
  { code: 'KeyA', label: 'A', action: 'left', text: 'Влево' },
  { code: 'KeyD', label: 'D', action: 'right', text: 'Вправо' },
  { code: 'KeyJ', label: 'J', action: 'jab', text: 'Джеб (передняя рука)' },
  { code: 'KeyK', label: 'K', action: 'cross', text: 'Кросс (задняя рука)' },
  { code: 'KeyU', label: 'U', action: 'hook', text: 'Хук' },
  { code: 'KeyI', label: 'I', action: 'uppercut', text: 'Апперкот' },
  { code: 'KeyH', label: 'H', action: 'kick_low', text: 'Лоу-кик' },
  { code: 'KeyN', label: 'N', action: 'kick_body', text: 'Кик в корпус' },
  { code: 'KeyM', label: 'M', action: 'kick_high', text: 'Хай-кик' },
  { code: 'KeyG', label: 'G', action: 'takedown', text: 'Проход в ноги / бросок' },
  { code: 'KeyL', label: 'L', action: 'signature', text: 'Фирменная комбинация' },
  { code: 'Space', label: 'Space', action: 'block', text: 'Блок' },
  { code: 'KeyQ', label: 'Q', action: 'dodge_left', text: 'Уход влево' },
  { code: 'KeyE', label: 'E', action: 'dodge_right', text: 'Уход вправо' },
  { code: 'KeyC', label: 'C', action: 'weave', text: 'Нырок' },
  { code: 'KeyR', label: 'R', action: 'camera', text: 'Сменить камеру' },
  { code: 'Escape', label: 'Esc', action: 'pause', text: 'Пауза / меню' },
];

export const MAC_NOTES = [
  ['Esc', 'на Mac — та же клавиша, слева сверху'],
  ['Space', 'пробел'],
  ['Fn', 'не требуется: игра не использует F-клавиши'],
];

export class Input {
  constructor(target = window) {
    this.down = new Set();
    this.pressed = new Set();
    this._onDown = (e) => {
      if (e.repeat) return;
      this.down.add(e.code);
      this.pressed.add(e.code);
      if (['Space', 'ArrowUp', 'ArrowDown'].includes(e.code)) e.preventDefault();
    };
    this._onUp = (e) => this.down.delete(e.code);
    target.addEventListener('keydown', this._onDown);
    target.addEventListener('keyup', this._onUp);
    this.target = target;
  }

  held(code) { return this.down.has(code); }

  // True once per physical press; cleared by endFrame().
  tapped(code) { return this.pressed.has(code); }

  endFrame() { this.pressed.clear(); }

  dispose() {
    this.target.removeEventListener('keydown', this._onDown);
    this.target.removeEventListener('keyup', this._onUp);
  }
}
