#!/usr/bin/env python3
"""
Generate docs/_static/logo.svg (and optionally logo.png via cairosvg).

Design
------
Four flat-color Gantt bars cascade top-left to bottom-right.
The bar group is centered horizontally and vertically in the canvas.
Curly braces { } are placed with IDENTICAL padding on each side of the bar
group edges — { is right-aligned to (bars_left - BRACE_PAD),
} is left-aligned to (bars_right + BRACE_PAD).

Run from the repo root:
    python docs/make_logo.py
"""
from __future__ import annotations

from pathlib import Path

# ── design tokens ─────────────────────────────────────────────────────────────
CANVAS_W = 300
CANVAS_H = 240
BG       = "#0d1117"

COLORS = ["#4ecdc4", "#ff6b6b", "#58a4b0", "#ffb347"]

BAR_H       = 22    # px  bar height
BAR_GAP     = 9     # px  vertical gap between bars
STEP_X      = 21    # px  each bar starts this many px further right than the one above
WIDTHS      = [84, 78, 72, 66]  # bar widths, narrowing per row

BRACE_FONT_SIZE = 52           # px
BRACE_COLOR     = "#58a4b0"
BRACE_OPACITY   = "0.55"
BRACE_PAD       = 8            # px  gap between brace text-anchor x and nearest bar edge

# ── derived geometry ──────────────────────────────────────────────────────────
N = len(COLORS)

# Bar x positions — group centered in canvas
rel_x      = [i * STEP_X for i in range(N)]
group_w    = max(rel_x[i] + WIDTHS[i] for i in range(N))  # total bar group width
bars_left  = (CANVAS_W - group_w) / 2
bars_right = bars_left + group_w
abs_x      = [bars_left + rel_x[i] for i in range(N)]

# Bar y positions — stack centered in canvas
row_step   = BAR_H + BAR_GAP
stack_h    = (N - 1) * row_step + BAR_H
bars_top   = (CANVAS_H - stack_h) / 2
abs_y      = [bars_top + i * row_step for i in range(N)]
brace_y    = bars_top + stack_h / 2   # vertical midpoint for brace alignment

# Brace anchor x — identical padding from bar group edges
brace_l_x  = bars_left  - BRACE_PAD  # { is right-aligned (text-anchor="end")   to this x
brace_r_x  = bars_right + BRACE_PAD  # } is left-aligned  (text-anchor="start") to this x

# ── build SVG ─────────────────────────────────────────────────────────────────
bar_rects = "\n  ".join(
    f'<rect x="{abs_x[i]:.2f}" y="{abs_y[i]:.2f}" '
    f'width="{WIDTHS[i]}" height="{BAR_H}" '
    f'fill="{COLORS[i]}" opacity="0.92"/>'
    for i in range(N)
)

svg = f"""\
<?xml version="1.0" encoding="utf-8"?>
<svg xmlns="http://www.w3.org/2000/svg"
     viewBox="0 0 {CANVAS_W} {CANVAS_H}"
     width="{CANVAS_W}" height="{CANVAS_H}">
  <!-- background -->
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{BG}"/>
  <!-- bars: left={bars_left:.2f} right={bars_right:.2f} (centered in {CANVAS_W}px canvas) -->
  {bar_rects}
  <!-- braces: both {BRACE_PAD}px from bar group edge, vertically centred at y={brace_y:.2f} -->
  <text x="{brace_l_x:.2f}" y="{brace_y:.2f}"
        font-family="monospace" font-size="{BRACE_FONT_SIZE}"
        fill="{BRACE_COLOR}" opacity="{BRACE_OPACITY}"
        text-anchor="end" dominant-baseline="middle">{{</text>
  <text x="{brace_r_x:.2f}" y="{brace_y:.2f}"
        font-family="monospace" font-size="{BRACE_FONT_SIZE}"
        fill="{BRACE_COLOR}" opacity="{BRACE_OPACITY}"
        text-anchor="start" dominant-baseline="middle">}}</text>
</svg>
"""

# ── write SVG ─────────────────────────────────────────────────────────────────
OUT = Path(__file__).parent / "_static"
OUT.mkdir(parents=True, exist_ok=True)

svg_path = OUT / "logo.svg"
svg_path.write_text(svg, encoding="utf-8")
print(f"  {svg_path.relative_to(Path(__file__).parent)}")

# PNG via rsvg-convert (part of librsvg, installed via `brew install librsvg`)
import subprocess, shutil
png_path = OUT / "logo.png"
if shutil.which("rsvg-convert"):
    subprocess.run(
        ["rsvg-convert", "-w", "600", "-h", "480", str(svg_path), "-o", str(png_path)],
        check=True,
    )
    print(f"  {png_path.relative_to(Path(__file__).parent)}")
else:
    print("  (rsvg-convert not found — install with `brew install librsvg` for PNG output)")

print("Done.")
