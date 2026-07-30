#!/usr/bin/env python3
"""
Extract Chinese textures from iQue OoT binary files.

Reads texture XML definitions from xml/<category>/*.xml, extracts raw N64
texture data from corresponding raw/<File>.bin, decodes to RGBA, and saves
as PNG via Pillow.

Output structure (one folder per <File>, one PNG per <Texture>):
    soh/assets/custom/
    ├── textures/
    │   ├── do_action_static/
    │   │   ├── gAttackDoActionCHITex.ia4.png
    │   │   └── ...
    │   └── ...
    ├── objects/
    │   └── object_goma/
    │       └── gGohmaTitleCardCHITex.i8.png
    └── overlays/
        └── ovl_End_Title/
            └── ...

Usage:
    uv run texture_extract/extract.py
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

# ---------------------------------------------------------------------------
# Paths — resolved relative to this script file
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent           # scripts/chinese/texture_extract
REPO = HERE.parent.parent.parent                 # Shipwright-CN/
XML_DIR = HERE / "xml"
BIN_DIR = HERE / "raw"
OUTPUT_BASE = REPO / "soh" / "assets" / "custom"

# Category subdirectories under xml/ and soh/assets/custom/
CATEGORIES = ["objects", "overlays", "textures"]


# ---------------------------------------------------------------------------
# N64 texture format decoders
# ---------------------------------------------------------------------------
def _expand4(v4: int) -> int:
    """Expand 4-bit → 8-bit by replication."""
    return (v4 << 4) | v4


def decode_i8(data: bytes, w: int, h: int) -> bytes:
    """Grayscale8bpp: 8-bit intensity → RGBA."""
    pixels = bytearray(w * h * 4)
    for i in range(w * h):
        v = data[i]
        off = i * 4
        pixels[off] = v
        pixels[off + 1] = v
        pixels[off + 2] = v
        pixels[off + 3] = 255
    return bytes(pixels)


def decode_i4(data: bytes, w: int, h: int) -> bytes:
    """Grayscale4bpp: 4-bit intensity (2 px/byte, high nibble first) → RGBA."""
    pixels = bytearray(w * h * 4)
    dst = 0
    for b in data:
        for shift in (4, 0):
            if dst >= w * h * 4:
                break
            v = _expand4((b >> shift) & 0x0F)
            pixels[dst] = v
            pixels[dst + 1] = v
            pixels[dst + 2] = v
            pixels[dst + 3] = 255
            dst += 4
    return bytes(pixels)


def decode_ia4(data: bytes, w: int, h: int) -> bytes:
    """GrayscaleAlpha4bpp: 3-bit I + 1-bit A (2 px/byte, high nibble first)."""
    pixels = bytearray(w * h * 4)
    dst = 0
    for b in data:
        for shift in (4, 0):
            if dst >= w * h * 4:
                break
            nibble = (b >> shift) & 0x0F
            i3 = (nibble >> 1) & 0x07
            i8 = (i3 << 5) | (i3 << 2) | (i3 >> 1)
            a8 = 255 if (nibble & 0x01) else 0
            pixels[dst] = i8
            pixels[dst + 1] = i8
            pixels[dst + 2] = i8
            pixels[dst + 3] = a8
            dst += 4
    return bytes(pixels)


def decode_ia8(data: bytes, w: int, h: int) -> bytes:
    """GrayscaleAlpha8bpp: 4-bit I + 4-bit A (1 byte/px, hi-nibble=I, lo=A)."""
    pixels = bytearray(w * h * 4)
    for i in range(w * h):
        b = data[i]
        off = i * 4
        pixels[off] = _expand4((b >> 4) & 0x0F)
        pixels[off + 1] = pixels[off]
        pixels[off + 2] = pixels[off]
        pixels[off + 3] = _expand4(b & 0x0F)
    return bytes(pixels)


def decode_ia16(data: bytes, w: int, h: int) -> bytes:
    """GrayscaleAlpha16bpp: 8-bit I + 8-bit A (2 bytes/px)."""
    pixels = bytearray(w * h * 4)
    for i in range(w * h):
        off = i * 4
        pixels[off] = data[i * 2]
        pixels[off + 1] = pixels[off]
        pixels[off + 2] = pixels[off]
        pixels[off + 3] = data[i * 2 + 1]
    return bytes(pixels)


def decode_rgba16(data: bytes, w: int, h: int) -> bytes:
    """RGBA16bpp: RGBA5551 big-endian → RGBA."""
    pixels = bytearray(w * h * 4)
    for i in range(w * h):
        v = (data[i * 2] << 8) | data[i * 2 + 1]
        off = i * 4
        pixels[off] = ((v >> 11) & 0x1F) * 255 // 31
        pixels[off + 1] = ((v >> 6) & 0x1F) * 255 // 31
        pixels[off + 2] = ((v >> 1) & 0x1F) * 255 // 31
        pixels[off + 3] = 255 if (v & 1) else 0
    return bytes(pixels)


def decode_rgba32(data: bytes, _w: int = 0, _h: int = 0) -> bytes:
    """RGBA32bpp → RGBA (direct)."""
    return data


DECODERS = {
    "i8": decode_i8,
    "i4": decode_i4,
    "ia4": decode_ia4,
    "ia8": decode_ia8,
    "ia16": decode_ia16,
    "rgba16": decode_rgba16,
    "rgba32": decode_rgba32,
}

# Bytes per pixel — matches ZAPD GetPixelMultiplyer()
BYTES_PER_PIXEL = {
    "i4": 0.5, "ia4": 0.5, "ci4": 0.5,
    "i8": 1.0, "ia8": 1.0, "ci8": 1.0,
    "ia16": 2.0, "rgba16": 2.0,
    "rgba32": 4.0,
}


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------
def parse_all_xmls(xml_dir: Path) -> list[dict]:
    """
    Parse all texture XMLs from xml_dir/<category>/*.xml.
    Returns flat list of texture dicts with keys:
        category, file_name, name, format, width, height, offset.
    """
    textures: list[dict] = []
    for category in CATEGORIES:
        cat_dir = xml_dir / category
        if not cat_dir.is_dir():
            continue
        for xml_path in sorted(cat_dir.glob("*.xml")):
            tree = ET.parse(xml_path)
            for file_elem in tree.getroot().findall("File"):
                file_name = file_elem.get("Name")
                if not file_name:
                    continue
                for tex_elem in file_elem.findall("Texture"):
                    name = tex_elem.get("Name")
                    if not name:
                        continue
                    w = int(tex_elem.get("Width", "0"), 0)
                    h = int(tex_elem.get("Height", "0"), 0)
                    if w == 0 or h == 0:
                        continue
                    textures.append({
                        "category": category,
                        "file_name": file_name,
                        "name": name,
                        "format": tex_elem.get("Format", "rgba32"),
                        "width": w,
                        "height": h,
                        "offset": int(tex_elem.get("Offset", "0"), 0),
                    })
    return textures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    if not XML_DIR.exists():
        print(f"ERROR: XML directory not found: {XML_DIR}")
        return
    if not BIN_DIR.exists():
        print(f"ERROR: Bin directory not found: {BIN_DIR}")
        return

    # Build .bin index
    available_bins: dict[str, Path] = {
        f.stem: f for f in BIN_DIR.glob("*.bin")
    }

    textures = parse_all_xmls(XML_DIR)
    xml_count = sum(1 for cat in CATEGORIES
                    for _ in (XML_DIR / cat).glob("*.xml")
                    if (XML_DIR / cat).is_dir())
    print(f"XMLs:  {xml_count} files  ({', '.join(CATEGORIES)})")
    print(f"Bins:  {len(available_bins)} files")
    print(f"Defs:  {len(textures)} texture definitions")
    print(f"Output: {OUTPUT_BASE}/<category>/")
    print()

    success = 0
    skipped = 0

    for tex in textures:
        file_name = tex["file_name"]
        category = tex["category"]
        out_name = f"{tex['name']}.{tex['format']}.png"
        out_path = OUTPUT_BASE / category / file_name / out_name

        # Look up binary
        bin_path = available_bins.get(file_name)
        if bin_path is None:
            print(f"  SKIP: {out_name} — '{file_name}.bin' not found")
            skipped += 1
            continue

        try:
            file_data = bin_path.read_bytes()
        except OSError as e:
            print(f"  ERROR: {out_name} — cannot read bin: {e}")
            skipped += 1
            continue

        # Compute raw size
        bpp = BYTES_PER_PIXEL.get(tex["format"].lower())
        if bpp is None:
            bpp = 4.0
        raw_size = int(tex["width"] * tex["height"] * bpp)

        if tex["offset"] + raw_size > len(file_data):
            print(f"  SKIP: {out_name} — bounds: "
                  f"0x{tex['offset']:X}+0x{raw_size:X} > 0x{len(file_data):X}")
            skipped += 1
            continue

        decoder = DECODERS.get(tex["format"].lower())
        if decoder is None:
            print(f"  SKIP: {out_name} — unknown format '{tex['format']}'")
            skipped += 1
            continue

        raw = file_data[tex["offset"]:tex["offset"] + raw_size]
        pixels = decoder(raw, tex["width"], tex["height"])

        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img = Image.frombytes("RGBA", (tex["width"], tex["height"]), pixels)
            img.save(out_path, "PNG")
            success += 1
        except Exception as e:
            print(f"  ERROR: {out_name} — {e}")
            skipped += 1

    # Summary
    print(f"\n{'=' * 50}")
    print(f"Done: {success} extracted  |  {skipped} skipped  |  {len(textures)} total")
    print(f"Output: {OUTPUT_BASE}/<category>/")

    # Show folder stats per category
    if success > 0:
        for category in CATEGORIES:
            cat_dir = OUTPUT_BASE / category
            if not cat_dir.is_dir():
                continue
            folders = sorted(d for d in cat_dir.iterdir() if d.is_dir())
            if folders:
                print(f"\n  {category}/  ({len(folders)} folders)")
                for d in folders:
                    count = len(list(d.glob("*.png")))
                    print(f"    {d.name}/  ({count} PNGs)")


if __name__ == "__main__":
    main()
