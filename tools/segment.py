#!/usr/bin/env python3
"""Split a humanoid mesh into head / arms / legs / torso automatically.

The fighters were generated with their gloves resting against the chest, so
the arm and torso surfaces are welded together. Plain distance-based
splitting bleeds straight across that contact patch. This instead:

  1. welds the STL soup into a connected vertex graph,
  2. finds the five extremities (head crown, two hands, two feet) by
     farthest-point sampling using geodesic -- along-the-surface -- distance,
  3. isolates each limb with a graph min-cut against a seed in the pelvis.

The min-cut is what handles the welded gloves: to separate a hand from the
pelvis it must sever *every* path, so it cuts the shoulder and the
glove-to-chest bridge at the same time, and it does so at the cheapest
girth it can find.

    python3 tools/segment.py                        # all humanoids
    python3 tools/segment.py --only fighter_gloves_b

Writes build/segmentation/<name>.npz (positions, faces, per-vertex labels)
plus a colour-coded preview PNG. Requires numpy, scipy and pillow.
"""

import argparse
import heapq
import struct
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import maximum_flow

REPO = Path(__file__).resolve().parent.parent

TORSO, ARM_R, ARM_L, LEG_L, LEG_R, HEAD = range(6)
PART_NAMES = {TORSO: "torso", ARM_R: "arm_R", ARM_L: "arm_L",
              LEG_L: "leg_L", LEG_R: "leg_R", HEAD: "head"}
PART_COLOURS = {TORSO: (150, 150, 160), ARM_R: (220, 70, 70), ARM_L: (70, 130, 230),
                LEG_L: (80, 200, 110), LEG_R: (240, 180, 50), HEAD: (190, 90, 210)}

# Seed radius per limb, as a fraction of body height. Arms need a small seed
# (a big one would already spill onto the chest through the welded gloves);
# legs and head tolerate more, which keeps the cut off the ankle and jaw.
SEED_FRACTION = {ARM_R: 0.09, ARM_L: 0.09, LEG_L: 0.23, LEG_R: 0.23, HEAD: 0.15}


def load_welded(path):
    """Read a binary STL and weld its unshared corners into a vertex graph."""
    with open(path, "rb") as fh:
        fh.read(80)
        count = struct.unpack("<I", fh.read(4))[0]
        payload = fh.read(count * 50)
    records = np.frombuffer(payload, dtype=np.uint8).reshape(count, 50)
    corners = records[:, 12:48].copy().view("<f4").reshape(-1, 3).astype(np.float32)
    keys = np.round(corners.astype(np.float64), 6)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    pos = corners[first]
    faces = inverse.reshape(-1, 3)
    # Z-up to Y-up, then stand the model on the origin.
    pos = pos[:, [0, 2, 1]] * np.array([1, 1, -1], dtype=np.float32)
    pos -= np.array([(pos[:, 0].min() + pos[:, 0].max()) / 2, pos[:, 1].min(),
                     (pos[:, 2].min() + pos[:, 2].max()) / 2], dtype=np.float32)
    return pos, faces


def adjacency(faces):
    adj = defaultdict(set)
    for a, b, c in faces:
        adj[a].update((b, c))
        adj[b].update((a, c))
        adj[c].update((a, b))
    return adj


def edge_list(faces):
    edges = set()
    for a, b, c in faces:
        for u, v in ((a, b), (b, c), (a, c)):
            edges.add((min(u, v), max(u, v)))
    return np.array(sorted(edges))


def geodesic(pos, adj, seeds):
    """Dijkstra over the edge graph -- distance along the surface, not through it."""
    dist = np.full(len(pos), np.inf)
    heap = []
    for s in seeds:
        dist[s] = 0.0
        heapq.heappush(heap, (0.0, int(s)))
    while heap:
        du, u = heapq.heappop(heap)
        if du > dist[u] + 1e-12:
            continue
        pu = pos[u]
        for v in adj.get(u, ()):
            nd = du + float(np.linalg.norm(pos[v] - pu))
            if nd < dist[v] - 1e-9:
                dist[v] = nd
                heapq.heappush(heap, (nd, int(v)))
    return dist


def find_extremities(pos, adj, height, samples=9):
    """Farthest-point sampling from the pelvis: crown, two hands, two feet.

    Hand height is not a usable signal -- these figures carry their arms
    anywhere from hanging at the hip (31% of body height) to a raised guard
    (68%). What is stable is lateral reach, so the hands are picked as the
    most sideways-extreme pair left once the crown and feet are taken.
    """
    seed = int(np.argmin(np.abs(pos[:, 1] - 0.55 * height)
                         + 2 * np.abs(pos[:, 0]) + 2 * np.abs(pos[:, 2])))
    dist = geodesic(pos, adj, [seed])
    tips = []
    for _ in range(samples):
        t = int(np.argmax(dist))
        tips.append(t)
        dist = np.minimum(dist, geodesic(pos, adj, [t]))

    crown = max(tips, key=lambda t: pos[t, 1])
    grounded = sorted([t for t in tips if pos[t, 1] < 0.10 * height],
                      key=lambda t: pos[t, 1])[:2]
    if len(grounded) != 2:
        raise RuntimeError(f"found {len(grounded)} feet, expected 2")
    feet = sorted(grounded, key=lambda t: pos[t, 0])

    rest = [t for t in tips if t != crown and t not in feet]
    right = [t for t in rest if pos[t, 0] < 0]
    left = [t for t in rest if pos[t, 0] > 0]
    if not right or not left:
        raise RuntimeError("could not find a hand on each side")
    hands = (max(right, key=lambda t: -pos[t, 0]), max(left, key=lambda t: pos[t, 0]))

    # +X is the model's left in this orientation.
    return {HEAD: crown, ARM_R: hands[0], ARM_L: hands[1],
            LEG_L: feet[0], LEG_R: feet[1]}


def min_cut(pos, edges, lengths, n, source, sink):
    """Cheapest set of edges separating source from sink; returns the source side."""
    cap = np.maximum((lengths * 4000).astype(np.int32), 1)
    S, T = n, n + 1
    big = np.int32(10 ** 7)
    rows = np.concatenate([edges[:, 0], edges[:, 1], [S] * len(source), source, sink])
    cols = np.concatenate([edges[:, 1], edges[:, 0], source, [S] * len(source), [T] * len(sink)])
    data = np.concatenate([cap, cap, [big] * len(source), [big] * len(source), [big] * len(sink)])
    graph = sp.csr_matrix((data, (rows, cols)), shape=(n + 2, n + 2), dtype=np.int32)

    residual = (graph - maximum_flow(graph, S, T).flow).tocsr()
    reached = np.zeros(n + 2, bool)
    stack = [S]
    reached[S] = True
    while stack:
        u = stack.pop()
        lo, hi = residual.indptr[u], residual.indptr[u + 1]
        for v, w in zip(residual.indices[lo:hi], residual.data[lo:hi]):
            if w > 0 and not reached[v]:
                reached[v] = True
                stack.append(int(v))
    return reached[:n]


def segment(pos, faces):
    adj = adjacency(faces)
    edges = edge_list(faces)
    lengths = np.linalg.norm(pos[edges[:, 0]] - pos[edges[:, 1]], axis=1)
    height = pos[:, 1].max()
    tips = find_extremities(pos, adj, height)

    pelvis = np.where((pos[:, 1] > 0.40 * height) & (pos[:, 1] < 0.48 * height)
                      & (np.abs(pos[:, 0]) < 0.05 * height))[0]
    if len(pelvis) == 0:
        raise RuntimeError("no pelvis seed found")

    labels = np.zeros(len(pos), np.int32)
    for part in (ARM_R, ARM_L, LEG_L, LEG_R, HEAD):
        dist = geodesic(pos, adj, [tips[part]])
        source = np.where(dist < SEED_FRACTION[part] * height)[0]
        side = min_cut(pos, edges, lengths, len(pos), source, pelvis)
        labels[side & (labels == TORSO)] = part
    return labels, tips


def preview(pos, faces, labels, out_path):
    from PIL import Image, ImageDraw

    face_label = np.array([np.bincount(labels[f], minlength=6).argmax() for f in faces])
    size = 380
    views = [(0, 0), (0.8, 0.1), (1.57, 0), (2.6, 0.1)]
    sheet = Image.new("RGB", (len(views) * size, size + 26), (255, 255, 255))

    centre = (pos.min(0) + pos.max(0)) / 2
    span = (pos.max(0) - pos.min(0)).max()
    for col, (yaw, pitch) in enumerate(views):
        cy, sy, cp, spitch = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)
        rot = (np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
               @ np.array([[1, 0, 0], [0, cp, -spitch], [0, spitch, cp]]))
        tri = (((pos - centre) / span) @ rot.T)[faces]
        px = ((tri[:, :, 0] * 0.92 + 0.5) * size).astype(np.int32)
        py = ((0.5 - tri[:, :, 1] * 0.92) * size).astype(np.int32)
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        norm = np.linalg.norm(normals, axis=1, keepdims=True)
        norm[norm == 0] = 1
        light = np.array([0.4, 0.6, 0.7])
        shade = np.clip((normals / norm) @ (light / np.linalg.norm(light)), 0, 1) * 0.65 + 0.35

        img = Image.new("RGB", (size, size), (250, 250, 252))
        draw = ImageDraw.Draw(img)
        for i in np.argsort(tri[:, :, 2].mean(1)):
            base = PART_COLOURS[face_label[i]]
            g = shade[i]
            draw.polygon([(px[i, 0], py[i, 0]), (px[i, 1], py[i, 1]), (px[i, 2], py[i, 2])],
                         fill=(int(base[0] * g), int(base[1] * g), int(base[2] * g)))
        sheet.paste(img, (col * size, 0))

    counts = "  ".join(f"{PART_NAMES[k]}={int((labels == k).sum())}" for k in range(6))
    ImageDraw.Draw(sheet).text((6, size + 8), counts, fill=(0, 0, 0))
    sheet.save(out_path)
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=REPO / "assets" / "models")
    ap.add_argument("--out", type=Path, default=REPO / "build" / "segmentation")
    ap.add_argument("--only", action="append", help="stem to process (repeatable)")
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args()

    stems = args.only or [p.stem for p in sorted(args.src.glob("*.stl"))
                          if p.stem.startswith(("fighter_", "mannequin_", "npc_"))]
    args.out.mkdir(parents=True, exist_ok=True)

    failures = 0
    for stem in stems:
        src = args.src / f"{stem}.stl"
        if not src.exists():
            sys.exit(f"no such model: {src}")
        pos, faces = load_welded(src)
        try:
            labels, tips = segment(pos, faces)
        except RuntimeError as exc:
            print(f"{stem:28} SKIPPED -- {exc}")
            failures += 1
            continue
        np.savez_compressed(args.out / f"{stem}.npz", positions=pos, faces=faces,
                            labels=labels, tips=np.array([tips[k] for k in range(1, 6)]))
        counts = ("  ".join(f"{PART_NAMES[k]}={int((labels == k).sum())}" for k in range(6))
                  if args.no_preview else preview(pos, faces, labels, args.out / f"{stem}.png"))
        print(f"{stem:28} {counts}")

    if failures:
        print(f"\n{failures} model(s) skipped")


if __name__ == "__main__":
    main()
