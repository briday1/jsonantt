# jsonantt

**jsonantt** generates beautiful Gantt chart images from a simple JSON description.  
Charts are rendered with [matplotlib](https://matplotlib.org/) so they can be saved as `.png`, `.pdf`, `.svg`, and more.

---

## Features

- **Infinitely nestable tasks** — define sub-tasks, sub-sub-tasks, etc.
- **Auto date computation** — parent task start/end are derived automatically from children when not specified.
- **Milestone markers** — easy `"milestone": true` flag with chart-level defaults and per-milestone marker overrides.
- **Optional task descriptions and extra fields** — add long-form context per task, plus arbitrary metadata like assignee or cost for table output.
- **Fully colourable** — set colours per-task; children inherit their parent's colour.
- **Recursive child colour lightening** — inherited subtask colours can optionally lighten at each nested level.
- **Clean, indented y-axis labels** — task names are left-aligned with proper indentation per depth level.
- **Table output mode** — render a task summary table with the same hierarchy and colour cues.
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
  "style": {
    "milestone_color": "#FFD700",
    "milestone_marker": "D"
  },
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

### 2. Generate the chart or table

**CLI:**

```bash
jsonantt project.json project.png
jsonantt project.json project.pdf   # vector PDF
jsonantt project.json project.svg   # scalable SVG
jsonantt --dpi 300 project.json project.png   # high-resolution PNG
jsonantt -r 1 project.json project.png   # top-level tasks only
jsonantt --renderdepth 2 project.json project.png   # include one child level
jsonantt -t project.json project-table.png   # task name / description table
jsonantt -t project.json project-table.csv   # CSV table export
jsonantt agreed.json compare.png --compare actual.json   # outline vs actual compare chart
jsonantt -t agreed.json compare-table.csv --compare actual.json   # compare table with signed offsets
jsonantt project.json project.png --date-line today --date-line-color "#C00000"   # single target line
```

**Python API:**

```python
from jsonantt import load_chart, render_chart, render_compare_chart, render_compare_table, render_table

config = load_chart("project.json")
actual = load_chart("actual.json")
render_chart(config, "project.png", dpi=150)
render_chart(config, "summary.png", dpi=150, render_depth=1)
render_table(config, "project-table.png", dpi=150)
render_compare_chart(config, actual, "compare.png", dpi=150)
render_compare_table(config, actual, "compare-table.csv", dpi=150)
```

`render_depth=0` renders all nested levels. `1` renders only top-level tasks, `2` includes one level of children, and so on.

`--table` / `-t` switches the output to a table view. By default it renders `Task`, `Name`, and `Description`. The `Task` column keeps hierarchy numbering, the `Name` column stays unindented, `style.table_colorize` controls the side color accent, and `style.table_show_markers` controls whether milestone rows use a diamond marker in that gutter.

You can customize the table columns with `style.table_columns`. Each entry can be either a string field name or an object with `field` and optional `title`. The special fields `task`, `name`, and `description` preserve the existing behavior; any other field is read from the task object, including extra task keys like `assignee` or `cost`.

```json
{
  "style": {
    "table_columns": [
      "task",
      "name",
      { "field": "assignee", "title": "Owner" },
      { "field": "cost", "title": "Cost" },
      "description"
    ]
  },
  "tasks": [
    {
      "name": "API Design",
      "start": "2024-01-01",
      "end": "2024-01-10",
      "assignee": "Morgan",
      "cost": 1200,
      "description": "Finalize endpoints and review contracts."
    }
  ]
}
```

Description and Name cells wrap to the measured rendered width of the column, and the row height expands to fit the wrapped lines. Very long unbroken tokens are not split mid-word, so they can still clip horizontally.

`--milestones-only` works with `--table` to render only milestone rows in a dedicated milestone table. `--no-milestones` does the opposite and excludes milestones.

If the table output path ends in `.csv`, `jsonantt` writes CSV instead of an image.

`--compare` turns the first JSON input into the planned/agreed baseline and overlays the second JSON as the updated/actual state. In compare charts, planned bars are drawn as slightly larger unfilled outlines, actual bars are drawn normally, removed planned tasks are struck through with no actual bar, and actual-only tasks render as normal filled bars. In compare tables and CSV output, the `Offset` column shows signed duration changes like `+2d`, `-1w`, `+3mo`, or `+1y`; milestones use the signed date shift instead.

Use `--date-line` to draw a single vertical reference line on chart outputs. It accepts either a date in the input file's `dateformat` or the special value `today`. Use `--date-line-color` to control its color.

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
| `description` | string | Optional long-form text used by table output |
| any other key | any JSON value | Preserved on the task and available to `style.table_columns` for table output |
| `id` | string | Unique identifier used for `not_before` references |
| `start` | date string | Bar start date |
| `end` | date string | Bar end date |
| `duration` | string or int | Duration from `start` (or resolved `not_before` end): `"14d"`, `"2w"`, `"3m"`, `"2y"`, or a plain integer (days) |
| `not_before` | string | `id` of another task — this task starts immediately after that task ends |
| `color` | CSS hex string | Bar colour, or milestone colour override for an individual milestone (e.g. `"#4472C4"`) |
| `milestone` | boolean | Render as a diamond milestone instead of a bar |
| `date` | date string | Milestone date (used when `milestone: true`) |
| `marker` | string | Milestone marker override for an individual milestone (matplotlib marker symbol such as `"D"`, `"o"`, `"s"`, `"*"`) |
| `marker_size` | number | Override milestone diamond size in points |
| `bold` | boolean | Render label in bold (top-level tasks are auto-bolded by default) |
| `children` | array | Nested sub-tasks (infinitely nestable) |

> **Auto date computation:** When a task has `children` but no explicit `start`/`end`, the dates are computed automatically as the earliest child start and latest child end, recursively.

> **Duration formats:** `d`/`day`/`days`, `w`/`week`/`weeks`, `m`/`month`/`months`, `y`/`year`/`years` — e.g. `"14d"`, `"2w"`, `"3m"`, `"1y"`.

### Style object

| Field | Default | Description |
|-------|---------|-------------|
| `width` | `14` | Figure width in inches |
| `row_height` | `0.3` | Height of each task row in inches |
| `bar_height` | `0.5` | Bar height as a fraction of `row_height` |
| `font_size` | `12` | Base font size in points |
| `indent_size` | `3` | Spaces added per depth level in labels |
| `label_fraction` | `0.0` | Fraction of figure width used for labels; `0` means auto-size from measured text width |
| `subtask_lightening_pct` | `0.0` | Percentage to lighten inherited subtask colours at each nested level; `20` means each inherited step moves 20% toward white |
| `colors` | palette | Array of default hex colours cycled per top-level task |
| `background` | `"#FFFFFF"` | Figure background colour |
| `grid_color` | `"#E0E0E0"` | Vertical gridline colour |
| `row_band_color` | `"#F5F5F5"` | Alternating row band colour |
| `milestone_color` | `"#FFD700"` | Default milestone colour |
| `milestone_marker` | `"D"` | Default milestone marker symbol |
| `milestone_size` | `14` | Default milestone marker size in points |
| `major_tick` | `null` | Major tick unit: `"year"`, `"quarter"`, `"month"`, `"week"` |
| `minor_tick` | `null` | Minor tick unit: `"quarter"`, `"month"`, `"week"`, `"day"` |
| `major_grid_width` | `2.0` | Major gridline linewidth |
| `minor_grid_width` | `1.5` | Minor gridline linewidth |
| `tick_position` | `"top"` | X-axis label position: `"top"`, `"bottom"`, or `"both"` |
| `bold_tasks` | `true` | Auto-bold top-level (depth 0) task labels |
| `number_tasks` | `true` | Prefix task labels with hierarchy numbers like `1`, `1.1`, `1.2` |
| `table_colorize` | `true` | Show a task-coloured accent bar in table output; when `false`, both accent bars and milestone markers are suppressed |
| `table_show_markers` | `true` | Replace the accent bar with a milestone diamond for milestone rows in table output when table colours are enabled |
| `table_columns` | `[]` | Ordered table column definitions. Empty means the default `Task`, `Name`, `Description` columns. Entries can be field-name strings or objects like `{ "field": "cost", "title": "Cost" }` |

---

## Examples

See the [examples/](https://github.com/briday1/jsonantt/tree/main/examples) folder for ready-to-run JSON files.

### Simple project

[examples/simple.json](https://github.com/briday1/jsonantt/blob/main/examples/simple.json) — a five-phase project with milestones

![simple](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/simple.png)

### Dependencies

[examples/dependencies.json](https://github.com/briday1/jsonantt/blob/main/examples/dependencies.json) — `id`, `duration`, and `not_before`

![dependencies](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/dependencies.png)

### Render depth

[examples/renderdepth.json](https://github.com/briday1/jsonantt/blob/main/examples/renderdepth.json) — nested tasks that are useful with `-r` / `--renderdepth`

Full depth, `render_depth=0`:

![render depth all](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth.png)

One child level, `-r 2`:

![render depth mid](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth-mid.png)

Top level only, `-r 1`:

![render depth top](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth-top.png)

Table output, `-t`:

![render depth table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth-table.png)

Milestones only, `-t --milestones-only`:

![render depth milestones table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth-milestones.png)

No milestones, `-t --no-milestones`:

![render depth no milestones table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/renderdepth-no-milestones.png)

Try the same file with different depth limits:

```bash
jsonantt examples/renderdepth.json examples/renderdepth-all.png      # full depth
jsonantt -r 1 examples/renderdepth.json examples/renderdepth-top.png # top-level only
jsonantt -r 2 examples/renderdepth.json examples/renderdepth-mid.png # one child level
jsonantt -t examples/renderdepth.json examples/renderdepth-table.png # task table view
jsonantt -t --milestones-only examples/renderdepth.json examples/renderdepth-milestones.png # milestones only
jsonantt -t --no-milestones examples/renderdepth.json examples/renderdepth-no-milestones.png # exclude milestones
jsonantt -t examples/renderdepth.json examples/renderdepth-table.csv # CSV table export
```

### Color schemes

[examples/colors.json](https://github.com/briday1/jsonantt/blob/main/examples/colors.json) — custom palette, background, grid, row band, milestone colours, and custom milestone markers

![color schemes](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/colors.png)

### Compare mode

[examples/compare-planned.json](https://github.com/briday1/jsonantt/blob/main/examples/compare-planned.json) and [examples/compare-actual.json](https://github.com/briday1/jsonantt/blob/main/examples/compare-actual.json) — planned vs actual comparison with a CLI date line

Compare chart:

![compare chart](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/compare.png)

Compare table image:

![compare table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/compare-table.png)

CSV export:

[examples/compare-table.csv](https://github.com/briday1/jsonantt/blob/main/examples/compare-table.csv)

### Description wrapping

[examples/description-wrap.json](https://github.com/briday1/jsonantt/blob/main/examples/description-wrap.json) — demonstrates normal word wrapping in table output and the edge case where a single unbroken token will not wrap

Table output, `-t`:

![description wrap table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/description-wrap-table.png)

CSV export:

[examples/description-wrap-table.csv](https://github.com/briday1/jsonantt/blob/main/examples/description-wrap-table.csv)

### Custom table fields

[examples/costs.json](https://github.com/briday1/jsonantt/blob/main/examples/costs.json) — shows `style.table_columns` with custom `Owner` and `Cost` columns sourced from task fields like `assignee` and `cost`

CSV export:

[examples/costs-table.csv](https://github.com/briday1/jsonantt/blob/main/examples/costs-table.csv)

### Complex roadmap

[examples/complex.json](https://github.com/briday1/jsonantt/blob/main/examples/complex.json) — a multi-year roadmap with deep nesting, task descriptions, and custom colours

![complex](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/complex.png)

Table output, `-t`:

![complex table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/complex-table.png)

Milestones only, `-t --milestones-only`:

![complex milestones table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/complex-milestones.png)

No milestones, `-t --no-milestones`:

![complex no milestones table](https://raw.githubusercontent.com/briday1/jsonantt/main/examples/complex-no-milestones.png)


## How to Run

```bash
jsonantt examples/simple.json examples/simple.png                    # basic milestones
jsonantt examples/dependencies.json examples/dependencies.png        # not_before scheduling
jsonantt examples/renderdepth.json examples/renderdepth.png          # full nested view
jsonantt -r 1 examples/renderdepth.json examples/renderdepth-top.png # top-level only
jsonantt -r 2 examples/renderdepth.json examples/renderdepth-mid.png # one child level
jsonantt -t examples/renderdepth.json examples/renderdepth-table.png # task table with descriptions
jsonantt -t --milestones-only examples/renderdepth.json examples/renderdepth-milestones.png # milestone table
jsonantt -t --no-milestones examples/renderdepth.json examples/renderdepth-no-milestones.png # table without milestones
jsonantt -t examples/renderdepth.json examples/renderdepth-table.csv # CSV export
jsonantt examples/colors.json examples/colors.png                    # custom palette and background
jsonantt examples/compare-planned.json examples/compare.png --compare examples/compare-actual.json --date-line 2024-03-01 --date-line-color "#C00000" # compare chart with target line
jsonantt -t examples/compare-planned.json examples/compare-table.png --compare examples/compare-actual.json # compare table image
jsonantt -t examples/compare-planned.json examples/compare-table.csv --compare examples/compare-actual.json # compare table CSV
jsonantt -t examples/description-wrap.json examples/description-wrap-table.png # wrapped descriptions table image
jsonantt -t examples/description-wrap.json examples/description-wrap-table.csv # wrapped descriptions CSV
jsonantt -t examples/costs.json examples/costs-table.csv                # custom cost/owner columns CSV
jsonantt examples/complex.json examples/complex.png                  # deep roadmap example
jsonantt -t examples/complex.json examples/complex-table.png         # full complex table
jsonantt -t --milestones-only examples/complex.json examples/complex-milestones.png # complex milestones only
jsonantt -t --no-milestones examples/complex.json examples/complex-no-milestones.png # complex without milestones
```

