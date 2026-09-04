Studio (interactive web UI)
===========================

``jsonantt serve`` opens the **jsonantt studio**: a browser workspace with a JSON
source sidebar, a live canvas, and a properties/objects side panel. It mirrors the
layout and interaction model of `pugflow <https://github.com/briday1/pugflow>`_,
but keeps jsonantt's JSON documents as the single source of truth.

.. code-block:: bash

   jsonantt serve                 # start with the built-in starter chart
   jsonantt serve project.json    # open an existing chart
   jsonantt serve --port 8080 --no-browser

Layout
------

.. list-table::
   :widths: 26 74
   :header-rows: 0

   * - **Sidebar**
     - JSON source editor with line numbers and syntax highlighting. Parse errors are
       reported inline without discarding the last valid render.
   * - **Canvas**
     - Tabbed views over the same document: **Gantt** (default) and **Table**.
       Every edit re-renders the canvas immediately.
   * - **Objects panel**
     - Tasks, milestones, and dependency arrows. Selecting an entry highlights it on
       the canvas and opens its properties box.

Canvas tabs
-----------

* **Gantt** — bars, milestone diamonds, gridlines, alternating row bands, chart title,
  optional dependency arrows, and an optional "today" marker. With
  ``style.fiscal_year_start`` set, year/quarter ticks follow the fiscal calendar
  (``FY26``, ``Q1 FY26``…).
* **Table** — the same task table the CLI renders with ``--table``: hierarchy numbering,
  milestone markers, and the colour gutter, honouring ``style.table_columns`` (including
  ``rollup``/``total``/``display_factor``), ``style.table_colorize`` and
  ``style.table_show_markers``. Double-click the table to jump straight to the table
  settings.

The Gantt view is rendered as SVG and can be copied or saved from the **File** menu.
Clicking a bar, milestone, or table row selects the same object everywhere — canvas,
objects panel, and properties box stay in sync.

Chart settings
--------------

**Settings → Chart settings…** opens a dialog for the overall chart configuration (the
fields that apply to the whole document rather than one object):

* **General** — ``title``, ``dateformat``, and the chart ``start``/``end`` axis overrides
  (date fields include a calendar popup).
* **Time scale** — ``style.major_tick``/``style.minor_tick`` (days, weeks, months,
  quarters, or years) and ``style.fiscal_year_start`` to switch the axis to a fiscal
  calendar referenced from any month (fiscal quarters and years are labelled
  ``Q1 FY26``, ``FY26``…).
* **Table** — ``style.table_columns`` plus the ``table_colorize`` / ``table_show_markers``
  options.
* **Appearance** — background/grid/row-band/milestone colours, row height, font size,
  render depth, subtask lightening, bold and numbering options.

Every change rewrites the JSON source and re-renders live, so settings persist through
the same undo/redo, save, and export flow as any other edit.

Properties box
--------------

Clicking a bar, milestone, table row, arrow, or objects-panel entry opens a floating
(draggable) properties box. Task properties cover ``name``, ``id``, ``start``, ``end``,
``duration``, ``not_before``, ``color``, milestone flags, milestone dates, and
``description`` — date fields offer a calendar popup that writes dates in the chart's
own ``dateformat``. Editing a field rewrites the JSON source instantly.

The **Relationships** section explains how the entry is wired into the plan:

* **Depends on (upstream)** — the task referenced by ``not_before``, the parent task,
  and any task that points at this one through an ``arrows`` entry.
* **Feeds into (downstream)** — subtasks, tasks whose ``not_before`` names this task,
  and arrow targets.

Each related entry is a button: click it to jump the selection to that task.

Editing and shortcuts
---------------------

* **New** menu adds a task, a subtask of the current selection, a milestone, or an arrow.
* **Examples** menu loads bundled starter documents.
* **Format JSON** reformats the source with the *exact same formatter as the CLI*
  (``jsonantt fmt``), via the local server's ``/api/format`` endpoint, so studio output
  is byte-for-byte identical to CLI output. Under static hosting a matching in-browser
  implementation (2-space indent, trailing newline) is used instead.
* Undo/redo (also ``Ctrl``/``Cmd`` + ``Z``), ``Escape`` clears the selection, and
  ``Delete`` removes the selected task or arrow.
* Zoom controls, ``Ctrl``/``Cmd`` + mouse wheel zoom, and a **Fit** button (Gantt view).
* Light/dark theme toggle in **Settings**; the source is kept in ``localStorage``.

Limitations
-----------

The studio previews charts with a browser-side implementation of the jsonantt model.
It covers tasks, nesting, durations, ``not_before`` chaining, milestones (including
milestone chains), colours, fiscal calendars, and arrows. Image output, burn/compare
rendering, and ``filename`` includes remain command-line features, since they need the
Python renderer and local file access.

Static hosting
--------------

The studio is a dependency-free static bundle (``jsonantt/web``), so it can also be
published to any static host. The repository ships a ``Deploy studio to GitHub Pages``
workflow that uploads that directory whenever it changes on ``main``. When hosted
statically the studio works exactly as it does locally, except that the version badge
and the ``?project=1`` handoff need the local ``jsonantt serve`` server.
