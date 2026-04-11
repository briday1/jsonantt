Command-Line Reference
======================

Synopsis
--------

.. code-block:: text

   jsonantt [OPTIONS] INPUT OUTPUT

``INPUT`` is a path to a JSON chart description file.
``OUTPUT`` is the destination image path. Supported formats: ``.png``, ``.pdf``, ``.svg``.

Modes
-----

jsonantt has five mutually-exclusive output modes. The default (no flag) is a Gantt chart.

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Flag
     - Description
   * - *(none)*
     - Gantt chart image
   * - ``-t`` / ``--table``
     - Task table image
   * - ``--burn``
     - Funded burn-down chart
   * - ``--burn-table``
     - Burn matrix table (time buckets × groups)
   * - ``--compare SECOND_JSON``
     - Side-by-side comparison of two JSON schedules

Gantt chart
-----------

.. code-block:: bash

   jsonantt project.json chart.png
   jsonantt project.json chart.png --dpi 300
   jsonantt project.json chart.png --renderdepth 2
   jsonantt project.json chart.png --date-line 2025-06-01
   jsonantt project.json chart.png --date-line today --date-line-color "#C00000"

Task table
----------

.. code-block:: bash

   jsonantt -t project.json table.png
   jsonantt -t project.json table.png --milestones-only
   jsonantt -t project.json table.png --no-milestones

Compare mode
------------

.. code-block:: bash

   jsonantt planned.json compare.png --compare actual.json
   jsonantt -t planned.json compare-table.png --compare actual.json

The **first** file is the baseline (planned / agreed).
The **second** file (``--compare``) is the updated or actual state.

Burn chart
----------

.. code-block:: bash

   # Monthly burn, grouped by top-level task (depth 0)
   jsonantt project.json burn.png --burn \
     --burn-field cost --burn-period month --burn-group 0

   # Quarterly burn, all leaf tasks
   jsonantt project.json burn.png --burn \
     --burn-field hours --burn-period quarter --burn-group leaf

   # Annual burn, apply a display multiplier (e.g. values in cents → dollars)
   jsonantt project.json burn.png --burn \
     --burn-field cost --burn-period year --burn-display-factor 0.01

Burn table
----------

.. code-block:: bash

   jsonantt project.json burn.csv --burn-table \
     --burn-field cost --burn-period month --burn-group 0

Option reference
----------------

.. list-table::
   :widths: 35 15 50
   :header-rows: 1

   * - Option
     - Default
     - Description
   * - ``--dpi INT``
     - ``150``
     - Image resolution (raster formats only).
   * - ``-r`` / ``--renderdepth INT``
     - ``0``
     - Maximum nesting depth to render. ``0`` renders all levels. ``1`` renders only top-level tasks, ``2`` includes one nesting level, and so on.
   * - ``--date-line DATE``
     - —
     - Draw a vertical line at this date. Accepts the chart's ``dateformat`` or the special value ``today``. Only valid for chart mode.
   * - ``--date-line-color COLOR``
     - ``#C00000``
     - Hex color for ``--date-line``.
   * - ``-c`` / ``--compare SECOND_JSON``
     - —
     - Enable compare mode. ``INPUT`` is the baseline; ``SECOND_JSON`` is the actual/updated schedule.
   * - ``--milestones-only``
     - —
     - Table mode only — render only milestone rows.
   * - ``--no-milestones``
     - —
     - Table mode only — exclude milestone rows.
   * - ``--burn-field FIELD``
     - ``cost``
     - Numeric task field to aggregate for burn output.
   * - ``--burn-period PERIOD``
     - ``month``
     - Bucket size: ``day``, ``week``, ``month``, ``quarter``, or ``year``.
   * - ``--burn-group GROUP``
     - ``0``
     - Grouping strategy: ``total`` (one line), ``leaf`` (per leaf task), or a non-negative integer depth (``0`` = top-level, ``1`` = second level, …).
   * - ``--burn-display-factor FACTOR``
     - ``1``
     - Display-only numeric multiplier applied to all burn output values (e.g. ``0.001`` to show thousands).

Exit codes
----------

.. list-table::
   :widths: 15 85
   :header-rows: 1

   * - Code
     - Meaning
   * - ``0``
     - Success
   * - ``1``
     - Input file not found, parse error, or render error
