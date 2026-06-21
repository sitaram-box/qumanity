#!/usr/bin/env python3
"""Qumanity Ecosystem diagram — precise pre-calculated coordinates."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = ASSETS_DIR / "images"
PNG_PATH = IMAGES_DIR / "ecosystem_perfect.png"
PDF_PATH = IMAGES_DIR / "ecosystem_perfect.pdf"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN = "#2D5016"
GOLD = "#C9A84C"
DARK = "#333333"
LIGHT = "#F5F5F5"
WHITE = "#FFFFFF"
ARROW = "#666666"

Z_BOX = 2
Z_ARROW = 3
Z_TEXT = 10


def box(
    ax,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    subtext: str,
    bg_color: str,
    text_color: str,
) -> None:
    """Draw box first, then title + subtext centred inside."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.05",
        facecolor=bg_color,
        edgecolor=bg_color,
        linewidth=1.5,
        zorder=Z_BOX,
    )
    ax.add_patch(rect)

    if subtext:
        ax.text(
            x + w / 2, y + h * 0.65, title,
            fontsize=10, fontweight="bold",
            color=text_color, ha="center", va="center",
            zorder=Z_TEXT, clip_on=True,
        )
        ax.text(
            x + w / 2, y + h * 0.32, subtext,
            fontsize=7.5, color=text_color,
            ha="center", va="center",
            linespacing=1.15,
            zorder=Z_TEXT, clip_on=True,
        )
    else:
        ax.text(
            x + w / 2, y + h / 2, title,
            fontsize=11, fontweight="bold",
            color=text_color, ha="center", va="center",
            zorder=Z_TEXT, clip_on=True,
        )


def arrow(ax, x1: float, y1: float, x2: float, y2: float) -> None:
    arr = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=11, linewidth=1.4,
        color=ARROW, shrinkA=3, shrinkB=3, zorder=Z_ARROW,
    )
    ax.add_patch(arr)


def create_ecosystem_diagram() -> plt.Figure:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    })

    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.5)
    ax.axis("off")
    ax.set_facecolor(WHITE)

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(5, 7.2, "QUMANITY ECOSYSTEM OVERVIEW",
            fontsize=16, fontweight="bold", color=GREEN, ha="center", zorder=Z_TEXT)
    ax.text(5, 6.9, "A Quantum-Informed Governance Protocol",
            fontsize=11, color=DARK, ha="center", zorder=Z_TEXT)

    # ── Row 1: Citizens (4.0, 6.0) 2.0 x 0.6 ───────────────────────────────
    box(ax, 4.0, 6.0, 2.0, 0.6, "Citizens & Communities", "", LIGHT, DARK)

    # ── Row 2: Interfaces ────────────────────────────────────────────────────
    box(ax, 1.5, 4.4, 2.8, 0.8, "Website", "Public Transparency", GOLD, WHITE)
    box(ax, 5.7, 4.4, 2.8, 0.8, "iOS / macOS App", "Daily Governance", GOLD, WHITE)

    # ── Row 3a: Innovations top row (y=2.7, 1.6 x 0.9) ───────────────────────
    box(ax, 1.2, 2.7, 1.6, 0.9, "Four Timelines",
        "Private to Personal\nto Public to Global", GREEN, WHITE)
    box(ax, 3.0, 2.7, 1.6, 0.9, "Nested Governance",
        "Village to Tehsil to District\nto State to Nation to Earth", GREEN, WHITE)
    box(ax, 4.8, 2.7, 1.6, 0.9, "Dual-Key Identity",
        "Private ID + Public ID", GREEN, WHITE)

    # ── Row 3b: Innovations bottom row (y=1.6) ───────────────────────────────
    box(ax, 1.2, 1.6, 1.6, 0.9, "Karma Points Ledger",
        "Transparent · Verifiable\nNon-inflationary", GREEN, WHITE)
    box(ax, 3.0, 1.6, 1.6, 0.9, "Zodiac Elections",
        "Monthly · Regular · Fair", GREEN, WHITE)

    # ── Row 4: PLNN (2.5, 0.6) 5.0 x 0.6 ───────────────────────────────────
    box(ax, 2.5, 0.6, 5.0, 0.6, "PLNN",
        "Data Sovereignty · Offline-First · Nested Nodes", GREEN, WHITE)

    # ── Arrows between layers ────────────────────────────────────────────────
    arrow(ax, 5.0, 6.0, 2.9, 5.2)      # Citizens → Website
    arrow(ax, 5.0, 6.0, 7.1, 5.2)     # Citizens → App
    arrow(ax, 2.9, 4.4, 2.0, 3.6)     # Website → Innovations
    arrow(ax, 7.1, 4.4, 4.0, 3.6)     # App → Innovations
    arrow(ax, 5.0, 2.7, 5.0, 1.2)     # Innovations → PLNN

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.text(5, 0.1, "SITA Foundation · qumanity.in",
            fontsize=8, color=DARK, ha="center", zorder=Z_TEXT)

    fig.tight_layout(pad=0.3)
    return fig


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    fig = create_ecosystem_diagram()
    save_kw = dict(bbox_inches="tight", facecolor=WHITE, edgecolor="none")
    fig.savefig(PNG_PATH, dpi=300, **save_kw)
    fig.savefig(PDF_PATH, **save_kw)
    plt.close(fig)
    print(f"Saved PNG: {PNG_PATH} ({PNG_PATH.stat().st_size // 1024} KB)")
    print(f"Saved PDF: {PDF_PATH}")


if __name__ == "__main__":
    main()
