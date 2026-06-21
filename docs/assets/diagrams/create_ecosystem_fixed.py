#!/usr/bin/env python3
"""
Qumanity Ecosystem diagram — fixed layout.
All text drawn AFTER boxes (higher zorder). No overlapping elements.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ── Colours ──────────────────────────────────────────────────────────────────
SITA_GREEN = "#2D5016"
MUTED_GOLD = "#C9A84C"
DARK_GRAY = "#333333"
LIGHT_GRAY = "#F5F5F5"
SUBTLE_GREEN = "#e8f0e5"
ARROW_GRAY = "#666666"
WHITE = "#FFFFFF"

# ── Spacing rules ────────────────────────────────────────────────────────────
PAD_IN = 0.1       # minimum padding inside boxes
GAP_BOX = 0.2      # gap between adjacent boxes
GAP_ROW = 0.3      # gap between rows

# ── Font sizes ───────────────────────────────────────────────────────────────
FONT_TITLE = 14
FONT_LAYER = 12
FONT_ITEM = 10
FONT_SUB = 8

# ── Innovation box size ──────────────────────────────────────────────────────
INN_W = 2.5
INN_H = 1.0

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = ASSETS_DIR / "images"
PDF_PATH = IMAGES_DIR / "ecosystem_fixed.pdf"
PNG_PATH = IMAGES_DIR / "ecosystem_fixed.png"

INNOVATIONS = [
    ("Four Timelines", "Private to Personal\nto Public to Global"),
    ("Nested Governance", "Village to Earth\n(8 Levels)"),
    ("Dual-Key Identity", "Private ID +\nPublic ID"),
    ("Karma Points Ledger", "Transparent\nVerifiable"),
    ("Zodiac Elections", "Monthly\nRegular · Fair"),
]

Z_BOX = 2   # boxes
Z_ARROW = 3
Z_TEXT = 10  # always on top


def draw_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    facecolor: str,
    edgecolor: str | None = None,
    linewidth: float = 1.5,
    zorder: int = Z_BOX,
) -> FancyBboxPatch:
    """Draw rounded box only — no text."""
    edge = edgecolor if edgecolor is not None else facecolor
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad={PAD_IN * 0.08},rounding_size=0.02",
        facecolor=facecolor,
        edgecolor=edge,
        linewidth=linewidth,
        zorder=zorder,
    )
    ax.add_patch(box)
    return box


def add_text_in_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str = "",
    *,
    title_size: float = FONT_ITEM,
    sub_size: float = FONT_SUB,
    color: str = WHITE,
    bold_title: bool = True,
) -> None:
    """Place title + subtitle inside box bounds. Call AFTER draw_box."""
    cx = x + width / 2
    cy = y + height / 2

    if subtitle:
        ax.text(
            cx, cy + height * 0.18, title,
            fontsize=title_size,
            fontweight="bold" if bold_title else "normal",
            color=color,
            ha="center", va="center",
            zorder=Z_TEXT,
            clip_on=True,
        )
        ax.text(
            cx, cy - height * 0.18, subtitle,
            fontsize=sub_size,
            fontweight="normal",
            color=color,
            ha="center", va="center",
            linespacing=1.2,
            zorder=Z_TEXT,
            clip_on=True,
        )
    else:
        ax.text(
            cx, cy, title,
            fontsize=title_size,
            fontweight="bold" if bold_title else "normal",
            color=color,
            ha="center", va="center",
            linespacing=1.3,
            zorder=Z_TEXT,
            clip_on=True,
        )


def add_box(
    ax,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    subtitle: str = "",
    *,
    bg_color: str = SITA_GREEN,
    text_color: str = WHITE,
    edgecolor: str | None = None,
    title_size: float = FONT_ITEM,
    linewidth: float = 1.5,
) -> None:
    """Box first, then text on top."""
    draw_box(ax, x, y, width, height,
             facecolor=bg_color, edgecolor=edgecolor, linewidth=linewidth)
    add_text_in_box(
        ax, x, y, width, height, title, subtitle,
        title_size=title_size, color=text_color,
    )


def draw_arrow(ax, x1: float, y1: float, x2: float, y2: float) -> None:
    arrow = FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.5,
        color=ARROW_GRAY,
        shrinkA=3,
        shrinkB=3,
        zorder=Z_ARROW,
    )
    ax.add_patch(arrow)


def innovation_positions() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Compute centred 3+2 grid positions."""
    row1_w = 3 * INN_W + 2 * GAP_BOX
    row2_w = 2 * INN_W + GAP_BOX
    row1_x0 = (10 - row1_w) / 2
    row2_x0 = (10 - row2_w) / 2

    row1 = [
        (row1_x0 + i * (INN_W + GAP_BOX), 0.0)
        for i in range(3)
    ]
    row2 = [
        (row2_x0 + i * (INN_W + GAP_BOX), 0.0)
        for i in range(2)
    ]
    return row1, row2


def create_diagram() -> plt.Figure:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Arial", "DejaVu Sans"],
    })

    fig, ax = plt.subplots(figsize=(10, 7.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7.5)
    ax.axis("off")
    ax.set_facecolor(WHITE)

    # ── Title (text only) ────────────────────────────────────────────────────
    ax.text(5, 7.12, "QUMANITY ECOSYSTEM OVERVIEW",
            fontsize=FONT_TITLE, fontweight="bold", color=SITA_GREEN,
            ha="center", va="center", zorder=Z_TEXT)
    ax.text(5, 6.78, "A Quantum-Informed Governance Protocol",
            fontsize=FONT_ITEM, color=DARK_GRAY,
            ha="center", va="center", zorder=Z_TEXT)
    ax.plot([1.5, 8.5], [6.55, 6.55], color=MUTED_GOLD, linewidth=1.2, zorder=Z_ARROW)

    # ── Layer 1: Citizens ────────────────────────────────────────────────────
    cit_x, cit_y, cit_w, cit_h = 1.5, 5.72, 7.0, 0.65
    add_box(ax, cit_x, cit_y, cit_w, cit_h,
            "Citizens & Communities", "",
            bg_color=LIGHT_GRAY, text_color=DARK_GRAY,
            edgecolor=SITA_GREEN, title_size=FONT_LAYER, linewidth=2)

    # ── Layer 2: Interfaces ──────────────────────────────────────────────────
    iface_y, iface_h, iface_w = 4.52, 0.78, 3.0
    web_x, app_x = 1.0, 6.0
    add_box(ax, web_x, iface_y, iface_w, iface_h,
            "Website", "Public Transparency\nqumanity.in",
            bg_color=MUTED_GOLD, text_color=WHITE, linewidth=2)
    add_box(ax, app_x, iface_y, iface_w, iface_h,
            "iOS / macOS App", "Daily Governance",
            bg_color=MUTED_GOLD, text_color=WHITE, linewidth=2)

    # ── Layer 3: Five Innovations panel ──────────────────────────────────────
    panel_x, panel_w = 0.35, 9.3
    row2_y = 1.55
    row1_y = row2_y + INN_H + GAP_ROW
    panel_y = row1_y - 0.55
    panel_h = (row1_y + INN_H) - panel_y + 0.15

    # Panel background
    draw_box(ax, panel_x, panel_y, panel_w, panel_h,
             facecolor=SUBTLE_GREEN, edgecolor=SITA_GREEN, linewidth=2)

    # Panel title (after box)
    ax.text(5, panel_y + panel_h - 0.28,
            "Five Innovations — Core Protocol",
            fontsize=FONT_LAYER, fontweight="bold", color=SITA_GREEN,
            ha="center", va="center", zorder=Z_TEXT)

    # Innovation boxes — boxes first, then all text
    row1_pos, row2_pos = innovation_positions()
    inn_boxes: list[tuple[float, float, str, str]] = []

    for i, (bx, _) in enumerate(row1_pos):
        draw_box(ax, bx, row1_y, INN_W, INN_H, facecolor=SITA_GREEN, linewidth=1.5)
        inn_boxes.append((bx, row1_y, INNOVATIONS[i][0], INNOVATIONS[i][1]))

    for i, (bx, _) in enumerate(row2_pos):
        draw_box(ax, bx, row2_y, INN_W, INN_H, facecolor=SITA_GREEN, linewidth=1.5)
        inn_boxes.append((bx, row2_y, INNOVATIONS[3 + i][0], INNOVATIONS[3 + i][1]))

    for bx, by, title, subtitle in inn_boxes:
        add_text_in_box(ax, bx, by, INN_W, INN_H, title, subtitle)

    # ── Layer 4: PLNN ────────────────────────────────────────────────────────
    plnn_x, plnn_y, plnn_w, plnn_h = 1.5, 0.42, 7.0, 0.68
    add_box(ax, plnn_x, plnn_y, plnn_w, plnn_h,
            "PLNN", "Data Sovereignty  ·  Offline-First  ·  Nested Nodes",
            bg_color=SITA_GREEN, text_color=WHITE, title_size=FONT_LAYER, linewidth=2)

    # ── Arrows (below text zorder) ───────────────────────────────────────────
    draw_arrow(ax, 5, cit_y, web_x + iface_w / 2, iface_y + iface_h)
    draw_arrow(ax, 5, cit_y, app_x + iface_w / 2, iface_y + iface_h)
    draw_arrow(ax, web_x + iface_w / 2, iface_y, 3.0, panel_y + panel_h)
    draw_arrow(ax, app_x + iface_w / 2, iface_y, 7.0, panel_y + panel_h)
    draw_arrow(ax, 5, panel_y, 5, plnn_y + plnn_h)

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.text(5, 0.12, "SITA Foundation · qumanity.in",
            fontsize=FONT_ITEM, color=DARK_GRAY,
            ha="center", va="center", zorder=Z_TEXT)

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
