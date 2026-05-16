#!/usr/bin/env python3
"""
Prepare the homepage hero image: copy JPEG backup, resize, export WebP.

Install dependency:
  pip install Pillow

Run from the project root (do not commit before reviewing output):
  python prepare_image.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError as exc:
    print("Pillow is required: pip install Pillow", file=sys.stderr)
    raise SystemExit(1) from exc

# Project layout
PROJECT_ROOT = Path(__file__).resolve().parent
IMAGES_DIR = PROJECT_ROOT / "static" / "images"
BACKUP_NAME = "earth5_backup.jpeg"
WEBP_NAME = "earth5.webp"

# Try common locations for the source photo (edit if yours differs)
SOURCE_CANDIDATES = [
    Path("/Users/macmudgal/Desktop/earth5.jpeg"),
    Path.home() / "Desktop" / "earth5.jpeg",
]

MAX_WIDTH_PX = 600
WEBP_QUALITY = 80


def find_source() -> Path:
    for p in SOURCE_CANDIDATES:
        if p.is_file():
            return p.resolve()
    searched = ", ".join(str(p) for p in SOURCE_CANDIDATES)
    raise FileNotFoundError(
        f"No source JPEG found. Tried: {searched}. "
        "Place earth5.jpeg on your Desktop or set SOURCE_CANDIDATES in prepare_image.py."
    )


def main() -> None:
    src = find_source()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    backup_path = IMAGES_DIR / BACKUP_NAME
    shutil.copy2(src, backup_path)

    with Image.open(src) as im:
        if im.mode == "RGBA":
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")

        # Fits within width MAX_WIDTH_PX (height follows aspect ratio)
        im.thumbnail((MAX_WIDTH_PX, MAX_WIDTH_PX * 4), Image.Resampling.LANCZOS)

        out_webp = IMAGES_DIR / WEBP_NAME
        im.save(out_webp, format="WEBP", quality=WEBP_QUALITY, method=6)

    print(
        "Done.\n"
        f"  Backup JPEG: {backup_path}\n"
        f"  WebP ({WEBP_QUALITY}% quality, max width {MAX_WIDTH_PX}px): {out_webp}\n"
        f"  Source used: {src}"
    )


if __name__ == "__main__":
    main()
