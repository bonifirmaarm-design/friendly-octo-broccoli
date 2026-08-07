#!/usr/bin/env python3
"""Import the textured OBJ archives (mesh + UVs + PBR maps) into assets/fighters.

The later generator runs produced a much better asset than the original STLs:
an OBJ carrying real UVs, a 4K base-colour map and a packed metallic/roughness
map. This unpacks such an archive, rewrites the material to a predictable
name, and downsamples the maps -- 4K per fighter is ~12 MB of texture, which
is not worth carrying in git when 2K is indistinguishable at gameplay
distance. The untouched originals stay in the upload commits on main.

    python3 tools/import_textured.py <archive.zip> --name fighter_apose_01
    python3 tools/import_textured.py --from-git origin/main   # every archive there

Requires pillow.
"""

import argparse
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None
REPO = Path(__file__).resolve().parent.parent

BASE_SIZE = 2048      # base colour keeps more detail: it carries tattoos and logos
PBR_SIZE = 1024       # roughness/metallic is low-frequency, 1K is plenty
BASE_QUALITY = 88
PBR_QUALITY = 85


def find_members(names):
    """Locate the mesh, material and texture maps inside an archive listing."""
    obj = next((n for n in names if n.lower().endswith(".obj")), None)
    mtl = next((n for n in names if n.lower().endswith(".mtl")), None)
    images = [n for n in names if n.lower().endswith((".jpg", ".jpeg", ".png"))]
    # The generator names the packed map "..._metallic.jpg-..._roughness.png",
    # so anything mentioning metallic or roughness is the PBR map and the
    # remaining image is the base colour.
    pbr = next((n for n in images if "metallic" in n.lower() or "roughness" in n.lower()), None)
    base = next((n for n in images if n != pbr), None)
    return obj, mtl, base, pbr


def convert_map(src, dst, size, quality):
    img = Image.open(src).convert("RGB")
    if max(img.size) > size:
        img = img.resize((size, size), Image.LANCZOS)
    img.save(dst, "JPEG", quality=quality, optimize=True)
    return img.size


def import_archive(archive, name, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        obj, mtl, base, pbr = find_members(zf.namelist())
        if not obj:
            raise SystemExit(f"{archive}: no .obj inside")
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            zf.extractall(tmp)

            shutil.copy(tmp / obj, out_dir / f"{name}.obj")
            sizes = {}
            if base:
                sizes["base"] = convert_map(tmp / base, out_dir / f"{name}_basecolor.jpg",
                                            BASE_SIZE, BASE_QUALITY)
            if pbr:
                sizes["pbr"] = convert_map(tmp / pbr, out_dir / f"{name}_metallic_roughness.jpg",
                                           PBR_SIZE, PBR_QUALITY)

    # Point the OBJ at our material file rather than the generator's name.
    obj_path = out_dir / f"{name}.obj"
    lines = obj_path.read_text().splitlines()
    kept = [ln for ln in lines if not ln.startswith(("mtllib", "usemtl"))]
    obj_path.write_text("\n".join([f"mtllib {name}.mtl", f"usemtl {name}"] + kept) + "\n")

    (out_dir / f"{name}.mtl").write_text(
        f"newmtl {name}\n"
        "Ka 0.000 0.000 0.000\nKd 1.000 1.000 1.000\nKs 0.200 0.200 0.200\n"
        "Ns 40.0\nd 1.0\nillum 2\n"
        f"map_Kd {name}_basecolor.jpg\n"
        + (f"map_Pr {name}_metallic_roughness.jpg\n" if pbr else "")
    )
    return sizes


def archives_in_git(ref):
    listing = subprocess.run(["git", "ls-tree", "-r", "--name-only", ref],
                             capture_output=True, text=True, check=True).stdout.split()
    return [n for n in listing if n.endswith(".zip")]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archives", nargs="*", type=Path)
    ap.add_argument("--name", help="asset name (single archive only)")
    ap.add_argument("--from-git", metavar="REF",
                    help="pull every textured archive out of a git ref instead")
    ap.add_argument("--out", type=Path, default=REPO / "assets" / "fighters")
    args = ap.parse_args()

    jobs = []
    tmpdir = None
    if args.from_git:
        tmpdir = tempfile.mkdtemp()
        for member in archives_in_git(args.from_git):
            blob = subprocess.run(["git", "show", f"{args.from_git}:{member}"],
                                  capture_output=True, check=True).stdout
            path = Path(tmpdir) / member
            path.write_bytes(blob)
            with zipfile.ZipFile(path) as zf:
                if not any(n.lower().endswith(".obj") for n in zf.namelist()):
                    continue  # the STL-only uploads are handled by stl_to_glb.py
            # Number the accepted archives, not every archive in the ref.
            jobs.append((path, f"fighter_apose_{len(jobs) + 1:02d}"))
    else:
        if not args.archives:
            sys.exit("give an archive path or --from-git REF")
        if args.name and len(args.archives) > 1:
            sys.exit("--name only makes sense with a single archive")
        for i, a in enumerate(args.archives, 1):
            jobs.append((a, args.name or f"fighter_apose_{i:02d}"))

    for path, name in jobs:
        sizes = import_archive(path, name, args.out)
        detail = "  ".join(f"{k}={v[0]}px" for k, v in sizes.items())
        print(f"{name:22} <- {Path(path).name[:20]}  {detail}")

    if tmpdir:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
