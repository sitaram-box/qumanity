#!/usr/bin/env python3
"""Qumanity Ecosystem diagram — publication-ready final version."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = ASSETS_DIR / "images"
PNG_PATH = IMAGES_DIR / "ecosystem_final.png"
PDF_PATH = IMAGES_DIR / "ecosystem_final.pdf"

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN = "#2D5016"
GOLD = "#C9A84C"
DARK = "#333333"
LIGHT = "#F5F5F5"
CONTAINER_BG = "#F5F8F5"
WHITE = "#FFFFFF"
ARROW = "#666666"

Z_CONTAINER = 1
Z_BOX = 2
Z_ARROW = 3
Z_TEXT = 10

FIG_W, FIG_H = 11, 9
CX = FIG_W / 2

BOX_PAD = 0.12
ARROW_LW = 2.75
ARROW_LABEL_SIZE = 9

# ── Innovation subtext (single-line, clean separators) ───────────────────────
INNOVATIONS_TOP = [
    ("Four Timelines", "Private \u2192 Personal \u2192 Public \u2192 Global"),
    ("Nested Governance", "Village \u2192 Earth (8 Levels)"),
    ("Dual-Key Identity", "Private ID + Public ID"),
]
INNOVATIONS_BOTTOM = [
    ("Karma Points Ledger", "Transparent \u00b7 Verifiable \u00b7 Non-inflationary"),
    ("Zodiac Elections", "Monthly \u00b7 Regular \u00b7 Fair"),
]


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
    *,
    fontsize_title: float = 10,
    fontsize_sub: float = 7,
    pad: float = BOX_PAD,
) -> None:
    """Draw rounded box with centred title and subtext."""
    rect = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad={pad}",
        facecolor=bg_color,
        edgecolor=bg_color,
        linewidth=2,
        zorder=Z_BOX,
    )
    ax.add_patch(rect)

    cx = x + w / 2
    if subtext:
        ax.text(
            cx, y + h * 0.68, title,
            fontsize=fontsize_title, fontweight="bold",
            color=text_color, ha="center", va="center",
            zorder=Z_TEXT, clip_on=True,
        )
        ax.text(
            cx, y + h * 0.32, subtext,
            fontsize=fontsize_sub, color=text_color,
            ha="center", va="center",
            zorder=Z_TEXT, clip_on=True,
        )
    else:
        ax.text(
            cx, y + h / 2, title,
            fontsize=fontsize_title + 1, fontweight="bold",
            color=text_color, ha="center", va="center",
            zorder=Z_TEXT, clip_on=True,
        )


def add_arrow(
    ax,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    label: str | None = None,
) -> None:
    """Add an arrow between two points with an optional label."""
    ax.annotate(
        "",
        xy=(x2, y2),
        xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle="->",
            color=ARROW,
            lw=ARROW_LW,
            connectionstyle="arc3,rad=0",
            shrinkA=2,
            shrinkB=2,
        ),
        zorder=Z_ARROW,
    )

    if label:
        mid_x = (x1 + x2) / 2
        mid_y = (y1 + y2) / 2
        ax.text(
            mid_x + 0.35, mid_y, label,
            fontsize=ARROW_LABEL_SIZE, color=ARROW,
            ha="center", va="center", fontweight="bold",
            zorder=Z_TEXT,
            bbox=dict(
                boxstyle="round,pad=0.25",
                facecolor=WHITE,
                edgecolor="none",
                alpha=0.92,
            ),
        )


def _place_row(
    ax,
    items: list[tuple[str, str]],
    x0: float,
    y: float,
    w: float,
    h: float,
    gap: float,
) -> None:
    """Place a horizontal row of innovation boxes."""
    for i, (title, subtext) in enumerate(items):
        box(
            ax, x0 + i * (w + gap), y, w, h,
            title, subtext, GREEN, WHITE,
            fontsize_sub=6.5,
        )


def create_ecosystem_diagram() -> plt.Figure:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Helvetica Neue", "Arial"],
    })

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.axis("off")
    ax.set_facecolor(WHITE)

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(CX, 8.45, "QUMANITY ECOSYSTEM OVERVIEW",
            fontsize=16, fontweight="bold", color=GREEN, ha="center", zorder=Z_TEXT)
    ax.text(CX, 8.05, "A Quantum-Informed Governance Protocol",
            fontsize=11, color=DARK, ha="center", zorder=Z_TEXT)

    # ── Layer 1: Citizens ──────────────────────────────────────────────────────
    CIT_Y, CIT_H, CIT_W = 6.5, 0.6, 2.4
    box(ax, CX - CIT_W / 2, CIT_Y, CIT_W, CIT_H,
        "Citizens & Communities", "", LIGHT, DARK)

    # ── Layer 2: Interfaces ────────────────────────────────────────────────────
    IFACE_Y, IFACE_H, IFACE_W = 5.0, 0.9, 3.4
    box(ax, 1.2, IFACE_Y, IFACE_W, IFACE_H,
        "Website", "Public Transparency", GOLD, WHITE)
    box(ax, 5.8, IFACE_Y, IFACE_W, IFACE_H,
        "iOS / macOS App", "Daily Governance", GOLD, WHITE)

    # ── Layer 3: Five Innovations container ────────────────────────────────────
    CONT_X, CONT_Y, CONT_W, CONT_H = 0.8, 2.2, 9.4, 2.0
    container = FancyBboxPatch(
        (CONT_X, CONT_Y), CONT_W, CONT_H,
        boxstyle="round,pad=0.12",
        facecolor=CONTAINER_BG,
        edgecolor=GREEN,
        linestyle="--",
        linewidth=2,
        zorder=Z_CONTAINER,
    )
    ax.add_patch(container)

    ax.text(
        CX, CONT_Y + CONT_H - 0.22,
        "Five Innovations \u2014 Core Protocol",
        fontsize=12, fontweight="bold", color=GREEN,
        ha="center", va="center", zorder=Z_TEXT,
    )

    INN_GAP = 0.3
    INN_W_TOP, INN_H_TOP = 2.3, 0.72
    INN_W_BOT, INN_H_BOT = 2.55, 0.58
    TOP_Y, BOT_Y = 3.05, 2.38

    top_span = 3 * INN_W_TOP + 2 * INN_GAP
    top_x0 = CONT_X + (CONT_W - top_span) / 2
    _place_row(ax, INNOVATIONS_TOP, top_x0, TOP_Y, INN_W_TOP, INN_H_TOP, INN_GAP)

    bot_span = 2 * INN_W_BOT + INN_GAP
    bot_x0 = CONT_X + (CONT_W - bot_span) / 2
    _place_row(ax, INNOVATIONS_BOTTOM, bot_x0, BOT_Y, INN_W_BOT, INN_H_BOT, INN_GAP)

    # ── Layer 4: PLNN ────────────────────────────────────────────────────────
    PLNN_Y, PLNN_H, PLNN_W = 0.8, 0.7, 6.0
    box(ax, CX - PLNN_W / 2, PLNN_Y, PLNN_W, PLNN_H, "PLNN",
        "Data Sovereignty \u00b7 Offline-First \u00b7 Nested Nodes", GREEN, WHITE)

    # ── Layer arrows with labels ─────────────────────────────────────────────
    interfaces_top = IFACE_Y + IFACE_H
    innovations_top = CONT_Y + CONT_H
    plnn_top = PLNN_Y + PLNN_H

    arrows_data = [
        (CX, CIT_Y, CX, interfaces_top, "Engages"),
        (CX, IFACE_Y, CX, innovations_top, "Governs"),
        (CX, CONT_Y, CX, plnn_top, "Stores"),
    ]
    for x1, y1, x2, y2, label in arrows_data:
        add_arrow(ax, x1, y1, x2, y2, label)

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.text(CX, 0.2, "SITA Foundation \u00b7 qumanity.in",
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
