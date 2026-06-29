#!/usr/bin/env python3
"""Edit earth13.png: saffron → dark black, pure white map, remove text."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "earth13.png"
DEFAULT_DST = ROOT / "static" / "images" / "earth13.png"

BLACK = np.array([10, 10, 10], dtype=np.uint8)
WHITE = np.array([255, 255, 255], dtype=np.uint8)


def edit_earth_image(src: Path, dst: Path) -> None:
    img = Image.open(src).convert("RGB")
    data = np.array(img, dtype=np.float32)
    r, g, b = data[:, :, 0], data[:, :, 1], data[:, :, 2]
    brightness = (r + g + b) / 3.0

    # Saffron / orange background only — everything else is the white map (text removed).
    is_saffron = (r > 160) & (g > 80) & (g < 210) & (b < 120) & (r > g)

    out = np.where(is_saffron[..., None], BLACK, WHITE)

    dst.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(out.astype(np.uint8)).save(dst, optimize=True)
    white_px = int(np.sum(~is_saffron))
    black_px = int(np.sum(is_saffron))
    print(f"Saved {dst} ({img.size[0]}x{img.size[1]})")
    print(f"  White pixels: {white_px:,}")
    print(f"  Black pixels: {black_px:,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Edit earth13 for hero background")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC)
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST)
    args = parser.parse_args()
    if not args.src.is_file():
        print(f"Source not found: {args.src}", file=sys.stderr)
        sys.exit(1)
    edit_earth_image(args.src, args.dst)


if __name__ == "__main__":
    main()
