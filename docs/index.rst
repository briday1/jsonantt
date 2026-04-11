jsonantt
========

.. image:: _static/logo.png
   :alt: jsonantt logo
   :width: 160px
   :align: right

**jsonantt** turns a plain JSON file into a polished Gantt chart image in one command.
No code required — describe your project in JSON, run ``jsonantt``, get a PNG.

.. code-block:: bash

   pip install jsonantt
   jsonantt project.json chart.png

What it can do
--------------

.. list-table::
   :widths: 30 70
   :header-rows: 0

   * - **Gantt chart**
     - Hierarchical task bars with auto-colored phases, milestones, tick marks, and gridlines
   * - **Task table**
     - Formatted image table of tasks with optional milestone-only or no-milestone filtering
   * - **Compare mode**
     - Side-by-side baseline vs. actual schedule diff in both chart and table form
   * - **Burn chart**
     - Funded burn-down chart from any numeric task field (cost, hours, points, …)
   * - **Duration scheduling**
     - Tasks defined with ``duration`` instead of an end date (days, weeks, months, years)
   * - **Dependency chaining**
     - ``not_before`` links automatically cascade start dates across tasks and phases
   * - **Deep nesting**
     - Unlimited parent/child hierarchy; summary bars auto-span their children
   * - **Style control**
     - 25+ style fields covering layout, typography, colors, ticks, gridlines, and table appearance

----

.. toctree::
   :maxdepth: 2
   :caption: Getting started

   quickstart

.. toctree::
   :maxdepth: 2
   :caption: Reference

   json-reference
   style-guide
   cli

.. toctree::
   :maxdepth: 2
   :caption: Walkthroughs

   examples
