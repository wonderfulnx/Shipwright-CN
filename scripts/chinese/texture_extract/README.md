# Chinese Texture Extraction

Extracts Chinese-language texture PNGs from the iQue (CN) version ROM.

## Directory Layout

```
scripts/chinese/texture_extract/
├── extract.py              ← texture extraction script
├── append_chi_decls.py     ← write OTR declarations into .h files
├── xml/                    ← texture XML definitions by category
│   ├── textures/           (do_action_static, item_name_static, …)
│   ├── objects/            (object_mag, …)
│   └── overlays/           (ovl_End_Title, …)
└── raw/                    ← decompressed binary files dumped from ROM (*.bin)
```

Output goes to `soh/assets/custom/<category>/<File>/` — one folder per `<File>`, one PNG per `<Texture>`.

## Workflow

1. Place decompressed `.bin` files in `raw/`
2. Run extraction: `uv run texture_extract/extract.py`
3. Run declarations: `uv run texture_extract/append_chi_decls.py`
4. Re-run `uv run message/generate_assets.py` to refresh font/message data

## Prerequisites: Dumping Binary Files from ROM

Use [Z64Utils](https://github.com/zeldaret/Z64Utils) to export the required `.bin` files from an iQue ROM (`oot_ique.z64`). Place them in `raw/` matching the `<File Name="...">` attributes in each XML.

### XML → ROM Files

| Category | XML | ROM Files Needed |
|----------|-----|------------------|
| textures | `boss_title_cards.xml` | `object_bv`, `object_fd`, `object_fhg`, `object_ganon`, `object_ganon2`, `object_goma`, `object_kingdodongo`, `object_mo`, `object_sst`, `object_tw` |
| textures | `do_action_static.xml` | `do_action_static` |
| textures | `icon_item_gameover_static.xml` | `icon_item_gameover_static` |
| textures | `icon_item_nes_static.xml` | `icon_item_nes_static` |
| textures | `icon_item_static.xml` | `icon_item_static` |
| textures | `item_name_static.xml` | `item_name_static` |
| textures | `map_name_static.xml` | `map_name_static` |
| textures | `parameter_static.xml` | `parameter_static` |
| textures | `place_title_cards.xml` | `g_pn_01` through `g_pn_57` |
| textures | `title_static.xml` | `title_static` |
| objects | `object_mag.xml` | `object_mag` |
| overlays | `ovl_End_Title.xml` | `ovl_End_Title` |

## Supported Texture Formats

| Format | Bits/pixel | Channel layout | Bytes/pixel |
|--------|-----------|----------------|-------------|
| `i4` | 4 | 4-bit intensity | 0.5 |
| `i8` | 8 | 8-bit intensity | 1 |
| `ia4` | 4 | 3-bit I + 1-bit A | 0.5 |
| `ia8` | 8 | 4-bit I + 4-bit A | 1 |
| `ia16` | 16 | 8-bit I + 8-bit A | 2 |
| `rgba16` | 16 | RGBA5551 | 2 |
| `rgba32` | 32 | RGBA8888 | 4 |

Format names follow ZAPD convention (total bits per pixel, not per channel).
