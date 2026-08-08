#!/usr/bin/env python3
"""Fit a humanoid skeleton to an A-pose fighter and export a skinned GLB.

Nothing here is hand-placed. The joints are read out of the mesh itself:

  * the five extremities come from farthest-point sampling over geodesic
    distance (see segment.py),
  * walking geodesic rings outward from each extremity gives a centreline --
    the ring centres trace the middle of the limb -- and the joints are
    sampled along it,
  * the limb stops where the ring suddenly widens, which is where the limb
    meets the torso, so shoulder and hip land without being told where the
    body is.

Skin weights start as a hard nearest-bone assignment, masked by the
segmentation so a chest vertex can never be claimed by a hand bone, and are
then diffused across the mesh into smooth blends.

    python3 tools/autorig.py                       # every fighter and both officials
    python3 tools/autorig.py --src assets/staff    # just one directory
    python3 tools/autorig.py --only fighter_apose_01 --test-pose

The referee and the corner coach are rigged by the same code as the fighters
and are picked up by default along with them. They used to have to be asked
for by name, which meant a clean build produced a cage with nobody officiating
it and said nothing about why.

--test-pose bends the shoulders and knees in the exported file, which is the
quickest way to see whether the weights deform sanely.

Requires numpy, scipy and pillow.
"""

import argparse
import base64
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from segment import (adjacency, geodesic, find_extremities, segment,  # noqa: E402
                     ARM_R, ARM_L, LEG_L, LEG_R, HEAD, TORSO)

REPO = Path(__file__).resolve().parent.parent

# Where each joint sits along the arm centreline, which runs from the
# fingertip to where the arm meets the torso -- about 0.44 of standing height,
# being hand (0.108 H) plus forearm (0.146 H) plus upper arm (0.186 H). The
# fractions below are those segment lengths divided by that total.
#
# They used to be guesses, and they were out by a whole joint: what the rig
# called the shoulder sat on the elbow, the elbow sat mid-forearm, and the
# hand sat inside the fingers. Two consequences, both of which looked like
# separate bugs. The hand bone owned the far half of the forearm and swung it
# rigidly about a point in the middle of it, so wrists crumpled into a lump
# on every clip. And the whole arm measured 0.375 m instead of 0.55, so a
# punch authored as "reach 95% of arm length" stopped well short of straight
# -- the fighters looked like they were shadow-boxing at a wall six inches in
# front of them.
ARM_STOPS = {"hand": 0.245, "lower": 0.577, "upper": 0.97}

# The clavicle is not on the arm's centreline at all: it runs inboard from the
# shoulder joint towards the neck. Placed as a fraction of that gap.
SHOULDER_INSET = 0.55

# Legs and spine are placed by height instead, as fractions of standing
# height, following ordinary human proportions.
LEG_HEIGHTS = {"foot": 0.045, "lower": 0.28, "upper": 0.50}
SPINE_HEIGHTS = {"Hips": 0.53, "Spine": 0.62, "Chest": 0.72, "Neck": 0.82, "Head": 0.88}
HIP_HALF_WIDTH = 0.085   # hip socket offset from the midline, as a fraction of height

BONES = [
    ("Hips", None), ("Spine", "Hips"), ("Chest", "Spine"),
    ("Neck", "Chest"), ("Head", "Neck"),
    ("Shoulder_L", "Chest"), ("UpperArm_L", "Shoulder_L"),
    ("LowerArm_L", "UpperArm_L"), ("Hand_L", "LowerArm_L"),
    ("Shoulder_R", "Chest"), ("UpperArm_R", "Shoulder_R"),
    ("LowerArm_R", "UpperArm_R"), ("Hand_R", "LowerArm_R"),
    ("UpperLeg_L", "Hips"), ("LowerLeg_L", "UpperLeg_L"), ("Foot_L", "LowerLeg_L"),
    ("UpperLeg_R", "Hips"), ("LowerLeg_R", "UpperLeg_R"), ("Foot_R", "LowerLeg_R"),
]

# Which segmentation labels a bone is allowed to influence. Without this the
# nearest-bone search hands chest vertices to the upper-arm bone, because in
# an A-pose the armpit is physically closer to the arm than to the spine.
#
# Both forearms have to accept torso as well, and the reason is a flaw one
# level down: the min-cut that isolates a limb finds the cheapest cut, and on
# an arm that is the wrist, not the shoulder. So "arm" comes back as roughly
# a hand -- 676 vertices against a leg's 1415 -- and everything from the
# elbow up is labelled torso. The hand bone then took almost all of the arm
# label and the forearm bone was left with fifty-eight vertices out of
# twenty-three thousand, which is to say the elbow did not bend at all: the
# forearm was welded to the upper arm and the hand swung from the wrist.
# That is what put a flat blade of geometry where each fighter's arm should
# be. Distance still keeps the forearm bone local -- it sits half a metre
# from the chest, which has spine bones running through it.
BONE_PARTS = {
    "Hips": {TORSO}, "Spine": {TORSO}, "Chest": {TORSO},
    "Neck": {TORSO, HEAD}, "Head": {HEAD},
    # The clavicles may hold torso only. Once they were placed properly --
    # running inboard from the shoulder joint toward the neck rather than
    # sitting on the elbow -- their segment lies right across the deltoid, and
    # nearest-bone handed them the whole shoulder cap. Nothing in the move
    # library rotates a clavicle, so that cap then stayed behind while the arm
    # swung, and the mesh between them stretched into a sheet across the chest.
    "Shoulder_L": {TORSO}, "UpperArm_L": {ARM_L, TORSO},
    "LowerArm_L": {ARM_L, TORSO}, "Hand_L": {ARM_L},
    "Shoulder_R": {TORSO}, "UpperArm_R": {ARM_R, TORSO},
    "LowerArm_R": {ARM_R, TORSO}, "Hand_R": {ARM_R},
    "UpperLeg_L": {LEG_L, TORSO}, "LowerLeg_L": {LEG_L}, "Foot_L": {LEG_L},
    "UpperLeg_R": {LEG_R, TORSO}, "LowerLeg_R": {LEG_R}, "Foot_R": {LEG_R},
}


def load_obj(path):
    """Read positions, UVs and faces, keeping the UV index per corner."""
    verts, uvs, faces, face_uvs = [], [], [], []
    for line in path.read_text().splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("vt "):
            # OBJ puts the texture origin at the bottom-left, glTF at the
            # top-left, so V has to be flipped on the way in. Without this the
            # atlas lands upside down: not obviously mirrored, because a body
            # atlas is not symmetric, but smeared into patches of shorts
            # across the chest and skin where the shorts should be. It reads
            # as "the model has no texture" rather than as a flip, which is
            # what made it survive this long.
            u, v = (float(x) for x in line.split()[1:3])
            uvs.append([u, 1.0 - v])
        elif line.startswith("f "):
            corners = [c.split("/") for c in line.split()[1:4]]
            faces.append([int(c[0]) - 1 for c in corners])
            face_uvs.append([int(c[1]) - 1 if len(c) > 1 and c[1] else 0 for c in corners])
    return (np.array(verts, np.float32), np.array(uvs, np.float32),
            np.array(faces, np.int64), np.array(face_uvs, np.int64))


def weld(verts, uvs, faces, face_uvs):
    """Weld by position *and* UV so texture seams survive."""
    corner_pos = verts[faces].reshape(-1, 3)
    corner_uv = (uvs[face_uvs].reshape(-1, 2) if len(uvs)
                 else np.zeros((len(faces) * 3, 2), np.float32))
    keys = np.round(np.hstack([corner_pos, corner_uv]).astype(np.float64), 6)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    return corner_pos[first], corner_uv[first], inverse.reshape(-1, 3).astype(np.int64)


def collapse_positions(pos):
    """Map UV-split vertices onto shared positions, for graph work."""
    keys = np.round(pos.astype(np.float64), 6)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    return pos[first], inverse


def centreline(pos, adj, tip, step):
    """Ring centres walking outward from a tip; stops where the limb widens."""
    dist = geodesic(pos, adj, [tip])
    finite = dist[np.isfinite(dist)].max()
    pts, counts = [], []
    r = 0.0
    while r < finite:
        band = (dist >= r) & (dist < r + step)
        if band.sum() >= 6:
            pts.append(pos[band].mean(0))
            counts.append(int(band.sum()))
        r += step
    pts, counts = np.array(pts), np.array(counts)

    # The limb ends where the cross-section balloons into the torso. Compare
    # against the median girth of the run so far rather than the previous
    # ring, which is too noisy to threshold on.
    stop = len(pts)
    for i in range(4, len(counts)):
        if counts[i] > 2.2 * np.median(counts[:i]):
            stop = i
            break
    return pts[:stop]


def sample_along(points, fraction):
    """Point at `fraction` of the arc length of a polyline."""
    if len(points) < 2:
        return points[0]
    steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
    arc = np.concatenate([[0], np.cumsum(steps)])
    return np.array([np.interp(fraction * arc[-1], arc, points[:, k]) for k in range(3)],
                    dtype=np.float32)


def sample_at_height(points, target_y):
    """Point on a polyline nearest a given height, with its X/Z interpolated.

    Legs are vertical, so anatomical height locates a knee or a hip socket far
    more reliably than arc length does -- the foot contributes a big chunk of
    arc before the ankle and drags every fraction downward. The centreline is
    still what supplies the sideways and front-back offset.
    """
    ys = points[:, 1]
    if len(points) < 2:
        return points[0]
    order = np.argsort(ys)
    ys_sorted = ys[order]
    out = [np.interp(target_y, ys_sorted, points[order, k]) for k in range(3)]
    out[1] = target_y
    return np.array(out, dtype=np.float32)


def build_skeleton(pos, adj, labels, height):
    tips = find_extremities(pos, adj, height)
    joints = {}

    for part, prefix in ((ARM_L, "L"), (ARM_R, "R")):
        line = centreline(pos, adj, tips[part], 0.03 * height)
        joints[f"Hand_{prefix}"] = sample_along(line, ARM_STOPS["hand"])
        joints[f"LowerArm_{prefix}"] = sample_along(line, ARM_STOPS["lower"])
        joints[f"UpperArm_{prefix}"] = sample_along(line, ARM_STOPS["upper"])

    hips_xz = []
    for part, prefix in ((LEG_L, "L"), (LEG_R, "R")):
        line = centreline(pos, adj, tips[part], 0.03 * height)
        joints[f"Foot_{prefix}"] = sample_at_height(line, LEG_HEIGHTS["foot"] * height)
        joints[f"LowerLeg_{prefix}"] = sample_at_height(line, LEG_HEIGHTS["lower"] * height)
        upper = sample_at_height(line, LEG_HEIGHTS["upper"] * height)
        # At hip height the two thigh centrelines have already converged
        # toward the crotch, so they read far narrower than the real sockets.
        # Set the socket offset from proportion and take only the side.
        upper[0] = np.sign(upper[0] or (1 if prefix == "L" else -1)) * HIP_HALF_WIDTH * height
        joints[f"UpperLeg_{prefix}"] = upper
        hips_xz.append(upper)

    # Spine chain rides the body's midline at anatomical heights. Depth comes
    # from the average of the hip sockets so a leaning figure stays upright
    # relative to itself.
    depth = float(np.mean([p[2] for p in hips_xz]))
    for name, frac in SPINE_HEIGHTS.items():
        joints[name] = np.array([0.0, frac * height, depth], np.float32)

    # Clavicles last, once the neck exists to aim them at: each one runs from
    # its shoulder joint inboard toward the base of the neck.
    for prefix in ("L", "R"):
        shoulder_joint = joints[f"UpperArm_{prefix}"]
        joints[f"Shoulder_{prefix}"] = (
            shoulder_joint + (joints["Neck"] - shoulder_joint) * SHOULDER_INSET
        ).astype(np.float32)
    return joints


def smooth_weights(dense, faces, rounds, strength=0.55):
    """Blur the weight field along the mesh so part boundaries stop tearing.

    The segmentation mask is a hard wall: an arm vertex may only be driven by
    arm bones and its torso neighbour only by torso bones, so the surface
    splits open at the shoulder the moment the arm rotates. Averaging each
    vertex's weights with its neighbours a few times turns that wall into a
    gradient, which is what makes the seam hold together.
    """
    import scipy.sparse as sp

    n = len(dense)
    rows = np.concatenate([faces[:, 0], faces[:, 1], faces[:, 1],
                           faces[:, 2], faces[:, 0], faces[:, 2]])
    cols = np.concatenate([faces[:, 1], faces[:, 0], faces[:, 2],
                           faces[:, 1], faces[:, 2], faces[:, 0]])
    adjacency_matrix = sp.csr_matrix((np.ones(len(rows), np.float32), (rows, cols)),
                                     shape=(n, n))
    adjacency_matrix.data[:] = 1.0
    degree = np.asarray(adjacency_matrix.sum(1)).ravel()
    degree[degree == 0] = 1.0

    for _ in range(rounds):
        neighbour_mean = adjacency_matrix @ dense / degree[:, None]
        dense = (1.0 - strength) * dense + strength * neighbour_mean
    return dense


def bone_segments(joints):
    """The span each bone actually drives: from its own joint to its child.

    Getting this backwards is easy and quietly ruinous. A bone named for the
    knee, measured from hip to knee, covers the thigh -- so the shin ends up
    with no territory at all and the knee cannot bend. Leaf bones (hand, foot,
    head) have no child, so they get a short stub continuing the limb.
    """
    names = [n for n, _ in BONES]
    parents = dict(BONES)
    first_child = {}
    for child, parent in BONES:
        if parent is not None and parent not in first_child:
            first_child[parent] = child

    segments = []
    for name in names:
        if name in first_child:
            tail = joints[first_child[name]]
        else:
            tail = joints[name] + (joints[name] - joints[parents[name]]) * 0.6
        segments.append((joints[name], tail))
    return segments


def skin_weights(pos, labels, joints, faces, max_influences=4, diffusion=90):
    """Assign each vertex to its nearest bone, then diffuse across the surface.

    Weighting directly by inverse distance does not work on a torso: it is wide
    enough that every spine bone sits at nearly the same distance from a chest
    vertex, so the weights spread thinly over five or six bones and which four
    survive truncation differs between neighbours. Since one of those bones may
    be a swinging arm, the surface rips. Starting from a hard nearest-bone
    assignment and letting it diffuse over the mesh keeps each vertex bound to
    a small, locally consistent set of bones with smooth transitions between
    them.
    """
    names = [n for n, _ in BONES]
    segments = bone_segments(joints)

    dists = np.empty((len(pos), len(names)), np.float32)
    for i, (a, b) in enumerate(segments):
        ab = b - a
        denom = float(ab @ ab) or 1.0
        t = np.clip(((pos - a) @ ab) / denom, 0.0, 1.0)[:, None]
        dists[:, i] = np.linalg.norm(pos - (a + t * ab), axis=1)
        allowed = np.isin(labels, list(BONE_PARTS[names[i]]))
        dists[~allowed, i] = np.inf

    # Vertices whose part no bone claims (rare) fall back to plain distance.
    orphan = ~np.isfinite(dists).any(1)
    if orphan.any():
        for i, (a, b) in enumerate(segments):
            ab = b - a
            denom = float(ab @ ab) or 1.0
            t = np.clip(((pos[orphan] - a) @ ab) / denom, 0.0, 1.0)[:, None]
            dists[orphan, i] = np.linalg.norm(pos[orphan] - (a + t * ab), axis=1)

    dense = np.zeros((len(pos), len(names)), np.float32)
    dense[np.arange(len(pos)), np.argmin(np.where(np.isfinite(dists), dists, np.inf), axis=1)] = 1.0
    dense = smooth_weights(dense, faces, diffusion)

    order = np.argsort(-dense, axis=1)[:, :max_influences]
    picked = np.take_along_axis(dense, order, axis=1)
    total = picked.sum(1, keepdims=True)
    total[total == 0] = 1.0
    return order.astype(np.uint16), (picked / total).astype(np.float32)


def quat_axis_angle(axis, angle):
    axis = np.asarray(axis, np.float64)
    axis = axis / (np.linalg.norm(axis) or 1.0)
    s = np.sin(angle / 2)
    return [float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(np.cos(angle / 2))]


TEST_POSE = {
    # A fighter's guard: arms brought down out of the A-pose, elbows folded
    # in front, knees softened. Deliberately ordinary -- an extreme pose
    # flatters nothing and hides where the weights actually misbehave.
    "UpperArm_L": ("z", -1.15), "UpperArm_R": ("z", 1.15),
    "LowerArm_L": ("x", -1.05), "LowerArm_R": ("x", -1.05),
    "LowerLeg_L": ("x", 0.35), "LowerLeg_R": ("x", 0.35),
    "Spine": ("y", 0.15),
}


def export_glb(path, pos, uv, faces, joints, joint_idx, joint_w,
               texture=None, test_pose=False):
    names = [n for n, _ in BONES]
    parents = dict(BONES)
    index_of = {n: i for i, n in enumerate(names)}

    # glTF joint nodes carry translations relative to their parent.
    local = {}
    for name in names:
        parent = parents[name]
        local[name] = joints[name] - (joints[parent] if parent else np.zeros(3, np.float32))

    inverse_bind = np.zeros((len(names), 16), np.float32)
    for i, name in enumerate(names):
        m = np.eye(4, dtype=np.float32)
        m[:3, 3] = -joints[name]
        inverse_bind[i] = m.T.reshape(-1)   # glTF matrices are column-major

    normals = np.zeros_like(pos)
    tri = pos[faces]
    face_n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    for col in range(3):
        np.add.at(normals, faces[:, col], face_n)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals /= lengths

    chunks, views, accessors = [], [], []
    offset = 0

    def add(array, target=None, kind="VEC3", ctype=5126, minmax=False):
        nonlocal offset
        raw = array.tobytes()
        raw += b"\x00" * (-len(raw) % 4)
        chunks.append(raw)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(raw)}
        if target:
            view["target"] = target
        views.append(view)
        offset += len(raw)
        acc = {"bufferView": len(views) - 1, "componentType": ctype,
               "count": int(len(array)), "type": kind}
        if minmax:
            acc["min"] = array.min(0).tolist()
            acc["max"] = array.max(0).tolist()
        accessors.append(acc)
        return len(accessors) - 1

    a_idx = add(faces.astype(np.uint32).reshape(-1), 34963, "SCALAR", 5125)
    a_pos = add(pos.astype(np.float32), 34962, "VEC3", 5126, minmax=True)
    a_nrm = add(normals.astype(np.float32), 34962)
    a_uv = add(uv.astype(np.float32), 34962, "VEC2")
    a_j = add(joint_idx.astype(np.uint16), 34962, "VEC4", 5123)
    a_w = add(joint_w.astype(np.float32), 34962, "VEC4")
    a_ibm = add(inverse_bind, None, "MAT4")

    nodes = [{"name": "Armature", "children": [1]}]
    for i, name in enumerate(names):
        node = {"name": name, "translation": [float(x) for x in local[name]]}
        kids = [index_of[c] + 1 for c, p in BONES if p == name]
        if kids:
            node["children"] = kids
        if test_pose and name in TEST_POSE:
            axis, angle = TEST_POSE[name]
            node["rotation"] = quat_axis_angle({"x": (1, 0, 0), "y": (0, 1, 0),
                                                "z": (0, 0, 1)}[axis], angle)
        nodes.append(node)
    mesh_node = len(nodes)
    nodes.append({"name": "Fighter", "mesh": 0, "skin": 0})

    gltf = {
        "asset": {"version": "2.0", "generator": "autorig.py"},
        "scene": 0,
        "scenes": [{"nodes": [0, mesh_node]}],
        "nodes": nodes,
        "skins": [{"inverseBindMatrices": a_ibm, "skeleton": 1,
                   "joints": [index_of[n] + 1 for n in names]}],
        "meshes": [{"name": "Fighter", "primitives": [{
            "attributes": {"POSITION": a_pos, "NORMAL": a_nrm, "TEXCOORD_0": a_uv,
                           "JOINTS_0": a_j, "WEIGHTS_0": a_w},
            "indices": a_idx, "material": 0}]}],
        "materials": [{"name": "fighter", "pbrMetallicRoughness": {
            "metallicFactor": 0.0, "roughnessFactor": 0.75}}],
    }

    if texture and texture.exists():
        data = base64.b64encode(texture.read_bytes()).decode()
        gltf["images"] = [{"uri": f"data:image/jpeg;base64,{data}"}]
        gltf["samplers"] = [{"magFilter": 9729, "minFilter": 9987,
                             "wrapS": 10497, "wrapT": 10497}]
        gltf["textures"] = [{"sampler": 0, "source": 0}]
        gltf["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}

    blob = b"".join(chunks)
    gltf["buffers"] = [{"byteLength": len(blob)}]
    gltf["bufferViews"] = views
    gltf["accessors"] = accessors

    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942))
        fh.write(blob)


def rig(obj_path, out_path, test_pose=False):
    verts, uvs, faces_v, faces_uv = load_obj(obj_path)
    pos, uv, faces = weld(verts, uvs, faces_v, faces_uv)
    pos = pos - np.array([(pos[:, 0].min() + pos[:, 0].max()) / 2, pos[:, 1].min(),
                          (pos[:, 2].min() + pos[:, 2].max()) / 2], np.float32)

    # Graph work happens on position-welded vertices; UV splits would break
    # connectivity and strand whole texture islands.
    gpos, back = collapse_positions(pos)
    gfaces = back[faces]
    height = float(pos[:, 1].max())

    glabels, _ = segment(gpos, gfaces)
    joints = build_skeleton(gpos, adjacency(gfaces), glabels, height)
    # Weights are solved on the position-welded mesh: smoothing has to travel
    # across UV seams, and on the split mesh those seams are disconnected.
    gidx, gweights = skin_weights(gpos, glabels, joints, gfaces)
    joint_idx, joint_w = gidx[back], gweights[back]

    texture = obj_path.with_name(obj_path.stem + "_basecolor.jpg")
    export_glb(out_path, pos, uv, faces, joints, joint_idx, joint_w,
               texture=texture, test_pose=test_pose)
    return joints, height


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, action="append",
                    help="directory of .obj sources; repeatable, defaults to "
                         "assets/fighters and assets/staff")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "rigged")
    ap.add_argument("--only", action="append")
    ap.add_argument("--test-pose", action="store_true",
                    help="bend shoulders, elbows and knees in the export")
    args = ap.parse_args()

    roots = args.src or [REPO / "assets" / "fighters", REPO / "assets" / "staff"]
    if args.only:
        sources = []
        for stem in args.only:
            found = next((r / f"{stem}.obj" for r in roots
                          if (r / f"{stem}.obj").exists()), None)
            if found is None:
                sys.exit(f"no such model: {stem}.obj in "
                         + ", ".join(str(r) for r in roots))
            sources.append(found)
    else:
        sources = [p for root in roots for p in sorted(root.glob("*.obj"))]
    if not sources:
        sys.exit("no .obj sources in " + ", ".join(str(r) for r in roots))
    args.out.mkdir(parents=True, exist_ok=True)

    for src in sources:
        if not src.exists():
            sys.exit(f"no such model: {src}")
        dst = args.out / f"{src.stem}.glb"
        joints, height = rig(src, dst, args.test_pose)
        print(f"{src.stem:22} height={height:.2f}  bones={len(BONES)}  "
              f"{dst.stat().st_size / 1e6:5.2f} MB -> {dst}")


if __name__ == "__main__":
    main()
