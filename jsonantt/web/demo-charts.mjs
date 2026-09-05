/** Small starter documents used by ?demo=1 / ?demo=2 and first run. */

export const STARTER = {
  title: 'Product delivery plan',
  description: 'A product roadmap from discovery through launch, with chained work and dependency arrows.',
  dateformat: '%Y-%m-%d',
  style: {
    subtask_lightening_pct: 25,
    major_tick: 'year',
    minor_tick: 'quarter',
  },
  tasks: [
    {
      id: 'discovery',
      name: 'Discovery',
      color: '#4472C4',
      tasks: [
        { id: 'research', name: 'User research', start: '2026-01-05', duration: '6w', description: 'Interview customers and synthesize the main product needs.' },
        { id: 'scoping', name: 'Scoping', not_before: 'research', duration: '3w', description: 'Turn research findings into a delivery scope and release plan.' },
      ],
    },
    {
      id: 'build',
      name: 'Build',
      color: '#70AD47',
      not_before: 'discovery',
      duration: '5m',
      description: 'Implement, integrate, and validate the agreed product scope.',
    },
    {
      id: 'launch',
      name: 'Launch',
      milestone: true,
      major_milestone: true,
      not_before: 'build',
      color: '#FFD700',
      description: 'Release the completed product to customers.',
    },
  ],
  arrows: [
    { from: 'discovery', to: 'build', label: 'hand-off' },
    { from: 'build', to: 'launch' },
  ],
};

export const MILESTONE_DEMO = {
  title: 'Milestone chain',
  description: 'A two-phase delivery plan with recurring reviews and a major go-live milestone.',
  dateformat: '%Y-%m-%d',
  style: { number_milestones: true },
  tasks: [
    { name: 'Phase 1', start: '2026-02-02', end: '2026-05-29', color: '#ED7D31', description: 'Complete the first delivery phase and prepare for formal review.' },
    { name: 'Gate reviews', milestone: true, date: ['2026-03-02', '2026-04-06', '2026-05-04'], description: 'Recurring checkpoints for scope, quality, and delivery readiness.' },
    { name: 'Phase 2', start: '2026-06-01', end: '2026-10-30', color: '#7030A0', description: 'Complete the second delivery phase and production preparation.' },
    { name: 'Go live', milestone: true, major_milestone: true, date: '2026-11-02', description: 'Production launch and transition to operations.' },
  ],
};

export const COST_DEMO = {
  title: 'Delivery budget',
  description: 'Planned spend across discovery and delivery. Compare period-spend bars in Burn, remaining allocation in Burndown, and cumulative allocation with dotted task budgets in Burnup. Explore cost or effort, reporting periods, and task grouping.',
  dateformat: '%Y-%m-%d',
  style: {
    major_tick: 'month', minor_tick: 'week', number_milestones: true,
    table_columns: ['task', 'name', { field: 'cost', title: 'Cost ($)', rollup: 'sum', total: true },
      { field: 'effort', title: 'Effort (days)', rollup: 'sum', total: true }, 'description'],
  },
  tasks: [
    { id: 'discovery', name: 'Discovery', description: 'Understand needs and agree scope.', color: '#4472C4', tasks: [
      { id: 'research', name: 'Research', start: '2026-01-01', end: '2026-02-01', cost: 18000, effort: 30, description: 'Customer interviews and synthesis.' },
      { id: 'scope', name: 'Scope', start: '2026-02-01', end: '2026-03-01', cost: 12000, effort: 20, description: 'Define the delivery plan.' },
    ] },
    { id: 'delivery', name: 'Delivery', description: 'Build and release the product.', color: '#70AD47', tasks: [
      { id: 'build', name: 'Build', start: '2026-02-15', end: '2026-05-01', cost: 60000, effort: 100, description: 'Implementation and integration.' },
      { id: 'test', name: 'Validation', start: '2026-04-01', end: '2026-05-15', cost: 24000, effort: 40, description: 'Acceptance testing and release readiness.' },
      { id: 'launch', name: 'Launch', milestone: true, date: '2026-05-15', cost: 6000, effort: 10, description: 'Production launch and handover.' },
    ] },
  ],
  arrows: [{ from: 'research', to: 'scope' }, { from: 'test', to: 'launch' }],
};

export const DEMOS = Object.freeze({ 1: STARTER, 2: MILESTONE_DEMO, 3: COST_DEMO });
