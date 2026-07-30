#!/usr/bin/env python3
"""Generate chinese_menu_hd.o2r — HD texture mod for Chinese UI textures.

Reads HD PNGs from scripts/chinese/hd_textures/ (do_action_static,
item_name_static, map_name_static) and packs them into an O2R mod file.

Each HD PNG must have a corresponding custom (non-HD) CHI texture in
soh/assets/custom/textures/<folder>/ to determine origin size.

Usage:
    uv run hd_textures/generate_hd_menu_o2r.py
"""

from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Paths
HERE = Path(__file__).resolve().parent             # scripts/chinese/hd_textures/
REPO = HERE.parent.parent.parent                   # Shipwright-CN/
CUSTOM_DIR = REPO / "soh" / "assets" / "custom"
HD_DIR = HERE                                       # HD PNGs grouped by category
OUT_O2R = REPO / "chinese_menu_hd.o2r"

CATEGORIES = ["textures", "objects", "overlays"]

# OTR binary format constants
OTR_HEADER_SIZE = 0x40
RESOURCE_TYPE_TEXTURE = 0x4F544558
TEX_FLAG_LOAD_AS_RAW = 1

# Fast::TextureType enum values (libultraship/include/fast/resource/type/Texture.h)
RGBA32 = 1
RGBA16 = 2
I4     = 5   # Grayscale4bpp        (4bpp, 0.5 B/px)
I8     = 6   # Grayscale8bpp        (8bpp, 1 B/px)
IA4    = 7   # GrayscaleAlpha4bpp   (4bpp, 0.5 B/px)
IA8    = 8   # GrayscaleAlpha8bpp   (8bpp, 1 B/px)
IA16   = 9   # GrayscaleAlpha16bpp  (16bpp, 2 B/px)


def tex_type_from_png_name(png_name: str) -> int:
    """Return the Fast::TextureType value based on the PNG format suffix."""
    if ".rgba32." in png_name:
        return RGBA32
    if ".rgba16." in png_name:
        return RGBA16
    if ".ia16." in png_name:
        return IA16
    if ".ia8." in png_name:
        return IA8
    if ".i8." in png_name:
        return I8
    if ".i4." in png_name:
        return I4
    return IA4  # default for ia4


def orig_bytes_per_row(orig_w: int, tex_type: int) -> float:
    """Original bytes per row for the given texture type."""
    if tex_type in (RGBA32,):               # 32bpp: 4 bytes/pixel
        return orig_w * 4.0
    if tex_type in (RGBA16, IA16):          # 16bpp: 2 bytes/pixel
        return orig_w * 2.0
    if tex_type in (I8, IA8):               # 8bpp: 1 byte/pixel
        return orig_w * 1.0
    return orig_w * 0.5                     # I4 / IA4: 4bpp: 0.5 byte/pixel


def verify_coverage() -> dict[str, list[tuple[str, Path, Path]]]:
    """Check every custom CHI PNG has a matching HD PNG.

    Scans soh/assets/custom/<category>/<folder>/ for *CHI*.png files and
    expects matching HD PNGs at scripts/chinese/hd_textures/<category>/<folder>/.
    Returns dict keyed by "category/folder".
    """
    result: dict[str, list[tuple[str, Path, Path]]] = {}
    missing: list[str] = []

    for category in CATEGORIES:
        custom_cat = CUSTOM_DIR / category
        hd_cat = HD_DIR / category
        if not custom_cat.is_dir():
            continue

        for custom_dir in sorted(custom_cat.iterdir()):
            if not custom_dir.is_dir():
                continue
            folder = custom_dir.name
            custom_hd_dir = hd_cat / folder

            entries: list[tuple[str, Path, Path]] = []
            for png in sorted(custom_dir.iterdir()):
                if not png.name.endswith(".png") or "CHI" not in png.name:
                    continue
                tex_name = png.name.split(".")[0]
                hd_png = custom_hd_dir / f"{tex_name}.png"
                if not hd_png.exists():
                    missing.append(f"  {category}/{folder}/{tex_name}: "
                                   f"HD PNG not found at {hd_png}")
                entries.append((tex_name, png, hd_png))

            if entries:
                result[f"{category}/{folder}"] = entries

    if missing:
        print("ERROR: Missing HD textures:")
        for m in missing:
            print(m)
        sys.exit(1)

    return result


def build_otr_resource(rgba_data: bytes, orig_w: int, orig_h: int,
                       hd_w: int, hd_h: int, tex_type: int) -> bytes:
    """Build a complete OTR binary resource for one HD texture."""
    buf = bytearray()

    # OTR Header (64 bytes)
    buf += struct.pack("<B", 0)
    buf += struct.pack("<B", 0)
    buf += struct.pack("<BB", 0, 0)
    buf += struct.pack("<I", RESOURCE_TYPE_TEXTURE)
    buf += struct.pack("<I", 1)
    buf += struct.pack("<Q", 0xDEADBEEFDEADBEEF)
    while len(buf) < OTR_HEADER_SIZE:
        buf += struct.pack("<I", 0)

    # Scale factors — correct for the original texture format
    obpr = orig_bytes_per_row(orig_w, tex_type)
    h_byte_scale = (hd_w * 4.0) / obpr      # HD RGBA32 bytes-per-row ÷ orig bytes-per-row
    v_pixel_scale = float(hd_h) / orig_h    # HD height ÷ orig height

    # V1 Texture Data
    buf += struct.pack("<I", tex_type)
    buf += struct.pack("<I", hd_w)
    buf += struct.pack("<I", hd_h)
    buf += struct.pack("<I", TEX_FLAG_LOAD_AS_RAW)
    buf += struct.pack("<f", h_byte_scale)
    buf += struct.pack("<f", v_pixel_scale)
    buf += struct.pack("<I", len(rgba_data))
    buf += rgba_data

    return bytes(buf)


def main():
    if not HAS_PIL:
        print("Pillow not installed. Run: uv sync")
        sys.exit(1)

    print("Verifying HD texture coverage...")
    entries_by_folder = verify_coverage()
    total = sum(len(v) for v in entries_by_folder.values())
    print(f"  All {total} custom CHI textures have matching HD PNGs.\n")

    print(f"Packing O2R → {OUT_O2R} ...")
    not_8x: list[str] = []
    with zipfile.ZipFile(str(OUT_O2R), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("portVersion", "9.2.3")

        count = 0
        for path_key, entries in entries_by_folder.items():
            for tex_name, custom_png, hd_png in entries:
                # Read original dimensions from the custom PNG
                with Image.open(custom_png) as orig:
                    orig_w, orig_h = orig.size

                # Derive texture type from the custom PNG suffix
                tex_type = tex_type_from_png_name(custom_png.name)

                # Read HD RGBA data
                with Image.open(hd_png) as hd_img:
                    hd_img = hd_img.convert("RGBA")
                    hd_w, hd_h = hd_img.size
                    rgba_data = hd_img.tobytes("raw", "RGBA")

                # Warn if HD is not exactly 8× the original
                if hd_w != orig_w * 8 or hd_h != orig_h * 8:
                    not_8x.append(f"  {path_key}/{tex_name}  "
                                  f"orig={orig_w}×{orig_h}  hd={hd_w}×{hd_h}")
                    print(f"  WARNING: {path_key}/{tex_name}: "
                          f"expected {orig_w*8}×{orig_h*8}, got {hd_w}×{hd_h}")

                otr_data = build_otr_resource(rgba_data, orig_w, orig_h,
                                              hd_w, hd_h, tex_type)
                zf.writestr(f"alt/{path_key}/{tex_name}", otr_data)
                count += 1

    if not_8x:
        print(f"  There are {len(not_8x)} texture(s) not exactly 8× the original size.")
    else:
        print(f"  All {count} textures are exactly 8× the original size.")
    size_mb = OUT_O2R.stat().st_size / 1024 / 1024
    print(f"\nDone: {OUT_O2R} ({size_mb:.1f} MB, {count} textures)")
    print(f"Place in: mods/chinese_menu_hd.o2r")


if __name__ == "__main__":
    main()
