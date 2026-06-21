#!/usr/bin/env python3
"""Simple, clean Qumanity Ecosystem Overview diagram for white papers."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ── Minimal palette (4 colors) ───────────────────────────────────────────────
SITA_GREEN = "#2D5016"
MUTED_GOLD = "#C9A84C"
DARK_GRAY = "#333333"
LIGHT_GRAY = "#F5F5F5"
SUBTLE_GREEN = "#e8f0e5"
ARROW_GRAY = "#666666"
WHITE = "#FFFFFF"

# ── Font sizes ───────────────────────────────────────────────────────────────
FONT_TITLE = 14
FONT_LAYER = 12
FONT_ITEM = 10
FONT_SUB = 8

# ── Innovation grid dimensions (inches / data units) ───────────────────────
INN_W = 3.0
INN_H = 1.2
INN_GAP = 0.2

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = ASSETS_DIR / "images"
PDF_PATH = IMAGES_DIR / "ecosystem_simple.pdf"
PNG_PATH = IMAGES_DIR / "ecosystem_simple.png"

INNOVATIONS = [
    ("Four Timelines", "Private to Personal\nto Public to Global"),
    ("Nested Governance", "Village to Earth\n(8 Levels)"),
    ("Dual-Key Identity", "Private ID +\nPublic ID"),
    ("Karma Points Ledger", "Transparent\n· Verifiable"),
    ("Zodiac Elections", "Monthly · Regular\n· Fair"),
]


def create_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    color: str,
    *,
    text_color: str = DARK_GRAY,
    fontsize: float = FONT_ITEM,
    bold: bool = True,
    edgecolor: str | None = None,
    linewidth: float = 1.5,
) -> FancyBboxPatch:
    """Create a simple rounded box with centred text."""
    edge = edgecolor if edgecolor is not None else color
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.02,rounding_size=0.015",
        facecolor=color, edgecolor=edge, linewidth=linewidth,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2, y + height / 2, text,
        fontsize=fontsize, fontweight="bold" if bold else "normal",
        color=text_color, ha="center", va="center", linespacing=1.35,
    )
    return box


def create_innovation_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str,
    color: str = SITA_GREEN,
) -> None:
    """Single innovation box — title in upper half, subtitle below."""
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.04,rounding_size=0.02",
        facecolor=color, edgecolor=color, linewidth=1.5,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2, y + height * 0.62, title,
        fontsize=FONT_ITEM, fontweight="bold", color=WHITE,
        ha="center", va="center",
    )
    ax.text(
        x + width / 2, y + height * 0.32, subtitle,
        fontsize=FONT_SUB, fontweight="normal", color=WHITE,
        ha="center", va="center", linespacing=1.2,
    )


def create_arrow(ax, x1: float, y1: float, x2: float, y2: float) -> None:
    """Simple arrow between two points."""
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=12, linewidth=1.5,
        color=ARROW_GRAY, shrinkA=2, shrinkB=2,
    )
    ax.add_patch(arrow)


def create_innovations_panel(ax, panel_x: float, panel_y: float, panel_w: float, panel_h: float) -> None:
    """Five Innovations — 3+2 grid of individual boxes."""
    # Outer container
    outer = FancyBboxPatch(
        (panel_x, panel_y), panel_w, panel_h,
        boxstyle="round,pad=0.02,rounding_size=0.015",
        facecolor=SUBTLE_GREEN, edgecolor=SITA_GREEN, linewidth=2,
    )
    ax.add_patch(outer)

    ax.text(
        panel_x + panel_w / 2, panel_y + panel_h - 0.28,
        "Five Innovations — Core Protocol",
        ha="center", va="center",
        fontsize=FONT_LAYER, fontweight="bold", color=SITA_GREEN,
    )

    # Grid geometry
    row1_w = 3 * INN_W + 2 * INN_GAP
    row2_w = 2 * INN_W + INN_GAP
    row1_x = panel_x + (panel_w - row1_w) / 2
    row2_x = panel_x + (panel_w - row2_w) / 2

    row2_y = panel_y + 0.35
    row1_y = row2_y + INN_H + 0.25

    # Row 1: three boxes
    for i in range(3):
        bx = row1_x + i * (INN_W + INN_GAP)
        title, subtitle = INNOVATIONS[i]
        create_innovation_box(ax, bx, row1_y, INN_W, INN_H, title, subtitle)

    # Row 2: two boxes
    for i in range(2):
        bx = row2_x + i * (INN_W + INN_GAP)
        title, subtitle = INNOVATIONS[3 + i]
        create_innovation_box(ax, bx, row2_y, INN_W, INN_H, title, subtitle)


def create_diagram() -> plt.Figure:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        }
    )

    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.5)
    ax.axis("off")
    ax.set_facecolor(WHITE)

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(5, 7.08, "QUMANITY ECOSYSTEM OVERVIEW",
            ha="center", va="center", fontsize=FONT_TITLE,
            fontweight="bold", color=SITA_GREEN)
    ax.text(5, 6.72, "A Quantum-Informed Governance Protocol",
            ha="center", va="center", fontsize=FONT_ITEM,
            fontweight="normal", color=DARK_GRAY)
    ax.plot([1.5, 8.5], [6.48, 6.48], color=MUTED_GOLD, linewidth=1.2)

    # ── Layer 1: Citizens ────────────────────────────────────────────────────
    citizens_w, citizens_h = 7.0, 0.62
    citizens_x = (10 - citizens_w) / 2
    citizens_y = 5.62
    create_box(
        ax, citizens_x, citizens_y, citizens_w, citizens_h,
        "Citizens & Communities",
        LIGHT_GRAY, text_color=DARK_GRAY, fontsize=FONT_LAYER,
        edgecolor=SITA_GREEN, linewidth=2,
    )

    # ── Layer 2: Two Interfaces ──────────────────────────────────────────────
    iface_y = 4.28
    iface_h = 0.82
    iface_w = 2.75
    gap = 0.7
    web_x = 5 - gap / 2 - iface_w
    app_x = 5 + gap / 2

    create_box(
        ax, web_x, iface_y, iface_w, iface_h,
        "Website\nPublic Transparency\nqumanity.in",
        LIGHT_GRAY, text_color=DARK_GRAY, fontsize=FONT_ITEM,
        edgecolor=MUTED_GOLD, linewidth=2,
    )
    create_box(
        ax, app_x, iface_y, iface_w, iface_h,
        "iOS / macOS App\nDaily Governance",
        LIGHT_GRAY, text_color=DARK_GRAY, fontsize=FONT_ITEM,
        edgecolor=MUTED_GOLD, linewidth=2,
    )

    # ── Layer 3: Five Innovations grid ───────────────────────────────────────
    panel_x, panel_y = 0.25, 0.92
    panel_w, panel_h = 9.5, 2.95
    create_innovations_panel(ax, panel_x, panel_y, panel_w, panel_h)

    # ── Layer 4: PLNN ────────────────────────────────────────────────────────
    plnn_x, plnn_y = 1.0, 0.18
    plnn_w, plnn_h = 8.0, 0.58
    create_box(
        ax, plnn_x, plnn_y, plnn_w, plnn_h,
        "PLNN — Data Sovereignty  ·  Offline-First  ·  Nested Nodes",
        LIGHT_GRAY, text_color=DARK_GRAY, fontsize=FONT_LAYER,
        edgecolor=SITA_GREEN, linewidth=2,
    )

    # ── Arrows between layers ────────────────────────────────────────────────
    create_arrow(ax, 5, citizens_y, web_x + iface_w / 2, iface_y + iface_h)
    create_arrow(ax, 5, citizens_y, app_x + iface_w / 2, iface_y + iface_h)
    create_arrow(ax, web_x + iface_w / 2, iface_y, 3.2, panel_y + panel_h)
    create_arrow(ax, app_x + iface_w / 2, iface_y, 6.8, panel_y + panel_h)
    create_arrow(ax, 5, panel_y, 5, plnn_y + plnn_h)

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.text(5, 0.06, "SITA Foundation · qumanity.in",
            ha="center", va="center", fontsize=FONT_ITEM,
            fontweight="normal", color=DARK_GRAY)

    fig.tight_layout(pad=0.4)
    return fig


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    fig = create_diagram()

    save_kw = dict(bbox_inches="tight", facecolor=WHITE, edgecolor="none")
    fig.savefig(PDF_PATH, format="pdf", **save_kw)
    fig.savefig(PNG_PATH, format="png", dpi=300, **save_kw)
    plt.close(fig)

    print(f"Saved PDF: {PDF_PATH}")
    print(f"Saved PNG: {PNG_PATH} ({PNG_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
