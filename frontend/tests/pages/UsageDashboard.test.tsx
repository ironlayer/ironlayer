import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import UsageDashboard from '../../src/pages/UsageDashboard';

/* ------------------------------------------------------------------ */
/* Mocks                                                               */
/* ------------------------------------------------------------------ */

const mockSummary = {
  total_events: 1234,
  events_by_type: {
    plan_run: 45,
    plan_apply: 12,
    ai_call: 320,
    model_loaded: 150,
    backfill_run: 7,
    api_request: 700,
  },
  period_start: '2024-06-01T00:00:00Z',
  period_end: '2024-06-30T23:59:59Z',
};

const mockEvents = [
  {
    event_id: 'evt-abc123',
    tenant_id: 'test-tenant',
    event_type: 'plan_run',
    quantity: 1,
    created_at: '2024-06-15T12:00:00Z',
    metadata: {},
  },
  {
    event_id: 'evt-def456',
    tenant_id: 'test-tenant',
    event_type: 'ai_call',
    quantity: 1,
    created_at: '2024-06-15T12:01:00Z',
    metadata: {},
  },
];

vi.mock('../../src/hooks/useUsage', () => ({
  useUsageSummary: vi.fn(() => ({
    summary: mockSummary,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
  useUsageEvents: vi.fn(() => ({
    events: mockEvents,
    total: 2,
    loading: false,
    error: null,
    refetch: vi.fn(),
  })),
}));

// Mock recharts to avoid rendering issues in test environment
vi.mock('recharts', () => ({
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => null,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  Legend: () => null,
}));

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('UsageDashboard', () => {
  it('renders the page header', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('Usage Dashboard')).toBeInTheDocument();
    expect(
      screen.getByText('Monitor platform usage across all metered operations')
    ).toBeInTheDocument();
  });

  it('renders period selector with options', () => {
    render(<UsageDashboard />);
    const select = screen.getAllByRole('combobox')[0];
    expect(select).toBeInTheDocument();
    expect(screen.getByText('Last 7 days')).toBeInTheDocument();
    expect(screen.getByText('Last 14 days')).toBeInTheDocument();
    expect(screen.getByText('Last 30 days')).toBeInTheDocument();
    expect(screen.getByText('Last 90 days')).toBeInTheDocument();
  });

  it('renders stat cards for all event types', () => {
    render(<UsageDashboard />);
    // Some labels appear in both stat cards and quota section, so use getAllByText
    expect(screen.getAllByText('Plan Runs').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Plan Applies').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('AI Calls').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Models Loaded').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Backfills').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('API Requests').length).toBeGreaterThanOrEqual(1);
  });

  it('displays correct event counts in stat cards', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('320')).toBeInTheDocument();
    expect(screen.getByText('150')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument();
    expect(screen.getByText('700')).toBeInTheDocument();
  });

  it('shows total events banner', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('Total Events')).toBeInTheDocument();
    expect(screen.getByText('1,234')).toBeInTheDocument();
  });

  it('renders bar chart section', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('Events by Type')).toBeInTheDocument();
    expect(screen.getByTestId('bar-chart')).toBeInTheDocument();
  });

  it('renders quota usage section', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('Quota Usage')).toBeInTheDocument();
  });

  it('renders recent events table', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('Recent Events')).toBeInTheDocument();
    expect(screen.getByText('Event')).toBeInTheDocument();
    expect(screen.getByText('Type')).toBeInTheDocument();
    expect(screen.getByText('Qty')).toBeInTheDocument();
    expect(screen.getByText('Timestamp')).toBeInTheDocument();
  });

  it('displays events in the table', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('evt-abc123')).toBeInTheDocument();
    expect(screen.getByText('evt-def456')).toBeInTheDocument();
  });

  it('shows total count in the events header', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('2 total')).toBeInTheDocument();
  });

  it('renders event type filter dropdown in events table', () => {
    render(<UsageDashboard />);
    expect(screen.getByText('All types')).toBeInTheDocument();
  });

  it('stat cards are clickable for filtering', () => {
    render(<UsageDashboard />);
    // Find the button that contains "Plan Runs" text
    const buttons = screen.getAllByRole('button');
    const planRunButton = buttons.find(
      (btn) => btn.textContent?.includes('Plan Runs')
    );
    expect(planRunButton).toBeTruthy();
  });
});

describe('UsageDashboard - error state', () => {
  it('displays error message when data loading fails', async () => {
    // Override the mock for this test
    const { useUsageSummary } = await import('../../src/hooks/useUsage');
    (useUsageSummary as any).mockReturnValueOnce({
      summary: null,
      loading: false,
      error: 'Network error',
      refetch: vi.fn(),
    });

    render(<UsageDashboard />);
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });
});
