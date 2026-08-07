#!/usr/bin/env python3
"""Author attack animations onto the rigged fighters and bake them into GLB.

Poses are described by where the hands and feet go, not by per-bone Euler
angles. A punch is "lead fist to here, at this height, at this time"; a
two-bone IK solver turns that into shoulder and elbow rotations. Authoring
by angles means guessing how a rotation composes through a parent that has
already turned, which is unreadable and produces broken-looking limbs.

Every clip is written as a glTF animation, so three.js can play it straight
off the file with AnimationMixer -- no runtime rigging code.

    python3 tools/animate.py                      # all rigged fighters
    python3 tools/animate.py --list               # show the clip library
    python3 tools/animate.py --only fighter_apose_01 --preview

Requires numpy and scipy.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation, Slerp  # noqa: F401

REPO = Path(__file__).resolve().parent.parent

# Targets are written in a body-relative frame so one clip fits every fighter:
#   x = sideways (+ is the fighter's left)
#   y = height as a fraction of the fighter's own height
#   z = forward (+ is the way the fighter faces)
# Reach is expressed as a fraction of the arm's or leg's own length, so a
# short fighter does not overextend and a tall one does not fall short.


def _p(x, y, z):
    return np.array([x, y, z], np.float64)


# ---------------------------------------------------------------------------
# Pose vocabulary
#
# GUARD is the resting stance every clip starts and ends on. Strikes are
# written as departures from it, which keeps the library short and makes
# blending between clips land in a consistent place.
# ---------------------------------------------------------------------------

GUARD = {
    "hand_L": _p(0.13, 0.79, 0.20), "hand_R": _p(-0.11, 0.82, 0.16),
    "foot_L": _p(0.16, 0.02, 0.16), "foot_R": _p(-0.17, 0.02, -0.18),
    "hips": (0.0, -0.30, 0.0), "spine": (0.04, -0.10, 0.0), "chest": (0.0, -0.12, 0.0),
    "head": (0.0, 0.20, 0.0),
}


def pose(**overrides):
    """A guard stance with some parts moved."""
    out = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in GUARD.items()}
    out.update(overrides)
    return out


# Each clip is (loop, [(time_seconds, pose), ...]).
CLIPS = {
    "idle": (True, [
        (0.00, pose()),
        (0.90, pose(hand_L=_p(0.13, 0.81, 0.20), hand_R=_p(-0.11, 0.84, 0.16),
                    chest=(0.0, -0.12, 0.02))),
        (1.80, pose()),
    ]),
    "jab": (False, [
        (0.00, pose()),
        (0.09, pose(hand_L=_p(0.10, 0.80, 0.30), chest=(0.0, -0.22, 0.0))),
        (0.19, pose(hand_L=_p(0.02, 0.84, 0.62), chest=(0.0, 0.10, 0.0),
                    hips=(0.0, -0.10, 0.0))),
        (0.34, pose(hand_L=_p(0.09, 0.81, 0.34), chest=(0.0, -0.14, 0.0))),
        (0.48, pose()),
    ]),
    "cross": (False, [
        (0.00, pose()),
        (0.10, pose(hand_R=_p(-0.16, 0.83, 0.06), chest=(0.0, -0.34, 0.0),
                    hips=(0.0, -0.22, 0.0))),
        (0.24, pose(hand_R=_p(0.01, 0.85, 0.66), chest=(0.0, 0.30, 0.0),
                    hips=(0.0, 0.24, 0.0), foot_R=_p(-0.17, 0.05, -0.14))),
        (0.42, pose(hand_R=_p(-0.12, 0.82, 0.24), chest=(0.0, -0.05, 0.0))),
        (0.58, pose()),
    ]),
    "hook": (False, [
        (0.00, pose()),
        (0.11, pose(hand_L=_p(0.26, 0.80, 0.10), chest=(0.0, -0.34, 0.0))),
        (0.26, pose(hand_L=_p(-0.16, 0.86, 0.44), chest=(0.0, 0.34, 0.0),
                    hips=(0.0, 0.26, 0.0))),
        (0.44, pose(hand_L=_p(0.10, 0.82, 0.26), chest=(0.0, -0.06, 0.0))),
        (0.60, pose()),
    ]),
    "uppercut": (False, [
        (0.00, pose()),
        (0.12, pose(hand_R=_p(-0.14, 0.62, 0.22), chest=(0.10, -0.30, 0.0),
                    hips=(0.0, -0.18, 0.0))),
        (0.27, pose(hand_R=_p(-0.04, 1.02, 0.40), chest=(-0.16, 0.20, 0.0),
                    hips=(0.0, 0.18, 0.0))),
        (0.45, pose(hand_R=_p(-0.12, 0.83, 0.20))),
        (0.62, pose()),
    ]),
    "kick_low": (False, [
        (0.00, pose()),
        (0.12, pose(foot_R=_p(-0.24, 0.14, -0.24), hips=(0.0, -0.22, 0.0))),
        (0.28, pose(foot_R=_p(-0.06, 0.30, 0.60), hips=(0.0, 0.30, 0.0),
                    chest=(0.06, 0.22, 0.0), hand_L=_p(0.22, 0.74, 0.10))),
        (0.48, pose(foot_R=_p(-0.20, 0.06, -0.10), hips=(0.0, 0.05, 0.0))),
        (0.68, pose()),
    ]),
    "kick_high": (False, [
        (0.00, pose()),
        (0.14, pose(foot_R=_p(-0.26, 0.18, -0.26), hips=(0.0, -0.28, 0.0),
                    chest=(0.0, -0.20, 0.0))),
        (0.34, pose(foot_R=_p(0.00, 0.92, 0.52), hips=(0.0, 0.42, 0.0),
                    chest=(0.10, 0.34, 0.0), head=(0.0, 0.30, 0.0),
                    hand_L=_p(0.30, 0.60, 0.04), hand_R=_p(-0.24, 0.92, 0.10))),
        (0.56, pose(foot_R=_p(-0.22, 0.08, -0.12), hips=(0.0, 0.10, 0.0))),
        (0.80, pose()),
    ]),
    "knee": (False, [
        (0.00, pose()),
        (0.11, pose(hips=(0.0, -0.18, 0.0), chest=(-0.10, -0.12, 0.0))),
        (0.26, pose(foot_R=_p(-0.10, 0.60, 0.34), hips=(-0.12, -0.10, 0.0),
                    chest=(0.20, -0.08, 0.0),
                    hand_L=_p(0.10, 0.94, 0.34), hand_R=_p(-0.08, 0.96, 0.30))),
        (0.44, pose(foot_R=_p(-0.17, 0.06, -0.14))),
        (0.62, pose()),
    ]),
    "block": (False, [
        (0.00, pose()),
        (0.10, pose(hand_L=_p(0.14, 0.94, 0.26), hand_R=_p(-0.13, 0.95, 0.24),
                    chest=(0.14, 0.0, 0.0), head=(0.14, 0.0, 0.0))),
        (0.40, pose(hand_L=_p(0.14, 0.94, 0.26), hand_R=_p(-0.13, 0.95, 0.24),
                    chest=(0.14, 0.0, 0.0), head=(0.14, 0.0, 0.0))),
        (0.55, pose()),
    ]),
    "hit_head": (False, [
        (0.00, pose()),
        (0.08, pose(head=(-0.34, 0.40, 0.0), chest=(-0.16, 0.26, 0.0),
                    hand_L=_p(0.20, 0.72, 0.10), hips=(0.0, 0.16, 0.0))),
        (0.30, pose(head=(0.06, 0.10, 0.0), chest=(0.04, -0.04, 0.0))),
        (0.50, pose()),
    ]),
    "knockdown": (False, [
        (0.00, pose()),
        (0.10, pose(head=(-0.40, 0.30, 0.0), chest=(-0.24, 0.20, 0.0))),
        (0.45, pose(hips=(-0.55, 0.20, 0.0), chest=(-0.40, 0.10, 0.0),
                    head=(-0.30, 0.0, 0.0),
                    foot_L=_p(0.20, 0.20, -0.30), foot_R=_p(-0.22, 0.16, -0.34),
                    hand_L=_p(0.30, 0.30, -0.20), hand_R=_p(-0.30, 0.28, -0.24))),
        (1.10, pose(hips=(-1.20, 0.10, 0.0), chest=(-0.70, 0.0, 0.0),
                    head=(-0.20, 0.0, 0.0),
                    foot_L=_p(0.22, 0.10, -0.55), foot_R=_p(-0.24, 0.08, -0.58),
                    hand_L=_p(0.34, 0.14, -0.34), hand_R=_p(-0.34, 0.12, -0.36))),
    ]),
}

# One signature combination per fighter, built by splicing clips end to end.
# The overlap trims the recovery tail of each strike so the next one starts
# before the last has fully reset -- that is what makes a combo read as one
# motion instead of separate punches.
COMBOS = {
    "fighter_apose_01": ("combo_boxer", ["jab", "cross", "hook"], 0.12),
    "fighter_apose_02": ("combo_kickboxer", ["jab", "cross", "kick_low"], 0.14),
    "fighter_apose_03": ("combo_clinch", ["uppercut", "knee", "hook"], 0.10),
    "fighter_apose_04": ("combo_striker", ["jab", "jab", "kick_high"], 0.13),
}


# ---------------------------------------------------------------------------
# Rig reading and IK
# ---------------------------------------------------------------------------

def read_glb(path):
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_len])
    bin_len = struct.unpack_from("<I", data, 20 + json_len)[0]
    return gltf, bytearray(data[28 + json_len:28 + json_len + bin_len])


def joint_world_positions(gltf):
    """Rest-pose world position of every joint, plus its node index."""
    positions, parent_of = {}, {}

    def walk(node_index, origin, parent_name):
        node = gltf["nodes"][node_index]
        here = origin + np.array(node.get("translation", [0, 0, 0]), np.float64)
        name = node.get("name")
        if name:
            positions[name] = here
            parent_of[name] = parent_name
        for child in node.get("children", []):
            walk(child, here, name)

    walk(0, np.zeros(3), None)
    index_of = {n.get("name"): i for i, n in enumerate(gltf["nodes"]) if n.get("name")}
    return positions, parent_of, index_of


def two_bone_ik(root, target, len_upper, len_lower, pole):
    """Return (elbow, effector) for a two-bone chain reaching toward target."""
    to_target = target - root
    reach = np.linalg.norm(to_target)
    span = len_upper + len_lower
    reach = float(np.clip(reach, abs(len_upper - len_lower) + 1e-4, span - 1e-4))
    direction = to_target / (np.linalg.norm(to_target) or 1.0)
    effector = root + direction * reach

    cos_root = np.clip((len_upper ** 2 + reach ** 2 - len_lower ** 2)
                       / (2 * len_upper * reach), -1.0, 1.0)
    angle = float(np.arccos(cos_root))

    # Swing the elbow off the straight line, toward the pole hint.
    side = pole - direction * float(pole @ direction)
    norm = np.linalg.norm(side)
    side = (side / norm if norm > 1e-6
            else np.cross(direction, [0.0, 0.0, 1.0]))
    elbow = root + len_upper * (direction * np.cos(angle) + side * np.sin(angle))
    return elbow, effector


def align(from_dir, to_dir):
    """Shortest rotation carrying one direction onto another."""
    a = from_dir / (np.linalg.norm(from_dir) or 1.0)
    b = to_dir / (np.linalg.norm(to_dir) or 1.0)
    axis = np.cross(a, b)
    length = np.linalg.norm(axis)
    if length < 1e-9:
        if a @ b > 0:
            return Rotation.identity()
        fallback = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(fallback) < 1e-6:
            fallback = np.cross(a, [0.0, 1.0, 0.0])
        return Rotation.from_rotvec(fallback / np.linalg.norm(fallback) * np.pi)
    return Rotation.from_rotvec(axis / length * float(np.arctan2(length, a @ b)))


class Solver:
    """Turns a pose (hand/foot targets plus torso angles) into bone rotations."""

    CHAINS = {
        "hand_L": ("UpperArm_L", "LowerArm_L", "Hand_L"),
        "hand_R": ("UpperArm_R", "LowerArm_R", "Hand_R"),
        "foot_L": ("UpperLeg_L", "LowerLeg_L", "Foot_L"),
        "foot_R": ("UpperLeg_R", "LowerLeg_R", "Foot_R"),
    }
    TORSO = {"hips": "Hips", "spine": "Spine", "chest": "Chest", "head": "Head"}

    def __init__(self, rest, parent_of):
        self.rest = rest
        self.parent_of = parent_of
        self.height = max(p[1] for p in rest.values())

    def _world_rotation(self, local, bone):
        """Accumulated rotation of a bone's parent chain."""
        rotation = Rotation.identity()
        chain = []
        node = self.parent_of.get(bone)
        while node:
            chain.append(node)
            node = self.parent_of.get(node)
        for name in reversed(chain):
            rotation = rotation * local.get(name, Rotation.identity())
        return rotation

    def solve(self, target_pose):
        local = {}
        for key, bone in self.TORSO.items():
            if key in target_pose:
                local[bone] = Rotation.from_euler("xyz", target_pose[key])

        for key, (upper, lower, tip) in self.CHAINS.items():
            if key not in target_pose:
                continue
            spec = target_pose[key]
            target = np.array([spec[0] * self.height, spec[1] * self.height,
                               spec[2] * self.height], np.float64)

            root_rest, mid_rest, tip_rest = self.rest[upper], self.rest[lower], self.rest[tip]
            parent_rotation = self._world_rotation(local, upper)
            root = self.rest[self.parent_of[upper]] + parent_rotation.apply(
                root_rest - self.rest[self.parent_of[upper]])

            len_upper = float(np.linalg.norm(mid_rest - root_rest))
            len_lower = float(np.linalg.norm(tip_rest - mid_rest))
            # Elbows point back and out; knees point forward.
            pole = (np.array([np.sign(root_rest[0]) * 0.5, -0.2, -1.0])
                    if key.startswith("hand")
                    else np.array([np.sign(root_rest[0]) * 0.2, -0.2, 1.0]))
            elbow, effector = two_bone_ik(root, target, len_upper, len_lower, pole)

            upper_now = parent_rotation.apply(mid_rest - root_rest)
            upper_rotation = align(upper_now, elbow - root)
            local[upper] = parent_rotation.inv() * upper_rotation * parent_rotation

            after_upper = upper_rotation * parent_rotation
            lower_now = after_upper.apply(tip_rest - mid_rest)
            lower_rotation = align(lower_now, effector - elbow)
            local[lower] = after_upper.inv() * lower_rotation * after_upper
        return local


# ---------------------------------------------------------------------------
# Baking
# ---------------------------------------------------------------------------

def splice(clips, order, overlap):
    """Chain clips into one, trimming `overlap` seconds off each seam."""
    frames, clock = [], 0.0
    for i, name in enumerate(order):
        _, keys = clips[name]
        cut = keys[:-1] if i < len(order) - 1 else keys
        for time, target in cut:
            frames.append((clock + time, target))
        clock += cut[-1][0] + (0.0 if i == len(order) - 1 else -overlap + cut[-1][0] * 0)
        clock = frames[-1][0] - overlap if i < len(order) - 1 else clock
    # Guarantee strictly increasing times after the trims.
    cleaned = [frames[0]]
    for time, target in frames[1:]:
        cleaned.append((max(time, cleaned[-1][0] + 1e-3), target))
    return cleaned


def bake(gltf, blob, solver, index_of, clips):
    animations, accessors, views = [], gltf["accessors"], gltf["bufferViews"]

    def add(array):
        raw = array.astype(np.float32).tobytes()
        raw += b"\x00" * (-len(raw) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)})
        blob.extend(raw)
        accessors.append({
            "bufferView": len(views) - 1, "componentType": 5126,
            "count": int(len(array)),
            "type": "SCALAR" if array.ndim == 1 else f"VEC{array.shape[1]}",
        })
        if array.ndim == 1:
            accessors[-1]["min"] = [float(array.min())]
            accessors[-1]["max"] = [float(array.max())]
        return len(accessors) - 1

    for name, (loop, frames) in clips.items():
        times = np.array([t for t, _ in frames], np.float32)
        solved = [solver.solve(p) for _, p in frames]
        bones = sorted({b for s in solved for b in s})
        channels, samplers = [], []
        for bone in bones:
            quats = np.array([s.get(bone, Rotation.identity()).as_quat() for s in solved])
            # Keep the quaternion path on one hemisphere or the slerp between
            # keys takes the long way round and the limb spins.
            for i in range(1, len(quats)):
                if quats[i] @ quats[i - 1] < 0:
                    quats[i] = -quats[i]
            samplers.append({"input": add(times), "output": add(quats),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": index_of[bone], "path": "rotation"}})
        animations.append({"name": name, "channels": channels, "samplers": samplers,
                           "extras": {"loop": bool(loop),
                                      "duration": float(times[-1])}})
    gltf["animations"] = animations
    return gltf, blob


def write_glb(path, gltf, blob):
    gltf["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942))
        fh.write(bytes(blob))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=REPO / "build" / "rigged")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "animated")
    ap.add_argument("--only", action="append")
    ap.add_argument("--list", action="store_true", help="print the clip library and exit")
    args = ap.parse_args()

    if args.list:
        for name, (loop, frames) in CLIPS.items():
            print(f"  {name:12} {frames[-1][0]:.2f}s  {len(frames)} keys"
                  f"{'  (loops)' if loop else ''}")
        for fighter, (name, order, _) in COMBOS.items():
            print(f"  {name:12} {fighter} = {' -> '.join(order)}")
        return

    sources = ([args.src / f"{s}.glb" for s in args.only] if args.only
               else sorted(args.src.glob("*.glb")))
    if not sources:
        sys.exit(f"no rigged GLB under {args.src}; run tools/autorig.py first")
    args.out.mkdir(parents=True, exist_ok=True)

    for src in sources:
        gltf, blob = read_glb(src)
        rest, parent_of, index_of = joint_world_positions(gltf)
        solver = Solver(rest, parent_of)

        clips = dict(CLIPS)
        if src.stem in COMBOS:
            name, order, overlap = COMBOS[src.stem]
            clips[name] = (False, splice(CLIPS, order, overlap))

        gltf, blob = bake(gltf, blob, solver, index_of, clips)
        dst = args.out / src.name
        write_glb(dst, gltf, blob)
        total = sum(a["extras"]["duration"] for a in gltf["animations"])
        print(f"{src.stem:22} {len(clips):2d} clips  {total:5.2f}s total  "
              f"{dst.stat().st_size / 1e6:5.2f} MB")


if __name__ == "__main__":
    main()
