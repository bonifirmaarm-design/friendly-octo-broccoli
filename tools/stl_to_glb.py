#!/usr/bin/env python3
"""Convert the binary STL source meshes into indexed glTF-Binary (.glb).

STL stores every triangle as three unshared vertices with a single face
normal, which no engine wants to import directly. This welds vertices by
position, averages the face normals into smooth vertex normals, and writes
a single-mesh GLB.

    python3 tools/stl_to_glb.py                  # assets/models -> build/glb
    python3 tools/stl_to_glb.py --scale 0.925    # ~1.85 m tall humans (see CATALOG.md)

Requires numpy. There are still no UVs, no materials and no skeleton in the
output -- see docs/ANIMATION.md for what has to happen before these can be
animated.
"""

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent


def load_stl(path):
    """Return an (n, 3, 3) array of triangle corner positions."""
    with open(path, "rb") as fh:
        fh.read(80)
        count = struct.unpack("<I", fh.read(4))[0]
        payload = fh.read(count * 50)
    if len(payload) != count * 50:
        raise ValueError(f"{path.name}: truncated, expected {count} triangles")
    records = np.frombuffer(payload, dtype=np.uint8).reshape(count, 50)
    # bytes 0:12 are the face normal, 12:48 the three corners, 48:50 attributes
    return records[:, 12:48].copy().view("<f4").reshape(count, 3, 3)


def weld(tri, up_axis_swap=True, scale=1.0):
    """Weld duplicate corners and build smooth normals.

    STL from photogrammetry-style generators is Z-up; glTF is Y-up, so the
    axes are swapped unless the caller opts out.
    """
    corners = tri.reshape(-1, 3).astype(np.float32)
    # Quantise before welding so float noise does not split seams.
    keys = np.round(corners.astype(np.float64), 6)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    positions = corners[first]
    indices = inverse.reshape(-1, 3).astype(np.uint32)

    # Area-weighted face normals accumulated onto the shared vertices.
    p0, p1, p2 = positions[indices[:, 0]], positions[indices[:, 1]], positions[indices[:, 2]]
    face = np.cross(p1 - p0, p2 - p0)
    normals = np.zeros_like(positions)
    for col in range(3):
        np.add.at(normals, indices[:, col], face)
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    lengths[lengths == 0] = 1.0
    normals /= lengths

    if up_axis_swap:
        positions = positions[:, [0, 2, 1]] * np.array([1, 1, -1], dtype=np.float32)
        normals = normals[:, [0, 2, 1]] * np.array([1, 1, -1], dtype=np.float32)

    # Drop the model onto y=0 and centre it on the ground plane, so every
    # asset shares one origin convention: feet at the origin, +Y up.
    positions = positions * np.float32(scale)
    lo, hi = positions.min(0), positions.max(0)
    positions -= np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2], dtype=np.float32)

    return positions.astype(np.float32), normals.astype(np.float32), indices


# These meshes come from STL, which carries no UVs and no materials, so every
# one of them used to export with the same flat 0.8 grey. That is fine for a
# mesh you are about to rig and texture, and ruinous for the two dozen that go
# straight into the scene: the whole cageside -- camera crews, press row, the
# belt, the towel, the water -- rendered as identical white plastic dummies.
#
# A base colour per role is not a texture, but it is the difference between a
# lit arena and a shelf of mannequins. Longest prefix wins.
TINTS = {
    "npc_cameraman": ((0.09, 0.10, 0.12), 0.85, 0.0),
    "npc_commentator": ((0.13, 0.14, 0.19), 0.80, 0.0),
    "npc_interviewer": ((0.16, 0.18, 0.24), 0.80, 0.0),
    "npc_official": ((0.10, 0.11, 0.14), 0.80, 0.0),
    "npc_suit_bald": ((0.11, 0.12, 0.16), 0.75, 0.0),
    "npc_suit_haired": ((0.15, 0.14, 0.17), 0.75, 0.0),
    "npc_suit": ((0.12, 0.13, 0.17), 0.75, 0.0),
    "prop_championship_belt": ((0.62, 0.48, 0.16), 0.28, 0.85),
    "prop_folded_towel": ((0.86, 0.87, 0.90), 0.95, 0.0),
    "prop_water_bottle": ((0.42, 0.66, 0.86), 0.20, 0.0),
    "prop_round_tub": ((0.14, 0.15, 0.18), 0.70, 0.0),
    "apparel": ((0.18, 0.20, 0.26), 0.85, 0.0),
    "fighter": ((0.72, 0.56, 0.46), 0.80, 0.0),
    "mannequin": ((0.66, 0.66, 0.70), 0.85, 0.0),
}


def tint_for(name):
    key = max((k for k in TINTS if name.startswith(k)), key=len, default=None)
    colour, roughness, metallic = TINTS.get(key, ((0.8, 0.8, 0.8), 0.8, 0.0))
    return list(colour) + [1.0], roughness, metallic


def write_glb(path, positions, normals, indices, name):
    def pad(buf, fill=b"\x00"):
        return buf + fill * (-len(buf) % 4)

    idx_bytes = pad(indices.tobytes())
    pos_bytes = pad(positions.tobytes())
    nrm_bytes = pad(normals.tobytes())
    blob = idx_bytes + pos_bytes + nrm_bytes

    base_colour, roughness, metallic = tint_for(name)
    gltf = {
        "asset": {"version": "2.0", "generator": "stl_to_glb.py"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": name}],
        "meshes": [{
            "name": name,
            "primitives": [{
                "attributes": {"POSITION": 1, "NORMAL": 2},
                "indices": 0,
                "material": 0,
            }],
        }],
        "materials": [{
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": base_colour,
                "metallicFactor": metallic,
                "roughnessFactor": roughness,
            },
        }],
        "buffers": [{"byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(idx_bytes), "target": 34963},
            {"buffer": 0, "byteOffset": len(idx_bytes), "byteLength": len(pos_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(idx_bytes) + len(pos_bytes), "byteLength": len(nrm_bytes), "target": 34962},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5125, "count": int(indices.size), "type": "SCALAR"},
            {"bufferView": 1, "componentType": 5126, "count": int(len(positions)), "type": "VEC3",
             "min": positions.min(0).tolist(), "max": positions.max(0).tolist()},
            {"bufferView": 2, "componentType": 5126, "count": int(len(normals)), "type": "VEC3"},
        ],
    }

    json_bytes = pad(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    total = 12 + 8 + len(json_bytes) + 8 + len(blob)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<III", 0x46546C67, 2, total))
        fh.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        fh.write(json_bytes)
        fh.write(struct.pack("<II", len(blob), 0x004E4942))
        fh.write(blob)


def write_obj(path, positions, normals, indices, name):
    """Wavefront OBJ -- what Mixamo's auto-rigger accepts (it will not take STL)."""
    with open(path, "w") as fh:
        fh.write(f"# {name}\no {name}\n")
        for p in positions:
            fh.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
        for n in normals:
            fh.write(f"vn {n[0]:.6f} {n[1]:.6f} {n[2]:.6f}\n")
        for a, b, c in indices + 1:  # OBJ indices are 1-based
            fh.write(f"f {a}//{a} {b}//{b} {c}//{c}\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=REPO / "assets" / "models")
    ap.add_argument("--out", type=Path, default=None,
                    help="output directory (default build/glb or build/obj by --format)")
    ap.add_argument("--format", choices=("glb", "obj"), default="glb",
                    help="glb for the engine, obj to upload to Mixamo")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="uniform scale applied before export; sources are normalised to a 2-unit "
                         "box, so 0.925 makes a full-height figure roughly 1.85 m")
    ap.add_argument("--keep-z-up", action="store_true", help="skip the Z-up to Y-up axis swap")
    ap.add_argument("--scales", type=Path, nargs="?", const=REPO / "assets" / "scales.json",
                    help="JSON of per-asset scale multipliers; overrides --scale per asset "
                         "(defaults to assets/scales.json when given no value)")
    args = ap.parse_args()

    scales = {}
    if args.scales:
        scales = {k: v for k, v in json.loads(args.scales.read_text()).items()
                  if not k.startswith("_")}

    sources = sorted(args.src.glob("*.stl"))
    if not sources:
        sys.exit(f"no .stl files under {args.src}")
    out = args.out or REPO / "build" / args.format
    out.mkdir(parents=True, exist_ok=True)

    for src in sources:
        tri = load_stl(src)
        scale = scales.get(src.stem, args.scale)
        positions, normals, indices = weld(tri, not args.keep_z_up, scale)
        dst = out / f"{src.stem}.{args.format}"
        if args.format == "glb":
            write_glb(dst, positions, normals, indices, src.stem)
        else:
            write_obj(dst, positions, normals, indices, src.stem)
        size = positions.max(0) - positions.min(0)
        print(f"{src.stem:32} {len(tri):6d} tris  {len(tri) * 3:7d} -> {len(positions):6d} verts  "
              f"x{scale:<6.3f} {size[0]:4.2f}x{size[1]:4.2f}x{size[2]:4.2f} m  "
              f"{dst.stat().st_size / 1e6:5.2f} MB")


if __name__ == "__main__":
    main()
