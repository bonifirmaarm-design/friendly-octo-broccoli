#!/usr/bin/env python3
"""Small procedural mesh builder: primitives, material groups, GLB output.

The arena is built from code rather than modelled, so it needs boxes, tubes
and prisms that can be accumulated into material groups and written out as a
single glTF-Binary. Kept separate from the arena itself so the octagon and
the seating do not each reimplement a cylinder.
"""

import json
import struct
from collections import defaultdict

import numpy as np


def _normalise(v):
    n = np.linalg.norm(v)
    return v / n if n > 1e-12 else v


def basis(direction):
    """An orthonormal frame whose Z runs along `direction`."""
    z = _normalise(np.asarray(direction, float))
    helper = np.array([0.0, 1.0, 0.0]) if abs(z[1]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = _normalise(np.cross(helper, z))
    return np.stack([x, np.cross(z, x), z], axis=1)


class Mesh:
    """Triangles accumulated per material."""

    def __init__(self):
        self.groups = defaultdict(lambda: ([], []))

    def add(self, material, vertices, faces):
        verts, tris = self.groups[material]
        offset = len(verts)
        verts.extend(np.asarray(vertices, np.float32))
        tris.extend((np.asarray(faces, np.int64) + offset))

    # -- primitives ---------------------------------------------------------

    def box(self, material, centre, size, yaw=0.0):
        cx, cy, cz = np.asarray(centre, float)
        sx, sy, sz = np.asarray(size, float) / 2
        corners = np.array([[-sx, -sy, -sz], [sx, -sy, -sz], [sx, sy, -sz], [-sx, sy, -sz],
                            [-sx, -sy, sz], [sx, -sy, sz], [sx, sy, sz], [-sx, sy, sz]])
        if yaw:
            c, s = np.cos(yaw), np.sin(yaw)
            rot = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
            corners = corners @ rot.T
        corners += (cx, cy, cz)
        faces = [[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                 [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]
        self.add(material, corners, faces)

    def tube(self, material, start, end, radius, segments=8):
        start, end = np.asarray(start, float), np.asarray(end, float)
        axis = end - start
        if np.linalg.norm(axis) < 1e-9:
            return
        frame = basis(axis)
        angles = np.linspace(0, 2 * np.pi, segments, endpoint=False)
        ring = np.stack([np.cos(angles) * radius, np.sin(angles) * radius,
                         np.zeros(segments)], axis=1) @ frame.T
        verts = np.vstack([ring + start, ring + end])
        faces = []
        for i in range(segments):
            j = (i + 1) % segments
            faces += [[i, j, segments + j], [i, segments + j, segments + i]]
        self.add(material, verts, faces)

    def prism(self, material, outline, y_bottom, y_top):
        """Extrude a closed 2D outline (list of (x, z)) vertically."""
        outline = np.asarray(outline, float)
        n = len(outline)
        bottom = np.column_stack([outline[:, 0], np.full(n, y_bottom), outline[:, 1]])
        top = np.column_stack([outline[:, 0], np.full(n, y_top), outline[:, 1]])
        verts = np.vstack([bottom, top])
        faces = []
        for i in range(n):
            j = (i + 1) % n
            faces += [[i, j, n + j], [i, n + j, n + i]]
        for i in range(1, n - 1):          # caps, fanned from vertex 0
            faces.append([0, i, i + 1])
            faces.append([n, n + i + 1, n + i])
        self.add(material, verts, faces)

    def quad(self, material, a, b, c, d):
        self.add(material, [a, b, c, d], [[0, 1, 2], [0, 2, 3]])

    def band(self, material, outline_a, y_a, outline_b, y_b, closed=True):
        """A closed ribbon between two outlines, each at its own height.

        Stepped seating is built from these rather than from stacked solid
        prisms: a prism at each row's outer radius simply encloses every row
        inside it, and the bowl renders as a wall.
        """
        a = np.asarray(outline_a, float)
        b = np.asarray(outline_b, float)
        n = len(a)
        lower = np.column_stack([a[:, 0], np.full(n, y_a), a[:, 1]])
        upper = np.column_stack([b[:, 0], np.full(n, y_b), b[:, 1]])
        verts = np.vstack([lower, upper])
        faces = []
        for i in range(n if closed else n - 1):
            j = (i + 1) % n
            faces += [[i, j, n + j], [i, n + j, n + i]]
        self.add(material, verts, faces)

    # -- output -------------------------------------------------------------

    def counts(self):
        return {m: len(f) for m, (_, f) in self.groups.items()}

    def write_glb(self, path, materials, name="Scene"):
        chunks, views, accessors, primitives = [], [], [], []
        offset = 0

        def add_buffer(array, kind, ctype, target, minmax=False):
            nonlocal offset
            raw = np.ascontiguousarray(array).tobytes()
            raw += b"\x00" * (-len(raw) % 4)
            chunks.append(raw)
            views.append({"buffer": 0, "byteOffset": offset,
                          "byteLength": len(raw), "target": target})
            offset += len(raw)
            acc = {"bufferView": len(views) - 1, "componentType": ctype,
                   "count": int(len(array)), "type": kind}
            if minmax:
                acc["min"] = array.min(0).tolist()
                acc["max"] = array.max(0).tolist()
            accessors.append(acc)
            return len(accessors) - 1

        order = [m for m in materials if m in self.groups]
        for index, material in enumerate(order):
            verts, faces = self.groups[material]
            positions = np.asarray(verts, np.float32)
            indices = np.asarray(faces, np.uint32).reshape(-1)

            tri = positions[indices.reshape(-1, 3)]
            face_normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            normals = np.zeros_like(positions)
            for column in range(3):
                np.add.at(normals, indices.reshape(-1, 3)[:, column], face_normals)
            lengths = np.linalg.norm(normals, axis=1, keepdims=True)
            lengths[lengths == 0] = 1.0
            normals = (normals / lengths).astype(np.float32)

            primitives.append({
                "attributes": {
                    "POSITION": add_buffer(positions, "VEC3", 5126, 34962, minmax=True),
                    "NORMAL": add_buffer(normals, "VEC3", 5126, 34962),
                },
                "indices": add_buffer(indices, "SCALAR", 5125, 34963),
                "material": index,
            })

        blob = b"".join(chunks)
        gltf = {
            "asset": {"version": "2.0", "generator": "meshkit.py"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": primitives}],
            "materials": [materials[m] | {"name": m} for m in order],
            "buffers": [{"byteLength": len(blob)}],
            "bufferViews": views,
            "accessors": accessors,
        }
        js = json.dumps(gltf, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        with open(path, "wb") as fh:
            fh.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob)))
            fh.write(struct.pack("<II", len(js), 0x4E4F534A))
            fh.write(js)
            fh.write(struct.pack("<II", len(blob), 0x004E4942))
            fh.write(blob)
        return len(blob)


def pbr(colour, metallic=0.0, roughness=0.8, alpha=None, double_sided=True):
    material = {"pbrMetallicRoughness": {
        "baseColorFactor": list(colour) + [1.0 if alpha is None else alpha],
        "metallicFactor": metallic, "roughnessFactor": roughness},
        "doubleSided": double_sided}
    if alpha is not None and alpha < 1.0:
        material["alphaMode"] = "BLEND"
    return material
