Studio (interactive web UI)
===========================

``jsonantt serve`` opens the **jsonantt studio**: a browser workspace with a JSON
source sidebar, a live canvas, and a properties/objects side panel. It mirrors the
layout and interaction model of `pugflow <https://github.com/briday1/pugflow>`_,
but keeps jsonantt's JSON documents as the single source of truth.

`Open the hosted GUI <https://briday1.github.io/jsonantt/>`_ for browser editing
without installation. To enable PNG/SVG/CSV exports, run your own local server below.

Running your own local server
-----------------------------

Install Python 3.8 or newer. On macOS/Linux, create an isolated environment and
install the published package:

.. code-block:: bash

   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install --upgrade jsonantt
   jsonantt serve

On Windows, use these PowerShell commands (activation is not required):

.. code-block:: powershell

   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install --upgrade jsonantt
   .\.venv\Scripts\jsonantt.exe serve

The server opens http://127.0.0.1:4174/ automatically. Leave the terminal running
while using the studio; press **Ctrl+C** in that terminal to stop it.
No Node.js installation or frontend build is needed.

Startup options:

.. code-block:: bash

   jsonantt serve                 # start with the built-in starter chart
   jsonantt serve project.json    # open an existing chart
   jsonantt serve --port 8080 --no-browser

With ``--port 8080 --no-browser``, open http://127.0.0.1:8080/ manually.
Use a different port if the default is already in use.

For the current repository version, clone it, create/activate a virtual environment
as above, and install in editable mode:

.. code-block:: bash

   git clone https://github.com/briday1/jsonantt.git
   cd jsonantt
   python -m pip install -e .
   jsonantt serve examples/simple.json

After a package upgrade or Python source edit, stop and restart the server and
refresh the browser. The running process does not automatically reload Python code.

Open http://127.0.0.1:4174/?demo=1 for the delivery demo, ``?demo=2`` for
milestones, or ``?demo=3`` for the cost/burn demo. These also work on the hosted GUI.
Use **File → Open JSON…** to load a document and **File → Save JSON…** to download
edits. Loading a file with ``jsonantt serve project.json`` does not enable automatic
writes back to that file.

To allow another device on a trusted local network to connect:

.. code-block:: bash

   jsonantt serve --host 0.0.0.0 --port 4174 --no-browser

On the other device, visit ``http://<server-LAN-IP>:4174/``. The default
``127.0.0.1`` binding accepts connections only from your own computer. This server
has no authentication; do not expose it directly to the public internet.

The local server provides the GUI and Python rendering/formatting endpoints.
A built static site also provides all previews and PNG/SVG/CSV export, using the
same Python renderer in a Pyodide worker (see Static hosting below).

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
  settings. The **Rows** selector switches between **With milestones**,
  **Milestones only**, and **No milestones**, preserving task numbering.
* **Burn** — interactive planned spend bars per reporting period. Choose a
  numeric field (such as ``cost`` or ``effort``), day/week/month/quarter/year
  buckets, total/individual/depth grouping, and a display multiplier. Hover to
  inspect values and select a series to edit its task.
* **Burndown** — a separate line chart showing the remaining planned allocation
  within the chart's date range, decreasing after each period.
* **Burnup** — a separate line chart showing cumulative planned allocation from zero.
  Dotted, colour-matched lines show each task/group's full source budget, even if
  the date range includes only part of the task. Choose Individual tasks for
  per-task lines. The selected numeric multiplier applies to budget lines too.
* **Burn table** — the same period allocations in a selectable matrix, with totals.

These are planned allocation views, not actual spend or completed-work tracking.

Burn tabs appear only when a task (including a nested task or milestone) has a
numeric custom field such as cost or effort. Zero allocations count as data;
IDs, durations, dates, and marker sizes do not. Removing all such values hides
all four burn-related tabs and returns an active burn view to Gantt.

The active table filter and burn controls also apply to PNG/SVG/CSV exports.
The export dialog identifies the selected table rows. If an older server cannot
confirm the filter, the GUI asks you to restart ``jsonantt serve`` and refresh
instead of downloading an unfiltered table.
The dedicated CLI commands use the same renderer as PNG/SVG exports:

.. code-block:: bash

   jsonantt --burn project.json spend.png --burn-period quarter
   jsonantt --burndown project.json burndown.png --burn-period quarter
   jsonantt --burnup project.json burnup.png --burn-period quarter --burn-group leaf --dpi 300

``--burn --burn-display remaining`` and ``--burn --burn-display cumulative``
remain supported aliases. Export errors are shown inside the export dialog;
restart the updated local server if it reports an unknown view.

All six canvas views use the same Python renderer as the CLI and export. Local
instances request SVG from ``/api/preview``; static sites run the bundled Python
sources in a Pyodide worker. The SVG is inserted as interactive elements, not an
image: task rows, bars, milestones, dependency arrows, and legend text remain
selectable, with tooltips. Table fills, columns, fonts, axes, and budget lines come
directly from the renderer. Zoom and Fit work on that SVG. Source changes retain
the current drawing until its replacement arrives; obsolete requests cannot
replace a newer view. There is no approximate drawing fallback.

The Gantt view provides **Rollup depth** and **Roll up milestones** controls.
These write ``style.render_depth`` and ``style.rollup_milestones`` and stay in
sync with Chart settings and exports. Clicking a rolled-up milestone selects
the descendant milestone, not the parent row. Task Properties includes **Cost**:
edit the original amount (including optional currency text), not its scaled
display value. Zero is a valid cost; clearing the field removes it.

The CLI also supports display-only overrides, without modifying the JSON source:

.. code-block:: bash

   jsonantt --burnup project.json burnup.png --value-scale millions --value-prefix '$' --value-decimals 2
   jsonantt --burn-table project.json burn.csv --value-scale thousands --value-prefix '$'

``--value-scale`` accepts ``units``, ``thousands``, ``millions``, or ``billions``.
``--value-suffix`` adds a unit annotation without scaling, and ``--value-fields``
selects comma-separated amount fields. Burn overrides target ``--burn-field`` unless
``--value-fields`` is explicit. Unspecified options retain the source style settings;
defaults retain existing output.

**Exports are fresh renderer output, never screenshots of the preview.** The
File → Export… dialog saves PNG or SVG and offers 96/150/300/600 DPI for PNG;
Save CSV… remains available for tables. Local instances use ``/api/export``;
static hosting uses the same renderer inside the worker. Rendering versions and
platforms can differ in font metrics, but there is only one chart style implementation.
Clicking a bar, milestone, or table row selects the same object everywhere — canvas,
objects panel, and properties box stay in sync.

Chart settings
--------------

**Settings → Chart settings…** opens a dialog for the overall chart configuration (the
fields that apply to the whole document rather than one object):

* **General** — ``title``, ``dateformat``, and the chart ``start``/``end`` axis overrides
  (date fields include a calendar popup).
* **Value display** — optional currency prefix, unit suffix, thousands/millions/
  billions scaling, decimal places, and affected fields. For example, prefix ``$``
  and scale ``millions`` display a raw cost of 1250000 as ``$1.25M``. Defaults keep
  existing output unchanged; costs are formatted without changing effort or IDs.
  See :doc:`style-guide` for already-scaled data and existing display multipliers.
* **Time scale** — ``style.major_tick``/``style.minor_tick`` (days, weeks, months,
  quarters, or years) and ``style.fiscal_year_start`` to switch the axis to a fiscal
  calendar referenced from any month (fiscal quarters and years are labelled
  ``Q1 FY26``, ``FY26``…).
* **Table** — ``style.table_columns`` plus the ``table_colorize`` / ``table_show_markers``
  options.
* **Colours** — inherited child lightening percentage, task palette, background,
  grid, and alternating row colours. Child lightening is applied to the immediate
  parent's resolved colour at each depth step, matching the CLI.
* **Layout** — chart width, font size, row/bar height, label-panel width,
  indentation, and visible task depth.
* **Labels and display** — bolding, task numbering, dependency arrows, and today's
  marker. These settings are saved in the chart source and used in exports.
* **Milestones / Major milestones / Milestone rollup** — fill, outline, symbol,
  size, M1/M2 numbering, and hidden milestone overlays at a limited render depth.

The form covers every field in the Python ``Style`` model. Controls show defaults,
offer **Reset**, and explain which views they affect: for example, row height is
Gantt-only because tables fit their rows to text. Turning a toggle off explicitly
saves ``false``. Table columns accept either comma-separated names or a complete
JSON array, including objects with totals and rollups; invalid JSON is rejected
without replacing the existing columns.

Every change rewrites the JSON source and re-renders live, so settings persist through
the same undo/redo, save, and export flow as any other edit.

After upgrading, restart ``jsonantt serve`` and refresh so the server recognises
the source-backed ``render_depth``, ``show_arrows``, and ``today_marker`` options.
The **Today marker** setting applies to Gantt, burndown, and burnup previews and
exports. In burn line charts, it follows the date's position within the reporting
period and is hidden outside the plotted range. The CLI also supports
``--date-line today`` (or a specific date) and ``--date-line-color`` for these views.

Properties box
--------------

Clicking a bar, milestone, table row, arrow, or objects-panel entry opens the
properties box. Drag its header to reposition it within the visible canvas.
The entire box stays inside the canvas when dragging, resizing, or changing its
contents; Delete and Close remain in the footer. The focused header also supports
arrow keys (Shift moves in larger steps). Task properties cover ``name``, ``id``, ``start``, ``end``,
``duration``, ``not_before``, ``color``, milestone flags, milestone dates, and
``description`` — date fields offer a calendar popup that writes dates in the chart's
own ``dateformat``. Editing a field rewrites the JSON source instantly.
Use **Add subtask** below the task name to create a child of that task and open
the child's properties. This works from both Gantt and table selections.
Scheduling dependencies are edited with **Not before**; existing arrows remain
selectable and editable in their own properties.
Start/end, chart start/end, milestone dates, and fiscal-year start all offer
calendar popups. Modal settings calendars open above the dialog's scrolling
content; milestone-chain picking replaces only the last date. Manual typing
remains available, with dates stored in the source's format (fiscal start uses MM-DD).

Comparing files and Git revisions
--------------------------------------------------

Open **File → Compare…**. In that popup use either **Choose baseline JSON…** to
upload any chart, or **Git history…** to browse the
selected local file's commits by date, SHA, and message. Clicking a revision
loads it as the baseline; it never replaces or saves the current editor.
Use **Apply comparison** at the bottom to confirm the selection and close the popup.
The current editor, including unsaved edits, is the actual/updated side.
Enable/disable **Compare mode** in the popup or File menu; the existing six output
tabs all use that mode. Gantt/task tables use the CLI comparison renderers;
burn, burndown, burnup, and burn tables show baseline/current native drawings
side by side. Comparison previews support zoom/fit and PNG/SVG export (CSV for tables).
Task editing remains in the ordinary Gantt/table views; comparison drawings are read-only.

To choose a local file, use **File → Open local file…**. Browse directories or
enter its full path. This works even if the server was started without a filename.
Click a file to highlight it and fill its full path, then confirm with **Open file**
(or **Use this file** when locating history). Double-clicking a file confirms directly.
If the current file's path is not yet known, clicking **Git history…** offers that
picker automatically to locate the file, without replacing unsaved editor content.
Git history follows that selected path, including renames, up to the latest 200
commits in the current branch. No Git checkout or disk writes are performed.
The ordinary **Open JSON…** upload works on static hosts too, but browser uploads
do not expose a trustworthy full path; use the local picker for Git integration.
The server account must be able to read the file and run Git.
Older running servers must be restarted to provide the new local-file/history endpoints.

Workspace recovery
------------------

Refreshing or revisiting restores unsaved source, selected file path, comparison
baseline/revision, canvas view, filters, zoom, selection, panel layout, scroll
positions, and the most recent 20 undo/redo entries. Even incomplete JSON is
kept. A recovered draft takes precedence over the startup file's disk snapshot.
An explicit different demo or startup file still opens the requested document.

Recovery is local to the browser and origin, not a save to disk or Git. Clearing
site data, private browsing, switching ports/origins, or storage limits can lose
recovery data. A warning appears if workspace storage fails. Save JSON for a
durable copy; optional undo history is dropped first if storage runs out.

See :doc:`api` for complete HTTP/Python functionality and local-file/history endpoints.

The **Relationships** section explains how the entry is wired into the plan:

* **Depends on (upstream)** — the task referenced by ``not_before``, the parent task,
  and any task that points at this one through an ``arrows`` entry.
* **Feeds into (downstream)** — subtasks, tasks whose ``not_before`` names this task,
  and arrow targets.

Each related entry is a button: click it to jump the selection to that task.

Editing and shortcuts
---------------------

* **New** menu adds a top-level task or milestone. Add subtasks from task properties.
* ``?demo=1`` loads the described product-delivery example and ``?demo=2`` loads
  the described milestone-chain example without adding permanent toolbar clutter.
  ``?demo=3`` loads a budget example with costs, effort, overlapping work, and
  a funded milestone.
* GUI edits format the source with two-space indentation and a trailing newline.
  Use ``jsonantt fmt`` for standalone command-line formatting.
* Undo/redo (also ``Ctrl``/``Cmd`` + ``Z``), ``Escape`` clears the selection, and
  ``Delete`` removes the selected task or arrow.
* Zoom controls, ``Ctrl``/``Cmd`` + mouse wheel zoom, and a **Fit** button for all views.
* **Settings → Theme** toggles between light and dark. Your OS chooses the initial
  theme unless you have a saved override; clicking the toggle remembers your choice.

Limitations
-----------

The studio uses a browser-side implementation of the jsonantt model for editing.
It covers tasks, nesting, durations, ``not_before`` chaining, milestones (including
milestone chains), colours, fiscal calendars, arrows, and planned burn allocation.
Static hosting needs WebAssembly, module workers, and access to the Pyodide CDN
on first use. The initial runtime/package download can take time and uses more
memory than the local-server option. If browser support, network policy, or memory
prevents rendering, the GUI reports the error; use ``jsonantt serve`` instead.
Use self-contained JSON in the GUI. **File → Append JSON…** can resolve filename
includes from selected files/folders into editable snapshots. Live filesystem
links remain a CLI/Python feature (``load_chart`` resolves them relative to the source file).

Appending / composing task files
------------------------------------------

**File → Append JSON…** accepts multiple JSON files. Use **Load folder…** when
includes live in nested directories, so their relative paths are retained.
Check the files to append and use the up/down buttons to choose their order.
Unchecked files remain available to resolve ``filename`` references; dependency
files are initially unchecked so they are not appended twice.

Choose **Append tasks inline** to append each selected file's task tree directly,
or **One parent task per file** to place it under a task named after that file.
Click **Append selected files** to confirm and close the popup. Importing is one
undoable operation and is included in workspace recovery.

This follows CLI inclusion semantics: only task trees are imported, not the
included chart's style, title, range, or arrows. Nested includes, task costs,
metadata, milestone chains, and cross-file scheduling references are retained.
Dates are converted from each source file's format to the current chart's format.
The destination's settings and existing arrows remain unchanged.

Imports are editable snapshots, not live links, so Save JSON produces one portable
file and property edits never write back to imported files. Missing/circular
includes and duplicate task IDs are reported before any source change. Load all
referenced JSON files, including unchecked dependencies, before confirming.
Static hosting uses the same Python composer inside Pyodide; the local server
provides ``POST /api/compose``. Neither composer reads arbitrary filesystem paths.

Static hosting
--------------

Build the assets and an archive of the current Python sources together:

.. code-block:: bash

   python -m jsonantt.static_site --output _site
   python -m http.server 8080 --directory _site

Deploy the resulting ``_site`` directory, not just ``jsonantt/web``. The archive
is generated from the real package, so no second copy of rendering code needs
maintenance. The GitHub Pages workflow rebuilds on Python and web asset changes.
Add ``--prerender`` to the build command to generate immediate, interactive SVG
previews for all built-in demos (requires Node.js). The Pages workflow enables
this automatically. These previews are generated by the Python renderer, not a
separate drawing implementation.

Previously rendered custom charts are cached in IndexedDB for fast refreshes.
The cache is bounded to 12 entries and four million SVG characters, keyed by
source, view options, renderer build, and date when today's marker is enabled.
Storage failures fall back to normal rendering. Source/settings/build changes
never reuse an incompatible drawing.

Pyodide is pinned to a versioned CDN URL. After a cached or bundled preview is
visible, the worker warms up in the background. It downloads matplotlib and fonts
alongside interpreter startup, then reuses them for edits and exports. New uncached
charts still need Python startup; restricted storage can prevent fast refreshes.
Your chart source is processed locally in the browser, not sent to the CDN.
The server version badge and ``?project=1`` handoff still require ``jsonantt serve``.
