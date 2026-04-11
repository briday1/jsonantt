Style Guide
===========

All style fields live inside the ``"style"`` object at the top level of your JSON file.
Every field is optional — the defaults produce a clean, publication-ready chart with no configuration needed.

.. code-block:: json

   {
     "style": {
       "major_tick": "year",
       "minor_tick": "quarter",
       "font_size": 11
     },
     "tasks": [ "..." ]
   }

All fields at a glance
----------------------

.. list-table::
   :widths: 28 16 14 42
   :header-rows: 1

   * - Field
     - Category
     - Default
     - Purpose
   * - ``width``
     - Layout
     - ``14.0``
     - Figure width in inches
   * - ``row_height``
     - Layout
     - ``0.3``
     - Row height in inches
   * - ``bar_height``
     - Layout
     - ``0.5``
     - Bar height as fraction of row height
   * - ``label_fraction``
     - Layout
     - ``0.0``
     - Label panel width (0 = auto)
   * - ``indent_size``
     - Layout
     - ``3``
     - Spaces added per nesting depth
   * - ``font_size``
     - Typography
     - ``12.0``
     - Base font size in points
   * - ``bold_tasks``
     - Typography
     - ``true``
     - Auto-bold top-level task labels
   * - ``number_tasks``
     - Typography
     - ``true``
     - Prefix labels with hierarchy numbers
   * - ``background``
     - Colors
     - ``"#FFFFFF"``
     - Figure background color
   * - ``grid_color``
     - Colors
     - ``"#E0E0E0"``
     - Vertical gridline color
   * - ``row_band_color``
     - Colors
     - ``"#F5F5F5"``
     - Alternating row band fill
   * - ``colors``
     - Colors
     - 10-color palette
     - Auto-cycle colors for top-level tasks
   * - ``subtask_lightening_pct``
     - Colors
     - ``0.0``
     - Lighten child colors per depth level (%)
   * - ``milestone_color``
     - Milestones
     - ``"#FFD700"``
     - Default milestone marker color
   * - ``milestone_marker``
     - Milestones
     - ``"D"``
     - Default milestone marker symbol
   * - ``milestone_size``
     - Milestones
     - ``14.0``
     - Default milestone marker size (pts)
   * - ``major_tick``
     - Ticks
     - ``null``
     - Major tick interval (year/quarter/month/week/day)
   * - ``minor_tick``
     - Ticks
     - ``null``
     - Minor tick interval (year/quarter/month/week/day)
   * - ``major_grid_width``
     - Ticks
     - ``2.0``
     - Major gridline linewidth
   * - ``minor_grid_width``
     - Ticks
     - ``1.5``
     - Minor gridline linewidth
   * - ``tick_position``
     - Ticks
     - ``"top"``
     - Tick label position: top / bottom / both
   * - ``table_colorize``
     - Table
     - ``true``
     - Show color accent gutter in table output
   * - ``table_show_markers``
     - Table
     - ``true``
     - Draw milestone markers in table output
   * - ``table_columns``
     - Table
     - ``[]``
     - Custom ordered column definitions

Layout
------

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``width``
     - ``14.0``
     - Figure width in inches. Increase for wide date ranges or many columns.
   * - ``row_height``
     - ``0.3``
     - Height of each row in inches. Lower values produce a more compact chart.
   * - ``bar_height``
     - ``0.5``
     - Bar height as a fraction of ``row_height``. ``0.5`` means the bar occupies half the row.
   * - ``label_fraction``
     - ``0.0``
     - Width of the task label panel as a fraction of the total figure width. ``0.0`` (default) auto-sizes the panel to fit the longest label.
   * - ``indent_size``
     - ``3``
     - Number of extra space characters added per nesting depth in the label panel.

Typography
----------

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``font_size``
     - ``12.0``
     - Base font size in points, applied to both task labels and tick labels.
   * - ``bold_tasks``
     - ``true``
     - When ``true``, depth-0 (top-level) task labels are automatically rendered in bold. Individual tasks can override this with the ``bold`` field.
   * - ``number_tasks``
     - ``true``
     - Prefix task labels with hierarchical numbers (``1``, ``1.1``, ``1.1.1``, …).

Colors
------

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``background``
     - ``"#FFFFFF"``
     - Figure and axes background color.
   * - ``grid_color``
     - ``"#E0E0E0"``
     - Color of all vertical gridlines.
   * - ``row_band_color``
     - ``"#F5F5F5"``
     - Alternating row band fill color (every other row is tinted). Also used as the label panel background tint.
   * - ``colors``
     - see below
     - Ordered list of hex colors automatically cycled across top-level tasks that have no explicit ``color``. The default palette is 10 colors (steel blue, orange, green, coral, sky blue, amber, purple, cyan, hot pink, emerald).
   * - ``subtask_lightening_pct``
     - ``0.0``
     - Percentage to lighten a child task's inherited parent color per depth step. ``25`` means each level is 25% lighter. Set to ``0`` to disable.

Milestones
----------

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``milestone_color``
     - ``"#FFD700"``
     - Default fill color for milestone markers when no task-level ``color`` is set.
   * - ``milestone_marker``
     - ``"D"``
     - Default matplotlib marker symbol for milestones. Common options: ``"D"`` (diamond), ``"*"`` (star), ``"^"`` (triangle), ``"o"`` (circle), ``"s"`` (square).
   * - ``milestone_size``
     - ``14.0``
     - Default marker size in points. Override per-task with ``marker_size``.

Tick marks and gridlines
------------------------

jsonantt draws two levels of tick marks: a *major* level (prominent gridlines, bold labels) and a *minor* level (lighter gridlines, no labels).

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``major_tick``
     - ``null``
     - Major tick interval. One of ``"year"``, ``"quarter"``, ``"month"``, ``"week"``, or ``"day"``. ``null`` disables major ticks.
   * - ``minor_tick``
     - ``null``
     - Minor tick interval. Same values as ``major_tick``. Typically set to a finer interval than ``major_tick``.
   * - ``major_grid_width``
     - ``2.0``
     - Linewidth of major gridlines.
   * - ``minor_grid_width``
     - ``1.5``
     - Linewidth of minor gridlines.
   * - ``tick_position``
     - ``"top"``
     - Where to draw the x-axis tick labels. Options: ``"top"``, ``"bottom"``, or ``"both"``.

Typical tick combinations:

.. list-table::
   :widths: 30 30 40
   :header-rows: 1

   * - ``major_tick``
     - ``minor_tick``
     - Best for
   * - ``"year"``
     - ``"quarter"``
     - Multi-year roadmaps
   * - ``"quarter"``
     - ``"month"``
     - 1–2 year plans
   * - ``"month"``
     - ``"week"``
     - Quarterly sprints
   * - ``"week"``
     - ``"day"``
     - Short-horizon detail

Table output
------------

These fields only affect ``-t`` / ``--table`` output.

.. list-table::
   :widths: 30 15 55
   :header-rows: 1

   * - Field
     - Default
     - Description
   * - ``table_colorize``
     - ``true``
     - Show task bar colors as an accent gutter in the table.
   * - ``table_show_markers``
     - ``true``
     - Draw milestone diamond markers in the table output.
   * - ``table_columns``
     - ``[]``
     - Ordered list of column definition objects. Empty list uses the default column set. See sub-table below.

``table_columns`` column definition object
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each entry in ``table_columns`` is an object with the following fields:

.. list-table::
   :widths: 20 12 18 50
   :header-rows: 1

   * - Field
     - Type
     - Default
     - Description
   * - ``field``
     - string
     - **required**
     - The data key to display. Built-in values: ``name``, ``start``, ``end``, ``duration``. Any custom key stored on a task (e.g. ``cost``, ``owner``) works too.
   * - ``label``
     - string
     - same as ``field``
     - Column header text.
   * - ``width``
     - number
     - auto
     - Column width in pixels.
   * - ``align``
     - string
     - ``"left"``
     - Text alignment: ``"left"``, ``"center"``, or ``"right"``.

.. code-block:: json

   {
     "style": {
       "table_columns": [
         { "field": "name",  "label": "Task",       "width": 220 },
         { "field": "start", "label": "Start",      "width": 100, "align": "center" },
         { "field": "end",   "label": "End",        "width": 100, "align": "center" },
         { "field": "owner", "label": "Owner",      "width": 120 },
         { "field": "cost",  "label": "Budget ($)", "width": 100, "align": "right" }
       ]
     }
   }

Full style example
------------------

This is the style block from the bundled ``complex.json`` example:

.. code-block:: json

   {
     "style": {
       "row_height": 0.3,
       "font_size": 12,
       "indent_size": 3,
       "subtask_lightening_pct": 25,
       "major_tick": "year",
       "minor_tick": "quarter",
       "tick_position": "both"
     }
   }

And a maximally-configured reference block showing every field:

.. code-block:: json

   {
     "style": {
       "width": 16.0,
       "row_height": 0.28,
       "bar_height": 0.5,
       "font_size": 11.0,
       "indent_size": 3,
       "label_fraction": 0.0,
       "subtask_lightening_pct": 20,
       "background": "#FFFFFF",
       "grid_color": "#E0E0E0",
       "row_band_color": "#F5F5F5",
       "milestone_color": "#FFD700",
       "milestone_marker": "D",
       "milestone_size": 14.0,
       "major_tick": "year",
       "minor_tick": "quarter",
       "major_grid_width": 2.0,
       "minor_grid_width": 1.5,
       "tick_position": "top",
       "bold_tasks": true,
       "number_tasks": true,
       "table_colorize": true,
       "table_show_markers": true
     }
   }
