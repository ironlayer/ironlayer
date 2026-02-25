import { useState } from 'react';
import {
  useAnalyticsOverview,
  useAnalyticsTenants,
  useAnalyticsRevenue,
  useAnalyticsCostBreakdown,
  useAnalyticsHealth,
} from '../hooks/useAdminAnalytics';
import { useCustomerHealthList } from '../hooks/useCustomerHealth';
import { triggerHealthCompute } from '../api/client';
import ErrorBoundary, { ChartErrorFallback } from '../components/ErrorBoundary';
import { SkeletonCard, SkeletonTable } from '../components/Skeleton';

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] p-4">
      <p className="text-xs text-zinc-400 uppercase tracking-wider">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-white">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-zinc-500">{sub}</p>}
    </div>
  );
}

function HealthBadge({ score }: { score: number }) {
  const color = score >= 60 ? 'text-emerald-400' : score >= 30 ? 'text-yellow-400' : 'text-red-400';
  return <span className={`font-mono text-sm font-semibold ${color}`}>{score.toFixed(0)}</span>;
}

function TrendArrow({ direction }: { direction: string | null }) {
  if (direction === 'improving') return <span className="text-emerald-400 text-xs ml-1">&#x25B2;</span>;
  if (direction === 'declining') return <span className="text-red-400 text-xs ml-1">&#x25BC;</span>;
  return <span className="text-zinc-500 text-xs ml-1">&#x2014;</span>;
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'active'
      ? 'bg-emerald-500/10 text-emerald-400'
      : status === 'at_risk'
        ? 'bg-yellow-500/10 text-yellow-400'
        : 'bg-red-500/10 text-red-400';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

export default function AdminDashboard() {
  const [tab, setTab] = useState<'overview' | 'tenants' | 'health' | 'system'>('overview');
  const [days] = useState(30);

  const overview = useAnalyticsOverview(days);
  const revenue = useAnalyticsRevenue();
  const tenants = useAnalyticsTenants(days);
  const costBreakdown = useAnalyticsCostBreakdown(days);
  const healthMetrics = useAnalyticsHealth(days);
  const customerHealth = useCustomerHealthList(undefined, 'health_score', 50, 0);
  const [computing, setComputing] = useState(false);

  const tabs = [
    { key: 'overview' as const, label: 'Overview' },
    { key: 'tenants' as const, label: 'Tenants' },
    { key: 'health' as const, label: 'Customer Health' },
    { key: 'system' as const, label: 'System Health' },
  ];

  const handleCompute = async () => {
    setComputing(true);
    try {
      await triggerHealthCompute();
      customerHealth.refetch();
    } finally {
      setComputing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">Admin Dashboard</h1>
        <span className="text-xs text-zinc-500">Last {days} days</span>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-white/[0.06] bg-white/[0.02] p-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`rounded-md px-4 py-1.5 text-sm transition-colors ${
              tab === t.key
                ? 'bg-white/[0.08] text-white font-medium'
                : 'text-zinc-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview Tab */}
      {tab === 'overview' && (
        <div className="space-y-6">
          {overview.loading ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
              {Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : overview.error ? (
            <p className="text-red-400">{overview.error}</p>
          ) : overview.data ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
              <StatCard label="Total Tenants" value={overview.data.total_tenants} />
              <StatCard label="Active Tenants" value={overview.data.active_tenants} />
              <StatCard label="Total Events" value={overview.data.total_events.toLocaleString()} />
              <StatCard label="Total Runs" value={overview.data.total_runs.toLocaleString()} />
              <StatCard label="Total Cost" value={`$${overview.data.total_cost_usd.toFixed(2)}`} />
            </div>
          ) : null}

          {/* Revenue */}
          {revenue.data && (
            <div className="space-y-3">
              <h2 className="text-lg font-semibold text-white">Revenue</h2>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                <StatCard label="MRR" value={`$${revenue.data.mrr_usd.toFixed(0)}`} />
                {Object.entries(revenue.data.tiers).map(([tier, info]) => (
                  <StatCard key={tier} label={`${tier} tier`} value={info.count} sub={`$${info.mrr.toFixed(0)} MRR`} />
                ))}
              </div>
            </div>
          )}

          {/* Cost Breakdown */}
          {costBreakdown.data && costBreakdown.data.items.length > 0 && (
            <ErrorBoundary fallback={<ChartErrorFallback />}>
              <div className="space-y-3">
                <h2 className="text-lg font-semibold text-white">Cost Breakdown</h2>
                <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
                  <table className="w-full text-sm">
                    <thead className="bg-white/[0.03]">
                      <tr className="text-left text-zinc-400">
                        <th className="px-4 py-2 font-medium">Model / Group</th>
                        <th className="px-4 py-2 font-medium text-right">Cost</th>
                        <th className="px-4 py-2 font-medium text-right">Runs</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04]">
                      {costBreakdown.data.items.slice(0, 10).map((item, i) => (
                        <tr key={i} className="text-zinc-300">
                          <td className="px-4 py-2 font-mono text-xs">{item.group}</td>
                          <td className="px-4 py-2 text-right">${item.cost_usd.toFixed(2)}</td>
                          <td className="px-4 py-2 text-right">{item.run_count}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </ErrorBoundary>
          )}
        </div>
      )}

      {/* Tenants Tab */}
      {tab === 'tenants' && (
        <div className="space-y-4">
          {tenants.loading ? (
            <SkeletonTable rows={5} cols={6} />
          ) : tenants.error ? (
            <p className="text-red-400">{tenants.error}</p>
          ) : tenants.data ? (
            <>
              <p className="text-sm text-zinc-400">{tenants.data.total} total tenants</p>
              <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
                <table className="w-full text-sm">
                  <thead className="bg-white/[0.03]">
                    <tr className="text-left text-zinc-400">
                      <th className="px-4 py-2 font-medium">Tenant</th>
                      <th className="px-4 py-2 font-medium">Tier</th>
                      <th className="px-4 py-2 font-medium text-right">Plan Runs</th>
                      <th className="px-4 py-2 font-medium text-right">AI Calls</th>
                      <th className="px-4 py-2 font-medium text-right">LLM Spend</th>
                      <th className="px-4 py-2 font-medium text-right">Total Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {tenants.data.tenants.map((t) => (
                      <tr key={t.tenant_id} className="text-zinc-300">
                        <td className="px-4 py-2 font-mono text-xs">{t.tenant_id}</td>
                        <td className="px-4 py-2">
                          <span className="rounded bg-white/[0.06] px-2 py-0.5 text-xs">{t.plan_tier}</span>
                        </td>
                        <td className="px-4 py-2 text-right">{t.plan_runs}</td>
                        <td className="px-4 py-2 text-right">{t.ai_calls}</td>
                        <td className="px-4 py-2 text-right">${t.llm_cost_usd.toFixed(2)}</td>
                        <td className="px-4 py-2 text-right font-medium">${t.total_cost_usd.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : null}
        </div>
      )}

      {/* Customer Health Tab */}
      {tab === 'health' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex gap-4">
              {customerHealth.data?.summary && (
                <>
                  <StatCard label="Active" value={customerHealth.data.summary.active} />
                  <StatCard label="At Risk" value={customerHealth.data.summary.at_risk} />
                  <StatCard label="Churning" value={customerHealth.data.summary.churning} />
                </>
              )}
            </div>
            <button
              onClick={handleCompute}
              disabled={computing}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              {computing ? 'Computing...' : 'Recompute Scores'}
            </button>
          </div>

          {customerHealth.loading ? (
            <SkeletonTable rows={5} cols={6} />
          ) : customerHealth.error ? (
            <p className="text-red-400">{customerHealth.error}</p>
          ) : customerHealth.data ? (
            <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
              <table className="w-full text-sm">
                <thead className="bg-white/[0.03]">
                  <tr className="text-left text-zinc-400">
                    <th className="px-4 py-2 font-medium">Tenant</th>
                    <th className="px-4 py-2 font-medium text-center">Score</th>
                    <th className="px-4 py-2 font-medium">Status</th>
                    <th className="px-4 py-2 font-medium">Trend</th>
                    <th className="px-4 py-2 font-medium">Last Login</th>
                    <th className="px-4 py-2 font-medium">Last Plan Run</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {customerHealth.data.tenants.map((h) => (
                    <tr key={h.tenant_id} className="text-zinc-300">
                      <td className="px-4 py-2 font-mono text-xs">{h.tenant_id}</td>
                      <td className="px-4 py-2 text-center">
                        <HealthBadge score={h.health_score} />
                      </td>
                      <td className="px-4 py-2">
                        <StatusBadge status={h.health_status} />
                      </td>
                      <td className="px-4 py-2">
                        <TrendArrow direction={h.trend_direction} />
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500">
                        {h.last_login_at ? new Date(h.last_login_at).toLocaleDateString() : 'Never'}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500">
                        {h.last_plan_run_at ? new Date(h.last_plan_run_at).toLocaleDateString() : 'Never'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      )}

      {/* System Health Tab */}
      {tab === 'system' && (
        <div className="space-y-4">
          {healthMetrics.loading ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              {Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)}
            </div>
          ) : healthMetrics.error ? (
            <p className="text-red-400">{healthMetrics.error}</p>
          ) : healthMetrics.data ? (
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
              <StatCard
                label="Error Rate"
                value={healthMetrics.data.error_rate !== null ? `${(healthMetrics.data.error_rate * 100).toFixed(1)}%` : 'N/A'}
                sub={`${healthMetrics.data.failed_runs} / ${healthMetrics.data.total_runs} runs`}
              />
              <StatCard
                label="P95 Runtime"
                value={healthMetrics.data.p95_runtime_seconds !== null ? `${healthMetrics.data.p95_runtime_seconds.toFixed(1)}s` : 'N/A'}
              />
              <StatCard
                label="AI Acceptance"
                value={healthMetrics.data.ai_acceptance_rate !== null ? `${(healthMetrics.data.ai_acceptance_rate * 100).toFixed(1)}%` : 'N/A'}
              />
              <StatCard
                label="AI Accuracy"
                value={healthMetrics.data.ai_avg_accuracy !== null ? `${(healthMetrics.data.ai_avg_accuracy * 100).toFixed(1)}%` : 'N/A'}
              />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
