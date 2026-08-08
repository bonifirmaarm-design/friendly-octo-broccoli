#!/usr/bin/env python3
"""The move library: stances, strikes, takedowns and per-fighter movesets.

Poses are written as where the hands and feet go, in the fighter's own frame:
x sideways (+ is his left), y height, z forward. Everything is a fraction of
that fighter's height, so one library fits all four without retuning.

Strikes are built by `strike()` rather than written out keyframe by keyframe.
A punch is always the same four beats -- load, fire, contact, recover -- and
spelling that out twenty times invites twenty slightly different rhythms.
"""

import numpy as np

from rigmath import Reach


def p(x, y, z):
    return np.array([x, y, z], float)


# The stance everything departs from and returns to.
#
# Reach matters more here than in any strike, because this is the pose held
# between all the others. A strike may aim past what the arm can cover -- the
# solver answers with a fully extended arm pointing that way, which is what a
# punch looks like anyway. A guard may not: aim the fists too far out and the
# same clamp leaves a man standing with his arms straight instead of covering
# up. Both fists therefore sit near 55-60% of arm reach, measured from where
# the shoulder ends up once the stance has bladed the torso, not from where it
# rests. Knee bend comes from dropping the hips; a standing leg really is
# almost straight, so pulling the feet in to bend the knees lifts them off the
# mat instead.
GUARD = {
    "hand_L": Reach((-0.30, 0.35, 0.89), 0.55),
    "hand_R": Reach((0.34, 0.34, 0.88), 0.58),
    "foot_L": p(0.16, 0.02, 0.16), "foot_R": p(-0.17, 0.02, -0.18),
    "root": (0.0, -0.035, 0.0),
    "hips": (0.0, -0.30, 0.0), "spine": (0.04, -0.10, 0.0), "chest": (0.0, -0.12, 0.0),
    "head": (0.0, 0.20, 0.0),
}

SOUTHPAW = dict(GUARD)   # lead side mirrored; Conor fights out of it
SOUTHPAW.update({
    "hand_L": Reach((-0.34, 0.34, 0.88), 0.58),
    "hand_R": Reach((0.30, 0.35, 0.89), 0.55),
    "foot_L": p(0.17, 0.02, -0.18), "foot_R": p(-0.16, 0.02, 0.16),
    "hips": (0.0, 0.30, 0.0), "spine": (0.04, 0.10, 0.0), "chest": (0.0, 0.12, 0.0),
    "head": (0.0, -0.20, 0.0),
})


def pose(base=None, **overrides):
    out = {k: (v.copy() if isinstance(v, np.ndarray) else v)
           for k, v in (base or GUARD).items()}
    out.update(overrides)
    return out


def strike(limb, windup, impact, *, base=None, load=None, fire=None,
           recover=None, timing=(0.11, 0.24, 0.40, 0.56), hold=0.0, **carry):
    """Four-beat strike: load, fire, contact settle, recover.

    `load` / `fire` / `recover` are extra pose overrides applied at those
    beats -- torso rotation, hip drive, the off hand dropping. `carry` is
    applied to every frame, for things that hold across the whole move such
    as a changed stance.
    """
    t_load, t_fire, t_settle, t_end = timing
    frames = [
        (0.00, pose(base, **carry)),
        (t_load, pose(base, **{limb: windup}, **(load or {}), **carry)),
        (t_fire, pose(base, **{limb: impact}, **(fire or {}), **carry)),
    ]
    if hold:
        frames.append((t_fire + hold, pose(base, **{limb: impact},
                                           **(fire or {}), **carry)))
    tail = hold
    rest_target = GUARD.get(limb, impact)
    if isinstance(rest_target, Reach):
        # The guard fists are reach-relative, so there is no coordinate to
        # average against; fall back to easing off the strike itself.
        midpoint = np.asarray(impact) * 0.55 + np.asarray(windup) * 0.45
    else:
        midpoint = (np.asarray(impact) + np.asarray(rest_target)) / 2
    frames.append((t_settle + tail, pose(base, **{limb: midpoint},
                                         **(recover or {}), **carry)))
    frames.append((t_end + tail, pose(base, **carry)))
    return False, frames


def walk_cycle(g, stride, period, lift, swagger=False, lean=0.0, arm_lift=0.0):
    """Four-contact walk, in place: contact, pass, contact, pass.

    The hips drop on each plant and rise as the leg straightens, and the
    shoulders counter-rotate against them -- without that the figure glides
    along level, which reads as sliding rather than walking.
    """
    base_x_l, base_x_r = g["foot_L"][0], g["foot_R"][0]
    ground = g["foot_L"][1]

    def foot(x, z, y=None):
        return p(x, ground if y is None else y, z)

    def frame(t, l_z, r_z, l_y, r_y, drop, roll, arms):
        # Arms hang and swing opposite the legs. Walking with the fists still
        # up at the chin is a guard, not a walk -- it is the single thing that
        # gives away a fighter who is "walking" by sliding a fighting stance
        # forward. The swing is small: it is a walkout, not a march.
        swing = arms * (0.30 if swagger else 0.34)
        drop_frac = (0.80 if swagger else 0.86) - arm_lift * 0.5
        rise = -0.94 + arm_lift          # climbing brings the hands up a little
        hands = {
            "hand_L": Reach((-0.16, rise, -swing + arm_lift), drop_frac),
            "hand_R": Reach((0.16, rise, swing + arm_lift), drop_frac),
        }
        return (t, pose(g, foot_L=foot(base_x_l, l_z, l_y),
                        foot_R=foot(base_x_r, r_z, r_y),
                        root=(0.0, g["root"][1] - drop, 0.0),
                        hips=(lean * 0.5, g["hips"][1] + roll * 0.10, 0.0),
                        chest=(lean, g["chest"][1] - roll * 0.16, 0.0),
                        head=(0.0, g["head"][1] * (0.4 if swagger else 1.0), 0.0),
                        **hands))

    half, quarter = period / 2, period / 4
    return [
        frame(0.0, stride, -stride, None, None, 0.02, 1.0, 1.0),
        frame(quarter, 0.0, 0.0, None, ground + lift, 0.0, 0.0, 0.0),
        frame(half, -stride, stride, None, None, 0.02, -1.0, -1.0),
        frame(3 * quarter, 0.0, 0.0, ground + lift, None, 0.0, 0.0, 0.0),
        frame(period, stride, -stride, None, None, 0.02, 1.0, 1.0),
    ]


# ---------------------------------------------------------------------------
# Shared clips every fighter gets
# ---------------------------------------------------------------------------

def base_clips(stance=None):
    g = stance or GUARD
    turn = -1.0 if stance is SOUTHPAW else 1.0

    return {
        "idle": (True, [
            (0.00, pose(g)),
            (0.90, pose(g, hand_L=g["hand_L"].nudged(0.03),
                        hand_R=g["hand_R"].nudged(0.03),
                        chest=(0.0, -0.12 * turn, 0.02))),
            (1.80, pose(g)),
        ]),
        # Walk cycles are authored in place: the feet slide back under a body
        # that never moves. Baking forward travel into a looping clip makes
        # the fighter teleport back to the start of the tunnel every cycle,
        # so the walk stays still and the scene drives him forward.
        "walk": (True, walk_cycle(g, stride=0.20, period=1.00, lift=0.10)),
        "walkout": (True, walk_cycle(g, stride=0.24, period=1.30, lift=0.12,
                                     swagger=True)),
        # Nobody walks into a cage on the flat: the platform is over a metre
        # up and you climb to it. Short stride, high knee, weight forward.
        "climb": (True, walk_cycle(g, stride=0.13, period=1.15, lift=0.26,
                                   lean=0.22, arm_lift=0.22)),
        "step_in": (False, [
            (0.00, pose(g)),
            (0.18, pose(g, root=(0.0, 0.01, 0.10), foot_L=g["foot_L"] + p(0, 0.06, 0.10))),
            (0.36, pose(g, root=(0.0, 0.0, 0.20),
                        foot_L=g["foot_L"] + p(0, 0, 0.20),
                        foot_R=g["foot_R"] + p(0, 0, 0.20))),
        ]),
        "block": (False, [
            (0.00, pose(g)),
            (0.10, pose(g, hand_L=p(0.14, 0.94, 0.26), hand_R=p(-0.13, 0.95, 0.24),
                        chest=(0.14, 0.0, 0.0), head=(0.14, 0.0, 0.0))),
            (0.40, pose(g, hand_L=p(0.14, 0.94, 0.26), hand_R=p(-0.13, 0.95, 0.24),
                        chest=(0.14, 0.0, 0.0), head=(0.14, 0.0, 0.0))),
            (0.55, pose(g)),
        ]),
        "slip": (False, [
            (0.00, pose(g)),
            (0.12, pose(g, chest=(0.10, -0.30 * turn, 0.30), head=(0.06, 0.0, 0.34),
                        hips=(0.0, -0.20 * turn, 0.10))),
            (0.34, pose(g)),
        ]),
        # Evasion. The body leans away first and the feet catch up -- stepping
        # squarely sideways with the torso upright reads as strafing, not as
        # slipping a punch.
        "dodge_left": (False, [
            (0.00, pose(g)),
            (0.11, pose(g, root=(0.06, -0.02, 0.0), chest=(0.06, 0.0, 0.34),
                        head=(0.04, 0.0, 0.30),
                        foot_L=g["foot_L"] + p(0.12, 0.0, 0.0))),
            (0.26, pose(g, root=(0.13, -0.01, 0.0), chest=(0.04, 0.0, 0.22),
                        head=(0.02, 0.0, 0.18),
                        foot_L=g["foot_L"] + p(0.13, 0.0, 0.0),
                        foot_R=g["foot_R"] + p(0.13, 0.0, 0.0))),
            (0.44, pose(g, root=(0.13, 0.0, 0.0),
                        foot_L=g["foot_L"] + p(0.13, 0.0, 0.0),
                        foot_R=g["foot_R"] + p(0.13, 0.0, 0.0))),
        ]),
        "dodge_right": (False, [
            (0.00, pose(g)),
            (0.11, pose(g, root=(-0.06, -0.02, 0.0), chest=(0.06, 0.0, -0.34),
                        head=(0.04, 0.0, -0.30),
                        foot_R=g["foot_R"] + p(-0.12, 0.0, 0.0))),
            (0.26, pose(g, root=(-0.13, -0.01, 0.0), chest=(0.04, 0.0, -0.22),
                        head=(0.02, 0.0, -0.18),
                        foot_L=g["foot_L"] + p(-0.13, 0.0, 0.0),
                        foot_R=g["foot_R"] + p(-0.13, 0.0, 0.0))),
            (0.44, pose(g, root=(-0.13, 0.0, 0.0),
                        foot_L=g["foot_L"] + p(-0.13, 0.0, 0.0),
                        foot_R=g["foot_R"] + p(-0.13, 0.0, 0.0))),
        ]),
        "weave": (False, [
            (0.00, pose(g)),
            (0.13, pose(g, root=(0.05, -0.11, 0.02), chest=(0.30, 0.0, 0.26),
                        head=(0.20, 0.0, 0.22))),
            (0.28, pose(g, root=(-0.05, -0.13, 0.03), chest=(0.34, 0.0, -0.26),
                        head=(0.22, 0.0, -0.22))),
            (0.46, pose(g, root=(-0.04, -0.03, 0.0), chest=(0.10, 0.0, -0.08))),
            (0.62, pose(g)),
        ]),
        "back_step": (False, [
            (0.00, pose(g)),
            (0.16, pose(g, root=(0.0, -0.01, -0.10), chest=(-0.06, 0.0, 0.0),
                        foot_R=g["foot_R"] + p(0, 0.05, -0.12))),
            (0.36, pose(g, root=(0.0, 0.0, -0.20),
                        foot_L=g["foot_L"] + p(0, 0, -0.20),
                        foot_R=g["foot_R"] + p(0, 0, -0.20))),
        ]),
        # Three covers, because they defend different things: hands high for
        # the head, elbows down for the body, and a full shell to sit behind.
        "block_high": (False, [
            (0.00, pose(g)),
            (0.08, pose(g, hand_L=Reach((-0.34, 0.72, 0.60), 0.62),
                        hand_R=Reach((0.34, 0.72, 0.60), 0.62),
                        chest=(0.10, 0.0, 0.0), head=(0.16, 0.0, 0.0))),
            (0.34, pose(g, hand_L=Reach((-0.34, 0.72, 0.60), 0.62),
                        hand_R=Reach((0.34, 0.72, 0.60), 0.62),
                        chest=(0.10, 0.0, 0.0), head=(0.16, 0.0, 0.0))),
            (0.50, pose(g)),
        ]),
        "block_body": (False, [
            (0.00, pose(g)),
            (0.09, pose(g, hand_L=Reach((-0.20, -0.30, 0.93), 0.52),
                        hand_R=Reach((0.20, -0.30, 0.93), 0.52),
                        chest=(0.26, 0.0, 0.0), head=(0.18, 0.0, 0.0),
                        root=(0.0, -0.06, 0.0))),
            (0.34, pose(g, hand_L=Reach((-0.20, -0.30, 0.93), 0.52),
                        hand_R=Reach((0.20, -0.30, 0.93), 0.52),
                        chest=(0.26, 0.0, 0.0), head=(0.18, 0.0, 0.0),
                        root=(0.0, -0.06, 0.0))),
            (0.52, pose(g)),
        ]),
        "cover_up": (False, [
            (0.00, pose(g)),
            (0.10, pose(g, hand_L=Reach((-0.10, 0.80, 0.59), 0.55),
                        hand_R=Reach((0.10, 0.80, 0.59), 0.55),
                        chest=(0.30, 0.0, 0.0), head=(0.26, 0.0, 0.0),
                        root=(0.0, -0.08, -0.02))),
            (0.70, pose(g, hand_L=Reach((-0.10, 0.80, 0.59), 0.55),
                        hand_R=Reach((0.10, 0.80, 0.59), 0.55),
                        chest=(0.32, 0.0, 0.02), head=(0.28, 0.0, 0.0),
                        root=(0.0, -0.09, -0.02))),
            (0.90, pose(g)),
        ]),
        "hit_head": (False, [
            (0.00, pose(g)),
            (0.08, pose(g, head=(-0.34, 0.40, 0.0), chest=(-0.16, 0.26, 0.0),
                        hand_L=p(0.20, 0.72, 0.10), hips=(0.0, 0.16, 0.0))),
            (0.30, pose(g, head=(0.06, 0.10, 0.0), chest=(0.04, -0.04, 0.0))),
            (0.50, pose(g)),
        ]),
        "hit_body": (False, [
            (0.00, pose(g)),
            (0.09, pose(g, chest=(0.34, 0.0, 0.0), head=(0.24, 0.0, 0.0),
                        hips=(0.14, 0.0, 0.0), root=(0.0, -0.03, -0.03))),
            (0.34, pose(g, chest=(0.12, 0.0, 0.0), root=(0.0, -0.01, 0.0))),
            (0.55, pose(g)),
        ]),
        "knockdown": (False, [
            (0.00, pose(g)),
            (0.10, pose(g, head=(-0.40, 0.30, 0.0), chest=(-0.24, 0.20, 0.0))),
            (0.45, pose(g, hips=(-0.55, 0.20, 0.0), chest=(-0.40, 0.10, 0.0),
                        head=(-0.30, 0.0, 0.0), root=(0.0, -0.16, -0.10),
                        foot_L=p(0.20, 0.20, -0.30), foot_R=p(-0.22, 0.16, -0.34),
                        hand_L=p(0.30, 0.30, -0.20), hand_R=p(-0.30, 0.28, -0.24))),
            (1.10, pose(g, hips=(-1.20, 0.10, 0.0), chest=(-0.70, 0.0, 0.0),
                        head=(-0.20, 0.0, 0.0), root=(0.0, -0.30, -0.22),
                        foot_L=p(0.22, 0.10, -0.55), foot_R=p(-0.24, 0.08, -0.58),
                        hand_L=p(0.34, 0.14, -0.34), hand_R=p(-0.34, 0.12, -0.36))),
        ]),
        "get_up": (False, [
            (0.00, pose(g, hips=(-1.20, 0.10, 0.0), chest=(-0.70, 0.0, 0.0),
                        root=(0.0, -0.30, -0.22),
                        foot_L=p(0.22, 0.10, -0.55), foot_R=p(-0.24, 0.08, -0.58),
                        hand_L=p(0.34, 0.14, -0.34), hand_R=p(-0.34, 0.12, -0.36))),
            (0.55, pose(g, hips=(-0.70, 0.10, 0.0), chest=(-0.40, 0.0, 0.0),
                        root=(0.0, -0.18, -0.12),
                        foot_L=p(0.20, 0.16, -0.30), foot_R=p(-0.22, 0.10, -0.34),
                        hand_L=p(0.30, 0.34, -0.10), hand_R=p(-0.30, 0.30, -0.16))),
            (1.05, pose(g, hips=(-0.25, 0.0, 0.0), root=(0.0, -0.06, -0.04),
                        chest=(-0.10, 0.0, 0.0))),
            (1.40, pose(g)),
        ]),
        **ground_clips(g),
        **corner_clips(g),
    }


# ---------------------------------------------------------------------------
# The ground
#
# A takedown that ends the exchange is not MMA. What happens after it is a
# position: one man on top inside the other's legs, the man underneath working
# to stand or to reverse. These are held poses more than motions -- the top
# game is mostly stillness punctuated by short, heavy strikes -- so they loop
# and the game blends between them.
# ---------------------------------------------------------------------------

FLOOR = -0.42          # how far the hips drop to lie on the mat


def ground_clips(g):
    flat = {"root": (0.0, FLOOR, 0.0)}
    # Legs out along the mat, for the poses where the fighter is on his back
    # and the legs are not doing anything in particular.
    sprawled = {"foot_L": p(0.22, 0.22, 0.24), "foot_R": p(-0.23, 0.20, 0.22)}

    def bottom(**over):
        """On his back, hips down, knees up: the guard."""
        base = dict(hips=(-1.35, 0.0, 0.0), chest=(0.30, 0.0, 0.0),
                    head=(0.30, 0.0, 0.0),
                    foot_L=p(0.22, 0.30, 0.22), foot_R=p(-0.23, 0.28, 0.20),
                    hand_L=Reach((-0.20, 0.55, 0.80), 0.60),
                    hand_R=Reach((0.20, 0.55, 0.80), 0.60), **flat)
        return pose(g, **{**base, **over})

    def top(**over):
        """Kneeling over him, posted on one hand."""
        base = dict(hips=(0.55, 0.0, 0.0), chest=(0.32, 0.0, 0.0),
                    head=(0.10, 0.0, 0.0), root=(0.0, -0.30, 0.10),
                    foot_L=p(0.26, 0.06, -0.34), foot_R=p(-0.27, 0.06, -0.36),
                    hand_L=Reach((-0.18, -0.72, 0.67), 0.90),
                    hand_R=Reach((0.18, -0.55, 0.81), 0.85))
        return pose(g, **{**base, **over})

    return {
        "ground_bottom": (True, [
            (0.00, bottom()),
            (1.10, bottom(chest=(0.34, 0.06, 0.0), foot_L=p(0.23, 0.33, 0.24))),
            (2.20, bottom()),
        ]),
        "ground_top": (True, [
            (0.00, top()),
            (1.20, top(chest=(0.36, -0.08, 0.0))),
            (2.40, top()),
        ]),
        # From the bottom: bridge the hips, frame, and scramble up.
        "ground_escape": (False, [
            (0.00, bottom()),
            (0.30, bottom(hips=(-1.05, 0.22, 0.0), root=(0.0, FLOOR + 0.10, -0.04),
                          chest=(0.10, 0.20, 0.0),
                          foot_L=p(0.24, 0.16, 0.10), foot_R=p(-0.25, 0.14, 0.08))),
            (0.70, pose(g, hips=(-0.55, 0.25, 0.0), root=(0.0, -0.24, -0.12),
                        chest=(-0.15, 0.15, 0.0),
                        foot_L=p(0.22, 0.14, -0.24), foot_R=p(-0.24, 0.10, -0.28),
                        hand_L=p(0.30, 0.32, -0.08), hand_R=p(-0.30, 0.30, -0.14))),
            (1.15, pose(g, hips=(-0.20, 0.0, 0.0), root=(0.0, -0.06, -0.04))),
            (1.45, pose(g)),
        ]),
        # Reverse him: hook the leg, turn the hips over, come up on top.
        "ground_sweep": (False, [
            (0.00, bottom()),
            (0.28, bottom(hips=(-1.15, -0.40, 0.0), chest=(0.28, -0.30, 0.0),
                          foot_L=p(0.26, 0.20, 0.26))),
            (0.62, pose(g, hips=(-0.30, -1.10, 0.0), chest=(0.20, -0.60, 0.0),
                        root=(0.10, FLOOR + 0.14, 0.06),
                        foot_L=p(0.24, 0.12, -0.10), foot_R=p(-0.22, 0.16, 0.14),
                        hand_L=p(0.32, 0.20, 0.18), hand_R=p(-0.28, 0.26, -0.06))),
            (1.00, top(hips=(0.50, -0.35, 0.0), chest=(0.30, -0.20, 0.0))),
            (1.30, top()),
        ]),
        # Submissions. Two bodies again, but they start already tangled on the
        # mat, so each side is authored on its own rather than solved from a
        # grip: there is no reaching involved, only squeezing and defending.
        #
        # The choke: one arm under the jaw, the other locking it, both legs
        # wrapped round the waist from behind.
        "sub_choke": (True, [
            (0.00, pose(g, hips=(-0.75, 0.10, 0.0), chest=(0.20, 0.10, 0.0),
                        root=(0.0, FLOOR + 0.10, -0.12),
                        foot_L=p(0.26, 0.34, 0.34), foot_R=p(-0.26, 0.32, 0.34),
                        hand_L=Reach((-0.55, 0.10, 0.83), 0.70),
                        hand_R=Reach((0.62, 0.06, 0.78), 0.66))),
            (0.85, pose(g, hips=(-0.85, 0.10, 0.0), chest=(0.28, 0.12, 0.0),
                        head=(-0.16, 0.0, 0.0), root=(0.0, FLOOR + 0.08, -0.14),
                        foot_L=p(0.24, 0.30, 0.36), foot_R=p(-0.24, 0.28, 0.36),
                        hand_L=Reach((-0.48, 0.14, 0.86), 0.62),
                        hand_R=Reach((0.55, 0.10, 0.83), 0.58))),
            (1.70, pose(g, hips=(-0.75, 0.10, 0.0), chest=(0.20, 0.10, 0.0),
                        root=(0.0, FLOOR + 0.10, -0.12),
                        foot_L=p(0.26, 0.34, 0.34), foot_R=p(-0.26, 0.32, 0.34),
                        hand_L=Reach((-0.55, 0.10, 0.83), 0.70),
                        hand_R=Reach((0.62, 0.06, 0.78), 0.66))),
        ]),
        "sub_choke_victim": (True, [
            (0.00, pose(g, hips=(-0.60, 0.0, 0.0), chest=(0.34, 0.0, 0.0),
                        head=(-0.34, 0.0, 0.0), root=(0.0, FLOOR + 0.06, 0.0),
                        foot_L=p(0.24, 0.14, 0.34), foot_R=p(-0.25, 0.12, 0.32),
                        hand_L=Reach((-0.30, 0.72, 0.62), 0.66),
                        hand_R=Reach((0.30, 0.72, 0.62), 0.66))),
            (0.85, pose(g, hips=(-0.62, 0.10, 0.0), chest=(0.38, 0.08, 0.0),
                        head=(-0.42, 0.06, 0.0), root=(0.0, FLOOR + 0.05, 0.0),
                        foot_L=p(0.26, 0.20, 0.30), foot_R=p(-0.27, 0.18, 0.28),
                        hand_L=Reach((-0.36, 0.66, 0.66), 0.72),
                        hand_R=Reach((0.24, 0.78, 0.58), 0.60))),
            (1.70, pose(g, hips=(-0.60, 0.0, 0.0), chest=(0.34, 0.0, 0.0),
                        head=(-0.34, 0.0, 0.0), root=(0.0, FLOOR + 0.06, 0.0),
                        foot_L=p(0.24, 0.14, 0.34), foot_R=p(-0.25, 0.12, 0.32),
                        hand_L=Reach((-0.30, 0.72, 0.62), 0.66),
                        hand_R=Reach((0.30, 0.72, 0.62), 0.66))),
        ]),
        # The armbar: hips up under the elbow, both legs across the chest.
        "sub_armbar": (True, [
            (0.00, pose(g, hips=(-1.15, 0.30, 0.0), chest=(0.10, 0.20, 0.0),
                        root=(0.10, FLOOR + 0.04, 0.06),
                        foot_L=p(0.16, 0.52, 0.30), foot_R=p(-0.20, 0.50, 0.26),
                        hand_L=Reach((-0.40, 0.36, 0.84), 0.80),
                        hand_R=Reach((0.36, 0.40, 0.84), 0.78))),
            (0.90, pose(g, hips=(-1.28, 0.30, 0.0), chest=(0.02, 0.22, 0.0),
                        root=(0.10, FLOOR + 0.10, 0.06),
                        foot_L=p(0.16, 0.56, 0.28), foot_R=p(-0.20, 0.54, 0.24),
                        hand_L=Reach((-0.34, 0.52, 0.78), 0.90),
                        hand_R=Reach((0.30, 0.56, 0.77), 0.88))),
            (1.80, pose(g, hips=(-1.15, 0.30, 0.0), chest=(0.10, 0.20, 0.0),
                        root=(0.10, FLOOR + 0.04, 0.06),
                        foot_L=p(0.16, 0.52, 0.30), foot_R=p(-0.20, 0.50, 0.26),
                        hand_L=Reach((-0.40, 0.36, 0.84), 0.80),
                        hand_R=Reach((0.36, 0.40, 0.84), 0.78))),
        ]),
        "sub_armbar_victim": (True, [
            (0.00, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.20, -0.16, 0.0),
                        head=(0.24, 0.0, 0.0), root=(0.0, FLOOR, 0.0),
                        foot_L=p(0.22, 0.22, 0.24), foot_R=p(-0.23, 0.20, 0.22),
                        hand_L=Reach((-0.20, 0.86, 0.46), 0.96),
                        hand_R=Reach((0.34, 0.30, 0.88), 0.60))),
            (0.90, pose(g, hips=(-1.34, -0.24, 0.0), chest=(0.26, -0.20, 0.0),
                        head=(0.30, 0.0, 0.0), root=(0.0, FLOOR, 0.0),
                        foot_L=p(0.24, 0.28, 0.20), foot_R=p(-0.25, 0.26, 0.18),
                        hand_L=Reach((-0.16, 0.92, 0.36), 0.98),
                        hand_R=Reach((0.40, 0.24, 0.88), 0.56))),
            (1.80, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.20, -0.16, 0.0),
                        head=(0.24, 0.0, 0.0), root=(0.0, FLOOR, 0.0),
                        foot_L=p(0.22, 0.22, 0.24), foot_R=p(-0.23, 0.20, 0.22),
                        hand_L=Reach((-0.20, 0.86, 0.46), 0.96),
                        hand_R=Reach((0.34, 0.30, 0.88), 0.60))),
        ]),
        # Tapping: the free hand slaps the mat three times, then goes limp.
        #
        # The feet have to be named even though the tap is all upper body.
        # Leave them out and they fall back to the standing guard's targets,
        # which sit under a fighter whose hips are a metre higher -- the legs
        # then fold so hard that the knee, not the foot, becomes the lowest
        # joint and buries itself in the canvas.
        "tap_out": (False, [
            (0.00, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.20, -0.16, 0.0),
                        root=(0.0, FLOOR, 0.0), **sprawled,
                        hand_R=Reach((0.40, 0.24, 0.88), 0.56))),
            (0.22, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.24, -0.16, 0.0),
                        root=(0.0, FLOOR, 0.0), **sprawled,
                        hand_R=Reach((0.52, -0.55, 0.65), 0.86))),
            (0.44, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.20, -0.16, 0.0),
                        root=(0.0, FLOOR, 0.0), **sprawled,
                        hand_R=Reach((0.40, 0.10, 0.91), 0.62))),
            (0.66, pose(g, hips=(-1.30, -0.20, 0.0), chest=(0.24, -0.16, 0.0),
                        root=(0.0, FLOOR, 0.0), **sprawled,
                        hand_R=Reach((0.52, -0.55, 0.65), 0.86))),
            (1.10, pose(g, hips=(-1.20, -0.10, 0.0), chest=(0.16, -0.08, 0.0),
                        root=(0.0, FLOOR, 0.0), head=(0.20, 0.0, 0.0), **sprawled,
                        hand_L=Reach((-0.55, -0.60, 0.58), 0.90),
                        hand_R=Reach((0.55, -0.60, 0.58), 0.90))),
            (2.00, pose(g, hips=(-1.20, -0.10, 0.0), chest=(0.16, -0.08, 0.0),
                        root=(0.0, FLOOR, 0.0), head=(0.20, 0.0, 0.0), **sprawled,
                        hand_L=Reach((-0.55, -0.60, 0.58), 0.90),
                        hand_R=Reach((0.55, -0.60, 0.58), 0.90))),
        ]),
        # The referee waves it off and both men are stood back up.
        "stand_up": (False, [
            (0.00, top()),
            (0.45, pose(g, hips=(-0.40, 0.0, 0.0), root=(0.0, -0.20, -0.06),
                        chest=(-0.20, 0.0, 0.0),
                        foot_L=p(0.20, 0.12, -0.20), foot_R=p(-0.22, 0.10, -0.24),
                        hand_L=p(0.30, 0.40, -0.02), hand_R=p(-0.30, 0.38, -0.08))),
            (0.90, pose(g, hips=(-0.15, 0.0, 0.0), root=(0.0, -0.06, 0.0))),
            (1.20, pose(g)),
        ]),
    }


# ---------------------------------------------------------------------------
# The corner, and what happens after the final bell
# ---------------------------------------------------------------------------

def corner_clips(g):
    seated = {"root": (0.0, -0.26, 0.0),
              "hips": (0.42, 0.0, 0.0), "chest": (-0.10, 0.0, 0.0),
              "foot_L": p(0.20, 0.02, 0.30), "foot_R": p(-0.21, 0.02, 0.28)}

    def stool(**over):
        base = dict(hand_L=Reach((-0.30, -0.62, 0.72), 0.72),
                    hand_R=Reach((0.30, -0.62, 0.72), 0.72), **seated)
        return pose(g, **{**base, **over})

    return {
        "corner_sit": (True, [
            (0.00, stool()),
            (1.30, stool(chest=(-0.06, 0.0, 0.0), head=(0.06, 0.0, 0.0))),
            (2.60, stool()),
        ]),
        # Bottle to the mouth, head tipped back, then handed away.
        "drink": (False, [
            (0.00, stool()),
            (0.45, stool(hand_R=Reach((0.10, 0.62, 0.78), 0.55),
                         head=(-0.30, 0.0, 0.0), chest=(-0.16, 0.0, 0.0))),
            (1.40, stool(hand_R=Reach((0.06, 0.72, 0.69), 0.50),
                         head=(-0.42, 0.0, 0.0), chest=(-0.20, 0.0, 0.0))),
            (1.90, stool(hand_R=Reach((0.20, 0.30, 0.93), 0.70), head=(-0.10, 0.0, 0.0))),
            (2.30, stool()),
        ]),
        # The towel goes over the face and round the back of the neck.
        "towel": (False, [
            (0.00, stool()),
            (0.40, stool(hand_L=Reach((-0.14, 0.66, 0.74), 0.52),
                         head=(0.10, 0.0, 0.0))),
            (0.95, stool(hand_L=Reach((-0.26, 0.74, 0.62), 0.48),
                         head=(0.16, 0.14, 0.0), chest=(-0.04, 0.10, 0.0))),
            (1.50, stool(hand_L=Reach((0.10, 0.78, 0.62), 0.50),
                         head=(0.14, -0.14, 0.0), chest=(-0.04, -0.10, 0.0))),
            (2.05, stool()),
        ]),
        # Arms out and up while the belt goes round the waist, then held aloft.
        "belt_receive": (False, [
            (0.00, pose(g)),
            (0.60, pose(g, hand_L=Reach((-0.72, 0.30, 0.62), 0.78),
                        hand_R=Reach((0.72, 0.30, 0.62), 0.78),
                        chest=(-0.10, 0.0, 0.0), head=(-0.12, 0.0, 0.0))),
            (1.80, pose(g, hand_L=Reach((-0.72, 0.30, 0.62), 0.78),
                        hand_R=Reach((0.72, 0.30, 0.62), 0.78),
                        chest=(-0.10, 0.0, 0.0), head=(-0.12, 0.0, 0.0))),
            (2.60, pose(g, hand_L=Reach((-0.34, 0.90, 0.28), 0.92),
                        hand_R=Reach((0.34, 0.90, 0.28), 0.92),
                        chest=(-0.20, 0.0, 0.0), head=(-0.26, 0.0, 0.0))),
            (4.20, pose(g, hand_L=Reach((-0.34, 0.90, 0.28), 0.92),
                        hand_R=Reach((0.34, 0.90, 0.28), 0.92),
                        chest=(-0.20, 0.0, 0.0), head=(-0.26, 0.0, 0.0))),
        ]),
        # The referee has hold of his wrist. Only the one arm goes up, and it
        # is the right one: the referee stands on the champion's right, and a
        # winner throwing up the arm on the far side of the man holding it
        # is the sort of thing you notice immediately and cannot unsee.
        "hand_raised": (True, [
            (0.00, pose(g, hand_R=Reach((0.30, 0.92, 0.24), 0.96),
                        chest=(-0.08, -0.10, 0.0), head=(-0.14, -0.06, 0.0))),
            (1.40, pose(g, hand_R=Reach((0.26, 0.94, 0.20), 0.97),
                        chest=(-0.12, -0.10, 0.0), head=(-0.18, -0.06, 0.0))),
            (2.80, pose(g, hand_R=Reach((0.30, 0.92, 0.24), 0.96),
                        chest=(-0.08, -0.10, 0.0), head=(-0.14, -0.06, 0.0))),
        ]),
    }


# ---------------------------------------------------------------------------
# Signature strikes -- the pool every fighter's moveset is drawn from
# ---------------------------------------------------------------------------

def strike_pool(g, turn=1.0):
    """Every strike, expressed against a given stance."""
    return {
        "jab": strike("hand_L", p(0.10, 0.80, 0.30), p(0.02, 0.84, 0.62), base=g,
                      load={"chest": (0.0, -0.22 * turn, 0.0)},
                      fire={"chest": (0.0, 0.10 * turn, 0.0)},
                      timing=(0.09, 0.19, 0.34, 0.48)),
        "cross": strike("hand_R", p(-0.16, 0.83, 0.06), p(0.01, 0.85, 0.66), base=g,
                        load={"chest": (0.0, -0.34 * turn, 0.0),
                              "hips": (0.0, -0.22 * turn, 0.0)},
                        fire={"chest": (0.0, 0.30 * turn, 0.0),
                              "hips": (0.0, 0.24 * turn, 0.0)},
                        timing=(0.10, 0.24, 0.42, 0.58)),
        "hook_L": strike("hand_L", p(0.26, 0.80, 0.10), p(-0.16, 0.86, 0.44), base=g,
                         load={"chest": (0.0, -0.34 * turn, 0.0)},
                         fire={"chest": (0.0, 0.34 * turn, 0.0),
                               "hips": (0.0, 0.26 * turn, 0.0)},
                         timing=(0.11, 0.26, 0.44, 0.60)),
        "hook_R": strike("hand_R", p(-0.28, 0.80, 0.08), p(0.16, 0.86, 0.46), base=g,
                         load={"chest": (0.0, 0.32 * turn, 0.0)},
                         fire={"chest": (0.0, -0.34 * turn, 0.0),
                               "hips": (0.0, -0.26 * turn, 0.0)},
                         timing=(0.11, 0.26, 0.44, 0.60)),
        "uppercut_L": strike("hand_L", p(0.14, 0.60, 0.24), p(0.04, 1.02, 0.42), base=g,
                             load={"chest": (0.10, -0.26 * turn, 0.0)},
                             fire={"chest": (-0.16, 0.18 * turn, 0.0),
                                   "hips": (0.0, 0.18 * turn, 0.0)},
                             timing=(0.12, 0.27, 0.45, 0.62)),
        "uppercut_R": strike("hand_R", p(-0.14, 0.62, 0.22), p(-0.04, 1.02, 0.40), base=g,
                             load={"chest": (0.10, 0.26 * turn, 0.0)},
                             fire={"chest": (-0.16, -0.18 * turn, 0.0),
                                   "hips": (0.0, -0.18 * turn, 0.0)},
                             timing=(0.12, 0.27, 0.45, 0.62)),
        "overhand_R": strike("hand_R", p(-0.26, 1.00, -0.04), p(0.06, 0.78, 0.60), base=g,
                             load={"chest": (-0.16, 0.30 * turn, 0.0)},
                             fire={"chest": (0.26, -0.30 * turn, 0.0),
                                   "hips": (0.0, -0.24 * turn, 0.0),
                                   "root": (0.0, -0.04, 0.05)},
                             timing=(0.13, 0.29, 0.48, 0.66)),
        "body_hook": strike("hand_L", p(0.26, 0.68, 0.10), p(-0.10, 0.62, 0.46), base=g,
                            load={"chest": (0.16, -0.30 * turn, 0.0),
                                  "root": (0.0, -0.05, 0.0)},
                            fire={"chest": (0.20, 0.28 * turn, 0.0),
                                  "root": (0.0, -0.04, 0.03)},
                            timing=(0.11, 0.26, 0.44, 0.60)),
        "elbow": strike("hand_R", p(-0.22, 0.94, 0.06), p(0.14, 0.92, 0.34), base=g,
                        load={"chest": (0.0, 0.30 * turn, 0.0)},
                        fire={"chest": (0.0, -0.36 * turn, 0.0),
                              "hips": (0.0, -0.22 * turn, 0.0)},
                        timing=(0.09, 0.20, 0.34, 0.48)),
        "spinning_elbow": (False, [
            (0.00, pose(g)),
            (0.13, pose(g, chest=(0.0, -0.60 * turn, 0.0), hips=(0.0, -0.50 * turn, 0.0),
                        hand_R=p(-0.20, 0.90, 0.02))),
            (0.30, pose(g, chest=(0.0, 1.30 * turn, 0.0), hips=(0.0, 1.50 * turn, 0.0),
                        hand_R=p(0.18, 0.92, 0.36), hand_L=p(0.24, 0.80, -0.10),
                        foot_L=p(0.10, 0.06, 0.20))),
            (0.46, pose(g, chest=(0.0, 2.60 * turn, 0.0), hips=(0.0, 2.90 * turn, 0.0),
                        hand_R=p(0.10, 0.88, 0.30))),
            (0.68, pose(g, chest=(0.0, 3.10 * turn, 0.0), hips=(0.0, 3.14 * turn, 0.0))),
        ]),
        "spinning_back_kick": (False, [
            (0.00, pose(g)),
            (0.14, pose(g, chest=(0.0, -0.55 * turn, 0.0), hips=(0.0, -0.45 * turn, 0.0),
                        foot_R=p(-0.20, 0.06, -0.24))),
            (0.32, pose(g, chest=(0.0, 1.20 * turn, 0.0), hips=(0.0, 1.40 * turn, 0.0),
                        foot_R=p(-0.10, 0.46, 0.20), root=(0.0, -0.03, 0.0))),
            (0.48, pose(g, chest=(0.0, 2.40 * turn, 0.0), hips=(0.0, 2.70 * turn, 0.0),
                        foot_R=p(0.02, 0.56, 0.62), root=(0.0, -0.02, 0.06))),
            (0.70, pose(g, chest=(0.0, 3.10 * turn, 0.0), hips=(0.0, 3.14 * turn, 0.0),
                        foot_R=p(-0.16, 0.06, -0.10))),
        ]),
        "kick_low": strike("foot_R", p(-0.24, 0.14, -0.24), p(-0.06, 0.30, 0.60), base=g,
                           load={"hips": (0.0, -0.22 * turn, 0.0)},
                           fire={"hips": (0.0, 0.30 * turn, 0.0),
                                 "chest": (0.06, 0.22 * turn, 0.0),
                                 "hand_L": p(0.22, 0.74, 0.10)},
                           timing=(0.12, 0.28, 0.48, 0.68)),
        "kick_body": strike("foot_R", p(-0.26, 0.18, -0.26), p(-0.02, 0.62, 0.58), base=g,
                            load={"hips": (0.0, -0.26 * turn, 0.0)},
                            fire={"hips": (0.0, 0.36 * turn, 0.0),
                                  "chest": (0.08, 0.28 * turn, 0.0),
                                  "hand_L": p(0.26, 0.68, 0.06)},
                            timing=(0.13, 0.31, 0.52, 0.74)),
        "kick_high": strike("foot_R", p(-0.26, 0.18, -0.26), p(0.00, 0.92, 0.52), base=g,
                            load={"hips": (0.0, -0.28 * turn, 0.0),
                                  "chest": (0.0, -0.20 * turn, 0.0)},
                            fire={"hips": (0.0, 0.42 * turn, 0.0),
                                  "chest": (0.10, 0.34 * turn, 0.0),
                                  "head": (0.0, 0.30 * turn, 0.0),
                                  "hand_L": p(0.30, 0.60, 0.04),
                                  "hand_R": p(-0.24, 0.92, 0.10)},
                            timing=(0.14, 0.34, 0.56, 0.80)),
        "front_kick": strike("foot_R", p(-0.16, 0.34, -0.10), p(-0.04, 0.66, 0.66), base=g,
                             load={"root": (0.0, -0.02, 0.0)},
                             fire={"chest": (-0.14, 0.0, 0.0), "hips": (-0.10, 0.0, 0.0)},
                             timing=(0.12, 0.26, 0.44, 0.62)),
        "teep": strike("foot_L", p(0.16, 0.38, 0.04), p(0.04, 0.58, 0.70), base=g,
                       fire={"chest": (-0.12, 0.0, 0.0), "root": (0.0, -0.02, -0.04)},
                       timing=(0.10, 0.21, 0.36, 0.52)),
        "oblique_kick": strike("foot_L", p(0.16, 0.26, 0.08), p(0.06, 0.30, 0.64), base=g,
                               load={"root": (0.0, -0.03, 0.0)},
                               fire={"chest": (-0.10, 0.0, 0.0), "root": (0.0, -0.04, 0.02)},
                               timing=(0.10, 0.22, 0.38, 0.54)),
        "side_kick": strike("foot_R", p(-0.24, 0.30, -0.14), p(-0.06, 0.52, 0.70), base=g,
                            load={"hips": (0.0, -0.40 * turn, 0.0),
                                  "chest": (0.0, -0.30 * turn, 0.0)},
                            fire={"hips": (0.0, -0.70 * turn, 0.0),
                                  "chest": (0.14, -0.50 * turn, 0.0),
                                  "root": (0.0, -0.03, 0.04)},
                            timing=(0.13, 0.29, 0.50, 0.70)),
        "knee": strike("foot_R", p(-0.17, 0.30, 0.0), p(-0.10, 0.60, 0.34), base=g,
                       load={"hips": (0.0, -0.18 * turn, 0.0),
                             "chest": (-0.10, -0.12 * turn, 0.0)},
                       fire={"hips": (-0.12, -0.10 * turn, 0.0),
                             "chest": (0.20, -0.08 * turn, 0.0),
                             "hand_L": p(0.10, 0.94, 0.34), "hand_R": p(-0.08, 0.96, 0.30)},
                       timing=(0.11, 0.26, 0.44, 0.62)),
        "flying_knee": (False, [
            (0.00, pose(g)),
            (0.12, pose(g, root=(0.0, -0.06, 0.02), hips=(0.0, -0.16 * turn, 0.0),
                        foot_L=p(0.16, 0.02, 0.12), foot_R=p(-0.17, 0.02, -0.20))),
            (0.30, pose(g, root=(0.0, 0.22, 0.30), foot_R=p(-0.08, 0.86, 0.34),
                        foot_L=p(0.16, 0.44, -0.14), chest=(0.16, -0.10 * turn, 0.0),
                        hand_L=p(0.14, 1.06, 0.30), hand_R=p(-0.12, 1.08, 0.26))),
            (0.52, pose(g, root=(0.0, 0.02, 0.34), foot_R=p(-0.16, 0.10, 0.14),
                        chest=(0.10, 0.0, 0.0))),
            (0.76, pose(g, root=(0.0, 0.0, 0.34))),
        ]),
        "superman_punch": (False, [
            (0.00, pose(g)),
            (0.12, pose(g, root=(0.0, -0.05, -0.02), foot_R=p(-0.18, 0.16, -0.28),
                        hand_R=p(-0.18, 0.86, 0.0))),
            (0.30, pose(g, root=(0.0, 0.14, 0.28), foot_R=p(-0.18, 0.30, -0.42),
                        foot_L=p(0.16, 0.26, -0.16),
                        hand_R=p(0.02, 0.90, 0.68), chest=(0.0, 0.26 * turn, 0.0))),
            (0.50, pose(g, root=(0.0, 0.0, 0.22), hand_R=p(-0.10, 0.84, 0.30))),
            (0.74, pose(g, root=(0.0, 0.0, 0.22))),
        ]),
        "level_change": (False, [
            (0.00, pose(g)),
            (0.16, pose(g, root=(0.0, -0.14, 0.06), chest=(0.30, 0.0, 0.0),
                        head=(0.10, 0.0, 0.0),
                        hand_L=p(0.20, 0.52, 0.34), hand_R=p(-0.18, 0.54, 0.32),
                        foot_L=p(0.18, 0.02, 0.24))),
            (0.40, pose(g, root=(0.0, -0.12, 0.06), chest=(0.28, 0.0, 0.0))),
            (0.62, pose(g)),
        ]),
        "ground_pound": (True, [
            (0.00, pose(g, root=(0.0, -0.34, 0.10), hips=(0.55, 0.0, 0.0),
                        chest=(0.30, 0.0, 0.0), head=(0.10, 0.0, 0.0),
                        foot_L=p(0.24, 0.06, -0.34), foot_R=p(-0.26, 0.06, -0.36),
                        hand_L=p(0.22, 0.30, 0.34), hand_R=p(-0.16, 0.72, 0.20))),
            (0.22, pose(g, root=(0.0, -0.34, 0.10), hips=(0.55, 0.0, 0.0),
                        chest=(0.42, -0.16, 0.0),
                        foot_L=p(0.24, 0.06, -0.34), foot_R=p(-0.26, 0.06, -0.36),
                        hand_L=p(0.22, 0.30, 0.34), hand_R=p(-0.04, 0.28, 0.44))),
            (0.46, pose(g, root=(0.0, -0.34, 0.10), hips=(0.55, 0.0, 0.0),
                        chest=(0.30, 0.0, 0.0),
                        foot_L=p(0.24, 0.06, -0.34), foot_R=p(-0.26, 0.06, -0.36),
                        hand_L=p(0.22, 0.30, 0.34), hand_R=p(-0.16, 0.72, 0.20))),
        ]),
        "walkoff": (False, [
            (0.00, pose(g)),
            (0.40, pose(g, hand_L=p(0.40, 0.96, -0.10), hand_R=p(-0.40, 0.96, -0.10),
                        chest=(-0.14, 0.0, 0.0), head=(-0.20, 0.0, 0.0))),
            (0.90, pose(g, hand_L=p(0.44, 1.02, -0.14), hand_R=p(-0.44, 1.02, -0.14),
                        chest=(-0.18, 0.0, 0.0), head=(-0.24, 0.0, 0.0))),
            (1.30, pose(g)),
        ]),
    }


# ---------------------------------------------------------------------------
# Takedowns and throws
#
# These are two-body moves. Each frame carries a pose for the attacker and one
# for the man being thrown, plus grip specs saying which part of him each hand
# holds. The grip is resolved against his actual posed skeleton at bake time,
# so the hands land on the leg wherever the leg happens to be -- authoring the
# hand positions by eye guarantees they drift off him the moment he moves.
#
# A grip is (joint_a, joint_b, t, out) -- a point t of the way along the bone
# between the two joints, pushed `out` sideways so the hand sits on the
# surface of the limb instead of inside its axis.
# ---------------------------------------------------------------------------

TAKEDOWNS = {
    "takedown_double_leg": {
        "offset": (0.0, 0.0, 0.40), "yaw": np.pi, "recovery": 0.55,
        "frames": [
            (0.00, pose(), pose(), {}),
            (0.18, pose(root=(0.0, -0.16, 0.10), chest=(0.34, 0.0, 0.0),
                        head=(0.12, 0.0, 0.0), foot_L=p(0.18, 0.02, 0.26)),
             pose(), {"hand_L": ("UpperLeg_R", "LowerLeg_R", 0.35, -0.05),
                      "hand_R": ("UpperLeg_L", "LowerLeg_L", 0.35, 0.05)}),
            (0.40, pose(root=(0.0, -0.20, 0.30), chest=(0.42, 0.0, 0.0),
                        head=(0.16, 0.0, 0.0),
                        foot_L=p(0.18, 0.02, 0.40), foot_R=p(-0.18, 0.06, 0.06)),
             pose(root=(0.0, -0.04, -0.10), hips=(-0.30, 0.0, 0.0),
                  chest=(0.20, 0.0, 0.0),
                  foot_L=p(0.18, 0.10, -0.24), foot_R=p(-0.19, 0.10, -0.30)),
             {"hand_L": ("UpperLeg_R", "LowerLeg_R", 0.30, -0.05),
              "hand_R": ("UpperLeg_L", "LowerLeg_L", 0.30, 0.05)}),
            (0.68, pose(root=(0.0, -0.26, 0.44), chest=(0.46, 0.10, 0.0),
                        foot_L=p(0.18, 0.02, 0.50), foot_R=p(-0.18, 0.10, 0.18)),
             pose(root=(0.0, -0.34, -0.42), hips=(-0.95, 0.0, 0.0),
                  chest=(0.34, 0.0, 0.0), head=(0.20, 0.0, 0.0),
                  foot_L=p(0.22, 0.34, -0.30), foot_R=p(-0.24, 0.32, -0.36),
                  hand_L=p(0.34, 0.20, -0.26), hand_R=p(-0.34, 0.18, -0.28)),
             {"hand_L": ("UpperLeg_R", "LowerLeg_R", 0.28, -0.05),
              "hand_R": ("UpperLeg_L", "LowerLeg_L", 0.28, 0.05)}),
            (1.00, pose(root=(0.0, -0.30, 0.46), chest=(0.40, 0.0, 0.0),
                        hips=(0.30, 0.0, 0.0),
                        foot_L=p(0.20, 0.06, 0.20), foot_R=p(-0.22, 0.06, 0.16)),
             pose(root=(0.0, -0.52, -0.50), hips=(-1.35, 0.0, 0.0),
                  chest=(0.20, 0.0, 0.0), head=(0.10, 0.0, 0.0),
                  foot_L=p(0.22, 0.24, -0.16), foot_R=p(-0.24, 0.22, -0.22),
                  hand_L=p(0.34, 0.12, -0.30), hand_R=p(-0.34, 0.10, -0.32)),
             {"hand_L": ("UpperLeg_R", "LowerLeg_R", 0.40, -0.06),
              "hand_R": ("Hips", "Chest", 0.30, 0.10)}),
        ],
    },
    "takedown_single_leg": {
        "offset": (0.10, 0.0, 0.40), "yaw": np.pi, "recovery": 0.55,
        "frames": [
            (0.00, pose(), pose(), {}),
            (0.20, pose(root=(0.0, -0.18, 0.12), chest=(0.30, -0.16, 0.0),
                        foot_L=p(0.20, 0.02, 0.26)),
             pose(), {"hand_L": ("UpperLeg_L", "LowerLeg_L", 0.55, 0.05),
                      "hand_R": ("LowerLeg_L", "Foot_L", 0.40, 0.05)}),
            (0.46, pose(root=(0.0, -0.14, 0.24), chest=(0.24, -0.22, 0.0),
                        foot_L=p(0.20, 0.02, 0.34), foot_R=p(-0.18, 0.04, 0.02)),
             pose(root=(0.0, 0.0, -0.06), hips=(-0.20, 0.20, 0.0),
                  foot_R=p(-0.12, 0.52, 0.26), foot_L=p(0.16, 0.02, -0.10),
                  hand_L=p(0.32, 0.74, 0.02)),
             {"hand_L": ("UpperLeg_L", "LowerLeg_L", 0.50, 0.05),
              "hand_R": ("LowerLeg_L", "Foot_L", 0.35, 0.05)}),
            (0.76, pose(root=(0.0, -0.10, 0.38), chest=(0.20, -0.36, 0.0),
                        hips=(0.0, -0.30, 0.0),
                        foot_L=p(0.20, 0.02, 0.42), foot_R=p(-0.16, 0.06, 0.16)),
             pose(root=(0.10, -0.34, -0.34), hips=(-0.60, 0.60, 0.0),
                  chest=(0.20, 0.30, 0.0),
                  foot_R=p(-0.06, 0.46, 0.10), foot_L=p(0.20, 0.16, -0.34),
                  hand_L=p(0.36, 0.22, -0.24), hand_R=p(-0.30, 0.28, -0.10)),
             {"hand_L": ("UpperLeg_L", "LowerLeg_L", 0.45, 0.05),
              "hand_R": ("LowerLeg_L", "Foot_L", 0.30, 0.05)}),
            (1.05, pose(root=(0.0, -0.24, 0.42), chest=(0.34, -0.20, 0.0),
                        hips=(0.20, -0.16, 0.0),
                        foot_L=p(0.20, 0.06, 0.22), foot_R=p(-0.20, 0.06, 0.14)),
             pose(root=(0.10, -0.52, -0.46), hips=(-1.30, 0.40, 0.0),
                  chest=(0.24, 0.20, 0.0),
                  foot_L=p(0.22, 0.22, -0.20), foot_R=p(-0.20, 0.26, -0.10),
                  hand_L=p(0.34, 0.12, -0.28), hand_R=p(-0.32, 0.14, -0.26)),
             {"hand_L": ("UpperLeg_L", "LowerLeg_L", 0.50, 0.06),
              "hand_R": ("Hips", "Chest", 0.25, 0.10)}),
        ],
    },
    "body_lock_throw": {
        "offset": (0.0, 0.0, 0.30), "yaw": np.pi, "recovery": 0.60,
        "frames": [
            (0.00, pose(), pose(), {}),
            (0.20, pose(root=(0.0, -0.06, 0.14), chest=(0.16, 0.0, 0.0)),
             pose(), {"hand_L": ("Hips", "Spine", 0.40, -0.14),
                      "hand_R": ("Hips", "Spine", 0.40, 0.14)}),
            (0.46, pose(root=(0.0, -0.10, 0.16), chest=(0.24, -0.40, 0.0),
                        hips=(0.0, -0.34, 0.0), foot_R=p(-0.22, 0.04, 0.10)),
             pose(root=(0.0, 0.10, -0.04), hips=(-0.20, 0.0, 0.0),
                  chest=(-0.20, 0.0, 0.0),
                  foot_L=p(0.18, 0.26, -0.16), foot_R=p(-0.20, 0.24, -0.20)),
             {"hand_L": ("Hips", "Spine", 0.40, -0.14),
              "hand_R": ("Hips", "Spine", 0.40, 0.14)}),
            (0.74, pose(root=(0.0, -0.14, 0.10), chest=(0.10, -0.90, 0.0),
                        hips=(0.0, -0.80, 0.0),
                        foot_L=p(0.16, 0.02, 0.10), foot_R=p(-0.24, 0.04, -0.06)),
             pose(root=(-0.30, -0.10, -0.16), hips=(-0.70, -0.80, 0.0),
                  chest=(-0.30, -0.30, 0.0), head=(-0.20, 0.0, 0.0),
                  foot_L=p(0.24, 0.50, -0.10), foot_R=p(-0.26, 0.46, -0.16),
                  hand_L=p(0.34, 0.40, -0.10), hand_R=p(-0.34, 0.38, -0.14)),
             {"hand_L": ("Hips", "Spine", 0.40, -0.14),
              "hand_R": ("Hips", "Spine", 0.40, 0.14)}),
            (1.06, pose(root=(0.0, -0.30, 0.06), chest=(0.34, -1.00, 0.0),
                        hips=(0.24, -0.90, 0.0),
                        foot_L=p(0.16, 0.06, 0.10), foot_R=p(-0.24, 0.06, -0.10)),
             pose(root=(-0.42, -0.52, -0.24), hips=(-1.40, -1.10, 0.0),
                  chest=(0.10, -0.30, 0.0), head=(0.0, 0.0, 0.0),
                  foot_L=p(0.24, 0.20, -0.26), foot_R=p(-0.26, 0.18, -0.30),
                  hand_L=p(0.34, 0.12, -0.30), hand_R=p(-0.34, 0.10, -0.32)),
             {"hand_L": ("Hips", "Spine", 0.45, -0.14),
              "hand_R": ("Hips", "Spine", 0.45, 0.14)}),
        ],
    },
    "trip_throw": {
        "offset": (0.06, 0.0, 0.32), "yaw": np.pi, "recovery": 0.55,
        "frames": [
            (0.00, pose(), pose(), {}),
            (0.20, pose(root=(0.0, -0.04, 0.12), chest=(0.10, -0.20, 0.0)),
             pose(), {"hand_L": ("Chest", "Neck", 0.50, -0.12),
                      "hand_R": ("UpperArm_L", "LowerArm_L", 0.60, 0.06)}),
            (0.44, pose(root=(0.0, -0.08, 0.18), chest=(0.14, -0.50, 0.0),
                        hips=(0.0, -0.40, 0.0), foot_R=p(-0.10, 0.16, 0.34)),
             pose(root=(0.0, -0.04, -0.06), hips=(-0.24, -0.20, 0.0),
                  chest=(-0.10, -0.20, 0.0), foot_L=p(0.20, 0.10, -0.22)),
             {"hand_L": ("Chest", "Neck", 0.50, -0.12),
              "hand_R": ("UpperArm_L", "LowerArm_L", 0.60, 0.06)}),
            (0.72, pose(root=(0.0, -0.14, 0.20), chest=(0.20, -0.80, 0.0),
                        hips=(0.0, -0.70, 0.0),
                        foot_R=p(-0.06, 0.06, 0.44), foot_L=p(0.18, 0.02, 0.10)),
             pose(root=(-0.16, -0.24, -0.26), hips=(-0.90, -0.50, 0.0),
                  chest=(-0.20, -0.30, 0.0), head=(-0.16, 0.0, 0.0),
                  foot_L=p(0.26, 0.44, -0.12), foot_R=p(-0.24, 0.40, -0.20),
                  hand_R=p(-0.34, 0.34, -0.16)),
             {"hand_L": ("Chest", "Neck", 0.50, -0.12),
              "hand_R": ("UpperArm_L", "LowerArm_L", 0.55, 0.06)}),
            (1.02, pose(root=(0.0, -0.26, 0.22), chest=(0.34, -0.86, 0.0),
                        hips=(0.22, -0.76, 0.0),
                        foot_L=p(0.18, 0.06, 0.12), foot_R=p(-0.20, 0.06, 0.24)),
             pose(root=(-0.24, -0.52, -0.34), hips=(-1.40, -0.70, 0.0),
                  chest=(0.10, -0.20, 0.0),
                  foot_L=p(0.26, 0.18, -0.28), foot_R=p(-0.24, 0.16, -0.32),
                  hand_L=p(0.34, 0.12, -0.30), hand_R=p(-0.34, 0.10, -0.32)),
             {"hand_L": ("Chest", "Neck", 0.45, -0.12),
              "hand_R": ("Hips", "Spine", 0.30, 0.12)}),
        ],
    },
}


# ---------------------------------------------------------------------------
# Movesets
# ---------------------------------------------------------------------------

FIGHTERS = {
    "fighter_apose_01": {
        "name": "khabib", "stance": "orthodox",
        "signature": ["takedown_double_leg", "takedown_single_leg", "body_lock_throw",
                      "ground_pound", "level_change", "overhand_R", "knee",
                      "jab", "cross", "hook_L", "uppercut_R", "kick_low", "body_hook"],
        "combos": {
            "combo_chain_wrestle": (["jab", "overhand_R", "level_change"], 0.12),
            "combo_smash": (["cross", "knee", "takedown_double_leg"], 0.14),
            # The takedown is not the end of the exchange: whoever lands it
            # starts hitting from the top.
            "combo_ground_and_pound": (["takedown_double_leg", "ground_pound"], 0.10),
        },
    },
    "fighter_apose_02": {
        "name": "jones", "stance": "orthodox",
        "signature": ["oblique_kick", "side_kick", "spinning_elbow", "elbow",
                      "flying_knee", "superman_punch", "kick_high", "front_kick",
                      "jab", "cross", "hook_R", "knee", "takedown_double_leg",
                      "ground_pound"],
        "combos": {
            "combo_range": (["oblique_kick", "jab", "side_kick"], 0.13),
            "combo_elbows": (["jab", "elbow", "spinning_elbow"], 0.11),
            "combo_ground_and_pound": (["takedown_double_leg", "ground_pound"], 0.10),
        },
    },
    "fighter_apose_03": {
        "name": "islam", "stance": "orthodox",
        "signature": ["takedown_double_leg", "trip_throw", "body_lock_throw",
                      "ground_pound", "kick_low", "kick_high", "front_kick",
                      "jab", "cross", "hook_L", "uppercut_R", "knee", "elbow"],
        "combos": {
            "combo_grind": (["jab", "cross", "trip_throw"], 0.13),
            "combo_strike_takedown": (["kick_low", "cross", "takedown_double_leg"], 0.14),
            "combo_ground_and_pound": (["trip_throw", "ground_pound"], 0.10),
        },
    },
    "fighter_apose_04": {
        "name": "conor", "stance": "southpaw",
        "signature": ["cross", "uppercut_L", "hook_L", "jab", "front_kick",
                      "kick_high", "spinning_back_kick", "teep", "body_hook",
                      "knee", "overhand_R", "walkoff", "kick_body"],
        "combos": {
            "combo_left_hand": (["jab", "cross", "hook_L"], 0.12),
            "combo_switch": (["teep", "cross", "spinning_back_kick"], 0.13),
        },
    },
}


def moveset(fighter_key):
    """Every clip a given fighter should carry."""
    spec = FIGHTERS[fighter_key]
    stance = SOUTHPAW if spec["stance"] == "southpaw" else GUARD
    turn = -1.0 if stance is SOUTHPAW else 1.0

    clips = {k: v for k, v in base_clips(stance).items()}
    pool = strike_pool(stance, turn)
    for move in spec["signature"]:
        if move in pool:
            clips[move] = pool[move]
    return clips, spec, stance, turn


# ---------------------------------------------------------------------------
# Staff: the referee and the corner coach
#
# They stand rather than fight, so they get their own base pose -- feet level,
# arms down -- instead of a bladed stance. The referee's vocabulary is the one
# you actually see: watching, breaking a stalled position, waving a fight off,
# raising the winner's hand and putting the belt on him.
# ---------------------------------------------------------------------------

STAND = {
    "hand_L": Reach((-0.22, -0.93, 0.30), 0.88),
    "hand_R": Reach((0.22, -0.93, 0.30), 0.88),
    "foot_L": p(0.13, 0.02, 0.02), "foot_R": p(-0.13, 0.02, -0.02),
    "root": (0.0, -0.01, 0.0),
    "hips": (0.0, 0.0, 0.0), "spine": (0.02, 0.0, 0.0), "chest": (0.0, 0.0, 0.0),
    "head": (0.0, 0.0, 0.0),
}


def staff_clips(role):
    g = STAND

    common = {
        "stand": (True, [
            (0.00, pose(g)),
            (1.60, pose(g, chest=(0.02, 0.05, 0.0), head=(0.03, 0.08, 0.0))),
            (3.20, pose(g)),
        ]),
        "walk": (True, walk_cycle(g, stride=0.17, period=1.05, lift=0.09)),
    }

    if role == "coach":
        return {
            **common,
            # Hands on the fence, shouting through it.
            "coach_shout": (True, [
                (0.00, pose(g, hand_L=Reach((-0.36, 0.30, 0.88), 0.80),
                            hand_R=Reach((0.36, 0.30, 0.88), 0.80),
                            chest=(0.16, 0.0, 0.0), head=(-0.10, 0.0, 0.0))),
                (0.55, pose(g, hand_L=Reach((-0.30, 0.44, 0.85), 0.84),
                            hand_R=Reach((0.42, 0.24, 0.87), 0.76),
                            chest=(0.20, -0.06, 0.0), head=(-0.16, -0.06, 0.0))),
                (1.10, pose(g, hand_L=Reach((-0.36, 0.30, 0.88), 0.80),
                            hand_R=Reach((0.36, 0.30, 0.88), 0.80),
                            chest=(0.16, 0.0, 0.0), head=(-0.10, 0.0, 0.0))),
            ]),
            # Arms folded, watching the round.
            "coach_watch": (True, [
                (0.00, pose(g, hand_L=Reach((0.55, -0.30, 0.78), 0.52),
                            hand_R=Reach((-0.55, -0.30, 0.78), 0.52),
                            chest=(0.06, 0.0, 0.0))),
                (2.00, pose(g, hand_L=Reach((0.55, -0.28, 0.79), 0.53),
                            hand_R=Reach((-0.55, -0.28, 0.79), 0.53),
                            chest=(0.08, 0.02, 0.0), head=(0.04, 0.05, 0.0))),
                (4.00, pose(g, hand_L=Reach((0.55, -0.30, 0.78), 0.52),
                            hand_R=Reach((-0.55, -0.30, 0.78), 0.52),
                            chest=(0.06, 0.0, 0.0))),
            ]),
            # Passing something through the fence: the arm goes out and stays
            # out, held at the top, because the fighter has to come and take
            # it. Both hands are used -- the left steadies him on the mesh --
            # so whichever prop the game hangs off the right hand reads as
            # being offered rather than dropped.
            "coach_hand": (True, [
                (0.00, pose(g, hand_L=Reach((-0.30, 0.24, 0.92), 0.72),
                            hand_R=Reach((0.34, -0.10, 0.93), 0.60),
                            chest=(0.10, -0.06, 0.0), head=(0.08, -0.08, 0.0))),
                (0.55, pose(g, hand_L=Reach((-0.30, 0.24, 0.92), 0.72),
                            hand_R=Reach((0.22, 0.16, 0.96), 0.94),
                            chest=(0.20, -0.10, 0.0), head=(0.12, -0.10, 0.0),
                            root=(0.0, -0.02, 0.05))),
                (2.20, pose(g, hand_L=Reach((-0.30, 0.24, 0.92), 0.72),
                            hand_R=Reach((0.20, 0.18, 0.96), 0.96),
                            chest=(0.22, -0.10, 0.0), head=(0.14, -0.10, 0.0),
                            root=(0.0, -0.02, 0.06))),
                (2.80, pose(g, hand_L=Reach((-0.30, 0.24, 0.92), 0.72),
                            hand_R=Reach((0.22, 0.16, 0.96), 0.94),
                            chest=(0.20, -0.10, 0.0), head=(0.12, -0.10, 0.0),
                            root=(0.0, -0.02, 0.05))),
            ]),
            # His man won. Both fists up, and he actually leaves the ground --
            # a coach who only raises his arms looks like he is stretching.
            "coach_jump": (True, [
                (0.00, pose(g, hand_L=Reach((-0.40, 0.30, 0.86), 0.60),
                            hand_R=Reach((0.40, 0.30, 0.86), 0.60),
                            hips=(0.0, 0.0, 0.0), root=(0.0, -0.16, 0.0),
                            foot_L=p(0.14, 0.02, 0.04), foot_R=p(-0.14, 0.02, -0.04))),
                (0.18, pose(g, hand_L=Reach((-0.34, 0.88, 0.32), 0.96),
                            hand_R=Reach((0.34, 0.88, 0.32), 0.96),
                            chest=(-0.14, 0.0, 0.0), head=(-0.20, 0.0, 0.0),
                            root=(0.0, 0.30, 0.0),
                            foot_L=p(0.14, -0.10, 0.06), foot_R=p(-0.14, -0.10, -0.06))),
                (0.46, pose(g, hand_L=Reach((-0.30, 0.94, 0.16), 0.98),
                            hand_R=Reach((0.30, 0.94, 0.16), 0.98),
                            chest=(-0.18, 0.0, 0.0), head=(-0.24, 0.0, 0.0),
                            root=(0.0, 0.46, 0.0),
                            foot_L=p(0.15, -0.16, 0.02), foot_R=p(-0.15, -0.16, -0.02))),
                (0.74, pose(g, hand_L=Reach((-0.34, 0.88, 0.32), 0.96),
                            hand_R=Reach((0.34, 0.88, 0.32), 0.96),
                            chest=(-0.14, 0.0, 0.0), head=(-0.20, 0.0, 0.0),
                            root=(0.0, 0.22, 0.0),
                            foot_L=p(0.14, -0.08, 0.06), foot_R=p(-0.14, -0.08, -0.06))),
                (0.94, pose(g, hand_L=Reach((-0.40, 0.46, 0.79), 0.72),
                            hand_R=Reach((0.40, 0.46, 0.79), 0.72),
                            chest=(0.10, 0.0, 0.0), root=(0.0, -0.22, 0.0),
                            foot_L=p(0.15, 0.02, 0.04), foot_R=p(-0.15, 0.02, -0.04))),
                (1.20, pose(g, hand_L=Reach((-0.40, 0.30, 0.86), 0.60),
                            hand_R=Reach((0.40, 0.30, 0.86), 0.60),
                            root=(0.0, -0.16, 0.0),
                            foot_L=p(0.14, 0.02, 0.04), foot_R=p(-0.14, 0.02, -0.04))),
            ]),
        }

    # -- referee ------------------------------------------------------------
    return {
        **common,
        # Crouched over the action, hands ready to step in.
        "ref_watch": (True, [
            (0.00, pose(g, root=(0.0, -0.10, 0.0), chest=(0.24, 0.0, 0.0),
                        head=(0.10, 0.0, 0.0),
                        hand_L=Reach((-0.28, -0.42, 0.86), 0.72),
                        hand_R=Reach((0.28, -0.42, 0.86), 0.72))),
            (1.40, pose(g, root=(0.0, -0.12, 0.02), chest=(0.28, 0.10, 0.0),
                        head=(0.12, 0.12, 0.0),
                        hand_L=Reach((-0.30, -0.38, 0.87), 0.74),
                        hand_R=Reach((0.26, -0.44, 0.86), 0.70))),
            (2.80, pose(g, root=(0.0, -0.10, 0.0), chest=(0.24, 0.0, 0.0),
                        head=(0.10, 0.0, 0.0),
                        hand_L=Reach((-0.28, -0.42, 0.86), 0.72),
                        hand_R=Reach((0.28, -0.42, 0.86), 0.72))),
        ]),
        # "Break!" -- both arms sweep apart between the fighters.
        "ref_break": (False, [
            (0.00, pose(g)),
            (0.22, pose(g, hand_L=Reach((-0.12, 0.10, 0.98), 0.80),
                        hand_R=Reach((0.12, 0.10, 0.98), 0.80),
                        chest=(0.14, 0.0, 0.0), root=(0.0, -0.06, 0.06))),
            (0.55, pose(g, hand_L=Reach((-0.92, 0.16, 0.36), 0.94),
                        hand_R=Reach((0.92, 0.16, 0.36), 0.94),
                        chest=(0.04, 0.0, 0.0), root=(0.0, -0.02, 0.02))),
            (0.85, pose(g, hand_L=Reach((-0.92, 0.16, 0.36), 0.94),
                        hand_R=Reach((0.92, 0.16, 0.36), 0.94))),
            (1.25, pose(g)),
        ]),
        # Waving it off: arms cross overhead, twice.
        "ref_wave_off": (False, [
            (0.00, pose(g)),
            (0.25, pose(g, hand_L=Reach((-0.62, 0.78, 0.10), 0.95),
                        hand_R=Reach((0.62, 0.78, 0.10), 0.95))),
            (0.55, pose(g, hand_L=Reach((0.34, 0.92, 0.10), 0.92),
                        hand_R=Reach((-0.34, 0.92, 0.10), 0.92))),
            (0.85, pose(g, hand_L=Reach((-0.62, 0.78, 0.10), 0.95),
                        hand_R=Reach((0.62, 0.78, 0.10), 0.95))),
            (1.15, pose(g, hand_L=Reach((0.34, 0.92, 0.10), 0.92),
                        hand_R=Reach((-0.34, 0.92, 0.10), 0.92))),
            (1.60, pose(g)),
        ]),
        # Counting a man down: pointing, arm dropping with each number.
        "ref_count": (True, [
            (0.00, pose(g, root=(0.0, -0.14, 0.0), chest=(0.30, 0.0, 0.0),
                        hand_R=Reach((0.20, 0.62, 0.76), 0.86))),
            (0.45, pose(g, root=(0.0, -0.14, 0.0), chest=(0.30, 0.0, 0.0),
                        hand_R=Reach((0.24, 0.18, 0.95), 0.90))),
            (0.90, pose(g, root=(0.0, -0.14, 0.0), chest=(0.30, 0.0, 0.0),
                        hand_R=Reach((0.20, 0.62, 0.76), 0.86))),
        ]),
        # The winner's hand goes up: referee holds his wrist and lifts.
        "ref_raise_hand": (False, [
            (0.00, pose(g)),
            (0.70, pose(g, hand_L=Reach((-0.48, 0.22, 0.85), 0.86),
                        chest=(0.06, -0.14, 0.0))),
            (1.60, pose(g, hand_L=Reach((-0.30, 0.92, 0.25), 0.97),
                        chest=(-0.10, -0.10, 0.0), head=(-0.18, 0.0, 0.0))),
            (3.20, pose(g, hand_L=Reach((-0.30, 0.92, 0.25), 0.97),
                        chest=(-0.10, -0.10, 0.0), head=(-0.18, 0.0, 0.0))),
            (3.90, pose(g)),
        ]),
        # Both hands take the belt and pass it round the champion's waist.
        "ref_belt": (False, [
            (0.00, pose(g)),
            (0.60, pose(g, hand_L=Reach((-0.34, -0.18, 0.92), 0.82),
                        hand_R=Reach((0.34, -0.18, 0.92), 0.82),
                        chest=(0.18, 0.0, 0.0), head=(0.14, 0.0, 0.0))),
            (1.50, pose(g, hand_L=Reach((-0.62, -0.02, 0.78), 0.90),
                        hand_R=Reach((0.62, -0.02, 0.78), 0.90),
                        chest=(0.24, 0.0, 0.0), head=(0.16, 0.0, 0.0),
                        root=(0.0, -0.05, 0.06))),
            (2.60, pose(g, hand_L=Reach((-0.86, 0.04, 0.50), 0.94),
                        hand_R=Reach((0.86, 0.04, 0.50), 0.94),
                        chest=(0.16, 0.0, 0.0), root=(0.0, -0.03, 0.02))),
            (3.40, pose(g, hand_L=Reach((-0.40, 0.30, 0.86), 0.70),
                        hand_R=Reach((0.40, 0.30, 0.86), 0.70),
                        chest=(0.0, 0.0, 0.0))),
            (4.00, pose(g)),
        ]),
    }


STAFF = {
    "official_referee": {"name": "referee", "role": "referee"},
    "official_coach": {"name": "coach", "role": "coach"},
}
