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


def p(x, y, z):
    return np.array([x, y, z], float)


# The stance everything departs from and returns to.
GUARD = {
    "hand_L": p(0.13, 0.79, 0.20), "hand_R": p(-0.11, 0.82, 0.16),
    "foot_L": p(0.16, 0.02, 0.16), "foot_R": p(-0.17, 0.02, -0.18),
    "root": (0.0, 0.0, 0.0),
    "hips": (0.0, -0.30, 0.0), "spine": (0.04, -0.10, 0.0), "chest": (0.0, -0.12, 0.0),
    "head": (0.0, 0.20, 0.0),
}

SOUTHPAW = dict(GUARD)   # lead side mirrored; Conor fights out of it
SOUTHPAW.update({
    "hand_L": p(0.11, 0.82, 0.16), "hand_R": p(-0.13, 0.79, 0.20),
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
    midpoint = (np.asarray(impact) + np.asarray(GUARD.get(limb, impact))) / 2
    frames.append((t_settle + tail, pose(base, **{limb: midpoint},
                                         **(recover or {}), **carry)))
    frames.append((t_end + tail, pose(base, **carry)))
    return False, frames


# ---------------------------------------------------------------------------
# Shared clips every fighter gets
# ---------------------------------------------------------------------------

def base_clips(stance=None):
    g = stance or GUARD
    turn = -1.0 if stance is SOUTHPAW else 1.0

    return {
        "idle": (True, [
            (0.00, pose(g)),
            (0.90, pose(g, hand_L=g["hand_L"] + p(0, 0.02, 0),
                        hand_R=g["hand_R"] + p(0, 0.02, 0),
                        chest=(0.0, -0.12 * turn, 0.02))),
            (1.80, pose(g)),
        ]),
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
        },
    },
    "fighter_apose_02": {
        "name": "jones", "stance": "orthodox",
        "signature": ["oblique_kick", "side_kick", "spinning_elbow", "elbow",
                      "flying_knee", "superman_punch", "kick_high", "front_kick",
                      "jab", "cross", "hook_R", "knee", "takedown_double_leg"],
        "combos": {
            "combo_range": (["oblique_kick", "jab", "side_kick"], 0.13),
            "combo_elbows": (["jab", "elbow", "spinning_elbow"], 0.11),
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
