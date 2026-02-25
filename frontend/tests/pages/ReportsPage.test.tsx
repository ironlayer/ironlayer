import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ReportsPage from '../../src/pages/ReportsPage';

/* ------------------------------------------------------------------ */
/* Mock data                                                           */
/* ------------------------------------------------------------------ */

const mockCostReport = {
  items: [
    { model: 'gpt-4o-mini', cost_usd: 45.2, run_count: 120 },
    { model: 'claude-3-haiku', cost_usd: 12.8, run_count: 85 },
  ],
  total_cost_usd: 58.0,
  period: { since: '2024-06-01', until: '2024-06-30' },
  group_by: 'model',
};

const mockUsageReport = {
  items: [
    { actor: 'user@example.com', action_count: 150 },
    { actor: 'admin@example.com', action_count: 85 },
  ],
  period: { since: '2024-06-01', until: '2024-06-30' },
  group_by: 'actor',
};

const mockLlmReport = {
  by_call_type: [
    { call_type: 'classify', cost_usd: 2.35, token_count: 12500 },
    { call_type: 'predict_cost', cost_usd: 1.12, token_count: 6800 },
  ],
  by_time: [
    { day: '2024-06-28', cost_usd: 1.5 },
    { day: '2024-06-29', cost_usd: 1.97 },
  ],
  total_cost_usd: 3.47,
  period: { since: '2024-06-01', until: '2024-06-30' },
};

/* ------------------------------------------------------------------ */
/* Hook mocks                                                          */
/* ------------------------------------------------------------------ */

let costReturn = { data: mockCostReport, loading: false, error: null };
let usageReturn = { data: mockUsageReport, loading: false, error: null };
let llmReturn = { data: mockLlmReport, loading: false, error: null };

vi.mock('../../src/hooks/useReports', () => ({
  useCostReport: vi.fn(() => costReturn),
  useUsageReport: vi.fn(() => usageReturn),
  useLLMReport: vi.fn(() => llmReturn),
}));

vi.mock('../../src/api/client', () => ({
  downloadReportExport: vi.fn(),
}));

/* ------------------------------------------------------------------ */
/* Cost Tab tests                                                      */
/* ------------------------------------------------------------------ */

describe('ReportsPage - Cost Tab', () => {
  beforeEach(() => {
    costReturn = { data: mockCostReport, loading: false, error: null };
    usageReturn = { data: mockUsageReport, loading: false, error: null };
    llmReturn = { data: mockLlmReport, loading: false, error: null };
  });

  it('renders the page title', () => {
    render(<ReportsPage />);
    expect(screen.getByText('Reports')).toBeInTheDocument();
  });

  it('shows all three tabs', () => {
    render(<ReportsPage />);
    expect(screen.getByText('Cost')).toBeInTheDocument();
    expect(screen.getByText('Usage')).toBeInTheDocument();
    expect(screen.getByText('LLM')).toBeInTheDocument();
  });

  it('displays cost total card', () => {
    render(<ReportsPage />);
    expect(screen.getByText('Total Cost')).toBeInTheDocument();
    expect(screen.getByText('$58.00')).toBeInTheDocument();
  });

  it('renders cost data table with model names', () => {
    render(<ReportsPage />);
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
    expect(screen.getByText('claude-3-haiku')).toBeInTheDocument();
  });

  it('renders date range pickers', () => {
    render(<ReportsPage />);
    expect(screen.getByText('From')).toBeInTheDocument();
    expect(screen.getByText('To')).toBeInTheDocument();
  });

  it('renders export buttons', () => {
    render(<ReportsPage />);
    expect(screen.getByText('Export CSV')).toBeInTheDocument();
    expect(screen.getByText('Export JSON')).toBeInTheDocument();
  });

  it('shows group-by dropdown for cost tab', () => {
    render(<ReportsPage />);
    expect(screen.getByText('Group by')).toBeInTheDocument();
  });

  it('shows skeleton loading state', () => {
    costReturn = { data: null, loading: true, error: null };
    const { container } = render(<ReportsPage />);
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error state', () => {
    costReturn = { data: null, loading: false, error: 'Failed to load' };
    render(<ReportsPage />);
    expect(screen.getByText('Failed to load')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Usage Tab tests                                                     */
/* ------------------------------------------------------------------ */

describe('ReportsPage - Usage Tab', () => {
  beforeEach(() => {
    costReturn = { data: mockCostReport, loading: false, error: null };
    usageReturn = { data: mockUsageReport, loading: false, error: null };
    llmReturn = { data: mockLlmReport, loading: false, error: null };
  });

  it('renders usage data when tab is clicked', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('Usage'));
    expect(screen.getByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByText('admin@example.com')).toBeInTheDocument();
  });

  it('shows skeleton loading state for usage', () => {
    usageReturn = { data: null, loading: true, error: null };
    const { container } = render(<ReportsPage />);
    fireEvent.click(screen.getByText('Usage'));
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows group-by dropdown for usage tab', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('Usage'));
    expect(screen.getByText('Group by')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* LLM Tab tests                                                       */
/* ------------------------------------------------------------------ */

describe('ReportsPage - LLM Tab', () => {
  beforeEach(() => {
    costReturn = { data: mockCostReport, loading: false, error: null };
    usageReturn = { data: mockUsageReport, loading: false, error: null };
    llmReturn = { data: mockLlmReport, loading: false, error: null };
  });

  it('renders LLM data when tab is clicked', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('LLM'));
    expect(screen.getByText('Total LLM Cost')).toBeInTheDocument();
    expect(screen.getByText('$3.4700')).toBeInTheDocument();
  });

  it('shows LLM by call type table', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('LLM'));
    expect(screen.getByText('By Call Type')).toBeInTheDocument();
    expect(screen.getByText('classify')).toBeInTheDocument();
    expect(screen.getByText('predict_cost')).toBeInTheDocument();
  });

  it('shows LLM by day table', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('LLM'));
    expect(screen.getByText('By Day')).toBeInTheDocument();
  });

  it('shows skeleton loading state for LLM', () => {
    llmReturn = { data: null, loading: true, error: null };
    const { container } = render(<ReportsPage />);
    fireEvent.click(screen.getByText('LLM'));
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('does not show group-by dropdown for LLM tab', () => {
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('LLM'));
    expect(screen.queryByText('Group by')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Empty data tests                                                    */
/* ------------------------------------------------------------------ */

describe('ReportsPage - Empty data', () => {
  it('shows no data message when cost report has empty items', () => {
    costReturn = {
      data: { ...mockCostReport, items: [], total_cost_usd: 0 },
      loading: false,
      error: null,
    };
    render(<ReportsPage />);
    expect(screen.getByText('No data for this period.')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Export button interaction                                            */
/* ------------------------------------------------------------------ */

describe('ReportsPage - Export', () => {
  it('calls downloadReportExport on CSV export click', async () => {
    const { downloadReportExport } = await import('../../src/api/client');
    costReturn = { data: mockCostReport, loading: false, error: null };
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('Export CSV'));
    expect(downloadReportExport).toHaveBeenCalled();
  });

  it('calls downloadReportExport on JSON export click', async () => {
    const { downloadReportExport } = await import('../../src/api/client');
    costReturn = { data: mockCostReport, loading: false, error: null };
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('Export JSON'));
    expect(downloadReportExport).toHaveBeenCalled();
  });
});
