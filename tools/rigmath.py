#!/usr/bin/env python3
"""Forward kinematics and IK for the fighter rigs.

Split out of animate.py because takedowns need it for something the strike
clips never did: to make one fighter grab another, you have to know where
the other fighter's thigh actually is at that instant, which means running
his pose forward before you can aim the attacker's hands at it.
"""

import numpy as np
from scipy.spatial.transform import Rotation

IDENTITY = Rotation.identity()


def two_bone_ik(root, target, len_upper, len_lower, pole):
    """Return (mid, effector) for a two-bone chain reaching toward target."""
    to_target = target - root
    reach = float(np.linalg.norm(to_target))
    span = len_upper + len_lower
    if reach < 1e-9:
        to_target = np.array([0.0, -1.0, 0.0])
        reach = 1e-9
    reach = float(np.clip(reach, abs(len_upper - len_lower) + 1e-4, span - 1e-4))
    direction = to_target / (np.linalg.norm(to_target) or 1.0)
    effector = root + direction * reach

    cos_root = np.clip((len_upper ** 2 + reach ** 2 - len_lower ** 2)
                       / (2 * len_upper * reach), -1.0, 1.0)
    angle = float(np.arccos(cos_root))

    # Swing the mid joint off the straight line, toward the pole hint, so the
    # elbow bends backward and the knee forward instead of picking a side at
    # random.
    side = pole - direction * float(pole @ direction)
    norm = float(np.linalg.norm(side))
    if norm < 1e-6:
        side = np.cross(direction, [0.0, 0.0, 1.0])
        norm = float(np.linalg.norm(side)) or 1.0
    side = side / norm
    mid = root + len_upper * (direction * np.cos(angle) + side * np.sin(angle))
    return mid, effector


def align(from_dir, to_dir):
    """Shortest rotation carrying one direction onto another."""
    a = from_dir / (np.linalg.norm(from_dir) or 1.0)
    b = to_dir / (np.linalg.norm(to_dir) or 1.0)
    axis = np.cross(a, b)
    length = float(np.linalg.norm(axis))
    if length < 1e-9:
        if a @ b > 0:
            return IDENTITY
        fallback = np.cross(a, [1.0, 0.0, 0.0])
        if np.linalg.norm(fallback) < 1e-6:
            fallback = np.cross(a, [0.0, 1.0, 0.0])
        return Rotation.from_rotvec(fallback / np.linalg.norm(fallback) * np.pi)
    return Rotation.from_rotvec(axis / length * float(np.arctan2(length, a @ b)))


class Rig:
    """A fighter's rest skeleton, with FK and limb IK on top of it."""

    CHAINS = {
        "hand_L": ("UpperArm_L", "LowerArm_L", "Hand_L"),
        "hand_R": ("UpperArm_R", "LowerArm_R", "Hand_R"),
        "foot_L": ("UpperLeg_L", "LowerLeg_L", "Foot_L"),
        "foot_R": ("UpperLeg_R", "LowerLeg_R", "Foot_R"),
    }
    TORSO = {"hips": "Hips", "spine": "Spine", "chest": "Chest",
             "neck": "Neck", "head": "Head"}

    def __init__(self, rest, parent_of):
        self.rest = rest
        self.parent_of = parent_of
        self.height = max(p[1] for p in rest.values())
        self.children = {}
        self.root = None
        for bone, parent in parent_of.items():
            if parent is None:
                self.root = bone
            else:
                self.children.setdefault(parent, []).append(bone)

    def fk(self, local, root_offset=None):
        """World position and rotation of every bone."""
        offset = np.zeros(3) if root_offset is None else np.asarray(root_offset, float)
        world_pos, world_rot = {}, {}

        stack = [self.root]
        while stack:
            bone = stack.pop()
            parent = self.parent_of[bone]
            if parent is None:
                world_rot[bone] = local.get(bone, IDENTITY)
                world_pos[bone] = self.rest[bone] + offset
            else:
                world_rot[bone] = world_rot[parent] * local.get(bone, IDENTITY)
                world_pos[bone] = world_pos[parent] + world_rot[parent].apply(
                    self.rest[bone] - self.rest[parent])
            stack.extend(self.children.get(bone, []))
        return world_pos, world_rot

    def reach(self, local, chain_key, target, root_offset=None):
        """Bend one limb so its tip reaches a world-space target.

        Writes the two resulting local rotations into `local` in place.
        """
        upper, lower, tip = self.CHAINS[chain_key]
        world_pos, world_rot = self.fk(local, root_offset)
        parent_rotation = world_rot[self.parent_of[upper]]
        root = world_pos[upper]

        len_upper = float(np.linalg.norm(self.rest[lower] - self.rest[upper]))
        len_lower = float(np.linalg.norm(self.rest[tip] - self.rest[lower]))
        side = np.sign(self.rest[upper][0]) or 1.0
        pole = (np.array([side * 0.5, -0.2, -1.0]) if chain_key.startswith("hand")
                else np.array([side * 0.2, -0.2, 1.0]))
        mid, effector = two_bone_ik(root, target, len_upper, len_lower, pole)

        upper_now = parent_rotation.apply(self.rest[lower] - self.rest[upper])
        upper_world = align(upper_now, mid - root) * parent_rotation
        local[upper] = parent_rotation.inv() * upper_world

        lower_now = upper_world.apply(self.rest[tip] - self.rest[lower])
        lower_world = align(lower_now, effector - mid) * upper_world
        local[lower] = upper_world.inv() * lower_world
        return local

    def solve(self, target_pose, extra_targets=None):
        """Turn a pose dict into local bone rotations.

        Torso angles are applied first because every limb hangs off them: an
        IK target is a world position, so the arm has to be solved against a
        chest that has already turned, or the hand lands somewhere else.
        """
        local = {}
        for key, bone in self.TORSO.items():
            if key in target_pose:
                local[bone] = Rotation.from_euler("xyz", target_pose[key])

        offset = np.asarray(target_pose.get("root", (0.0, 0.0, 0.0)), float) * self.height

        targets = {}
        for key in self.CHAINS:
            if key in target_pose:
                targets[key] = np.asarray(target_pose[key], float) * self.height
        if extra_targets:
            targets.update(extra_targets)   # grips win over the authored pose

        for key, target in targets.items():
            self.reach(local, key, target, offset)
        return local, offset


def place(points, offset, yaw, height):
    """Move a set of world points into another fighter's frame."""
    rotation = Rotation.from_euler("y", yaw)
    shift = np.asarray(offset, float) * height
    return {k: rotation.apply(v) + shift for k, v in points.items()}
