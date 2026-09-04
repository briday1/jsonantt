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
     - JSON source editor with line numbers, plus a ``STYLE`` tab that edits only the
       ``style`` block. Parse errors are reported inline without discarding the last
       valid render.
   * - **Canvas**
     - Tabbed views over the same document: **Gantt** (default) and **Graph**.
       Every edit re-renders the canvas immediately.
   * - **Objects panel**
     - Tasks, milestones, and dependency arrows. Selecting an entry highlights it on
       the canvas and opens its properties box.

Canvas tabs
-----------

* **Gantt** — bars, milestone diamonds, gridlines, alternating row bands, chart title,
  optional dependency arrows, and an optional "today" marker.
* **Graph** — the same model as a node/edge diagram: solid connectors for the task
  hierarchy and dashed connectors for ``arrows`` entries.

Both views are rendered as SVG and can be copied or saved from the **File** menu.

Properties box
--------------

Clicking a bar, milestone, graph node, arrow, or objects-panel entry opens a floating
(draggable) properties box. Task properties cover ``name``, ``id``, ``start``, ``end``,
``duration``, ``not_before``, ``color``, milestone flags, milestone dates, and
``description``. Editing a field rewrites the JSON source instantly.

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
* Undo/redo (also ``Ctrl``/``Cmd`` + ``Z``), ``Escape`` clears the selection, and
  ``Delete`` removes the selected task or arrow.
* Zoom controls, ``Ctrl``/``Cmd`` + mouse wheel zoom, and a **Fit** button.
* Light/dark theme toggle in **Settings**; the source is kept in ``localStorage``.

Limitations
-----------

The studio previews charts with a browser-side implementation of the jsonantt model.
It covers tasks, nesting, durations, ``not_before`` chaining, milestones (including
milestone chains), colours, and arrows. Image output, table/burn/compare rendering,
and ``filename`` includes remain command-line features, since they need the Python
renderer and local file access.

Static hosting
--------------

The studio is a dependency-free static bundle (``jsonantt/web``), so it can also be
published to any static host. The repository ships a ``Deploy studio to GitHub Pages``
workflow that uploads that directory whenever it changes on ``main``. When hosted
statically the studio works exactly as it does locally, except that the version badge
and the ``?project=1`` handoff need the local ``jsonantt serve`` server.
