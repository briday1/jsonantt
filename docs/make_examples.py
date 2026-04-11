#!/usr/bin/env python3
"""
Build all documentation example images.

Run from the repository root:
    python docs/make_examples.py

Or let Read the Docs run it automatically via the pre_build job in
.readthedocs.yaml.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

# Make sure the local package is importable when run without an install
sys.path.insert(0, str(Path(__file__).parent.parent))

from jsonantt.parser import load_chart
from jsonantt.renderer import render_burn_chart, render_chart, render_compare_chart, render_table

OUT = Path(__file__).parent / "_static" / "img"
OUT.mkdir(parents=True, exist_ok=True)

REPO_EXAMPLES = Path(__file__).parent.parent / "examples"
DOC_EXAMPLES  = Path(__file__).parent / "examples"


def render(json_path: Path, name: str, **kwargs) -> None:
    out = OUT / name
    config = load_chart(str(json_path))
    render_chart(config, str(out), dpi=150, **kwargs)
    print(f"  {out.relative_to(Path(__file__).parent)}")


print("Building documentation images …")

# ── bundled examples ──────────────────────────────────────────────────────────
render(REPO_EXAMPLES / "simple.json",       "example-simple.png")
render(REPO_EXAMPLES / "complex.json",      "example-complex.png")
render(REPO_EXAMPLES / "dependencies.json", "example-dependencies.png")

# ── targeted doc fixtures ─────────────────────────────────────────────────────
render(DOC_EXAMPLES / "quickstart.json",   "quickstart.png")
render(DOC_EXAMPLES / "milestones.json",   "milestones.png")
render(DOC_EXAMPLES / "durations.json",    "durations.png")

# ── task table ───────────────────────────────────────────────────────────────
out = OUT / "table.png"
config = load_chart(str(REPO_EXAMPLES / "simple.json"))
render_table(config, str(out), dpi=150)
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── compare chart ─────────────────────────────────────────────────────────────
out = OUT / "compare.png"
planned = load_chart(str(REPO_EXAMPLES / "compare-planned.json"))
actual  = load_chart(str(REPO_EXAMPLES / "compare-actual.json"))
render_compare_chart(planned, actual, str(out), dpi=150)
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── burn chart ────────────────────────────────────────────────────────────────
out = OUT / "burn.png"
config = load_chart(str(REPO_EXAMPLES / "costs.json"))
render_burn_chart(config, str(out), dpi=150, field="cost", period="month", group_by=0, display_factor=0.001)
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── date-line ──────────────────────────────────────────────────────────────────
out = OUT / "dateline.png"
config = load_chart(str(REPO_EXAMPLES / "simple.json"))
render_chart(config, str(out), dpi=150, date_line=date(2024, 6, 1))
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── renderdepth ────────────────────────────────────────────────────────────────
out = OUT / "renderdepth.png"
config = load_chart(str(REPO_EXAMPLES / "complex.json"))
render_chart(config, str(out), dpi=150, render_depth=2)
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── milestones-only table ──────────────────────────────────────────────────────
out = OUT / "milestones-only.png"
config = load_chart(str(REPO_EXAMPLES / "simple.json"))
render_table(config, str(out), dpi=150, milestones_only=True)
print(f"  {out.relative_to(Path(__file__).parent)}")

# ── table with custom columns (costs.json) ────────────────────────────────────
out = OUT / "table-columns.png"
config = load_chart(str(REPO_EXAMPLES / "costs.json"))
render_table(config, str(out), dpi=150)
print(f"  {out.relative_to(Path(__file__).parent)}")

print("Done.")
