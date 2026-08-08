#!/usr/bin/env python3
"""Generate the arena: octagon, cage, seating bowl and walkout tunnel.

Built from code rather than modelled, so the dimensions are the real ones and
stay editable. A regulation octagon is 9.14 m flat-to-flat with a 1.83 m
fence, raised 1.22 m off the floor; the seating bowl and tunnel are sized
around that.

The fence is real geometry -- diagonal wires woven into diamonds -- not a
texture with holes punched in it. A cage is seen from a few metres away
through a camera that moves, and a flat alpha plane gives itself away the
moment the angle changes.

    python3 tools/build_arena.py                 # -> build/arena/arena.glb
    python3 tools/build_arena.py --no-seats      # bare bowl, much lighter

Requires numpy.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from meshkit import Mesh, pbr  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# Regulation octagon, in metres.
APOTHEM = 4.57           # centre to the middle of a flat side
FENCE_HEIGHT = 1.83
PLATFORM_HEIGHT = 1.22
POST_RADIUS = 0.10
PAD_RADIUS = 0.16
WIRE_RADIUS = 0.009
WIRE_SPACING = 0.14      # diamond pitch of the chain-link

CIRCUMRADIUS = APOTHEM / np.cos(np.pi / 8)

MATERIALS = {
    "canvas": pbr((0.72, 0.73, 0.76), roughness=0.95),
    "canvas_logo": pbr((0.16, 0.20, 0.30), roughness=0.9),
    "apron": pbr((0.10, 0.10, 0.12), roughness=0.9),
    "padding": pbr((0.05, 0.05, 0.06), roughness=0.75),
    "wire": pbr((0.55, 0.57, 0.60), metallic=0.9, roughness=0.35),
    "floor": pbr((0.13, 0.14, 0.16), roughness=0.95),
    "structure": pbr((0.18, 0.19, 0.22), roughness=0.9),
    "seat_a": pbr((0.42, 0.09, 0.11), roughness=0.85),
    "seat_b": pbr((0.20, 0.21, 0.26), roughness=0.85),
    "tunnel": pbr((0.08, 0.08, 0.10), roughness=0.9),
}


def octagon(radius, rotation=np.pi / 8):
    angles = rotation + np.arange(8) * np.pi / 4
    return np.column_stack([np.cos(angles) * radius, np.sin(angles) * radius])


def build_platform(mesh):
    """The raised deck, its apron skirt and the canvas on top."""
    mesh.prism("apron", octagon(CIRCUMRADIUS + 0.55), 0.0, PLATFORM_HEIGHT)
    mesh.prism("canvas", octagon(CIRCUMRADIUS + 0.50),
               PLATFORM_HEIGHT, PLATFORM_HEIGHT + 0.04)
    # A darker inner ring, the way a canvas carries centre markings.
    mesh.prism("canvas_logo", octagon(CIRCUMRADIUS * 0.42),
               PLATFORM_HEIGHT + 0.04, PLATFORM_HEIGHT + 0.045)


def build_cage(mesh, gate_panel=5):
    """Eight padded posts, chain-link between them, padded top and bottom rails."""
    corners = octagon(CIRCUMRADIUS)
    base = PLATFORM_HEIGHT + 0.04
    top = base + FENCE_HEIGHT

    for x, z in corners:
        mesh.tube("padding", (x, base, z), (x, top + 0.10, z), PAD_RADIUS, segments=12)
        mesh.tube("structure", (x, base, z), (x, top + 0.10, z), POST_RADIUS, segments=10)

    for i in range(8):
        a, b = corners[i], corners[(i + 1) % 8]
        start = np.array([a[0], 0.0, a[1]])
        end = np.array([b[0], 0.0, b[1]])
        along = end - start
        width = float(np.linalg.norm(along))
        along = along / width
        inset = along * PAD_RADIUS
        panel_start, panel_width = start + inset, width - 2 * PAD_RADIUS

        # Rails top and bottom, padded.
        for height in (base + 0.03, top):
            mesh.tube("padding", panel_start + (0, height, 0),
                      panel_start + along * panel_width + (0, height, 0),
                      0.06, segments=8)

        if i == gate_panel:
            build_gate(mesh, panel_start, along, panel_width, base, top)
            continue
        weave(mesh, panel_start, along, panel_width, base + 0.05, top - 0.03)


def weave(mesh, origin, along, width, y_bottom, y_top):
    """Diagonal wires in both directions, clipped to the panel: chain-link."""
    height = y_top - y_bottom
    up = np.array([0.0, 1.0, 0.0])

    for sign in (1, -1):
        # Parametrise each wire by where its line crosses the bottom edge; a
        # 45-degree diagonal sweeps from -height to width+height to cover the
        # whole panel including the wires that enter through the sides.
        offsets = np.arange(-height, width + height, WIRE_SPACING)
        for offset in offsets:
            # Wire runs from (offset, 0) in direction (sign, 1), clipped to the box.
            points = []
            for t in (0.0, height):
                u = offset + sign * t
                points.append((u, t))
            (u0, t0), (u1, t1) = points
            # Clip against u in [0, width].
            if u0 < 0 or u0 > width or u1 < 0 or u1 > width:
                lo, hi = 0.0, height
                for edge in (0.0, width):
                    if abs(sign) > 0:
                        t_edge = (edge - offset) / sign
                        if 0.0 <= t_edge <= height:
                            if (offset + sign * lo < 0) or (offset + sign * lo > width):
                                lo = max(lo, t_edge)
                            else:
                                hi = min(hi, t_edge)
                if hi - lo < 0.05:
                    continue
                t0, t1 = lo, hi
                u0, u1 = offset + sign * t0, offset + sign * t1
            if not (0.0 - 1e-6 <= u0 <= width + 1e-6 and 0.0 - 1e-6 <= u1 <= width + 1e-6):
                continue
            p0 = origin + along * u0 + up * (y_bottom + t0)
            p1 = origin + along * u1 + up * (y_bottom + t1)
            mesh.tube("wire", p0, p1, WIRE_RADIUS, segments=5)


def build_gate(mesh, origin, along, width, base, top):
    """The door panel: a framed opening with the fence only above it."""
    up = np.array([0.0, 1.0, 0.0])
    door_width = 0.95
    left = (width - door_width) / 2
    door_top = base + 1.35

    for u in (left, left + door_width):
        mesh.tube("structure", origin + along * u + up * base,
                  origin + along * u + up * door_top, 0.05, segments=8)
    mesh.tube("structure", origin + along * left + up * door_top,
              origin + along * (left + door_width) + up * door_top, 0.05, segments=8)

    weave(mesh, origin, along, left, base + 0.05, top - 0.03)
    weave(mesh, origin + along * (left + door_width), along,
          width - left - door_width, base + 0.05, top - 0.03)
    weave(mesh, origin + along * left + up * (door_top - base), along,
          door_width, door_top, top - 0.03)


TUNNEL_ANGLE = -np.pi / 2      # the walkout runs out along -Z
TUNNEL_WEDGE = 0.20            # half-width of the gap cut through the stands


def ring(radius, segments=72, gap=None):
    """A ring of points, optionally opened by an angular gap.

    The stands are a near-circle rather than a scaled octagon: at this radius
    the eight flats read as a stop sign, and the arena wants to look round.
    """
    angles = np.linspace(-np.pi, np.pi, segments, endpoint=False)
    if gap is not None:
        centre, half = gap
        delta = np.abs(np.angle(np.exp(1j * (angles - centre))))
        angles = angles[delta > half]
    return np.column_stack([np.cos(angles) * radius, np.sin(angles) * radius]), gap is None


def build_bowl(mesh, rows=24, seats=True):
    """Stepped seating rising away from the cage, split by the walkout tunnel."""
    inner = 11.0
    tread = 0.92
    riser = 0.45
    gap = (TUNNEL_ANGLE, TUNNEL_WEDGE)

    for row in range(rows):
        r_in = inner + row * tread
        r_out = r_in + tread
        y_low = row * riser
        y_high = y_low + riser

        # Riser then tread. Each row is a ribbon, so the bowl stays open in
        # the middle; solid prisms would nest and the outermost would swallow
        # the whole arena.
        inner_ring, _ = ring(r_in, gap=gap)
        outer_ring, _ = ring(r_out, gap=gap)
        mesh.band("structure", inner_ring, y_low, inner_ring, y_high, closed=False)
        mesh.band("structure", inner_ring, y_high, outer_ring, y_high, closed=False)
        if not seats:
            continue

        # Seats sit on the tread, facing inward. Spacing is arc length, so
        # every row keeps the same seat pitch as the ring gets bigger.
        radius = r_in + tread * 0.55
        count = max(8, int(2 * np.pi * radius / 0.58))
        material = "seat_a" if row % 4 else "seat_b"
        for k in range(count):
            angle = -np.pi + 2 * np.pi * k / count
            if abs(np.angle(np.exp(1j * (angle - TUNNEL_ANGLE)))) <= TUNNEL_WEDGE:
                continue
            x, z = np.cos(angle) * radius, np.sin(angle) * radius
            mesh.box(material, (x, y_high + 0.22, z), (0.44, 0.44, 0.40), yaw=-angle)


def build_floor(mesh, radius=42.0):
    mesh.prism("floor", octagon(radius, rotation=np.pi / 8), -0.4, 0.0)


def build_tunnel(mesh, length=14.0, width=3.2, height=3.0):
    """The walkout tunnel, on the -Z side, aimed at the cage gate."""
    z_far = -(11.0 + length)
    z_near = -11.0
    for side in (-1, 1):
        mesh.box("tunnel", (side * (width / 2 + 0.15), height / 2, (z_far + z_near) / 2),
                 (0.3, height, length))
    mesh.box("tunnel", (0.0, height + 0.15, (z_far + z_near) / 2), (width + 0.6, 0.3, length))
    mesh.box("floor", (0.0, -0.05, (z_far + z_near) / 2), (width, 0.1, length))
    # Stairs up to the platform. They rise toward the cage, so the tallest
    # step is the one against the apron and the shortest meets the floor.
    steps = 6
    for i in range(steps):
        y = PLATFORM_HEIGHT * (steps - i) / steps
        mesh.box("structure", (0.0, y / 2, -(CIRCUMRADIUS + 0.75) - i * 0.42),
                 (2.4, y, 0.42))
    for side in (-1, 1):
        mesh.tube("structure", (side * 1.15, PLATFORM_HEIGHT, -(CIRCUMRADIUS + 0.6)),
                  (side * 1.15, PLATFORM_HEIGHT * 0.6, -(CIRCUMRADIUS + 0.75) - steps * 0.42),
                  0.04, segments=6)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=REPO / "build" / "arena" / "arena.glb")
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--no-seats", action="store_true")
    ap.add_argument("--cage-only", action="store_true")
    args = ap.parse_args()

    mesh = Mesh()
    build_platform(mesh)
    build_cage(mesh)
    if not args.cage_only:
        build_floor(mesh)
        build_tunnel(mesh)
        build_bowl(mesh, rows=args.rows, seats=not args.no_seats)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    size = mesh.write_glb(args.out, MATERIALS, name="Arena")

    total = sum(mesh.counts().values())
    for name, count in sorted(mesh.counts().items(), key=lambda kv: -kv[1]):
        print(f"  {name:14} {count:7d} треугольников")
    print(f"\n{total} треугольников, {size / 1e6:.2f} MB -> {args.out}")


if __name__ == "__main__":
    main()
