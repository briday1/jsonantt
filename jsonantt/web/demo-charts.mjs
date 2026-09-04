/** Small starter documents used by the Examples menu and first run. */

export const STARTER = {
  title: 'Product delivery plan',
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
        { id: 'research', name: 'User research', start: '2026-01-05', duration: '6w' },
        { id: 'scoping', name: 'Scoping', not_before: 'research', duration: '3w' },
      ],
    },
    {
      id: 'build',
      name: 'Build',
      color: '#70AD47',
      not_before: 'discovery',
      duration: '5m',
    },
    {
      id: 'launch',
      name: 'Launch',
      milestone: true,
      major_milestone: true,
      not_before: 'build',
      color: '#FFD700',
    },
  ],
  arrows: [
    { from: 'discovery', to: 'build', label: 'hand-off' },
    { from: 'build', to: 'launch' },
  ],
};

export const MILESTONE_DEMO = {
  title: 'Milestone chain',
  dateformat: '%Y-%m-%d',
  style: { number_milestones: true },
  tasks: [
    { name: 'Phase 1', start: '2026-02-02', end: '2026-05-29', color: '#ED7D31' },
    { name: 'Gate reviews', milestone: true, date: ['2026-03-02', '2026-04-06', '2026-05-04'] },
    { name: 'Phase 2', start: '2026-06-01', end: '2026-10-30', color: '#7030A0' },
    { name: 'Go live', milestone: true, major_milestone: true, date: '2026-11-02' },
  ],
};

export const EXAMPLES = [
  { id: 'starter', label: 'Product delivery plan', data: STARTER },
  { id: 'milestones', label: 'Milestone chain', data: MILESTONE_DEMO },
];
