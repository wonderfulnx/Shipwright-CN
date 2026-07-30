#!/usr/bin/env python3
"""
Append CHI texture OTR declarations to existing header files.

Scans soh/assets/custom/ for PNG files with "CHI" in the name and writes
corresponding #define + static char declarations into the matching header
files under soh/assets/.  Handles three directory layouts:

  Simple 1:1  — custom/<category>/<folder>/  →  assets/<category>/<folder>/<folder>.h
  Title cards — custom/textures/<folder>/     →  assets/textures/place_title_cards/<folder>.h
                                                 assets/textures/boss_title_cards/<folder>.h

Usage:
    uv run texture_extract/append_chi_decls.py
"""

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent           # scripts/chinese/texture_extract
REPO = HERE.parent.parent.parent                 # Shipwright-CN/
CUSTOM_BASE = REPO / "soh" / "assets" / "custom"
ASSETS_BASE = REPO / "soh" / "assets"

# Categories with simple 1:1 custom/<cat>/<folder> → assets/<cat>/<folder>/<folder>.h
SIMPLE_CATEGORIES = ["textures", "objects", "overlays"]

# Title cards: PNGs live in custom/textures/<folder>/,
# headers live in assets/textures/<subdir>/<folder>.h
TITLE_CARD_HEADER_DIRS = {
    "place_title_cards": ASSETS_BASE / "textures" / "place_title_cards",
    "boss_title_cards": ASSETS_BASE / "textures" / "boss_title_cards",
}

# Folders under custom/textures/ that are handled by the simple-category
# scanner and should be skipped by the title-card scanner.
_SKIP_IN_TITLE_CARDS = frozenset({
    "do_action_static", "item_name_static", "map_name_static",
    "icon_item_nes_static", "icon_item_gameover_static",
    "icon_item_static", "parameter_static", "title_static",
    "chinese_font",
})


# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------

def _append_chi_textures(png_dir: Path, header_path: Path,
                         otr_prefix: str) -> int:
    """Scan *png_dir* for *CHI* PNGs and append OTR declarations to *header_path*.

    Each PNG ``gFooBarCHITex.ia4.png`` generates::

        #define dgFooBarCHITex "__OTR__<prefix>/gFooBarCHITex"
        static const ALIGN_ASSET(2) char gFooBarCHITex[] = dgFooBarCHITex;

    Returns the number of CHI entries written (0 if none).
    """
    if not png_dir.is_dir():
        return 0

    pngs = sorted(p for p in png_dir.iterdir()
                  if p.name.endswith(".png") and "CHI" in p.name)
    if not pngs:
        return 0

    # Normalise prefix: strip trailing slash so we can add our own
    otr_prefix = otr_prefix.rstrip("/")

    content = header_path.read_text(encoding="utf-8")

    # Remove previous CHI block if present (idempotent)
    content = re.sub(
        r"\n// #region SOH \[Chinese\].*?// #endregion\n",
        "", content, flags=re.DOTALL,
    )

    lines = []
    for p in pngs:
        name = p.name.split(".")[0]  # strip .ia4.png / .i8.png / …
        lines.append(f'#define d{name} "__OTR__{otr_prefix}/{name}"')
        lines.append(f"static const ALIGN_ASSET(2) char {name}[] = d{name};")
        lines.append("")

    block = (
        "\n// #region SOH [Chinese]\n"
        + "\n".join(lines)
        + "// #endregion\n"
    )

    content = content.replace("#endif", block + "#endif")
    header_path.write_text(content, encoding="utf-8")
    print(f"  Wrote {len(pngs)} CHI entries → {header_path}")
    return len(pngs)


# ---------------------------------------------------------------------------
# Simple 1:1 categories
# ---------------------------------------------------------------------------

def append_simple_category(category: str) -> int:
    """Scan custom/<category>/ for folders, update assets/<category>/<folder>/<folder>.h.

    Returns total CHI entries written across all folders.
    """
    custom_dir = CUSTOM_BASE / category
    header_base = ASSETS_BASE / category

    if not custom_dir.is_dir():
        print(f"  Custom dir not found: {custom_dir} — skipping")
        return 0

    total = 0
    for folder in sorted(custom_dir.iterdir()):
        if not folder.is_dir():
            continue
        header_path = header_base / folder.name / f"{folder.name}.h"
        if not header_path.exists():
            continue
        total += _append_chi_textures(
            folder, header_path, f"{category}/{folder.name}",
        )

    if total:
        print(f"  category '{category}': {total} CHI entries written")
    return total


# ---------------------------------------------------------------------------
# Title cards
# ---------------------------------------------------------------------------

def append_title_cards() -> int:
    """Scan custom/textures/ for title-card folders.

    Title cards live under custom/textures/ but their headers are in
    assets/textures/place_title_cards/ or assets/textures/boss_title_cards/.
    The OTR prefix is derived from an existing ENG entry in the header.
    """
    custom_textures = CUSTOM_BASE / "textures"
    if not custom_textures.is_dir():
        return 0

    total = 0
    for folder in sorted(custom_textures.iterdir()):
        if not folder.is_dir():
            continue
        if folder.name in _SKIP_IN_TITLE_CARDS:
            continue

        # Find which header directory contains the matching .h file
        header_path = None
        for hd in TITLE_CARD_HEADER_DIRS.values():
            candidate = hd / f"{folder.name}.h"
            if candidate.exists():
                header_path = candidate
                break
        if header_path is None:
            continue

        # Extract OTR prefix from an existing ENG entry
        content = header_path.read_text(encoding="utf-8")
        m = re.search(r'"__OTR__([^"]+/)[^/"]+ENGTex"', content)
        if not m:
            continue
        otr_prefix = m.group(1)  # e.g. "textures/g_pn_01/"

        total += _append_chi_textures(folder, header_path, otr_prefix)

    if total:
        print(f"  title cards: {total} CHI entries written")
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Append CHI texture declarations ===\n")

    grand_total = 0

    for category in SIMPLE_CATEGORIES:
        print(f"-- {category} --")
        grand_total += append_simple_category(category)
        print()

    print("-- title cards --")
    grand_total += append_title_cards()
    print()

    print(f"=== Done: {grand_total} CHI declarations written ===")


if __name__ == "__main__":
    main()
