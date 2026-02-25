import { useCallback, useEffect, useState } from 'react';
import {
  CreditCard,
  ExternalLink,
  CheckCircle,
  AlertTriangle,
  ArrowUpCircle,
  Shield,
  Download,
  FileText,
  Users,
  UserPlus,
  Trash2,
  ChevronDown,
  X,
} from 'lucide-react';
import { useBilling } from '../hooks/useBilling';
import { useQuotas } from '../hooks/useQuotas';
import { useTeam } from '../hooks/useTeam';
import { useAuth } from '../contexts/AuthContext';
import { createPortalSession, fetchInvoices, downloadInvoicePdf } from '../api/client';
import type { Invoice } from '../api/types';

const TIER_CONFIG: Record<
  string,
  {
    label: string;
    color: string;
    bgColor: string;
    description: string;
  }
> = {
  community: {
    label: 'Community',
    color: 'text-gray-700',
    bgColor: 'bg-gray-100',
    description: 'Free tier for small teams and evaluation',
  },
  team: {
    label: 'Team',
    color: 'text-ironlayer-700',
    bgColor: 'bg-ironlayer-50',
    description: '$29/user/mo for growing teams',
  },
  enterprise: {
    label: 'Enterprise',
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    description: 'Unlimited usage with priority support',
  },
};

const ROLE_OPTIONS = ['viewer', 'operator', 'engineer', 'admin'] as const;

const ROLE_COLORS: Record<string, string> = {
  admin: 'bg-red-50 text-red-700',
  engineer: 'bg-blue-50 text-blue-700',
  operator: 'bg-yellow-50 text-yellow-700',
  viewer: 'bg-gray-100 text-gray-600',
};

/* ------------------------------------------------------------------ */
/* Invite Modal                                                        */
/* ------------------------------------------------------------------ */

function InviteModal({
  onClose,
  onInvite,
}: {
  onClose: () => void;
  onInvite: (email: string, role: string) => Promise<void>;
}) {
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('viewer');
  const [submitting, setSubmitting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setInviteError(null);
    try {
      await onInvite(email, role);
      onClose();
    } catch (err) {
      setInviteError(err instanceof Error ? err.message : 'Failed to invite member');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-md rounded-xl border border-gray-200 bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">Invite Team Member</h3>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            aria-label="Close"
          >
            <X className="h-5 w-5" size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="invite-email" className="mb-1 block text-sm font-medium text-gray-700">
              Email address
            </label>
            <input
              id="invite-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="colleague@company.com"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
          </div>

          <div>
            <label htmlFor="invite-role" className="mb-1 block text-sm font-medium text-gray-700">
              Role
            </label>
            <div className="relative">
              <select
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full appearance-none rounded-lg border border-gray-300 px-3 py-2 pr-8 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r}>
                    {r.charAt(0).toUpperCase() + r.slice(1)}
                  </option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" size={16} />
            </div>
          </div>

          {inviteError && (
            <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{inviteError}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || !email}
              className="rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white hover:bg-ironlayer-700 disabled:opacity-50"
            >
              {submitting ? 'Inviting...' : 'Send Invite'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main Page                                                           */
/* ------------------------------------------------------------------ */

function BillingPage() {
  const { subscription, loading: billingLoading, error: billingError } = useBilling();
  const { data: quotaData, loading: quotaLoading } = useQuotas();
  const { data: teamData, loading: teamLoading, error: teamError, invite, remove, updateRole } = useTeam();
  const auth = useAuth();
  const isAdmin = auth.user?.role === 'admin';

  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoicesTotal, setInvoicesTotal] = useState(0);
  const [invoicesLoading, setInvoicesLoading] = useState(true);
  const [invoicesError, setInvoicesError] = useState<string | null>(null);
  const [showInviteModal, setShowInviteModal] = useState(false);

  // Load invoices on mount with AbortController
  useEffect(() => {
    const controller = new AbortController();
    fetchInvoices(10, 0, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setInvoices(data.invoices);
          setInvoicesTotal(data.total);
        }
      })
      .catch((e: Error) => {
        if (!controller.signal.aborted) {
          setInvoicesError(e.message);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setInvoicesLoading(false);
        }
      });
    return () => controller.abort();
  }, []);

  const tier = subscription?.plan_tier ?? 'community';
  const config = TIER_CONFIG[tier] ?? TIER_CONFIG.community;
  const isActive = subscription?.status === 'active';

  const handleManageSubscription = async () => {
    try {
      const { url } = await createPortalSession(window.location.href);
      window.location.href = url;
    } catch {
      alert('Failed to open billing portal. Please try again.');
    }
  };

  const handleInvite = useCallback(
    async (email: string, role: string) => {
      await invite(email, role);
    },
    [invite],
  );

  const handleRemove = useCallback(
    async (userId: string) => {
      if (window.confirm('Are you sure you want to remove this team member?')) {
        try {
          await remove(userId);
        } catch (err) {
          alert(err instanceof Error ? err.message : 'Failed to remove member');
        }
      }
    },
    [remove],
  );

  const handleRoleChange = useCallback(
    async (userId: string, newRole: string) => {
      try {
        await updateRole(userId, newRole);
      } catch (err) {
        alert(err instanceof Error ? err.message : 'Failed to update role');
      }
    },
    [updateRole],
  );

  if (billingError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {billingError}
      </div>
    );
  }

  if (billingLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        Loading billing information...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Billing & Subscription</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage your subscription plan, team members, and view usage against your quotas
        </p>
      </div>

      {/* Current plan card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div
              className={`flex h-12 w-12 items-center justify-center rounded-xl ${config.bgColor}`}
            >
              <Shield className={`h-6 w-6 ${config.color}`} size={24} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold text-gray-900">{config.label}</h2>
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.bgColor} ${config.color}`}
                >
                  {config.label}
                </span>
              </div>
              <p className="mt-0.5 text-sm text-gray-500">{config.description}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {isActive ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2.5 py-0.5 text-xs font-medium text-green-700">
                <CheckCircle className="h-3 w-3" size={12} />
                Active
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-yellow-50 px-2.5 py-0.5 text-xs font-medium text-yellow-700">
                <AlertTriangle className="h-3 w-3" size={12} />
                {subscription?.status ?? 'Inactive'}
              </span>
            )}
          </div>
        </div>

        {/* Billing period */}
        {subscription?.period_start && (
          <div className="mt-4 rounded-lg bg-gray-50 px-4 py-3 text-sm text-gray-600">
            Current period:{' '}
            <span className="font-medium">
              {new Date(subscription.period_start).toLocaleDateString()} &ndash;{' '}
              {subscription.period_end
                ? new Date(subscription.period_end).toLocaleDateString()
                : 'Ongoing'}
            </span>
            {subscription.cancel_at_period_end && (
              <span className="ml-2 text-yellow-600">(Cancels at period end)</span>
            )}
          </div>
        )}
      </div>

      {/* Team Members */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Users className="h-5 w-5 text-gray-400" size={20} />
            <h3 className="text-sm font-semibold text-gray-900">Team Members</h3>
            {teamData && (
              <span className="text-xs text-gray-500">
                {teamData.seats_used}
                {teamData.seat_limit !== null ? ` / ${teamData.seat_limit} seats` : ' seats (unlimited)'}
              </span>
            )}
          </div>
          {isAdmin && tier !== 'community' && (
            <button
              onClick={() => setShowInviteModal(true)}
              className="inline-flex items-center gap-1.5 rounded-lg bg-ironlayer-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-ironlayer-700"
            >
              <UserPlus className="h-3.5 w-3.5" size={14} />
              Invite Member
            </button>
          )}
        </div>

        {/* Seat usage progress bar */}
        {teamData && teamData.seat_limit !== null && (
          <div className="mb-4">
            <div className="mb-1 flex justify-between text-xs text-gray-500">
              <span>Seat usage</span>
              <span>
                {teamData.seats_used} / {teamData.seat_limit}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  teamData.seat_limit > 0 && (teamData.seats_used / teamData.seat_limit) * 100 >= 90
                    ? 'bg-red-500'
                    : teamData.seat_limit > 0 && (teamData.seats_used / teamData.seat_limit) * 100 >= 70
                      ? 'bg-yellow-500'
                      : 'bg-ironlayer-500'
                }`}
                style={{
                  width: `${teamData.seat_limit > 0 ? Math.min((teamData.seats_used / teamData.seat_limit) * 100, 100) : 0}%`,
                }}
              />
            </div>
          </div>
        )}

        {teamLoading ? (
          <p className="text-sm text-gray-400">Loading team members...</p>
        ) : teamError ? (
          <p className="text-sm text-red-500">{teamError}</p>
        ) : teamData && teamData.members.length > 0 ? (
          <div className="overflow-hidden rounded-lg border border-gray-100">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-gray-500">
                  <th className="px-4 py-2 font-medium">Name</th>
                  <th className="px-4 py-2 font-medium">Email</th>
                  <th className="px-4 py-2 font-medium">Role</th>
                  <th className="px-4 py-2 font-medium text-center">Status</th>
                  {isAdmin && <th className="px-4 py-2 font-medium text-right">Actions</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {teamData.members.map((member) => (
                  <tr key={member.id}>
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {member.display_name}
                    </td>
                    <td className="px-4 py-3 text-gray-500">{member.email}</td>
                    <td className="px-4 py-3">
                      {isAdmin && member.id !== auth.user?.id ? (
                        <div className="relative">
                          <select
                            value={member.role}
                            onChange={(e) => handleRoleChange(member.id, e.target.value)}
                            className={`appearance-none rounded-full border-0 px-2.5 py-0.5 pr-7 text-xs font-medium focus:outline-none focus:ring-2 focus:ring-ironlayer-500 ${ROLE_COLORS[member.role] ?? ROLE_COLORS.viewer}`}
                          >
                            {ROLE_OPTIONS.map((r) => (
                              <option key={r} value={r}>
                                {r.charAt(0).toUpperCase() + r.slice(1)}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="pointer-events-none absolute right-1 top-1/2 h-3 w-3 -translate-y-1/2 text-gray-400" size={12} />
                        </div>
                      ) : (
                        <span
                          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ROLE_COLORS[member.role] ?? ROLE_COLORS.viewer}`}
                        >
                          {member.role.charAt(0).toUpperCase() + member.role.slice(1)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          member.is_active
                            ? 'bg-green-50 text-green-700'
                            : 'bg-gray-100 text-gray-500'
                        }`}
                      >
                        {member.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    {isAdmin && (
                      <td className="px-4 py-3 text-right">
                        {member.id !== auth.user?.id && member.is_active && (
                          <button
                            onClick={() => handleRemove(member.id)}
                            className="inline-flex items-center gap-1 text-xs text-red-500 hover:text-red-700"
                            title="Remove member"
                            aria-label={`Remove ${member.display_name}`}
                          >
                            <Trash2 className="h-3.5 w-3.5" size={14} />
                            Remove
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex flex-col items-center py-6 text-center">
            <Users className="mb-2 h-8 w-8 text-gray-300" size={32} />
            <p className="text-sm text-gray-500">No team members yet</p>
            {isAdmin && tier !== 'community' && (
              <p className="mt-1 text-xs text-gray-400">
                Invite your first team member to get started.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Usage vs Quotas */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <h3 className="mb-4 text-sm font-semibold text-gray-900">
          Usage vs. Quotas (Current Month)
        </h3>
        {quotaLoading ? (
          <p className="text-sm text-gray-400">Loading quota data...</p>
        ) : quotaData ? (
          <div className="space-y-5">
            {quotaData.quotas.map((q) => {
              const unlimited = q.limit === null;
              const pct = q.percentage ?? 0;

              return (
                <div key={q.event_type}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-medium text-gray-700">{q.name}</span>
                    <span className="text-gray-500">
                      {unlimited
                        ? `${q.used.toLocaleString()} (unlimited)`
                        : `${q.used.toLocaleString()} / ${q.limit!.toLocaleString()}`}
                    </span>
                  </div>
                  {!unlimited && (
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-100">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          pct >= 90
                            ? 'bg-red-500'
                            : pct >= 70
                              ? 'bg-yellow-500'
                              : 'bg-ironlayer-500'
                        }`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  )}
                  {!unlimited && pct >= 90 && (
                    <p className="mt-1 text-xs text-red-600">
                      You&apos;ve used {Math.round(pct)}% of your included{' '}
                      {q.name.toLowerCase()}. Consider upgrading.
                    </p>
                  )}
                </div>
              );
            })}

            {/* LLM Budget */}
            {quotaData.llm_budget && (
              <div className="mt-4 rounded-lg bg-gray-50 p-4">
                <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                  LLM Budget
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-xs text-gray-500">Daily Spend</p>
                    <p className="text-lg font-semibold text-gray-900">
                      ${quotaData.llm_budget.daily_used_usd.toFixed(4)}
                    </p>
                    {quotaData.llm_budget.daily_limit_usd !== null && (
                      <p className="text-xs text-gray-400">
                        of ${quotaData.llm_budget.daily_limit_usd.toFixed(2)} limit
                      </p>
                    )}
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Monthly Spend</p>
                    <p className="text-lg font-semibold text-gray-900">
                      ${quotaData.llm_budget.monthly_used_usd.toFixed(4)}
                    </p>
                    {quotaData.llm_budget.monthly_limit_usd !== null && (
                      <p className="text-xs text-gray-400">
                        of ${quotaData.llm_budget.monthly_limit_usd.toFixed(2)} limit
                      </p>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-400">Unable to load quota data.</p>
        )}
      </div>

      {/* Invoices */}
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Invoices</h3>
          {invoicesTotal > 0 && (
            <span className="text-xs text-gray-500">{invoicesTotal} total</span>
          )}
        </div>
        {invoicesLoading ? (
          <p className="text-sm text-gray-400">Loading invoices...</p>
        ) : invoicesError ? (
          <p className="text-sm text-red-500">{invoicesError}</p>
        ) : invoices.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <FileText className="mb-2 h-8 w-8 text-gray-300" size={32} />
            <p className="text-sm text-gray-500">No invoices yet</p>
            <p className="mt-1 text-xs text-gray-400">
              Invoices will appear here after your first billing cycle.
            </p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-gray-100">
            <table className="w-full text-sm">
              <thead className="bg-gray-50">
                <tr className="text-left text-gray-500">
                  <th className="px-4 py-2 font-medium">Invoice</th>
                  <th className="px-4 py-2 font-medium">Period</th>
                  <th className="px-4 py-2 font-medium text-right">Amount</th>
                  <th className="px-4 py-2 font-medium text-center">Status</th>
                  <th className="px-4 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {invoices.map((inv) => (
                  <tr key={inv.invoice_id}>
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">
                      {inv.invoice_number}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-500">
                      {inv.period_start
                        ? new Date(inv.period_start).toLocaleDateString()
                        : '\u2014'}{' '}
                      &ndash;{' '}
                      {inv.period_end
                        ? new Date(inv.period_end).toLocaleDateString()
                        : '\u2014'}
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-gray-900">
                      ${inv.total_usd.toFixed(2)}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          inv.status === 'paid'
                            ? 'bg-green-50 text-green-700'
                            : inv.status === 'void'
                              ? 'bg-gray-100 text-gray-500'
                              : 'bg-blue-50 text-blue-700'
                        }`}
                      >
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => downloadInvoicePdf(inv.invoice_id)}
                        className="inline-flex items-center gap-1 text-xs text-ironlayer-600 hover:text-ironlayer-800"
                        title="Download PDF"
                        aria-label={`Download PDF for invoice ${inv.invoice_number}`}
                      >
                        <Download className="h-3.5 w-3.5" size={14} />
                        PDF
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Manage subscription */}
        {subscription?.billing_enabled && (
          <button
            onClick={handleManageSubscription}
            className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-6 text-left transition-all hover:border-ironlayer-300 hover:shadow-md"
          >
            <CreditCard className="h-8 w-8 text-gray-400" size={32} />
            <div>
              <h3 className="font-semibold text-gray-900">Manage Subscription</h3>
              <p className="mt-0.5 text-sm text-gray-500">
                Update payment method, view invoices, or change plan
              </p>
            </div>
            <ExternalLink className="ml-auto h-4 w-4 text-gray-400" size={16} />
          </button>
        )}

        {/* Upgrade CTA */}
        {tier === 'community' && (
          <button
            onClick={handleManageSubscription}
            className="flex items-center gap-3 rounded-xl border-2 border-ironlayer-200 bg-ironlayer-50 p-6 text-left transition-all hover:border-ironlayer-400 hover:shadow-md"
          >
            <ArrowUpCircle className="h-8 w-8 text-ironlayer-500" size={32} />
            <div>
              <h3 className="font-semibold text-ironlayer-900">Upgrade to Team</h3>
              <p className="mt-0.5 text-sm text-ironlayer-600">
                $29/user/mo with AI advisory, team management, and priority support
              </p>
            </div>
          </button>
        )}
      </div>

      {/* Invite modal */}
      {showInviteModal && (
        <InviteModal onClose={() => setShowInviteModal(false)} onInvite={handleInvite} />
      )}
    </div>
  );
}

export default BillingPage;
