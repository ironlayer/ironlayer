import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import BillingPage from '../../src/pages/BillingPage';

/* ------------------------------------------------------------------ */
/* Auth context mock                                                   */
/* ------------------------------------------------------------------ */

vi.mock('../../src/contexts/AuthContext', () => ({
  useAuth: vi.fn(() => ({
    user: { id: 'u1', email: 'test@example.com', display_name: 'Test User', role: 'admin', tenant_id: 't1' },
    accessToken: 'fake-token',
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    signup: vi.fn(),
    logout: vi.fn(),
  })),
}));

/* ------------------------------------------------------------------ */
/* Team hook mock                                                      */
/* ------------------------------------------------------------------ */

vi.mock('../../src/hooks/useTeam', () => ({
  useTeam: vi.fn(() => ({
    data: null,
    loading: false,
    error: null,
    refetch: vi.fn(),
    invite: vi.fn(),
    remove: vi.fn(),
    updateRole: vi.fn(),
  })),
}));

/* ------------------------------------------------------------------ */
/* Mock data                                                           */
/* ------------------------------------------------------------------ */

const mockSubscription = {
  plan_tier: 'community',
  status: 'active',
  billing_enabled: false,
  subscription_id: null,
  period_start: null,
  period_end: null,
};

const mockTeamSubscription = {
  plan_tier: 'team',
  status: 'active',
  billing_enabled: true,
  subscription_id: 'sub_team_123',
  period_start: '2024-06-01T00:00:00Z',
  period_end: '2024-07-01T00:00:00Z',
  cancel_at_period_end: false,
};

const mockQuotaData = {
  quotas: [
    {
      event_type: 'plan_run',
      name: 'Plan Runs',
      used: 35,
      limit: 100,
      percentage: 35,
    },
    {
      event_type: 'ai_call',
      name: 'AI Advisory Calls',
      used: 200,
      limit: 500,
      percentage: 40,
    },
    {
      event_type: 'backfill_run',
      name: 'Backfill Runs',
      used: 5,
      limit: 50,
      percentage: 10,
    },
  ],
  llm_budget: {
    daily_used_usd: 0.0342,
    daily_limit_usd: 1.0,
    monthly_used_usd: 2.4567,
    monthly_limit_usd: 25.0,
  },
};

/* ------------------------------------------------------------------ */
/* Mutable return values (reset in beforeEach)                         */
/* ------------------------------------------------------------------ */

let mockBillingReturn: {
  subscription: typeof mockSubscription | typeof mockTeamSubscription | null;
  loading: boolean;
  error: string | null;
  refetch: ReturnType<typeof vi.fn>;
};

let mockQuotasReturn: {
  data: typeof mockQuotaData | null;
  loading: boolean;
  error: string | null;
  refetch: ReturnType<typeof vi.fn>;
};

const mockFetchInvoices = vi.fn(() =>
  Promise.resolve({ invoices: [], total: 0 }),
);
const mockDownloadInvoicePdf = vi.fn();
const mockCreatePortalSession = vi.fn(() =>
  Promise.resolve({ url: 'https://billing.stripe.com/session/ses_xxx' }),
);

/* ------------------------------------------------------------------ */
/* Module mocks                                                        */
/* ------------------------------------------------------------------ */

vi.mock('../../src/hooks/useBilling', () => ({
  useBilling: vi.fn(() => mockBillingReturn),
}));

vi.mock('../../src/hooks/useQuotas', () => ({
  useQuotas: vi.fn(() => mockQuotasReturn),
}));

vi.mock('../../src/api/client', () => ({
  createPortalSession: (...args: unknown[]) => mockCreatePortalSession(...args),
  fetchInvoices: (...args: unknown[]) => mockFetchInvoices(...args),
  downloadInvoicePdf: (...args: unknown[]) => mockDownloadInvoicePdf(...args),
}));

/* ------------------------------------------------------------------ */
/* Tests - Community tier                                              */
/* ------------------------------------------------------------------ */

describe('BillingPage - Community tier', () => {
  beforeEach(() => {
    mockBillingReturn = {
      subscription: mockSubscription,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: mockQuotaData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('renders the page header', () => {
    render(<BillingPage />);
    expect(screen.getByText('Billing & Subscription')).toBeInTheDocument();
  });

  it('displays Community plan name', () => {
    render(<BillingPage />);
    const communityLabels = screen.getAllByText('Community');
    expect(communityLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows Active status badge', () => {
    render(<BillingPage />);
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('displays community plan description', () => {
    render(<BillingPage />);
    expect(
      screen.getByText('Free tier for small teams and evaluation'),
    ).toBeInTheDocument();
  });

  it('shows upgrade CTA for community tier', () => {
    render(<BillingPage />);
    expect(screen.getByText('Upgrade to Team')).toBeInTheDocument();
  });

  it('renders usage vs quotas section', () => {
    render(<BillingPage />);
    expect(
      screen.getByText('Usage vs. Quotas (Current Month)'),
    ).toBeInTheDocument();
  });

  it('displays plan run usage count', () => {
    render(<BillingPage />);
    expect(screen.getByText('Plan Runs')).toBeInTheDocument();
    expect(screen.getByText('35 / 100')).toBeInTheDocument();
  });

  it('displays AI call usage count', () => {
    render(<BillingPage />);
    expect(screen.getByText('AI Advisory Calls')).toBeInTheDocument();
    expect(screen.getByText('200 / 500')).toBeInTheDocument();
  });

  it('displays backfill usage count', () => {
    render(<BillingPage />);
    expect(screen.getByText('Backfill Runs')).toBeInTheDocument();
    expect(screen.getByText('5 / 50')).toBeInTheDocument();
  });

  it('does not show Manage Subscription when billing is disabled', () => {
    render(<BillingPage />);
    expect(screen.queryByText('Manage Subscription')).not.toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Tests - Team tier                                                   */
/* ------------------------------------------------------------------ */

describe('BillingPage - Team tier', () => {
  beforeEach(() => {
    mockBillingReturn = {
      subscription: mockTeamSubscription as any,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: mockQuotaData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('displays Team plan name', () => {
    render(<BillingPage />);
    const teamLabels = screen.getAllByText('Team');
    expect(teamLabels.length).toBeGreaterThanOrEqual(1);
  });

  it('shows team plan description', () => {
    render(<BillingPage />);
    expect(
      screen.getByText('$29/user/mo for growing teams'),
    ).toBeInTheDocument();
  });

  it('does not show upgrade CTA for team tier', () => {
    render(<BillingPage />);
    expect(screen.queryByText('Upgrade to Team')).not.toBeInTheDocument();
  });

  it('shows Manage Subscription when billing is enabled', () => {
    render(<BillingPage />);
    expect(screen.getByText('Manage Subscription')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Tests - Loading and error states                                    */
/* ------------------------------------------------------------------ */

describe('BillingPage - Loading state', () => {
  beforeEach(() => {
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('shows loading indicator when billing data is loading', () => {
    mockBillingReturn = {
      subscription: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    };

    render(<BillingPage />);
    expect(
      screen.getByText('Loading billing information...'),
    ).toBeInTheDocument();
  });
});

describe('BillingPage - Error state', () => {
  beforeEach(() => {
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('shows error message when billing fails', () => {
    mockBillingReturn = {
      subscription: null,
      loading: false,
      error: 'Failed to load billing info',
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };

    render(<BillingPage />);
    expect(
      screen.getByText('Failed to load billing info'),
    ).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Tests - Quota display                                               */
/* ------------------------------------------------------------------ */

describe('BillingPage - Quota display', () => {
  beforeEach(() => {
    mockBillingReturn = {
      subscription: mockSubscription,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: mockQuotaData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('shows all quota names', () => {
    render(<BillingPage />);
    expect(screen.getByText('Plan Runs')).toBeInTheDocument();
    expect(screen.getByText('AI Advisory Calls')).toBeInTheDocument();
    expect(screen.getByText('Backfill Runs')).toBeInTheDocument();
  });

  it('shows used / limit text for each quota', () => {
    render(<BillingPage />);
    expect(screen.getByText('35 / 100')).toBeInTheDocument();
    expect(screen.getByText('200 / 500')).toBeInTheDocument();
    expect(screen.getByText('5 / 50')).toBeInTheDocument();
  });

  it('shows unlimited label when quota limit is null', () => {
    mockQuotasReturn = {
      data: {
        quotas: [
          {
            event_type: 'plan_run',
            name: 'Plan Runs',
            used: 42,
            limit: null,
            percentage: null,
          },
        ],
        llm_budget: null as any,
      },
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    render(<BillingPage />);
    expect(screen.getByText('42 (unlimited)')).toBeInTheDocument();
  });

  it('shows loading text when quotas are loading', () => {
    mockQuotasReturn = {
      data: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    };
    render(<BillingPage />);
    expect(screen.getByText('Loading quota data...')).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/* Tests - Invoice section                                             */
/* ------------------------------------------------------------------ */

describe('BillingPage - Invoices', () => {
  beforeEach(() => {
    mockBillingReturn = {
      subscription: mockSubscription,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: mockQuotaData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('shows "No invoices yet" when empty', async () => {
    render(<BillingPage />);
    expect(await screen.findByText('No invoices yet')).toBeInTheDocument();
  });

  it('calls fetchInvoices on mount', () => {
    render(<BillingPage />);
    expect(mockFetchInvoices).toHaveBeenCalledWith(10, 0, expect.anything());
  });
});

/* ------------------------------------------------------------------ */
/* Tests - LLM Budget section                                          */
/* ------------------------------------------------------------------ */

describe('BillingPage - LLM Budget', () => {
  beforeEach(() => {
    mockBillingReturn = {
      subscription: mockSubscription,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockQuotasReturn = {
      data: mockQuotaData,
      loading: false,
      error: null,
      refetch: vi.fn(),
    };
    mockFetchInvoices.mockClear();
    mockFetchInvoices.mockReturnValue(
      Promise.resolve({ invoices: [], total: 0 }),
    );
  });

  it('shows LLM Budget heading', () => {
    render(<BillingPage />);
    expect(screen.getByText('LLM Budget')).toBeInTheDocument();
  });

  it('shows daily spend amount', () => {
    render(<BillingPage />);
    expect(screen.getByText('Daily Spend')).toBeInTheDocument();
    expect(screen.getByText('$0.0342')).toBeInTheDocument();
  });

  it('shows daily limit', () => {
    render(<BillingPage />);
    expect(screen.getByText('of $1.00 limit')).toBeInTheDocument();
  });

  it('shows monthly spend amount', () => {
    render(<BillingPage />);
    expect(screen.getByText('Monthly Spend')).toBeInTheDocument();
    expect(screen.getByText('$2.4567')).toBeInTheDocument();
  });

  it('shows monthly limit', () => {
    render(<BillingPage />);
    expect(screen.getByText('of $25.00 limit')).toBeInTheDocument();
  });
});
