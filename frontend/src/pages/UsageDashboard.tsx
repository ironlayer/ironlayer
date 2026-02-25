import { useState } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import {
  Activity,
  BarChart2,
  Cpu,
  Database,
  GitMerge,
  Zap,
} from 'lucide-react';
import ErrorBoundary, { ChartErrorFallback } from '../components/ErrorBoundary';
import { useUsageSummary, useUsageEvents } from '../hooks/useUsage';

const EVENT_TYPE_LABELS: Record<string, string> = {
  plan_run: 'Plan Runs',
  plan_apply: 'Plan Applies',
  ai_call: 'AI Calls',
  model_loaded: 'Models Loaded',
  backfill_run: 'Backfills',
  api_request: 'API Requests',
};

const EVENT_TYPE_ICONS: Record<string, typeof Activity> = {
  plan_run: GitMerge,
  plan_apply: Zap,
  ai_call: Cpu,
  model_loaded: Database,
  backfill_run: Activity,
  api_request: BarChart2,
};

const EVENT_TYPE_COLORS: Record<string, string> = {
  plan_run: '#6366f1',
  plan_apply: '#f59e0b',
  ai_call: '#10b981',
  model_loaded: '#3b82f6',
  backfill_run: '#8b5cf6',
  api_request: '#6b7280',
};

const EVENT_TYPES = [
  'plan_run',
  'plan_apply',
  'ai_call',
  'model_loaded',
  'backfill_run',
  'api_request',
];

function UsageDashboard() {
  const [days, setDays] = useState(30);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const { summary, loading: summaryLoading, error: summaryError } = useUsageSummary(days);
  const { events, total, loading: eventsLoading, error: eventsError } = useUsageEvents(filterType, 20);

  // Build chart data from summary
  const barChartData = summary
    ? Object.entries(summary.events_by_type).map(([type, count]) => ({
        name: EVENT_TYPE_LABELS[type] ?? type,
        count,
        fill: EVENT_TYPE_COLORS[type] ?? '#6b7280',
      }))
    : [];

  const error = summaryError || eventsError;

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Usage Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Monitor platform usage across all metered operations
          </p>
        </div>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label="Select time range"
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50"
        >
          <option value={7}>Last 7 days</option>
          <option value={14}>Last 14 days</option>
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
        </select>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        {EVENT_TYPES.map((type) => {
          const Icon = EVENT_TYPE_ICONS[type] ?? Activity;
          const count = summary?.events_by_type[type] ?? 0;
          const label = EVENT_TYPE_LABELS[type] ?? type;

          return (
            <button
              key={type}
              onClick={() => setFilterType(filterType === type ? undefined : type)}
              className={`rounded-xl border p-4 text-left transition-all hover:shadow-md ${
                filterType === type
                  ? 'border-ironlayer-500 bg-ironlayer-50 ring-1 ring-ironlayer-500'
                  : 'border-gray-200 bg-white'
              }`}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-gray-400" size={16} />
                <span className="text-xs font-medium text-gray-500">{label}</span>
              </div>
              <p className="mt-2 text-2xl font-bold text-gray-900">
                {summaryLoading ? '...' : count.toLocaleString()}
              </p>
            </button>
          );
        })}
      </div>

      {/* Total banner */}
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm font-medium text-gray-500">Total Events</span>
            <p className="text-3xl font-bold text-gray-900">
              {summaryLoading ? '...' : (summary?.total_events ?? 0).toLocaleString()}
            </p>
          </div>
          <div className="text-right text-sm text-gray-500">
            {summary?.period_start && (
              <span>
                {new Date(summary.period_start).toLocaleDateString()} &ndash;{' '}
                {new Date(summary.period_end).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Bar chart: events by type */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-semibold text-gray-900">Events by Type</h3>
          <div className="h-64">
            <ErrorBoundary fallback={<ChartErrorFallback />}>
              {barChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={barChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis
                      dataKey="name"
                      tick={{ fontSize: 11 }}
                      angle={-20}
                      textAnchor="end"
                      height={60}
                    />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip
                      contentStyle={{ fontSize: 12 }}
                      formatter={(value: number) => [value.toLocaleString(), 'Count']}
                    />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-sm text-gray-400">
                  No usage data available
                </div>
              )}
            </ErrorBoundary>
          </div>
        </div>

        {/* Quota progress (placeholder -- real quotas come from billing) */}
        <div className="rounded-xl border border-gray-200 bg-white p-6">
          <h3 className="mb-4 text-sm font-semibold text-gray-900">Quota Usage</h3>
          <div className="space-y-4">
            {['plan_run', 'ai_call', 'backfill_run'].map((type) => {
              const count = summary?.events_by_type[type] ?? 0;
              const limit = type === 'plan_run' ? 100 : type === 'ai_call' ? 500 : 50;
              const pct = Math.min((count / limit) * 100, 100);
              const label = EVENT_TYPE_LABELS[type] ?? type;

              return (
                <div key={type}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="font-medium text-gray-700">{label}</span>
                    <span className="text-gray-500">
                      {count} / {limit}
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                    <div
                      className={`h-full rounded-full transition-all ${
                        pct >= 90
                          ? 'bg-red-500'
                          : pct >= 70
                            ? 'bg-yellow-500'
                            : 'bg-ironlayer-500'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Recent events table */}
      <div className="rounded-xl border border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h3 className="text-sm font-semibold text-gray-900">Recent Events</h3>
          <div className="flex items-center gap-2">
            <select
              value={filterType ?? ''}
              onChange={(e) => setFilterType(e.target.value || undefined)}
              aria-label="Filter by event type"
              className="rounded border border-gray-300 px-2 py-1 text-xs"
            >
              <option value="">All types</option>
              {EVENT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {EVENT_TYPE_LABELS[type] ?? type}
                </option>
              ))}
            </select>
            <span className="text-xs text-gray-500">{total} total</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-100 text-xs font-medium uppercase text-gray-500">
                <th className="px-6 py-3">Event</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Qty</th>
                <th className="px-6 py-3">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {eventsLoading ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                    Loading events...
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-gray-400">
                    No events found
                  </td>
                </tr>
              ) : (
                events.map((event) => (
                  <tr key={event.event_id} className="hover:bg-gray-50">
                    <td className="px-6 py-3 font-mono text-xs text-gray-600">
                      {event.event_id}
                    </td>
                    <td className="px-6 py-3">
                      <span
                        className="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{
                          backgroundColor: `${EVENT_TYPE_COLORS[event.event_type] ?? '#6b7280'}15`,
                          color: EVENT_TYPE_COLORS[event.event_type] ?? '#6b7280',
                        }}
                      >
                        {EVENT_TYPE_LABELS[event.event_type] ?? event.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-gray-700">{event.quantity}</td>
                    <td className="px-6 py-3 text-xs text-gray-500">
                      {new Date(event.created_at).toLocaleString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export default UsageDashboard;
