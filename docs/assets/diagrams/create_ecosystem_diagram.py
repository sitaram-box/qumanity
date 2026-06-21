#!/usr/bin/env python3
"""Generate publication-ready Qumanity Ecosystem Overview diagram."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# ── Colour palette ───────────────────────────────────────────────────────────
SITA_GREEN = "#2D5016"
SITA_GREEN_DARK = "#1a3009"
MUTED_GOLD = "#C9A84C"
MUTED_GOLD_DARK = "#8a7334"
DARK_GRAY = "#333333"
LIGHT_GRAY = "#F5F5F5"
WHITE = "#FFFFFF"
ARROW_COLOR = "#475569"

# ── Paths ────────────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).resolve().parents[1]  # docs/assets
IMAGES_DIR = ASSETS_DIR / "images"
PDF_PATH = IMAGES_DIR / "ecosystem_diagram.pdf"
PNG_PATH = IMAGES_DIR / "ecosystem_diagram.png"


def rounded_box(
    ax,
    xy: tuple[float, float],
    width: float,
    height: float,
    text: str,
    *,
    facecolor: str,
    edgecolor: str,
    textcolor: str = DARK_GRAY,
    fontsize: float = 11,
    fontweight: str = "normal",
    linewidth: float = 2.0,
    rounding: float = 0.02,
    ha: str = "center",
    va: str = "center",
    zorder: int = 2,
) -> FancyBboxPatch:
    """Draw a rounded rectangle with centred text."""
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle=f"round,pad=0.012,rounding_size={rounding}",
        linewidth=linewidth,
        edgecolor=edgecolor,
        facecolor=facecolor,
        zorder=zorder,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2,
        y + height / 2,
        text,
        ha=ha,
        va=va,
        fontsize=fontsize,
        fontweight=fontweight,
        color=textcolor,
        zorder=zorder + 1,
        linespacing=1.35,
    )
    return box


def container_box(
    ax,
    xy: tuple[float, float],
    width: float,
    height: float,
    label: str,
    *,
    facecolor: str,
    edgecolor: str,
    label_color: str = DARK_GRAY,
    linewidth: float = 2.0,
    zorder: int = 1,
) -> FancyBboxPatch:
    """Draw a labelled container rectangle."""
    x, y = xy
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.015,rounding_size=0.025",
        linewidth=linewidth,
        edgecolor=edgecolor,
        facecolor=facecolor,
        alpha=0.15 if facecolor == SITA_GREEN else 0.25,
        zorder=zorder,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2,
        y + height - 0.035,
        label,
        ha="center",
        va="top",
        fontsize=12,
        fontweight="bold",
        color=label_color,
        zorder=zorder + 1,
    )
    return box


def draw_arrow(
    ax,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    rad: float = 0.0,
    zorder: int = 0,
) -> None:
    """Draw a styled connection arrow."""
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle="-|>",
        mutation_scale=14,
        linewidth=1.8,
        color=ARROW_COLOR,
        connectionstyle=f"arc3,rad={rad}",
        zorder=zorder,
    )
    ax.add_patch(arrow)


def create_diagram() -> plt.Figure:
    """Build the Qumanity Ecosystem Overview figure."""
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
            "figure.dpi": 100,
        }
    )

    fig, ax = plt.subplots(figsize=(14, 11))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # ── Title ────────────────────────────────────────────────────────────────
    ax.text(
        0.5,
        0.97,
        "Qumanity Ecosystem Overview",
        ha="center",
        va="top",
        fontsize=22,
        fontweight="bold",
        color=SITA_GREEN,
    )
    ax.text(
        0.5,
        0.935,
        "Citizens → Interfaces → Core Protocol → PLNN Data Infrastructure",
        ha="center",
        va="top",
        fontsize=11,
        color=DARK_GRAY,
        style="italic",
    )

    # ── Layer 1: Citizens & Communities ──────────────────────────────────────
    citizens_w, citizens_h = 0.36, 0.07
    citizens_x = 0.5 - citizens_w / 2
    citizens_y = 0.84
    rounded_box(
        ax,
        (citizens_x, citizens_y),
        citizens_w,
        citizens_h,
        "Citizens & Communities",
        facecolor=LIGHT_GRAY,
        edgecolor=SITA_GREEN,
        textcolor=DARK_GRAY,
        fontsize=13,
        fontweight="bold",
        linewidth=2.5,
    )

    # ── Layer 2: Two Interfaces ──────────────────────────────────────────────
    iface_y = 0.68
    iface_h = 0.09
    iface_w = 0.34
    gap = 0.06
    web_x = 0.5 - iface_w - gap / 2
    app_x = 0.5 + gap / 2

    ax.text(
        0.5,
        iface_y + iface_h + 0.045,
        "Two Interfaces",
        ha="center",
        va="bottom",
        fontsize=12,
        fontweight="bold",
        color=MUTED_GOLD_DARK,
    )

    rounded_box(
        ax,
        (web_x, iface_y),
        iface_w,
        iface_h,
        "Website (qumanity.in)\nPublic Transparency",
        facecolor="#fdfaf3",
        edgecolor=MUTED_GOLD,
        textcolor=DARK_GRAY,
        fontsize=11,
        fontweight="bold",
        linewidth=2.0,
    )
    rounded_box(
        ax,
        (app_x, iface_y),
        iface_w,
        iface_h,
        "iOS / macOS App\nDaily Governance",
        facecolor="#fdfaf3",
        edgecolor=MUTED_GOLD,
        textcolor=DARK_GRAY,
        fontsize=11,
        fontweight="bold",
        linewidth=2.0,
    )

    # ── Layer 3: Five Innovations ────────────────────────────────────────────
    core_x, core_y = 0.06, 0.38
    core_w, core_h = 0.88, 0.22

    container_box(
        ax,
        (core_x, core_y),
        core_w,
        core_h,
        "Five Innovations — Core Protocol",
        facecolor=SITA_GREEN,
        edgecolor=SITA_GREEN,
        label_color=SITA_GREEN,
        linewidth=2.5,
    )

    innovations = [
        "Four\nTimelines",
        "Nested\nGovernance",
        "Dual-Key\nIdentity",
        "Karma Points\nLedger",
        "Zodiac\nElections",
    ]
    inn_w = 0.145
    inn_h = 0.11
    inn_y = core_y + 0.045
    total_w = len(innovations) * inn_w + (len(innovations) - 1) * 0.025
    start_x = 0.5 - total_w / 2

    inn_centers: list[float] = []
    for i, label in enumerate(innovations):
        x = start_x + i * (inn_w + 0.025)
        rounded_box(
            ax,
            (x, inn_y),
            inn_w,
            inn_h,
            label,
            facecolor=SITA_GREEN,
            edgecolor=SITA_GREEN_DARK,
            textcolor=WHITE,
            fontsize=10,
            fontweight="bold",
            linewidth=1.5,
            rounding=0.015,
        )
        inn_centers.append(x + inn_w / 2)

    # ── Layer 4: PLNN ────────────────────────────────────────────────────────
    plnn_x, plnn_y = 0.1, 0.12
    plnn_w, plnn_h = 0.8, 0.18

    container_box(
        ax,
        (plnn_x, plnn_y),
        plnn_w,
        plnn_h,
        "Planetary Ledger Node Network (PLNN)",
        facecolor=SITA_GREEN,
        edgecolor=MUTED_GOLD,
        label_color=SITA_GREEN,
        linewidth=2.5,
    )

    plnn_items = [
        ("Data\nSovereignty", 0.19),
        ("Offline-\nFirst", 0.50),
        ("Nested\nNodes", 0.81),
    ]
    plnn_box_w, plnn_box_h = 0.2, 0.09
    plnn_box_y = plnn_y + 0.04

    plnn_centers: list[float] = []
    for label, cx in plnn_items:
        x = cx - plnn_box_w / 2
        rounded_box(
            ax,
            (x, plnn_box_y),
            plnn_box_w,
            plnn_box_h,
            label,
            facecolor="#d4e0d0",
            edgecolor=SITA_GREEN,
            textcolor=SITA_GREEN,
            fontsize=10,
            fontweight="bold",
            linewidth=2.0,
            rounding=0.015,
        )
        plnn_centers.append(cx)

    # ── Arrows: Citizens → Interfaces ────────────────────────────────────────
    citizens_bottom = (0.5, citizens_y)
    web_top = (web_x + iface_w / 2, iface_y + iface_h)
    app_top = (app_x + iface_w / 2, iface_y + iface_h)
    draw_arrow(ax, citizens_bottom, web_top, rad=-0.08)
    draw_arrow(ax, citizens_bottom, app_top, rad=0.08)

    # ── Arrows: Interfaces → Core Protocol ───────────────────────────────────
    web_bottom = (web_x + iface_w / 2, iface_y)
    app_bottom = (app_x + iface_w / 2, iface_y)
    core_top_left = (0.32, core_y + core_h)
    core_top_right = (0.68, core_y + core_h)
    core_top_center = (0.5, core_y + core_h)
    draw_arrow(ax, web_bottom, core_top_left, rad=0.05)
    draw_arrow(ax, app_bottom, core_top_right, rad=-0.05)

    # ── Arrows: Core Protocol → PLNN ─────────────────────────────────────────
    core_bottom = (0.5, core_y)
    plnn_top = (0.5, plnn_y + plnn_h)
    draw_arrow(ax, core_bottom, plnn_top)

    # Subtle arrows from innovations to PLNN items
    for inn_cx in [inn_centers[0], inn_centers[2], inn_centers[4]]:
        draw_arrow(
            ax,
            (inn_cx, inn_y),
            (inn_cx, plnn_y + plnn_h + 0.01),
            rad=0.0,
            zorder=0,
        )

    # ── Layer labels (left margin) ───────────────────────────────────────────
    layer_labels = [
        (0.91, "Citizens"),
        (0.725, "Interfaces"),
        (0.49, "Core Protocol"),
        (0.21, "PLNN"),
    ]
    for y_pos, label in layer_labels:
        ax.text(
            0.02,
            y_pos,
            label,
            ha="left",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=ARROW_COLOR,
            rotation=90,
        )

    # ── Footer ───────────────────────────────────────────────────────────────
    ax.text(
        0.5,
        0.03,
        "SITA Foundation · Qumanity White Paper · June 2026",
        ha="center",
        va="bottom",
        fontsize=9,
        color=ARROW_COLOR,
    )

    fig.tight_layout(pad=1.2)
    return fig


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    fig = create_diagram()

    fig.savefig(
        PDF_PATH,
        format="pdf",
        bbox_inches="tight",
        facecolor=WHITE,
        edgecolor="none",
    )
    fig.savefig(
        PNG_PATH,
        format="png",
        dpi=300,
        bbox_inches="tight",
        facecolor=WHITE,
        edgecolor="none",
    )
    plt.close(fig)

    print(f"Saved PDF: {PDF_PATH}")
    print(f"Saved PNG: {PNG_PATH} ({PNG_PATH.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
