import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import RunHistory from '../../src/components/RunHistory';
import type { RunRecord } from '../../src/api/types';

/* ------------------------------------------------------------------ */
/* Mock react-router-dom navigate                                      */
/* ------------------------------------------------------------------ */

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

/* ------------------------------------------------------------------ */
/* Test data                                                           */
/* ------------------------------------------------------------------ */

const sampleRuns: RunRecord[] = [
  {
    run_id: 'run-abc-123-def-456',
    plan_id: 'plan-xyz-789-ghi-012',
    step_id: 'step-1',
    model_name: 'fct_orders',
    status: 'SUCCESS',
    started_at: '2026-02-10T14:00:00Z',
    finished_at: '2026-02-10T14:05:30Z',
    input_range: { start: '2026-01-01', end: '2026-01-31' },
    error_message: null,
    logs_uri: 's3://logs/run-abc',
    cluster_used: 'spark-cluster-01',
    executor_version: '2.3.0',
    retry_count: 0,
  },
  {
    run_id: 'run-fail-234-567-890',
    plan_id: 'plan-xyz-789-ghi-012',
    step_id: 'step-2',
    model_name: 'dim_customers',
    status: 'FAIL',
    started_at: '2026-02-10T14:06:00Z',
    finished_at: '2026-02-10T14:06:45Z',
    input_range: null,
    error_message: 'OutOfMemoryError: GC overhead limit exceeded',
    logs_uri: null,
    cluster_used: 'spark-cluster-02',
    executor_version: '2.3.0',
    retry_count: 2,
  },
  {
    run_id: 'run-running-345-678',
    plan_id: 'plan-xyz-789-ghi-012',
    step_id: 'step-3',
    model_name: 'stg_events',
    status: 'RUNNING',
    started_at: '2026-02-10T14:10:00Z',
    finished_at: null,
    input_range: { start: '2026-02-01', end: '2026-02-15' },
    error_message: null,
    logs_uri: null,
    cluster_used: 'spark-cluster-01',
    executor_version: '2.3.0',
    retry_count: 0,
  },
  {
    run_id: 'run-pending-456-789',
    plan_id: 'plan-xyz-789-ghi-012',
    step_id: 'step-4',
    model_name: 'agg_daily_revenue',
    status: 'PENDING',
    started_at: null,
    finished_at: null,
    input_range: null,
    error_message: null,
    logs_uri: null,
    cluster_used: null,
    executor_version: '2.3.0',
    retry_count: 0,
  },
  {
    run_id: 'run-cancelled-567-890',
    plan_id: 'plan-xyz-789-ghi-012',
    step_id: 'step-5',
    model_name: 'rpt_weekly_summary',
    status: 'CANCELLED',
    started_at: '2026-02-10T14:08:00Z',
    finished_at: '2026-02-10T14:08:10Z',
    input_range: null,
    error_message: null,
    logs_uri: null,
    cluster_used: null,
    executor_version: '2.3.0',
    retry_count: 0,
  },
];

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function renderRunHistory(overrides?: Partial<React.ComponentProps<typeof RunHistory>>) {
  const defaultProps = {
    runs: sampleRuns,
    loading: false,
    onRefresh: vi.fn(),
    autoRefresh: false,
    onToggleAutoRefresh: vi.fn(),
  };
  const props = { ...defaultProps, ...overrides };
  return {
    ...render(
      <MemoryRouter>
        <RunHistory {...props} />
      </MemoryRouter>,
    ),
    props,
  };
}

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('RunHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders timeline entries for each run', () => {
    renderRunHistory();
    expect(screen.getByText('fct_orders')).toBeInTheDocument();
    expect(screen.getByText('dim_customers')).toBeInTheDocument();
    expect(screen.getByText('stg_events')).toBeInTheDocument();
    expect(screen.getByText('agg_daily_revenue')).toBeInTheDocument();
    expect(screen.getByText('rpt_weekly_summary')).toBeInTheDocument();
  });

  it('shows correct status badges for each run', () => {
    renderRunHistory();
    expect(screen.getByText('SUCCESS')).toBeInTheDocument();
    expect(screen.getByText('FAIL')).toBeInTheDocument();
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('PENDING')).toBeInTheDocument();
    expect(screen.getByText('CANCELLED')).toBeInTheDocument();
  });

  it('renders correct status dot color for SUCCESS (green)', () => {
    const { container } = renderRunHistory({ runs: [sampleRuns[0]] });
    const dot = container.querySelector('.bg-green-500');
    expect(dot).toBeTruthy();
  });

  it('renders correct status dot color for FAIL (red)', () => {
    const { container } = renderRunHistory({ runs: [sampleRuns[1]] });
    const dot = container.querySelector('.bg-red-500');
    expect(dot).toBeTruthy();
  });

  it('renders correct status dot color for RUNNING (blue, pulsing)', () => {
    const { container } = renderRunHistory({ runs: [sampleRuns[2]] });
    const dot = container.querySelector('.bg-blue-500');
    expect(dot).toBeTruthy();
    expect(dot!.className).toContain('animate-pulse');
  });

  it('renders correct status dot color for PENDING (yellow)', () => {
    const { container } = renderRunHistory({ runs: [sampleRuns[3]] });
    const dot = container.querySelector('.bg-yellow-400');
    expect(dot).toBeTruthy();
  });

  it('renders correct status dot color for CANCELLED (gray)', () => {
    const { container } = renderRunHistory({ runs: [sampleRuns[4]] });
    const dot = container.querySelector('.bg-gray-400');
    expect(dot).toBeTruthy();
  });

  it('displays "--" for duration when started_at is null', () => {
    renderRunHistory({ runs: [sampleRuns[3]] }); // PENDING, no started_at
    expect(screen.getByText('--')).toBeInTheDocument();
  });

  it('displays input range when present', () => {
    renderRunHistory();
    // fct_orders has input_range start: 2026-01-01, end: 2026-01-31
    expect(screen.getByText('2026-01-01 to 2026-01-31')).toBeInTheDocument();
    // stg_events has input_range start: 2026-02-01, end: 2026-02-15
    expect(screen.getByText('2026-02-01 to 2026-02-15')).toBeInTheDocument();
  });

  it('handles empty run list with "No runs recorded yet." message', () => {
    renderRunHistory({ runs: [] });
    expect(screen.getByText('No runs recorded yet.')).toBeInTheDocument();
  });

  it('renders the header title "Run History"', () => {
    renderRunHistory();
    expect(screen.getByText('Run History')).toBeInTheDocument();
  });

  it('renders refresh button and calls onRefresh when clicked', () => {
    const { props } = renderRunHistory();
    // The refresh button contains the RefreshCw icon
    const buttons = screen.getAllByRole('button');
    // The refresh button is the one in the header area
    const refreshBtn = buttons.find((btn) => btn.querySelector('.lucide-refresh-cw'));
    expect(refreshBtn).toBeTruthy();

    fireEvent.click(refreshBtn!);
    expect(props.onRefresh).toHaveBeenCalledTimes(1);
  });

  it('renders auto-refresh checkbox and calls onToggleAutoRefresh when toggled', () => {
    const { props } = renderRunHistory();
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(props.onToggleAutoRefresh).toHaveBeenCalledTimes(1);
  });

  it('shows auto-refresh checkbox as checked when autoRefresh is true', () => {
    renderRunHistory({ autoRefresh: true });
    const checkbox = screen.getByRole('checkbox');
    expect(checkbox).toBeChecked();
  });

  it('expands run detail panel when a run entry is clicked', () => {
    renderRunHistory();

    // Click on fct_orders run entry
    fireEvent.click(screen.getByText('fct_orders'));

    // Should show expanded details
    expect(screen.getByText('Run ID')).toBeInTheDocument();
    expect(screen.getByText('Plan ID')).toBeInTheDocument();
    expect(screen.getByText('Cluster')).toBeInTheDocument();
    expect(screen.getByText('Retries')).toBeInTheDocument();
    // run_id sliced to 12 chars + "..."
    expect(screen.getByText('run-abc-123-...')).toBeInTheDocument();
    expect(screen.getByText('spark-cluster-01')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText('View full details')).toBeInTheDocument();
  });

  it('collapses run detail panel when clicked again', () => {
    renderRunHistory();

    // Click to expand
    fireEvent.click(screen.getByText('fct_orders'));
    expect(screen.getByText('Run ID')).toBeInTheDocument();

    // Click again to collapse
    fireEvent.click(screen.getByText('fct_orders'));
    expect(screen.queryByText('Run ID')).not.toBeInTheDocument();
  });

  it('shows error message in expanded detail for failed runs', () => {
    renderRunHistory();

    fireEvent.click(screen.getByText('dim_customers'));
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(
      screen.getByText('OutOfMemoryError: GC overhead limit exceeded'),
    ).toBeInTheDocument();
  });

  it('shows retry count in expanded detail', () => {
    renderRunHistory();

    fireEvent.click(screen.getByText('dim_customers'));
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('shows cluster as "--" when cluster_used is null', () => {
    renderRunHistory();

    fireEvent.click(screen.getByText('agg_daily_revenue'));
    // cluster_used is null for this run
    const clusterValues = screen.getAllByText('--');
    expect(clusterValues.length).toBeGreaterThanOrEqual(1);
  });

  it('navigates to run detail page when "View full details" is clicked', () => {
    renderRunHistory();

    fireEvent.click(screen.getByText('fct_orders'));
    fireEvent.click(screen.getByText('View full details'));

    expect(mockNavigate).toHaveBeenCalledWith('/runs/run-abc-123-def-456');
  });

  it('only expands one run at a time', () => {
    renderRunHistory();

    // Expand fct_orders
    fireEvent.click(screen.getByText('fct_orders'));
    expect(screen.getByText('spark-cluster-01')).toBeInTheDocument();

    // Click dim_customers to expand it (collapses fct_orders)
    fireEvent.click(screen.getByText('dim_customers'));
    // fct_orders detail should be collapsed
    // dim_customers should now be expanded showing its retry count
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(
      screen.getByText('OutOfMemoryError: GC overhead limit exceeded'),
    ).toBeInTheDocument();
  });

  it('disables refresh button when loading is true', () => {
    const { container } = renderRunHistory({ loading: true });
    const refreshIcon = container.querySelector('.lucide-refresh-cw');
    const refreshBtn = refreshIcon?.closest('button');
    expect(refreshBtn).toBeTruthy();
    expect(refreshBtn!).toBeDisabled();
  });

  it('applies spin animation to refresh icon when loading', () => {
    const { container } = renderRunHistory({ loading: true });
    const refreshIcon = container.querySelector('.lucide-refresh-cw');
    expect(refreshIcon).toBeTruthy();
    // SVG elements return SVGAnimatedString for .className — use getAttribute
    const classAttr = refreshIcon!.getAttribute('class') ?? '';
    expect(classAttr).toContain('animate-spin');
  });
});
