import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import AdminDashboard from '../../src/pages/AdminDashboard';

/* ------------------------------------------------------------------ */
/* Mock data                                                           */
/* ------------------------------------------------------------------ */

const mockOverview = {
  total_tenants: 25,
  active_tenants: 18,
  total_events: 12500,
  total_runs: 340,
  total_cost_usd: 1245.67,
};

const mockRevenue = {
  mrr_usd: 1547,
  tiers: {
    community: { count: 12, mrr: 0 },
    team: { count: 8, mrr: 392 },
    enterprise: { count: 5, mrr: 995 },
  },
};

const mockTenants = {
  tenants: [
    {
      tenant_id: 'acme-corp',
      plan_tier: 'team',
      plan_runs: 45,
      ai_calls: 120,
      api_requests: 980,
      run_cost_usd: 23.45,
      llm_cost_usd: 5.12,
      total_cost_usd: 28.57,
      llm_enabled: true,
      created_at: '2024-01-15T00:00:00Z',
    },
  ],
  total: 1,
};

const mockCostBreakdown = {
  items: [
    { group: 'gpt-4o-mini', cost_usd: 45.2, run_count: 120 },
    { group: 'claude-3-haiku', cost_usd: 12.8, run_count: 85 },
  ],
  total_cost_usd: 58.0,
};

const mockHealthMetrics = {
  error_rate: 0.023,
  p95_runtime_seconds: 14.5,
  total_runs: 340,
  failed_runs: 8,
  ai_acceptance_rate: 0.87,
  ai_avg_accuracy: 0.92,
};

const mockCustomerHealth = {
  tenants: [
    {
      tenant_id: 'acme-corp',
      health_score: 78.5,
      health_status: 'active' as const,
      trend_direction: 'improving',
      last_login_at: '2024-06-20T10:00:00Z',
      last_plan_run_at: '2024-06-19T15:30:00Z',
      computed_at: '2024-06-20T12:00:00Z',
    },
    {
      tenant_id: 'beta-inc',
      health_score: 42.0,
      health_status: 'at_risk' as const,
      trend_direction: 'declining',
      last_login_at: '2024-06-10T08:00:00Z',
      last_plan_run_at: null,
      computed_at: '2024-06-20T12:00:00Z',
    },
  ],
  total: 2,
  summary: { active: 1, at_risk: 1, churning: 0 },
};

/* ------------------------------------------------------------------ */
/* Default mock return values                                          */
/* ------------------------------------------------------------------ */

let overviewReturn = { data: mockOverview, loading: false, error: null };
let revenueReturn = { data: mockRevenue, loading: false, error: null };
let tenantsReturn = { data: mockTenants, loading: false, error: null };
let costBreakdownReturn = { data: mockCostBreakdown, loading: false, error: null };
let healthMetricsReturn = { data: mockHealthMetrics, loading: false, error: null };
let customerHealthReturn = {
  data: mockCustomerHealth,
  loading: false,
  error: null,
  refetch: vi.fn(),
};

vi.mock('../../src/hooks/useAdminAnalytics', () => ({
  useAnalyticsOverview: vi.fn(() => overviewReturn),
  useAnalyticsTenants: vi.fn(() => tenantsReturn),
  useAnalyticsRevenue: vi.fn(() => revenueReturn),
  useAnalyticsCostBreakdown: vi.fn(() => costBreakdownReturn),
  useAnalyticsHealth: vi.fn(() => healthMetricsReturn),
}));

vi.mock('../../src/hooks/useCustomerHealth', () => ({
  useCustomerHealthList: vi.fn(() => customerHealthReturn),
}));

vi.mock('../../src/api/client', () => ({
  triggerHealthCompute: vi.fn(() => Promise.resolve({ computed_count: 5, duration_ms: 1200 })),
}));

/* ------------------------------------------------------------------ */
/* Overview Tab tests                                                  */
/* ------------------------------------------------------------------ */

describe('AdminDashboard - Overview Tab', () => {
  beforeEach(() => {
    overviewReturn = { data: mockOverview, loading: false, error: null };
    revenueReturn = { data: mockRevenue, loading: false, error: null };
    costBreakdownReturn = { data: mockCostBreakdown, loading: false, error: null };
  });

  it('renders the page title', () => {
    render(<AdminDashboard />);
    expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
  });

  it('displays overview stat cards', () => {
    render(<AdminDashboard />);
    expect(screen.getByText('Total Tenants')).toBeInTheDocument();
    expect(screen.getByText('25')).toBeInTheDocument();
    expect(screen.getByText('Active Tenants')).toBeInTheDocument();
    expect(screen.getByText('18')).toBeInTheDocument();
    expect(screen.getByText('Total Events')).toBeInTheDocument();
    expect(screen.getByText('12,500')).toBeInTheDocument();
  });

  it('displays revenue section', () => {
    render(<AdminDashboard />);
    expect(screen.getByText('Revenue')).toBeInTheDocument();
    expect(screen.getByText('MRR')).toBeInTheDocument();
    expect(screen.getByText('$1547')).toBeInTheDocument();
  });

  it('displays cost breakdown table', () => {
    render(<AdminDashboard />);
    expect(screen.getByText('Cost Breakdown')).toBeInTheDocument();
    expect(screen.getByText('gpt-4o-mini')).toBeInTheDocument();
  });

  it('shows all four tabs', () => {
    render(<AdminDashboard />);
    expect(screen.getByText('Overview')).toBeInTheDocument();
    expect(screen.getByText('Tenants')).toBeInTheDocument();
    expect(screen.getByText('Customer Health')).toBeInTheDocument();
    expect(screen.getByText('System Health')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Overview loading state                                              */
/* ------------------------------------------------------------------ */

describe('AdminDashboard - Overview Loading', () => {
  it('shows skeleton placeholders when overview is loading', () => {
    overviewReturn = { data: null, loading: true, error: null };
    const { container } = render(<AdminDashboard />);
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error text on overview error', () => {
    overviewReturn = { data: null, loading: false, error: 'Server error' };
    render(<AdminDashboard />);
    expect(screen.getByText('Server error')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Tenants Tab tests                                                   */
/* ------------------------------------------------------------------ */

describe('AdminDashboard - Tenants Tab', () => {
  beforeEach(() => {
    tenantsReturn = { data: mockTenants, loading: false, error: null };
  });

  it('renders tenant table when tab is clicked', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Tenants'));
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('1 total tenants')).toBeInTheDocument();
  });

  it('shows tenant tier badge', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Tenants'));
    expect(screen.getByText('team')).toBeInTheDocument();
  });

  it('shows skeleton loading state for tenants tab', () => {
    tenantsReturn = { data: null, loading: true, error: null };
    const { container } = render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Tenants'));
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

/* ------------------------------------------------------------------ */
/* Customer Health Tab tests                                           */
/* ------------------------------------------------------------------ */

describe('AdminDashboard - Customer Health Tab', () => {
  beforeEach(() => {
    customerHealthReturn = {
      data: mockCustomerHealth,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
  });

  it('renders health summary cards when tab is clicked', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Customer Health'));
    expect(screen.getByText('Active')).toBeInTheDocument();
    expect(screen.getByText('At Risk')).toBeInTheDocument();
    expect(screen.getByText('Churning')).toBeInTheDocument();
  });

  it('displays tenant health scores', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Customer Health'));
    expect(screen.getByText('acme-corp')).toBeInTheDocument();
    expect(screen.getByText('beta-inc')).toBeInTheDocument();
  });

  it('shows Recompute Scores button', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Customer Health'));
    expect(screen.getByText('Recompute Scores')).toBeInTheDocument();
  });

  it('shows skeleton loading state for health data', () => {
    customerHealthReturn = {
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    };
    const { container } = render(<AdminDashboard />);
    fireEvent.click(screen.getByText('Customer Health'));
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});

/* ------------------------------------------------------------------ */
/* System Health Tab tests                                             */
/* ------------------------------------------------------------------ */

describe('AdminDashboard - System Health Tab', () => {
  beforeEach(() => {
    healthMetricsReturn = { data: mockHealthMetrics, loading: false, error: null };
  });

  it('renders system health metrics when tab is clicked', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('System Health'));
    expect(screen.getByText('Error Rate')).toBeInTheDocument();
    expect(screen.getByText('P95 Runtime')).toBeInTheDocument();
    expect(screen.getByText('AI Acceptance')).toBeInTheDocument();
    expect(screen.getByText('AI Accuracy')).toBeInTheDocument();
  });

  it('displays formatted error rate', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('System Health'));
    expect(screen.getByText('2.3%')).toBeInTheDocument();
  });

  it('displays formatted P95 runtime', () => {
    render(<AdminDashboard />);
    fireEvent.click(screen.getByText('System Health'));
    expect(screen.getByText('14.5s')).toBeInTheDocument();
  });

  it('shows skeleton loading state for system health', () => {
    healthMetricsReturn = { data: null, loading: true, error: null };
    const { container } = render(<AdminDashboard />);
    fireEvent.click(screen.getByText('System Health'));
    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
