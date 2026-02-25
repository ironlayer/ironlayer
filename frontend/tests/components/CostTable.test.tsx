import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import CostTable from '../../src/components/CostTable';
import type { PlanStep } from '../../src/api/types';

/* ------------------------------------------------------------------ */
/* Test data                                                           */
/* ------------------------------------------------------------------ */

const sampleSteps: PlanStep[] = [
  {
    step_id: 'step-1',
    model: 'fct_orders',
    run_type: 'FULL_REFRESH',
    input_range: null,
    depends_on: [],
    parallel_group: 0,
    reason: 'Schema change',
    estimated_compute_seconds: 600,
    estimated_cost_usd: 5.0,
  },
  {
    step_id: 'step-2',
    model: 'dim_customers',
    run_type: 'INCREMENTAL',
    input_range: { start: '2026-01-01', end: '2026-01-31' },
    depends_on: ['step-1'],
    parallel_group: 1,
    reason: 'Downstream refresh',
    estimated_compute_seconds: 120,
    estimated_cost_usd: 1.5,
  },
  {
    step_id: 'step-3',
    model: 'stg_events',
    run_type: 'INCREMENTAL',
    input_range: { start: '2026-02-01', end: '2026-02-15' },
    depends_on: [],
    parallel_group: 0,
    reason: 'New data',
    estimated_compute_seconds: 300,
    estimated_cost_usd: 3.25,
  },
];

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('CostTable', () => {
  it('renders cost breakdown rows for each step', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getByText('fct_orders')).toBeInTheDocument();
    expect(screen.getByText('dim_customers')).toBeInTheDocument();
    expect(screen.getByText('stg_events')).toBeInTheDocument();
  });

  it('displays run type badges', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getByText('FULL REFRESH')).toBeInTheDocument();
    // INCREMENTAL appears twice
    const incrementals = screen.getAllByText('INCREMENTAL');
    expect(incrementals).toHaveLength(2);
  });

  it('displays estimated cost for each row', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getByText('$5.00')).toBeInTheDocument();
    expect(screen.getByText('$1.50')).toBeInTheDocument();
    expect(screen.getByText('$3.25')).toBeInTheDocument();
  });

  it('displays formatted runtime for each row', () => {
    render(<CostTable steps={sampleSteps} />);
    // 600s -> "10m", 120s -> "2m", 300s -> "5m"
    expect(screen.getByText('10m')).toBeInTheDocument();
    expect(screen.getByText('2m')).toBeInTheDocument();
    expect(screen.getByText('5m')).toBeInTheDocument();
  });

  it('displays input range for steps that have one, and "--" for null ranges', () => {
    render(<CostTable steps={sampleSteps} />);
    // step-1 has null input_range -> "--"
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  it('displays parallel group labels', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getAllByText('Group 0')).toHaveLength(2);
    expect(screen.getByText('Group 1')).toBeInTheDocument();
  });

  it('shows total cost row with correct sum', () => {
    render(<CostTable steps={sampleSteps} />);
    // Total: 5.0 + 1.5 + 3.25 = 9.75
    expect(screen.getByText('$9.75')).toBeInTheDocument();
  });

  it('shows total row with step count', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getByText('Total (3 steps)')).toBeInTheDocument();
  });

  it('shows singular "step" for a single-step plan', () => {
    render(<CostTable steps={[sampleSteps[0]]} />);
    expect(screen.getByText('Total (1 step)')).toBeInTheDocument();
  });

  it('shows total runtime in the footer', () => {
    render(<CostTable steps={sampleSteps} />);
    // Total runtime: 600+120+300 = 1020s -> 17m
    expect(screen.getByText('17m')).toBeInTheDocument();
  });

  it('renders all six column headers', () => {
    render(<CostTable steps={sampleSteps} />);
    expect(screen.getByText('Model')).toBeInTheDocument();
    expect(screen.getByText('Run Type')).toBeInTheDocument();
    expect(screen.getByText('Input Range')).toBeInTheDocument();
    expect(screen.getByText('Est. Runtime')).toBeInTheDocument();
    expect(screen.getByText('Est. Cost')).toBeInTheDocument();
    expect(screen.getByText('Cluster Group')).toBeInTheDocument();
  });

  it('sorts by cost column in descending order by default', () => {
    const { container } = render(<CostTable steps={sampleSteps} />);
    // Default sort: estimated_cost_usd DESC -> fct_orders ($5.00) first, then stg_events ($3.25), then dim_customers ($1.50)
    const tbody = container.querySelector('tbody');
    expect(tbody).toBeTruthy();
    const rows = tbody!.querySelectorAll('tr');
    expect(rows).toHaveLength(3);
    // First row should be the highest cost model
    expect(within(rows[0]).getByText('fct_orders')).toBeInTheDocument();
    // Second row
    expect(within(rows[1]).getByText('stg_events')).toBeInTheDocument();
    // Third row
    expect(within(rows[2]).getByText('dim_customers')).toBeInTheDocument();
  });

  it('toggles sort direction when clicking the same column header', () => {
    const { container } = render(<CostTable steps={sampleSteps} />);
    const costHeader = screen.getByText('Est. Cost');

    // Click cost header to toggle to ascending
    fireEvent.click(costHeader);

    const tbody = container.querySelector('tbody');
    const rows = tbody!.querySelectorAll('tr');
    // ASC order: dim_customers ($1.50), stg_events ($3.25), fct_orders ($5.00)
    expect(within(rows[0]).getByText('dim_customers')).toBeInTheDocument();
    expect(within(rows[1]).getByText('stg_events')).toBeInTheDocument();
    expect(within(rows[2]).getByText('fct_orders')).toBeInTheDocument();
  });

  it('sorts by model name when clicking Model column', () => {
    const { container } = render(<CostTable steps={sampleSteps} />);
    const modelHeader = screen.getByText('Model');

    // Click model header -> sets field to 'model', direction to 'desc'
    fireEvent.click(modelHeader);

    const tbody = container.querySelector('tbody');
    const rows = tbody!.querySelectorAll('tr');
    // DESC alphabetical: stg_events, fct_orders, dim_customers
    expect(within(rows[0]).getByText('stg_events')).toBeInTheDocument();
    expect(within(rows[1]).getByText('fct_orders')).toBeInTheDocument();
    expect(within(rows[2]).getByText('dim_customers')).toBeInTheDocument();
  });

  it('handles empty steps array', () => {
    const { container } = render(<CostTable steps={[]} />);
    // Should render the table structure but no body rows
    const tbody = container.querySelector('tbody');
    expect(tbody).toBeTruthy();
    const rows = tbody!.querySelectorAll('tr');
    expect(rows).toHaveLength(0);

    // Total row should show 0 steps and $0.00
    expect(screen.getByText('Total (0 steps)')).toBeInTheDocument();
    expect(screen.getByText('$0.00')).toBeInTheDocument();
  });

  it('highlights high-cost rows with amber background', () => {
    // HIGH_COST_THRESHOLD = totalCost / steps.length * 2
    // totalCost = 9.75, steps.length = 3, threshold = 9.75/3*2 = 6.50
    // Only fct_orders ($5.00) is below threshold, so none are high-cost in this data.
    // Let's create data where one step clearly exceeds threshold.
    const skewedSteps: PlanStep[] = [
      { ...sampleSteps[0], estimated_cost_usd: 20.0 },
      { ...sampleSteps[1], estimated_cost_usd: 1.0 },
      { ...sampleSteps[2], estimated_cost_usd: 1.0 },
    ];
    // totalCost = 22, threshold = 22/3*2 ~= 14.67
    // fct_orders ($20) > 14.67 -> high cost
    const { container } = render(<CostTable steps={skewedSteps} />);
    const tbody = container.querySelector('tbody');
    const rows = tbody!.querySelectorAll('tr');
    // First row (highest cost, desc sort) should have amber class
    expect(rows[0].className).toContain('bg-amber-50/50');
  });
});
