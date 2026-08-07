#!/usr/bin/env python3
"""Check every fighter's every clip for the faults a still frame will not show.

Three things go wrong invisibly. A limb can solve to NaN. A joint can be
driven through the mat. And two keyframes can sit far apart in pose but close
in time, so what plays between them is a snap rather than a motion -- that one
is measured as limb speed in body heights per second, since a real punch peaks
near 5 and anything past 9 means the timeline is wrong rather than the fighter
being fast. It is how the combo splice was caught writing poses a millisecond
apart at 800 heights per second.

    python3 tools/validate.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import animate  # noqa: E402
import moves  # noqa: E402
from rigmath import Rig  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

FLOOR_TOLERANCE = 0.03    # fraction of height a joint may dip below the mat
SPEED_LIMIT = 9.0         # body heights per second


def main():
    issues = []
    for key in moves.FIGHTERS:
        gltf, _ = animate.read_glb(REPO / "build" / "rigged" / f"{key}.glb")
        rest, parent_of, _ = animate.read_rig(gltf)
        rig = Rig(rest, parent_of)
        height = rig.height
        tracks, _, spec = animate.build_tracks(rig, key)

        for name in sorted(tracks):
            lowest, speed = 9e9, 0.0
            has_nan = False
            previous, previous_time = None, None
            for time, local, offset in tracks[name]:
                positions = np.array(list(rig.fk(local, offset)[0].values()))
                if not np.isfinite(positions).all():
                    has_nan = True
                lowest = min(lowest, positions[:, 1].min())
                if previous is not None and time > previous_time:
                    speed = max(speed, np.linalg.norm(positions - previous, axis=1).max()
                                / height / (time - previous_time))
                previous, previous_time = positions, time

            faults = []
            if has_nan:
                faults.append("NaN")
            if lowest < -FLOOR_TOLERANCE * height:
                faults.append(f"пол {lowest / height:+.2f}")
            if speed > SPEED_LIMIT:
                faults.append(f"скорость {speed:.1f} роста/с")
            if faults:
                issues.append((spec["name"], name, ", ".join(faults)))

    print(f"проверено бойцов: {len(moves.FIGHTERS)}")
    if issues:
        print(f"\nПРОБЛЕМЫ ({len(issues)}):")
        for fighter, clip, fault in issues:
            print(f"  {fighter:8} {clip:28} {fault}")
    else:
        print("\nвсе клипы чистые")
    return 1 if any("NaN" in f or "скорость" in f for _, _, f in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
