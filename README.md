# jsonantt

**jsonantt** generates beautiful Gantt chart images from a simple JSON description.  
Charts are rendered with [matplotlib](https://matplotlib.org/) so they can be saved as `.png`, `.pdf`, `.svg`, and more.

---

## Features

- **Infinitely nestable tasks** — define sub-tasks, sub-sub-tasks, etc.
- **Auto date computation** — parent task start/end are derived automatically from children when not specified.
- **Milestone markers** — easy `"milestone": true` flag renders a distinctive diamond.
- **Fully colourable** — set colours per-task; children inherit their parent's colour.
- **Clean, indented y-axis labels** — task names are left-aligned with proper indentation per depth level.
- **PNG / PDF / SVG output** — whatever matplotlib supports.

---

## Installation

```bash
pip install jsonantt
```

Or, directly from source:

```bash
git clone https://github.com/briday1/jsonantt.git
cd jsonantt
pip install -e .
```

---

## Quick start

### 1. Create a JSON description

```json
{
  "title": "My Project",
  "dateformat": "%Y-%m-%d",
  "tasks": [
    {
      "name": "Phase 1 – Planning",
      "children": [
        { "name": "Requirements", "start": "2024-01-08", "end": "2024-01-19" },
        { "name": "Architecture",  "start": "2024-01-15", "end": "2024-01-31" }
      ]
    },
    { "name": "Planning done", "milestone": true, "date": "2024-01-31" },
    {
      "name": "Phase 2 – Build",
      "color": "#70AD47",
      "children": [
        { "name": "Backend",  "start": "2024-02-01", "end": "2024-03-01" },
        { "name": "Frontend", "start": "2024-02-12", "end": "2024-03-08" }
      ]
    },
    { "name": "Launch", "milestone": true, "date": "2024-04-01", "color": "#FF5757" }
  ]
}
```

### 2. Generate the chart

**CLI:**

```bash
jsonantt project.json project.png
jsonantt project.json project.pdf   # vector PDF
jsonantt project.json project.svg   # scalable SVG
jsonantt --dpi 300 project.json project.png   # high-resolution PNG
```

**Python API:**

```python
from jsonantt import load_chart, render_chart

config = load_chart("project.json")
render_chart(config, "project.png", dpi=150)
```

---

## JSON reference

| Field | Type | Description |
|-------|------|-------------|
| `title` | string | Optional chart title shown at the top |
| `dateformat` | string | `strptime` format string (default: `"%Y-%m-%d"`) |
| `start` | date string | Optional chart x-axis start date (overrides task dates) |
| `end` | date string | Optional chart x-axis end date |
| `style` | object | Visual style overrides (see below) |
| `tasks` | array | Top-level list of task objects |

### Task object

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | **Required.** Task label |
| `start` | date string | Bar start date |
| `end` | date string | Bar end date |
| `color` | CSS hex string | Bar/milestone colour (e.g. `"#4472C4"`) |
| `milestone` | boolean | Render as a diamond milestone instead of a bar |
| `date` | date string | Milestone date (used when `milestone: true`) |
| `children` | array | Nested sub-tasks (infinitely nestable) |

> **Auto date computation:** When a task has `children` but no explicit `start`/`end`, the dates are computed automatically as the earliest child start and latest child end, recursively.

### Style object

| Field | Default | Description |
|-------|---------|-------------|
| `width` | `14` | Figure width in inches |
| `row_height` | `0.45` | Height of each task row in inches |
| `bar_height` | `0.5` | Bar height as a fraction of `row_height` |
| `font_size` | `9` | Base font size in points |
| `indent_size` | `3` | Spaces added per depth level in labels |
| `label_fraction` | `0.28` | Fraction of figure width used for labels |
| `colors` | palette | Array of default hex colours cycled per top-level task |
| `background` | `"#FFFFFF"` | Figure background colour |
| `grid_color` | `"#E0E0E0"` | Vertical gridline colour |
| `row_band_color` | `"#F5F5F5"` | Alternating row band colour |
| `milestone_color` | `"#E65100"` | Default milestone colour |

---

## Examples

See the [`examples/`](examples/) folder for ready-to-run JSON files:

- [`examples/simple.json`](examples/simple.json) — a three-phase project with milestones
- [`examples/complex.json`](examples/complex.json) — a multi-quarter roadmap with deep nesting and custom colours

Generate them locally:

```bash
jsonantt examples/simple.json simple.png
jsonantt examples/complex.json complex.png
```

---

## License

MIT
