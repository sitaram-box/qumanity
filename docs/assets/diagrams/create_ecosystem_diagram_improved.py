#!/usr/bin/env python3
"""Generate polished, publication-ready Qumanity Ecosystem Overview diagram."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Rectangle

# ── Colour palette ───────────────────────────────────────────────────────────
SITA_GREEN = "#2D5016"
SITA_GREEN_LIGHT = "#4a7a3a"
DEEP_GREEN = "#1a3a0a"
MUTED_GOLD = "#C9A84C"
DEEP_GOLD = "#b8942a"
DARK_TEXT = "#2d2d2d"
WHITE = "#FFFFFF"
OFF_WHITE = "#f8faf8"
LIGHT_GRAY = "#F5F5F5"
SHADOW = "#00000018"

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]
IMAGES_DIR = ASSETS_DIR / "images"
PDF_PATH = IMAGES_DIR / "ecosystem_diagram_improved.pdf"
PNG_PATH = IMAGES_DIR / "ecosystem_diagram_improved.png"

FONT_STACK = ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"]


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": FONT_STACK,
            "figure.dpi": 100,
        }
    )


def draw_gradient_background(ax) -> None:
    """Subtle vertical gradient: light green → off-white."""
    gradient = np.linspace(0, 1, 512).reshape(-1, 1)
    cmap = LinearSegmentedColormap.from_list(
        "qumanity_bg",
        ["#eef4ea", OFF_WHITE, WHITE],
        N=256,
    )
    ax.imshow(
        gradient,
        aspect="auto",
        cmap=cmap,
        extent=[0, 1, 0, 1],
        origin="lower",
        zorder=0,
        alpha=0.95,
    )


def draw_decorative_border(ax) -> None:
    """Thin elegant outer border."""
    border = Rectangle(
        (0.02, 0.04),
        0.96,
        0.92,
        linewidth=1.5,
        edgecolor=MUTED_GOLD,
        facecolor="none",
        linestyle="-",
        zorder=1,
    )
    ax.add_patch(border)
    inner = Rectangle(
        (0.025, 0.045),
        0.95,
        0.91,
        linewidth=0.8,
        edgecolor=SITA_GREEN,
        facecolor="none",
        linestyle="-",
        alpha=0.35,
        zorder=1,
    )
    ax.add_patch(inner)


def shadow_box(
    ax,
    xy: tuple[float, float],
    width: float,
    height: float,
    *,
    offset: tuple[float, float] = (0.006, -0.006),
    rounding: float = 0.018,
    zorder: int = 2,
) -> None:
    """Drop shadow behind a rounded box."""
    x, y = xy
    ox, oy = offset
    shadow = FancyBboxPatch(
        (x + ox, y + oy),
        width,
        height,
        boxstyle=f"round,pad=0.01,rounding_size={rounding}",
        linewidth=0,
        facecolor="#000000",
        alpha=0.12,
        zorder=zorder,
    )
    ax.add_patch(shadow)


def rounded_box(
    ax,
    xy: tuple[float, float],
    width: float,
    height: float,
    *,
    facecolor: str,
    edgecolor: str,
    linewidth: float = 2.5,
    rounding: float = 0.018,
    zorder: int = 3,
    shadow: bool = True,
) -> FancyBboxPatch:
    x, y = xy
    if shadow:
        shadow_box(ax, xy, width, height, rounding=rounding, zorder=zorder - 1)
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad=0.01,rounding_size={rounding}",
        linewidth=linewidth,
        edgecolor=edgecolor,
        facecolor=facecolor,
        zorder=zorder,
    )
    ax.add_patch(box)
    return box


def icon_badge(
    ax,
    x: float,
    y: float,
    letter: str,
    *,
    radius: float = 0.018,
    facecolor: str = SITA_GREEN,
    edgecolor: str = MUTED_GOLD,
    textcolor: str = WHITE,
    fontsize: float = 10,
    zorder: int = 5,
) -> None:
    """Small circular icon badge with a single letter or symbol."""
    circle = Circle(
        (x, y),
        radius,
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.8,
        zorder=zorder,
    )
    ax.add_patch(circle)
    ax.text(
        x, y, letter,
        ha="center", va="center",
        fontsize=fontsize, fontweight="bold",
        color=textcolor, zorder=zorder + 1,
    )


def box_text(
    ax,
    x: float,
    y: float,
    lines: list[tuple[str, float, str, str]],
    *,
    zorder: int = 4,
    line_spacing: float = 1.25,
) -> None:
    """Render stacked text lines: (text, fontsize, weight, color)."""
    n = len(lines)
    total_offset = (n - 1) * 0.012
    for i, (text, size, weight, color) in enumerate(lines):
        y_pos = y + total_offset / 2 - i * 0.024
        ax.text(
            x, y_pos, text,
            ha="center", va="center",
            fontsize=size, fontweight=weight,
            color=color, zorder=zorder,
            linespacing=line_spacing,
        )


def draw_arrow(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    label: str | None = None,
    rad: float = 0.0,
    color: str = DEEP_GOLD,
    linewidth: float = 2.8,
    zorder: int = 2,
) -> None:
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=18,
        linewidth=linewidth,
        color=color,
        connectionstyle=f"arc3,rad={rad}",
        zorder=zorder,
        shrinkA=2,
        shrinkB=2,
    )
    ax.add_patch(arrow)
    if label:
        mx = (start[0] + end[0]) / 2 + rad * 0.04
        my = (start[1] + end[1]) / 2 + 0.012
        ax.text(
            mx,
            my,
            label,
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            color=SITA_GREEN,
            zorder=zorder + 1,
            bbox=dict(
                boxstyle="round,pad=0.2",
                facecolor=WHITE,
                edgecolor=MUTED_GOLD,
                linewidth=0.8,
                alpha=0.92,
            ),
        )


def draw_title_block(ax) -> None:
    """Branded title area with decorative rule."""
    # Brand mark (circular logo placeholder)
    logo = plt.Circle((0.085, 0.93), 0.028, facecolor=SITA_GREEN, edgecolor=MUTED_GOLD, linewidth=2.5, zorder=5)
    ax.add_patch(logo)
    ax.text(0.085, 0.93, "Q", ha="center", va="center", fontsize=18, fontweight="bold", color=WHITE, zorder=6)

    ax.text(
        0.5,
        0.955,
        "Qumanity Ecosystem Overview",
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        color=SITA_GREEN,
        zorder=5,
    )
    ax.text(
        0.5,
        0.918,
        "A Quantum-Informed Governance Protocol",
        ha="center",
        va="center",
        fontsize=12,
        fontweight="medium",
        color=SITA_GREEN_LIGHT,
        zorder=5,
    )
    # Decorative line
    ax.plot([0.22, 0.78], [0.895, 0.895], color=MUTED_GOLD, linewidth=2.2, solid_capstyle="round", zorder=5)
    ax.plot([0.35, 0.65], [0.888, 0.888], color=SITA_GREEN, linewidth=0.8, alpha=0.5, zorder=5)


def create_diagram() -> plt.Figure:
    setup_style()
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    draw_gradient_background(ax)
    draw_decorative_border(ax)
    draw_title_block(ax)

    # ── Layer 1: Citizens ────────────────────────────────────────────────────
    cw, ch = 0.32, 0.085
    cx, cy = 0.5 - cw / 2, 0.78
    rounded_box(ax, (cx, cy), cw, ch, facecolor=LIGHT_GRAY, edgecolor=SITA_GREEN, linewidth=3)
    icon_badge(ax, 0.5, cy + ch / 2 + 0.028, "C", facecolor=SITA_GREEN, fontsize=9)
    box_text(ax, 0.5, cy + ch / 2 - 0.002,
             [("Citizens & Communities", 12, "bold", DARK_TEXT)])
    box_text(ax, 0.5, cy + ch / 2 - 0.028,
             [("Villages · Towns · Nations", 9, "normal", SITA_GREEN_LIGHT)])

    # ── Layer 2: Two Interfaces ──────────────────────────────────────────────
    iy, ih, iw = 0.62, 0.095, 0.30
    gap = 0.05
    wx = 0.5 - iw - gap / 2
    ax_x = 0.5 + gap / 2

    ax.text(0.5, iy + ih + 0.028, "Two Interfaces", ha="center", va="bottom",
            fontsize=11, fontweight="bold", color=DEEP_GOLD, zorder=5)

    rounded_box(ax, (wx, iy), iw, ih, facecolor=MUTED_GOLD, edgecolor=DEEP_GOLD, linewidth=2.5)
    icon_badge(ax, wx + iw / 2, iy + ih / 2 + 0.028, "W", facecolor=DEEP_GOLD, edgecolor=WHITE, fontsize=9)
    box_text(ax, wx + iw / 2, iy + ih / 2 + 0.002,
             [("Website", 11, "bold", WHITE),
              ("qumanity.in", 9, "bold", WHITE),
              ("Public Transparency", 8, "normal", "#fff8e7")])

    rounded_box(ax, (ax_x, iy), iw, ih, facecolor=MUTED_GOLD, edgecolor=DEEP_GOLD, linewidth=2.5)
    icon_badge(ax, ax_x + iw / 2, iy + ih / 2 + 0.028, "A", facecolor=DEEP_GOLD, edgecolor=WHITE, fontsize=9)
    box_text(ax, ax_x + iw / 2, iy + ih / 2 - 0.005,
             [("iOS / macOS App", 11, "bold", WHITE),
              ("Daily Governance", 8, "normal", "#fff8e7")])

    # ── Layer 3: Five Innovations ────────────────────────────────────────────
    core_x, core_y, core_w, core_h = 0.07, 0.33, 0.86, 0.21
    shadow_box(ax, (core_x, core_y), core_w, core_h, rounding=0.022, zorder=2)
    core_container = FancyBboxPatch(
        (core_x, core_y), core_w, core_h,
        boxstyle="round,pad=0.012,rounding_size=0.022",
        linewidth=3, edgecolor=MUTED_GOLD, facecolor=SITA_GREEN, zorder=3,
    )
    ax.add_patch(core_container)
    ax.text(0.5, core_y + core_h - 0.028, "Five Innovations — Core Protocol",
            ha="center", va="top", fontsize=12, fontweight="bold", color=WHITE, zorder=4)

    innovations = [
        ("T", "Four\nTimelines"),
        ("G", "Nested\nGovernance"),
        ("I", "Dual-Key\nIdentity"),
        ("K", "Karma Points\nLedger"),
        ("Z", "Zodiac\nElections"),
    ]
    inn_w, inn_h = 0.138, 0.105
    inn_y = core_y + 0.038
    total = len(innovations) * inn_w + (len(innovations) - 1) * 0.022
    sx = 0.5 - total / 2

    for i, (badge, label) in enumerate(innovations):
        x = sx + i * (inn_w + 0.022)
        rounded_box(ax, (x, inn_y), inn_w, inn_h,
                    facecolor=WHITE, edgecolor=MUTED_GOLD, linewidth=2, shadow=True)
        icon_badge(ax, x + inn_w / 2, inn_y + inn_h / 2 + 0.024, badge,
                   facecolor=SITA_GREEN, fontsize=8, radius=0.016)
        box_text(ax, x + inn_w / 2, inn_y + inn_h / 2 - 0.018,
                 [(label, 8.5, "bold", SITA_GREEN)])

    # ── Layer 4: PLNN ────────────────────────────────────────────────────────
    px, py, pw, ph = 0.1, 0.09, 0.8, 0.17
    shadow_box(ax, (px, py), pw, ph, rounding=0.022, zorder=2)
    plnn_container = FancyBboxPatch(
        (px, py), pw, ph,
        boxstyle="round,pad=0.012,rounding_size=0.022",
        linewidth=3, edgecolor=MUTED_GOLD, facecolor=DEEP_GREEN, zorder=3,
    )
    ax.add_patch(plnn_container)
    ax.text(0.5, py + ph - 0.025, "Planetary Ledger Node Network (PLNN)",
            ha="center", va="top", fontsize=11, fontweight="bold", color=WHITE, zorder=4)

    plnn_items = [
        ("S", "Data\nSovereignty", 0.20),
        ("O", "Offline-\nFirst", 0.50),
        ("N", "Nested\nNodes", 0.80),
    ]
    pbw, pbh = 0.19, 0.085
    pby = py + 0.035

    for badge, label, center in plnn_items:
        x = center - pbw / 2
        rounded_box(ax, (x, pby), pbw, pbh,
                    facecolor=SITA_GREEN_LIGHT, edgecolor=MUTED_GOLD, linewidth=2, shadow=True)
        icon_badge(ax, center, pby + pbh / 2 + 0.016, badge,
                   facecolor=DEEP_GREEN, edgecolor=MUTED_GOLD, fontsize=8, radius=0.015)
        box_text(ax, center, pby + pbh / 2 - 0.018, [(label, 8.5, "bold", WHITE)])

    # ── Arrows with labels ───────────────────────────────────────────────────
    draw_arrow(ax, (0.5, cy), (wx + iw / 2, iy + ih), label="Engages", rad=-0.12)
    draw_arrow(ax, (0.5, cy), (ax_x + iw / 2, iy + ih), label="Engages", rad=0.12)

    draw_arrow(ax, (wx + iw / 2, iy), (0.35, core_y + core_h), label="Governs", rad=0.08)
    draw_arrow(ax, (ax_x + iw / 2, iy), (0.65, core_y + core_h), label="Governs", rad=-0.08)

    draw_arrow(ax, (0.5, core_y), (0.5, py + ph), label="Stores", rad=0.0, linewidth=3.2)

    # ── Layer rail labels ────────────────────────────────────────────────────
    rails = [(0.825, "CITIZENS"), (0.665, "INTERFACES"), (0.435, "PROTOCOL"), (0.175, "PLNN")]
    for y_pos, label in rails:
        ax.text(0.038, y_pos, label, ha="center", va="center", fontsize=7.5,
                fontweight="bold", color=SITA_GREEN, rotation=90, alpha=0.55, zorder=4)

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.plot([0.3, 0.7], [0.062, 0.062], color=MUTED_GOLD, linewidth=0.8, alpha=0.6, zorder=5)
    ax.text(0.5, 0.048, "SITA Foundation · qumanity.in", ha="center", va="center",
            fontsize=9, fontweight="medium", color=SITA_GREEN_LIGHT, zorder=5)

    fig.tight_layout(pad=0.6)
    return fig


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    fig = create_diagram()

    save_kw = dict(bbox_inches="tight", facecolor=OFF_WHITE, edgecolor="none")
    fig.savefig(PDF_PATH, format="pdf", **save_kw)
    fig.savefig(PNG_PATH, format="png", dpi=300, **save_kw)
    plt.close(fig)

    print(f"Saved PDF: {PDF_PATH}")
    print(f"Saved PNG: {PNG_PATH} ({PNG_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
