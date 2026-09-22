"""Generate three publication-quality SVG visualizations for the AI Agent Evaluation Lab."""

import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

OUT = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)
FACT_SHEET = Path(OUT) / "article_fact_sheet.md"


def save_svg(fig, path):
    """Save deterministic SVG text without generator-added trailing spaces."""
    fig.savefig(path, format="svg", bbox_inches="tight", metadata={"Date": None})
    svg_path = Path(path)
    normalized = "\n".join(
        line.rstrip() for line in svg_path.read_text(encoding="utf-8").splitlines()
    )
    svg_path.write_text(normalized + "\n", encoding="utf-8", newline="\n")


def canonical_results():
    """Read plotted rates from the authoritative publication fact sheet."""
    source = FACT_SHEET.read_text(encoding="utf-8")
    strict_start = source.index("### Strict deterministic acceptance")
    structural_start = source.index("### Structural response quality", strict_start)
    gap_start = source.index("### Gap between structural and strict", structural_start)
    strict_section = source[strict_start:structural_start]
    structural_section = source[structural_start:gap_start]

    def read_rows(section, pattern, denominator=False):
        parsed = {}
        for split in ("TEST", "HOLDOUT"):
            line = next(
                row for row in section.splitlines() if row.strip().startswith(f"| **{split}** |")
            )
            matches = re.findall(pattern, line)
            values = {}
            for match in matches:
                config = match[0]
                values[config] = (
                    100 * int(match[1]) / int(match[2]) if denominator else float(match[1])
                )
            if set(values) != {"H0", "H1", "S0", "S1"}:
                raise ValueError(f"Fact sheet is missing a {split} result")
            parsed[split] = values
        return parsed

    strict = read_rows(strict_section, r"([HS][01]):\s*(\d+)/(\d+)", denominator=True)
    structural = read_rows(structural_section, r"([HS][01]):\s*(\d+(?:\.\d+)?)%")
    return {"strict": strict, "structural": structural}


RESULTS = canonical_results()

# -- Shared style ----------------------------------------------------------
COLORS = {
    "train": "#4A7FB5",
    "test": "#D4646C",
    "holdout": "#7A7A7A",
    "test_bar": "#5B8DBE",
    "holdout_bar": "#2D3E50",
    "structural": "#5B8DBE",
    "strict": "#D4646C",
    "arrow": "#555555",
    "bg": "#FAFAFA",
    "border": "#CCCCCC",
    "text": "#333333",
    "muted": "#888888",
}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 10,
        "axes.titlesize": 13,
        "axes.labelsize": 11,
        "axes.edgecolor": COLORS["border"],
        "axes.linewidth": 0.6,
        "xtick.color": COLORS["text"],
        "ytick.color": COLORS["text"],
        "text.color": COLORS["text"],
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "svg.hashsalt": "agent-evaluation-lab",
    }
)


# ==========================================================================
# Visual A — Evaluation Lifecycle
# ==========================================================================
def visual_a():
    fig, ax = plt.subplots(figsize=(7, 3.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    # Stage boxes
    stages = [
        {
            "x": 0.3,
            "w": 2.8,
            "label": "TRAIN",
            "color": COLORS["train"],
            "lines": ["12 questions", "Haiku-guided dev", "2 checkpoints", "REGRESSION (6 q.)"],
        },
        {
            "x": 3.6,
            "w": 2.8,
            "label": "TEST",
            "color": COLORS["test"],
            "lines": ["10 sealed questions", "4 frozen configs", "Canonical compare()"],
        },
        {
            "x": 6.9,
            "w": 2.8,
            "label": "HOLDOUT",
            "color": COLORS["holdout"],
            "lines": [
                "6 sealed questions",
                "Confirmatory stage",
                "4 frozen configs",
                "No further changes",
            ],
        },
    ]

    box_y, box_h = 1.2, 2.8
    for s in stages:
        rect = mpatches.FancyBboxPatch(
            (s["x"], box_y),
            s["w"],
            box_h,
            boxstyle="round,pad=0.15",
            linewidth=1.2,
            edgecolor=s["color"],
            facecolor=s["color"] + "12",
        )
        ax.add_patch(rect)
        ax.text(
            s["x"] + s["w"] / 2,
            box_y + box_h - 0.35,
            s["label"],
            ha="center",
            va="top",
            fontsize=12,
            fontweight="bold",
            color=s["color"],
        )
        for i, line in enumerate(s["lines"]):
            ax.text(
                s["x"] + s["w"] / 2,
                box_y + box_h - 0.85 - i * 0.45,
                line,
                ha="center",
                va="top",
                fontsize=8.5,
                color=COLORS["text"],
            )

    # Arrows between stages
    arrow_kw = dict(arrowstyle="->", color=COLORS["arrow"], lw=1.5, connectionstyle="arc3,rad=0")
    for x_start, x_end in [(3.1, 3.6), (6.4, 6.9)]:
        ax.annotate(
            "",
            xy=(x_end, box_y + box_h / 2),
            xytext=(x_start, box_y + box_h / 2),
            arrowprops=arrow_kw,
        )

    # "No backward flow" markers
    for x_pos in [3.35, 6.65]:
        ax.text(
            x_pos,
            box_y + box_h / 2 + 0.45,
            "no backward flow",
            ha="center",
            va="bottom",
            fontsize=7,
            color=COLORS["test"],
            fontstyle="italic",
        )

    # Title
    ax.text(
        5,
        4.6,
        "Evaluation Lifecycle",
        ha="center",
        va="center",
        fontsize=14,
        fontweight="bold",
        color=COLORS["text"],
    )

    # Seal note
    ax.text(
        5,
        0.55,
        "Procedurally sealed — not independently blinded.",
        ha="center",
        va="center",
        fontsize=7.5,
        color=COLORS["muted"],
        fontstyle="italic",
        bbox=dict(
            boxstyle="round,pad=0.3",
            facecolor="#F5F5F5",
            edgecolor=COLORS["border"],
            lw=0.5,
        ),
    )

    # Left-to-right flow label
    ax.annotate(
        "",
        xy=(9.3, 0.15),
        xytext=(0.7, 0.15),
        arrowprops=dict(arrowstyle="->", color=COLORS["muted"], lw=0.8, ls="--"),
    )
    ax.text(5, 0.05, "information flow", ha="center", va="top", fontsize=7, color=COLORS["muted"])

    path = os.path.join(OUT, "visual_a_lifecycle.svg")
    save_svg(fig, path)
    plt.close(fig)
    print(f"Saved {path}")


# ==========================================================================
# Visual B — Structural Quality Grouped Bar Chart
# ==========================================================================
def visual_b():
    configs = ["H0", "H1", "S0", "S1"]
    test_vals = [RESULTS["structural"]["TEST"][name] for name in configs]
    holdout_vals = [RESULTS["structural"]["HOLDOUT"][name] for name in configs]

    x = np.arange(len(configs))
    bar_w = 0.32

    fig, ax = plt.subplots(figsize=(7, 4.2))

    bars_test = ax.bar(
        x - bar_w / 2,
        test_vals,
        bar_w,
        label="TEST",
        color=COLORS["test_bar"],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    bars_hold = ax.bar(
        x + bar_w / 2,
        holdout_vals,
        bar_w,
        label="HOLDOUT",
        color=COLORS["holdout_bar"],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )

    # Value labels on bars
    for bars in [bars_test, bars_hold]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    h + 1.5,
                    f"{int(h)}%",
                    ha="center",
                    va="bottom",
                    fontsize=8.5,
                    fontweight="bold",
                    color=COLORS["text"],
                )

    ax.set_xticks(x)
    ax.set_xticklabels(configs, fontsize=11, fontweight="bold")
    ax.set_ylabel("Valid Analytical JSON (%)", fontsize=10)
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))

    # Light horizontal gridlines only
    ax.yaxis.grid(True, color="#E8E8E8", linewidth=0.5, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)

    # Remove top/right spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        loc="upper left", frameon=True, framealpha=0.9, edgecolor=COLORS["border"], fontsize=9
    )

    # Titles
    fig.text(
        0.5,
        0.97,
        "Structural Response Quality: Valid Analytical JSON",
        ha="center",
        va="top",
        fontsize=13,
        fontweight="bold",
        color=COLORS["text"],
    )
    fig.text(
        0.5,
        0.93,
        "Parseable responses matching the answer contract schema",
        ha="center",
        va="top",
        fontsize=9.5,
        color=COLORS["muted"],
    )

    # Cold-start vs improved annotations
    ax.annotate(
        "cold-start",
        xy=(0.5, 0),
        xytext=(0.5, -14),
        ha="center",
        fontsize=8,
        color=COLORS["muted"],
        fontstyle="italic",
        annotation_clip=False,
    )
    ax.annotate(
        "improved",
        xy=(2.5, 0),
        xytext=(2.5, -14),
        ha="center",
        fontsize=8,
        color=COLORS["muted"],
        fontstyle="italic",
        annotation_clip=False,
    )

    # Bracket for cold-start (H0, S0) and improved (H1, S1)
    for _xs, _xe in [(-0.5, 0.5), (0.5, 1.5)]:
        pass  # keep it clean, the label is enough

    # Annotation note
    fig.text(
        0.98,
        0.02,
        "Structural quality, not strict deterministic acceptance",
        ha="right",
        va="bottom",
        fontsize=7,
        color=COLORS["muted"],
        fontstyle="italic",
    )

    fig.subplots_adjust(top=0.88, bottom=0.12)

    path = os.path.join(OUT, "visual_b_structural_quality.svg")
    save_svg(fig, path)
    plt.close(fig)
    print(f"Saved {path}")


# ==========================================================================
# Visual C — Strict vs Structural Gap
# ==========================================================================
def visual_c():
    categories = ["TEST\n(H1 + S1 avg)", "HOLDOUT\n(H1 + S1 avg)"]
    splits = ["TEST", "HOLDOUT"]
    structural = [
        sum(RESULTS["structural"][split][config] for config in ("H1", "S1")) / 2 for split in splits
    ]
    strict = [
        sum(RESULTS["strict"][split][config] for config in ("H1", "S1")) / 2 for split in splits
    ]

    x = np.arange(len(categories))
    bar_w = 0.30

    fig, ax = plt.subplots(figsize=(7, 4.2))

    bars_struct = ax.bar(
        x - bar_w / 2,
        structural,
        bar_w,
        label="Structural quality",
        color=COLORS["structural"],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )
    bars_strict = ax.bar(
        x + bar_w / 2,
        strict,
        bar_w,
        label="Strict acceptance",
        color=COLORS["strict"],
        edgecolor="white",
        linewidth=0.5,
        zorder=3,
    )

    # Value labels
    for bars in [bars_struct, bars_strict]:
        for bar in bars:
            h = bar.get_height()
            label = f"{round(h):d}%"
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h + 1.5,
                label,
                ha="center",
                va="bottom",
                fontsize=9.5,
                fontweight="bold",
                color=COLORS["text"],
            )

    # Gap annotations with curly brace feel
    for i in range(len(categories)):
        mid_x = x[i] + 0.02
        gap = structural[i] - strict[i]
        if gap > 5:
            y_top = structural[i]
            y_bot = strict[i]
            y_mid = (y_top + y_bot) / 2
            ax.annotate(
                "",
                xy=(mid_x + 0.42, y_top - 1),
                xytext=(mid_x + 0.42, y_bot + 1),
                arrowprops=dict(arrowstyle="<->", color=COLORS["muted"], lw=1.0),
            )
            ax.text(
                mid_x + 0.55,
                y_mid,
                f"gap\n{round(gap):d}pp",
                ha="left",
                va="center",
                fontsize=7.5,
                color=COLORS["muted"],
                fontweight="bold",
            )

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=10)
    ax.set_ylabel("Rate (%)", fontsize=10)
    ax.set_ylim(0, 115)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v)}%"))

    ax.yaxis.grid(True, color="#E8E8E8", linewidth=0.5, zorder=0)
    ax.xaxis.grid(False)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.legend(
        loc="upper left", frameon=True, framealpha=0.9, edgecolor=COLORS["border"], fontsize=9
    )

    # Titles
    fig.text(
        0.5,
        0.97,
        "Structural Quality vs Strict Acceptance",
        ha="center",
        va="top",
        fontsize=13,
        fontweight="bold",
        color=COLORS["text"],
    )
    fig.text(
        0.5,
        0.93,
        "Strict acceptance requires exact columns, units, caveats, and evidence IDs",
        ha="center",
        va="top",
        fontsize=9.5,
        color=COLORS["muted"],
    )

    # Gap cause annotation box
    gap_text = "Gap caused by: column naming, unit labels, caveat handling"
    fig.text(
        0.5,
        0.03,
        gap_text,
        ha="center",
        va="bottom",
        fontsize=8,
        color=COLORS["text"],
        fontstyle="italic",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="#FFF5F5",
            edgecolor=COLORS["strict"],
            lw=0.6,
        ),
    )

    fig.subplots_adjust(top=0.88, bottom=0.13)

    path = os.path.join(OUT, "visual_c_strict_vs_structural.svg")
    save_svg(fig, path)
    plt.close(fig)
    print(f"Saved {path}")


if __name__ == "__main__":
    visual_a()
    visual_b()
    visual_c()
    print("All visuals generated.")
