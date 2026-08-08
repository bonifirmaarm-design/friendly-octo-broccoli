#!/usr/bin/env python3
"""Fill the arena: a crowd in the seats and everyone who works cageside.

The crowd is grouped into angular sectors rather than built as one mesh or as
thousands of separate figures. One mesh cannot move, and a node per spectator
would be thousands of animation channels for a thing seen from twenty metres
away; a sector can be lifted, so the crowd murmurs on its own and rises when
something happens, which is all the life it needs at that distance.

Cageside people are not generated -- they are the uploaded NPC models, placed
by a manifest of transforms the scene reads. They only ever stand, so they
need no rig.

    python3 tools/populate.py         # -> build/arena/crowd.glb + placements.json

Requires numpy.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_arena import CIRCUMRADIUS, PLATFORM_HEIGHT, TUNNEL_ANGLE, TUNNEL_WEDGE  # noqa: E402
from meshkit import Mesh, pbr  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

SECTORS = 16
SEAT_INNER = 11.0
SEAT_TREAD = 0.92
SEAT_RISER = 0.45

SHIRTS = [(0.72, 0.20, 0.18), (0.16, 0.20, 0.34), (0.86, 0.84, 0.80),
          (0.20, 0.22, 0.24), (0.42, 0.28, 0.20), (0.24, 0.40, 0.30),
          (0.60, 0.52, 0.30), (0.34, 0.20, 0.36)]
SKINS = [(0.80, 0.62, 0.48), (0.62, 0.44, 0.32), (0.42, 0.29, 0.21),
         (0.88, 0.72, 0.58), (0.52, 0.36, 0.26)]


def crowd_materials():
    materials = {}
    for i, colour in enumerate(SHIRTS):
        materials[f"shirt_{i}"] = pbr(colour, roughness=0.9)
    for i, colour in enumerate(SKINS):
        materials[f"skin_{i}"] = pbr(colour, roughness=0.85)
    return materials


def build_crowd(rows=24, fill=0.86, seed=7):
    """One Mesh per sector; each spectator is a torso block and a head."""
    rng = np.random.default_rng(seed)
    sectors = [Mesh() for _ in range(SECTORS)]

    for row in range(rows):
        radius = SEAT_INNER + row * SEAT_TREAD + SEAT_TREAD * 0.55
        y = (row + 1) * SEAT_RISER
        count = max(8, int(2 * np.pi * radius / 0.58))
        for k in range(count):
            angle = -np.pi + 2 * np.pi * k / count
            if abs(np.angle(np.exp(1j * (angle - TUNNEL_ANGLE)))) <= TUNNEL_WEDGE:
                continue
            if rng.random() > fill:
                continue

            x, z = np.cos(angle) * radius, np.sin(angle) * radius
            sector = int((angle + np.pi) / (2 * np.pi) * SECTORS) % SECTORS
            mesh = sectors[sector]

            lean = rng.uniform(-0.03, 0.03)
            scale = rng.uniform(0.92, 1.08)
            shirt = f"shirt_{rng.integers(len(SHIRTS))}"
            skin = f"skin_{rng.integers(len(SKINS))}"
            # Seated: the torso starts just above the seat pan.
            mesh.box(shirt, (x + lean, y + 0.52 * scale, z),
                     (0.40, 0.56 * scale, 0.30), yaw=-angle)
            mesh.box(skin, (x + lean, y + 0.90 * scale, z),
                     (0.20, 0.22 * scale, 0.20), yaw=-angle)
    return sectors


def write_crowd_glb(path, sectors, materials):
    """One node per sector, plus a murmur loop and a standing ovation."""
    chunks, views, accessors, meshes, nodes = [], [], [], [], []
    offset = 0

    def add(array, kind, ctype, target=None, minmax=False):
        nonlocal offset
        raw = np.ascontiguousarray(array).tobytes()
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
            acc["min"] = array.min(0).tolist() if array.ndim > 1 else [float(array.min())]
            acc["max"] = array.max(0).tolist() if array.ndim > 1 else [float(array.max())]
        accessors.append(acc)
        return len(accessors) - 1

    material_order = list(materials)
    index_of_material = {m: i for i, m in enumerate(material_order)}

    for s, mesh in enumerate(sectors):
        primitives = []
        for material, (verts, faces) in mesh.groups.items():
            positions = np.asarray(verts, np.float32)
            indices = np.asarray(faces, np.uint32).reshape(-1)
            tri = positions[indices.reshape(-1, 3)]
            face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            normals = np.zeros_like(positions)
            for column in range(3):
                np.add.at(normals, indices.reshape(-1, 3)[:, column], face_normals)
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            lengths[lengths == 0] = 1.0
            primitives.append({
                "attributes": {
                    "POSITION": add(positions, "VEC3", 5126, 34962, minmax=True),
                    "NORMAL": add((normals / lengths).astype(np.float32),
                                  "VEC3", 5126, 34962)},
                "indices": add(indices, "SCALAR", 5125, 34963),
                "material": index_of_material[material]})
        meshes.append({"name": f"crowd_sector_{s}", "primitives": primitives})
        nodes.append({"name": f"crowd_sector_{s}", "mesh": s,
                      "translation": [0.0, 0.0, 0.0]})

    root = len(nodes)
    nodes.append({"name": "Crowd", "children": list(range(SECTORS))})

    animations = []
    for name, height, period, stagger in (("crowd_murmur", 0.035, 2.6, 0.55),
                                          ("crowd_ovation", 0.62, 1.4, 0.10)):
        channels, samplers = [], []
        for s in range(SECTORS):
            phase = (s * stagger) % 1.0
            times = np.array([0.0, period * 0.5, period], np.float32)
            lift = np.array([
                [0.0, height * np.sin(phase * 2 * np.pi) * 0.5, 0.0],
                [0.0, height * (1.0 if name == "crowd_ovation" else
                                np.sin((phase + 0.5) * 2 * np.pi) * 0.5), 0.0],
                [0.0, height * np.sin(phase * 2 * np.pi) * 0.5, 0.0]], np.float32)
            samplers.append({"input": add(times, "SCALAR", 5126, minmax=True),
                             "output": add(lift, "VEC3", 5126),
                             "interpolation": "LINEAR"})
            channels.append({"sampler": len(samplers) - 1,
                             "target": {"node": s, "path": "translation"}})
        animations.append({"name": name, "channels": channels, "samplers": samplers,
                           "extras": {"loop": True, "duration": float(period)}})

    blob = b"".join(chunks)
    gltf = {"asset": {"version": "2.0", "generator": "populate.py"},
            "scene": 0, "scenes": [{"nodes": [root]}],
            "nodes": nodes, "meshes": meshes,
            "materials": [materials[m] | {"name": m} for m in material_order],
            "animations": animations,
            "buffers": [{"byteLength": len(blob)}],
            "bufferViews": views, "accessors": accessors}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
        fh.write(struct.pack("<II", len(js), 0x4E4F534A))
        fh.write(js)
        fh.write(struct.pack("<II", len(blob), 0x004E4942))
        fh.write(blob)
    return len(blob)


def cageside():
    """Where everyone stands. Angles are measured the same way as the arena."""
    deck = PLATFORM_HEIGHT
    ring = CIRCUMRADIUS + 1.35     # just off the apron, on the arena floor

    def at(angle, radius, y=0.0, face_in=True):
        x, z = np.cos(angle) * radius, np.sin(angle) * radius
        yaw = float(np.arctan2(-x, -z)) if face_in else float(np.arctan2(x, z))
        return {"position": [round(float(x), 3), y, round(float(z), 3)],
                "yaw": round(yaw, 4)}

    people = []

    # Camera operators work the cage from four sides, on the floor.
    for i, angle in enumerate((0.35, 2.05, 3.6, 5.2)):
        model = "npc_cameraman_handheld" if i % 2 else "npc_cameraman_tripod"
        people.append({"role": "cameraman", "model": model,
                       "flash": True, **at(angle, ring + 0.5)})

    # The referee works inside the cage. He is rigged, so the game loads him
    # from build/animated by role rather than from this model name.
    people.append({"role": "referee", "model": "official_referee",
                   **at(np.pi * 0.75, CIRCUMRADIUS * 0.55, y=deck + 0.04)})

    # A corner each, at the fence, below the deck: this is where the coach
    # stands and shouts through the round.
    people.append({"role": "coach", "corner": "blue", "model": "official_coach",
                   **at(np.pi * 0.25, ring)})
    people.append({"role": "coach", "corner": "red", "model": "official_coach",
                   **at(np.pi * 1.25, ring)})

    # Commentary and press, further out, facing the cage.
    people.append({"role": "commentator", "model": "npc_commentator_mic",
                   **at(np.pi * 1.62, ring + 1.9)})
    for i, angle in enumerate(np.linspace(np.pi * 1.72, np.pi * 1.98, 3)):
        people.append({"role": "press", "model": ["npc_suit_haired_b", "npc_suit_c",
                                                  "npc_suit_bald_a"][i],
                       **at(angle, ring + 2.6)})

    # Corner props, on the deck where the fighter sits between rounds.
    props = [
        {"role": "stool", "model": None, "corner": "blue",
         **at(np.pi * 0.25, CIRCUMRADIUS * 0.82, y=deck + 0.04)},
        {"role": "towel", "model": "prop_folded_towel", "corner": "blue",
         **at(np.pi * 0.27, CIRCUMRADIUS * 0.86, y=deck + 0.10)},
        {"role": "water", "model": "prop_water_bottle", "corner": "blue",
         **at(np.pi * 0.23, CIRCUMRADIUS * 0.86, y=deck + 0.04)},
        {"role": "towel", "model": "prop_folded_towel", "corner": "red",
         **at(np.pi * 1.27, CIRCUMRADIUS * 0.86, y=deck + 0.10)},
        {"role": "water", "model": "prop_water_bottle", "corner": "red",
         **at(np.pi * 1.23, CIRCUMRADIUS * 0.86, y=deck + 0.04)},
        {"role": "belt", "model": "prop_championship_belt",
         **at(np.pi * 0.75, CIRCUMRADIUS * 0.30, y=deck + 0.04)},
    ]
    return people, props


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "arena")
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--fill", type=float, default=0.86,
                    help="fraction of seats occupied")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    sectors = build_crowd(rows=args.rows, fill=args.fill)
    materials = crowd_materials()
    size = write_crowd_glb(args.out / "crowd.glb", sectors, materials)
    total = sum(sum(m.counts().values()) for m in sectors)
    people = sum(len(m.groups.get(k, ([], []))[1]) for m in sectors for k in m.groups)

    people_list, props = cageside()
    (args.out / "placements.json").write_text(
        json.dumps({"cageside": people_list, "props": props,
                    "scale_hint": "fighters and NPCs are ~2 units tall; "
                                  "multiply by 0.93 for metres"}, indent=2))

    print(f"толпа: {total} треугольников в {SECTORS} секторах, "
          f"{size / 1e6:.2f} MB -> {args.out / 'crowd.glb'}")
    print(f"клипы: crowd_murmur (гул), crowd_ovation (встают)")
    print(f"у клетки: {len(people_list)} человек, {len(props)} предметов "
          f"-> {args.out / 'placements.json'}")


if __name__ == "__main__":
    main()
