API reference
=============

The CLI, local HTTP server, and hosted Pyodide worker all call the same Python
renderers. There is no separate API drawing style. Existing file-based Python
functions remain supported; ``render_document`` is the unified in-memory entry point.

Quick start: Python
-------------------

.. code-block:: python

   import json
   from pathlib import Path
   from jsonantt import render_document

   chart = json.loads(Path("project.json").read_text())
   image = render_document(chart, {
       "mode": "burnup", "format": "png", "dpi": 300,
       "burn": {"field": "cost", "period": "quarter", "group": "leaf"},
       "dateLine": "today",
       "valueFormat": {"value_scale": "thousands", "value_prefix": "$"},
   })
   Path("burnup.png").write_bytes(image)

``render_document(document, options=None)`` returns bytes and does not mutate the
document. Defaults are Gantt, SVG, 150 DPI, and the document's style settings.
Invalid options raise ``ValueError``; invalid source or rendering can also raise
parser/renderer exceptions. Requests are serialized around matplotlib.

Quick start: HTTP
------------------------------

Start ``jsonantt serve --no-browser`` (default address ``127.0.0.1:4174``).

.. code-block:: bash

   curl --fail-with-body http://127.0.0.1:4174/api
   curl --fail-with-body -H 'Content-Type: application/json' \
     --data-binary @project.json \
     'http://127.0.0.1:4174/api/export?mode=burnup&format=png&dpi=300&burn_period=quarter&date_line=today&value_scale=thousands&value_prefix=%24' \
     --output burnup.png

The request body is the chart itself, not a filename or ``{chart: ...}`` wrapper.
Use URL encoding for query values, especially ``#`` colors, ``$`` currency symbols,
spaces, and full file paths. HTTP output defaults to Gantt PNG at 150 DPI.

Endpoints
---------

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Endpoint
     - Result
   * - ``GET /api``
     - Machine-readable modes, formats, endpoints, and supported query names.
   * - ``GET /healthz``
     - Version, capabilities, and optional startup project path.
   * - ``POST /api/export``
     - PNG/SVG file bytes, or CSV for a table; attachment filename and MIME type.
   * - ``POST /api/preview``
     - SVG regardless of the format query. Six single-document views contain
       selection targets; comparison drawings are read-only, with zoom/fit in the GUI.
   * - ``POST /api/format``
     - Any valid JSON reformatted with two-space indentation and a trailing newline.
   * - ``POST /api/compose``
     - Portable chart JSON with selected task files appended (see Composition below).
   * - ``GET /api/files?path=directory``
     - Resolved directory, parent, and up to 1,000 visible directories/JSON files.
       Omit path for the startup file's directory or server working directory.
   * - ``GET /api/project?path=/full/path.json``
     - ``{path, source}``: validated chart source and resolved full path. Includes
       become editable snapshots (relative directory first, invocation directory
       second); source files are not changed.
   * - ``GET /api/history?path=/full/path.json``
     - ``{file, revisions, limit}``; latest 200 file commits, newest first.
       Each revision has ``date`` (commit date, ISO 8601), full ``sha``, ``message``, and historical ``path``.
   * - ``GET /api/history?path=/full/path.json&revision=FULL_SHA``
     - The selected historical chart JSON. SHA must appear in that file's list.
       Renames are followed. No checkout, reset, or working-tree writes occur.
   * - ``GET /__project.json``
     - Startup file snapshot when launched with ``jsonantt serve project.json``;
       otherwise 404. Browser draft recovery takes precedence on refresh.

History's ``path`` may be omitted only when the server was started with a file.
Paths refer to the machine running the local server, not a remote browser's disk.
Git must be installed and the file committed in the current branch's history.
Untracked files have no revisions. Invalid historical JSON produces an error,
without replacing the current document or existing comparison baseline.

Render modes
------------

.. list-table::
   :header-rows: 1
   :widths: 24 30 46

   * - API mode
     - CLI equivalent
     - Output
   * - ``gantt``
     - default
     - Hierarchical schedule, rollups, milestones, arrows.
   * - ``table``
     - ``--table``
     - Task/milestone table; PNG, SVG, CSV.
   * - ``burn``
     - ``--burn``
     - Spending by reporting period (stacked bars).
   * - ``burndown``
     - ``--burndown``
     - Remaining planned allocation over time.
   * - ``burnup``
     - ``--burnup``
     - Cumulative planned allocation and dotted task budgets.
   * - ``burn-table``
     - ``--burn-table``
     - Period allocation matrix; PNG, SVG, CSV.
   * - ``compare-gantt``
     - ``--compare actual.json``
     - Planned outline versus current/actual schedule.
   * - ``compare-table``
     - ``--table --compare actual.json``
     - Comparison table with signed offsets; PNG, SVG, CSV.
   * - ``compare-burn``, ``compare-burndown``, ``compare-burnup``, ``compare-burn-table``
     - Burn flag plus ``--compare actual.json``
     - Side-by-side baseline/current native outputs. Burn table also supports CSV
       with separately labeled Baseline/Current column groups.

Every mode supports PNG/SVG. Comparisons require this body, where both values
are complete chart documents:

.. code-block:: json

   {
     "planned": {"tasks": [{"id": "work", "name": "Work", "start": "2026-01-01", "duration": "4w"}]},
     "actual": {"tasks": [{"id": "work", "name": "Work", "start": "2026-01-08", "duration": "4w"}]}
   }

The baseline is ``planned``; the GUI's current, possibly unsaved editor is
``actual``. Matching and baseline styling follow the CLI comparison renderer.
Use stable task IDs across revisions. Burn comparison panels retain their own
periods, scales, and legends; read the labeled axes when comparing values.

Render options: complete CLI mapping
------------------------------------------------------------

The Python column names the key inside ``options``. Dots mean nested dictionaries.
HTTP uses the query parameter name shown. All options are optional.

.. list-table::
   :header-rows: 1
   :widths: 22 25 53

   * - HTTP query
     - Python option
     - Meaning / CLI equivalent
   * - ``mode``, ``format``
     - ``mode``, ``format``
     - Modes above; PNG/SVG/CSV. The CLI selects format from output extension.
   * - ``dpi``
     - ``dpi``
     - Positive integer, default 150; ``--dpi``. Raster only.
   * - ``render_depth``
     - ``renderDepth``
     - Non-negative integer; ``--renderdepth``. 0 = all levels, 1 = top level.
       Gantt/table and comparison modes; defaults to ``style.render_depth``.
   * - ``table_filter``
     - ``tableFilter``
     - ``all`` (default), ``milestones`` (``--milestones-only``), or
       ``tasks`` (``--no-milestones``); regular/comparison task tables.
   * - ``burn_field``
     - ``burn.field``
     - Numeric task field, default ``cost``; ``--burn-field``.
   * - ``burn_period``
     - ``burn.period``
     - ``day``, ``week``, ``month`` (default), ``quarter``, ``year``; ``--burn-period``.
   * - ``burn_group``
     - ``burn.group``
     - ``total``, ``leaf``, or non-negative depth (default 0); ``--burn-group``.
   * - ``burn_factor``
     - ``burn.factor``
     - Display multiplier, default 1; ``--burn-display-factor``.
   * - ``burn_display``
     - ``burn.display``
     - Legacy ``burn`` mode: ``spend``, ``remaining``, ``cumulative``;
       ``--burn-display``. Dedicated burndown/up modes determine their own display.
   * - ``date_line``
     - ``dateLine``
     - Date in the chart's ``dateformat`` or ``today``; ``--date-line``.
       Gantt/comparison Gantt and burn line charts only.
   * - ``date_line_color``
     - ``dateLineColor``
     - Default ``#C00000``; ``--date-line-color``. Also colors source-enabled today markers.
   * - ``value_scale``
     - ``valueFormat.value_scale``
     - ``units``, ``thousands``, ``millions``, ``billions``; ``--value-scale``.
   * - ``value_prefix``, ``value_suffix``
     - ``valueFormat.value_prefix``, ``valueFormat.value_suffix``
     - Currency/unit text; ``--value-prefix``, ``--value-suffix``. Empty clears an inherited value.
   * - ``value_decimals``
     - ``valueFormat.value_decimals``
     - Integer 0–8; ``--value-decimals``.
   * - ``value_fields``
     - ``valueFormat.value_fields``
     - HTTP comma-separated names; Python list. Empty string/list = all numeric fields;
       ``--value-fields``.
   * - preview endpoint
     - ``interactive``
     - Boolean, default false. Adds selection metadata where supported, without changing artwork.

Value overrides take precedence over source ``style`` and apply to both inputs
in comparison mode. Burn options apply only to burn modes; table filters and
render depth apply only to their views. Unrelated valid options are accepted
for compatibility with clients that keep one options object across tabs.
Unknown query/options names, repeated query parameters, invalid DPI/depth,
invalid dates, and unsupported output combinations are rejected.

Source-backed functionality
---------------------------

All remaining settings are passed through in the chart JSON, not duplicated as
query parameters. This includes every ``Style`` field: row lightening and bands,
background/grid/palette colors, font/layout settings, ticks and fiscal calendar,
milestone markers/numbering/rollups, ``today_marker``, ``show_arrows``, and table
column/total/value formatting. See :doc:`style-guide` and :doc:`json-reference`.

Task hierarchy (``tasks`` or ``children``), IDs, costs/custom numeric fields,
descriptions, start/end/duration, milestone chains, ``not_before`` scheduling,
and explicit arrows likewise live in the body. The API does not store edits:
change the JSON and render again. GUI undo/redo, selection, zoom, theme, calendar
popups, and recovery are client state, not rendering endpoints.

For file-oriented Python use, ``load_chart`` / ``parse_chart`` plus
``render_chart``, ``render_table``, ``render_compare_chart``,
``render_compare_table``, ``render_burn_chart`` and ``render_burn_table`` remain
available from ``jsonantt``. Their existing keyword arguments are unchanged.
For live ``filename`` includes, use ``load_chart(path)`` to resolve referenced files
relative to that source file first, then the invocation directory, followed by
the file-oriented render functions. Send self-contained JSON to rendering APIs;
the GUI's local file opener and uploaded-file composition dialog expand includes
before rendering. Browser uploads do not provide
the sibling files or a filesystem base directory for live includes. The composition
API can instead materialize explicitly provided file contents into one portable document.
For canonical JSON formatting use ``jsonantt.formatter.format_json_text`` or
``format_json_data``. ``jsonantt.server.create_server`` / ``serve`` handle local
hosting; ``jsonantt.static_site.build_site`` handles static packaging.

Composition
------------------------------

``jsonantt.compose_document(document, files, append=None, wrap=False, source_name=None)``
returns a new chart dictionary without mutating input. The equivalent
``POST /api/compose`` body uses the same named parameters:

.. code-block:: json

   {
     "document": {"title": "Combined plan", "tasks": []},
     "files": {
       "phase.json": {"tasks": [{"filename": "work.json"}]},
       "work.json": {"tasks": [{"name": "Work", "start": "2026-01-01", "duration": "4w"}]}
     },
     "append": ["phase.json"],
     "wrap": true
   }

``files`` maps relative filenames to complete chart objects; include paths resolve
relative to the containing virtual file first, then the file map's root (its
working directory). No files are read from disk. ``append``
lists roots in append order (omitting it appends every supplied file). ``wrap``
creates one parent per root, named after its filename without the extension.
``source_name`` supplies the virtual location of the current document if it also
contains includes. Imported titles, styles, ranges, and arrows are ignored.

The result expands filename-only includes inline and named includes as children,
normalizes imported dates into the destination format, and validates the merged
document. IDs must be unique. Missing/circular includes or invalid content return
HTTP 400 without modifying the source. These are editable snapshots, not live links.
The Pyodide adapter accepts the same payload with options
``{"action": "compose", "format": "json"}`` and returns UTF-8 JSON bytes.

Errors, hosting, and safety
----------------------------------------

API validation/render failures return HTTP 400 and ``{"error": "message"}``.
Unavailable startup/history configuration returns 404. Cross-origin local file
requests return 403. The server sends no-cache, nosniff, MIME, and length headers;
successful exports add a fixed attachment filename. A filtered task table also
returns ``X-Jsonantt-Table-Filter``.

This is a trusted local development server, not a multi-user service. Keep the
default loopback binding: local file APIs can read JSON files and list directories
accessible to the server account. They never write or run request-supplied shell
commands. Do not expose it to untrusted networks; authentication, authorization,
and resource limits are required for any such deployment.

Static hosting has no HTTP rendering/file/Git endpoints. It uses the same
``render_document`` implementation through the existing
``browser_renderer.render_json(source_text, options_json)`` worker adapter.
Uploaded comparison files work there; local filesystem/history access requires
``jsonantt serve``.
