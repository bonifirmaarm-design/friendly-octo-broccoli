#!/usr/bin/env python3
"""Bake each fighter's moveset into his rigged GLB as glTF animations.

Poses come from tools/moves.py and are written as hand and foot targets
rather than per-bone angles; a two-bone IK solver (tools/rigmath.py) turns
them into shoulder and elbow rotations. Authoring by angle means predicting
how a rotation composes through a parent that has already turned, which is
unreadable and lands limbs in impossible places.

Takedowns are two-body moves and are handled differently. The man being
thrown is solved first, run through forward kinematics, and placed in front
of the attacker; only then are the attacker's hands aimed at grip points
read off that posed skeleton. Authoring the grab as fixed hand positions
would look right in one frame and slide off him in every other.

    python3 tools/animate.py                    # all rigged fighters
    python3 tools/animate.py --list             # every fighter's moveset
    python3 tools/animate.py --only fighter_apose_01

Requires numpy and scipy.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
import moves  # noqa: E402
from rigmath import Rig  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def read_glb(path):
    data = path.read_bytes()
    json_len = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + json_len])
    bin_len = struct.unpack_from("<I", data, 20 + json_len)[0]
    return gltf, bytearray(data[28 + json_len:28 + json_len + bin_len])


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


def read_rig(gltf):
    """Rest-pose world positions, parent links and node indices for the joints."""
    positions, parent_of = {}, {}

    def walk(node_index, origin, parent_name):
        node = gltf["nodes"][node_index]
        here = origin + np.array(node.get("translation", [0, 0, 0]), float)
        name = node.get("name")
        if name:
            positions[name] = here
            parent_of[name] = parent_name
        for child in node.get("children", []):
            walk(child, here, name)

    walk(0, np.zeros(3), None)
    # The armature wrapper is not a joint; drop anything not in the skin.
    joints = {gltf["nodes"][j]["name"] for j in gltf["skins"][0]["joints"]}
    positions = {k: v for k, v in positions.items() if k in joints}
    parent_of = {k: (v if v in joints else None)
                 for k, v in parent_of.items() if k in joints}
    index_of = {n.get("name"): i for i, n in enumerate(gltf["nodes"]) if n.get("name")}
    return positions, parent_of, index_of


def grip_point(world_pos, spec):
    """World position of a hold: along a bone, pushed out to the limb surface."""
    joint_a, joint_b, along, outward = spec
    a, b = world_pos[joint_a], world_pos[joint_b]
    point = a + (b - a) * along
    axis = b - a
    length = np.linalg.norm(axis)
    if length > 1e-9:
        axis = axis / length
        side = np.cross(axis, [0.0, 1.0, 0.0])
        if np.linalg.norm(side) < 1e-6:
            side = np.cross(axis, [0.0, 0.0, 1.0])
        point = point + side / (np.linalg.norm(side) or 1.0) * outward
    return point


def solve_takedown(rig, spec):
    """Solve both bodies for a takedown; returns attacker and victim tracks.

    The attacker's forward and sideways position is derived from the hold
    rather than authored. Hand-written root motion cannot keep up with a man
    being thrown -- the grip is reachable in the frame it was tuned for and
    the arms stretch off him in every other. Solving the stance from the grip
    means the thrower stays with his opponent through the whole throw.
    """
    yaw = Rotation.from_euler("y", spec["yaw"])
    place = np.asarray(spec["offset"], float) * rig.height
    arm = (np.linalg.norm(rig.rest["LowerArm_L"] - rig.rest["UpperArm_L"])
           + np.linalg.norm(rig.rest["Hand_L"] - rig.rest["LowerArm_L"]))
    hold_at = 0.78 * arm     # how far in front of the chest a grip should sit
    rise = 0.75              # how much of the grip's drop the chest follows

    attacker, victim = [], []
    for time, attacker_pose, victim_pose, grips in spec["frames"]:
        victim_local, victim_offset = rig.solve(victim_pose)
        victim.append((time, victim_local, victim_offset))

        if not grips:
            attacker.append((time, *rig.solve(attacker_pose)))
            continue

        # The victim is solved in his own space; move him into the attacker's
        # before reading any hold off him.
        world_pos, _ = rig.fk(victim_local, victim_offset)
        targets = {hand: yaw.apply(grip_point(world_pos, hold)) + place
                   for hand, hold in grips.items()}
        centre = np.mean(list(targets.values()), axis=0)

        # Turn the attacker to face the hold and step him so it lands at arm's
        # length. Facing matters as much as distance: an authored torso twist
        # of half a radian swings the far shoulder back until that arm can no
        # longer reach, which is why the near hand would land on the opponent
        # and the far one hang in the air. The authored vertical drop is kept
        # -- that is the level change, not a byproduct.
        working = dict(attacker_pose)
        pitch, _, roll = working.get("hips", (0.0, 0.0, 0.0))
        for _ in range(2):
            local, offset = rig.solve(working)
            world = rig.fk(local, offset)[0]
            to_hold = centre - world["Hips"]
            working["hips"] = (pitch, float(np.arctan2(to_hold[0], to_hold[2])), roll)

            local, offset = rig.solve(working)
            chest = rig.fk(local, offset)[0]["Chest"]
            facing = Rotation.from_euler("y", working["hips"][1]).apply([0.0, 0.0, 1.0])
            wanted = centre - facing * hold_at
            # Height is solved too, not just the footprint. Finishing a
            # takedown means going down with the man you are holding; pinning
            # the attacker at his authored height leaves him standing upright
            # with his arms stretched to a grip on the floor.
            offset = offset + np.array([wanted[0] - chest[0],
                                        (wanted[1] - chest[1]) * rise,
                                        wanted[2] - chest[2]])
            # He finishes a takedown kneeling on the mat, so the floor is
            # roughly where his own hips would be if he knelt -- not standing height.
            offset[1] = max(offset[1], -0.44 * rig.height)
            working["root"] = tuple(offset / rig.height)

        attacker.append((time, *rig.solve(working, extra_targets=targets)))
    return attacker, victim


def solve_clip(rig, frames):
    return [(time, *rig.solve(target)) for time, target in frames]


def splice(tracks, overlap):
    """Chain solved tracks end to end, trimming `overlap` off each seam."""
    out, clock = [], 0.0
    for i, track in enumerate(tracks):
        for time, local, offset in track:
            out.append((clock + time, local, offset))
        clock = out[-1][0] - (overlap if i < len(tracks) - 1 else 0.0)
    cleaned = [out[0]]
    for time, local, offset in out[1:]:
        cleaned.append((max(time, cleaned[-1][0] + 1e-3), local, offset))
    return cleaned


def bake(gltf, blob, tracks, index_of, hips_rest, loops):
    accessors, views = gltf["accessors"], gltf["bufferViews"]

    def add(array, kind):
        raw = np.ascontiguousarray(array, np.float32).tobytes()
        raw += b"\x00" * (-len(raw) % 4)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(raw)})
        blob.extend(raw)
        accessors.append({"bufferView": len(views) - 1, "componentType": 5126,
                          "count": int(len(array)), "type": kind})
        if kind == "SCALAR":
            accessors[-1]["min"] = [float(np.min(array))]
            accessors[-1]["max"] = [float(np.max(array))]
        return len(accessors) - 1

    animations = []
    for name, track in tracks.items():
        times = np.array([t for t, _, _ in track], np.float32)
        time_accessor = add(times, "SCALAR")
        bones = sorted({b for _, local, _ in track for b in local})

        channels, samplers = [], []
        for bone in bones:
            quats = np.array([local.get(bone, Rotation.identity()).as_quat()
                              for _, local, _ in track])
            # Keep the path on one hemisphere, or the slerp between two keys
            # takes the long way round and the limb spins through the body.
            for i in range(1, len(quats)):
                if quats[i] @ quats[i - 1] < 0:
                    quats[i] = -quats[i]
            samplers.append({"input": time_accessor, "output": add(quats, "VEC4"),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": index_of[bone], "path": "rotation"}})

        offsets = np.array([offset for _, _, offset in track])
        if np.abs(offsets).max() > 1e-6:
            # Root motion: a level change drops the hips, a takedown drives
            # them forward, a knockdown puts them on the floor.
            samplers.append({"input": time_accessor,
                             "output": add(hips_rest + offsets, "VEC3"),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": index_of["Hips"], "path": "translation"}})

        animations.append({"name": name, "channels": channels, "samplers": samplers,
                           "extras": {"loop": bool(loops.get(name, False)),
                                      "duration": float(times[-1])}})
    gltf["animations"] = animations
    return gltf, blob


def build_tracks(rig, fighter_key):
    clips, spec, stance, _ = moves.moveset(fighter_key)
    tracks, loops = {}, {}

    for name, (loop, frames) in clips.items():
        tracks[name] = solve_clip(rig, frames)
        loops[name] = loop

    # Takedowns produce a clip for the thrower and one for the man thrown.
    # Both go into every fighter's file: anyone can end up on either end.
    for name, takedown in moves.TAKEDOWNS.items():
        attacker, victim = solve_takedown(rig, takedown)
        tracks[f"{name}_victim"] = victim
        if name in spec["signature"] or any(
                name in order for order, _ in spec["combos"].values()):
            tracks[name] = attacker

    for name, (order, overlap) in spec["combos"].items():
        missing = [m for m in order if m not in tracks]
        if missing:
            raise SystemExit(f"{fighter_key}: combo {name} wants {missing}")
        tracks[name] = splice([tracks[m] for m in order], overlap)
        loops[name] = False
    return tracks, loops, spec


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=REPO / "build" / "rigged")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "animated")
    ap.add_argument("--only", action="append")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for key, spec in moves.FIGHTERS.items():
            clips, _, _, _ = moves.moveset(key)
            print(f"\n{spec['name']}  ({key}, {spec['stance']})")
            print(f"  базовые:   {', '.join(sorted(clips))}")
            print(f"  фирменные: {', '.join(spec['signature'])}")
            for name, (order, _) in spec["combos"].items():
                print(f"  {name}: {' -> '.join(order)}")
        return

    sources = ([args.src / f"{s}.glb" for s in args.only] if args.only
               else sorted(args.src.glob("*.glb")))
    if not sources:
        sys.exit(f"no rigged GLB under {args.src}; run tools/autorig.py first")
    args.out.mkdir(parents=True, exist_ok=True)

    for src in sources:
        if src.stem not in moves.FIGHTERS:
            print(f"{src.stem:22} SKIPPED -- no moveset defined")
            continue
        gltf, blob = read_glb(src)
        rest, parent_of, index_of = read_rig(gltf)
        rig = Rig(rest, parent_of)
        hips_rest = np.array(gltf["nodes"][index_of["Hips"]].get("translation", [0, 0, 0]),
                             float)

        tracks, loops, spec = build_tracks(rig, src.stem)
        gltf, blob = bake(gltf, blob, tracks, index_of, hips_rest, loops)

        dst = args.out / src.name
        write_glb(dst, gltf, blob)
        attacks = sum(1 for n in tracks if not n.endswith("_victim")
                      and n not in ("idle", "block", "slip", "hit_head", "hit_body",
                                    "knockdown", "get_up", "step_in"))
        print(f"{spec['name']:8} {src.stem:20} {len(tracks):2d} clips "
              f"({attacks} атак)  {dst.stat().st_size / 1e6:5.2f} MB")


if __name__ == "__main__":
    main()
