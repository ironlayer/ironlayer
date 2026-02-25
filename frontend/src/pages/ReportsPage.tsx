import { useMemo, useState } from 'react';
import { useCostReport, useUsageReport, useLLMReport } from '../hooks/useReports';
import { downloadReportExport } from '../api/client';
import ErrorBoundary, { ChartErrorFallback } from '../components/ErrorBoundary';
import { SkeletonTable } from '../components/Skeleton';
import { toUTCDateString } from '../utils/formatting';

function DateInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-zinc-400">{label}</span>
      <input
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
      />
    </label>
  );
}

function GroupBySelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-zinc-400">Group by</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white focus:border-indigo-500 focus:outline-none"
      >
        {options.map((o) => (
          <option key={o} value={o} className="bg-zinc-900">
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

function ReportTable({ items }: { items: Record<string, string | number>[] }) {
  if (!items.length) return <p className="text-sm text-zinc-500">No data for this period.</p>;
  const headers = Object.keys(items[0]);
  return (
    <div className="overflow-x-auto rounded-lg border border-white/[0.06]">
      <table className="w-full text-sm">
        <thead className="bg-white/[0.03]">
          <tr>
            {headers.map((h) => (
              <th key={h} className="px-4 py-2 text-left font-medium text-zinc-400">
                {h.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-white/[0.04]">
          {items.map((row, i) => (
            <tr key={i} className="text-zinc-300">
              {headers.map((h) => (
                <td key={h} className="px-4 py-2 font-mono text-xs">
                  {typeof row[h] === 'number' ? (row[h] as number).toLocaleString() : String(row[h])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ReportsPage() {
  const [tab, setTab] = useState<'cost' | 'usage' | 'llm'>('cost');
  const today = new Date().toISOString().slice(0, 10);
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);

  const [since, setSince] = useState(thirtyDaysAgo);
  const [until, setUntil] = useState(today);
  const [costGroupBy, setCostGroupBy] = useState('model');
  const [usageGroupBy, setUsageGroupBy] = useState('actor');

  const dateRangeError = useMemo(() => {
    if (!since || !until) return null;
    if (until < since) return 'End date must be on or after start date.';
    return null;
  }, [since, until]);

  const utcSince = useMemo(() => toUTCDateString(since), [since]);
  const utcUntil = useMemo(() => toUTCDateString(until), [until]);

  // Only fetch when date range is valid
  const safeSince = dateRangeError ? '' : utcSince;
  const safeUntil = dateRangeError ? '' : utcUntil;

  const costReport = useCostReport(safeSince, safeUntil, costGroupBy);
  const usageReport = useUsageReport(safeSince, safeUntil, usageGroupBy);
  const llmReport = useLLMReport(safeSince, safeUntil);

  const tabs = [
    { key: 'cost' as const, label: 'Cost' },
    { key: 'usage' as const, label: 'Usage' },
    { key: 'llm' as const, label: 'LLM' },
  ];

  const handleExport = (fmt: string) => {
    downloadReportExport(tab, since, until, fmt);
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">Reports</h1>

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

      {/* Controls */}
      <div className="flex flex-wrap items-end gap-4">
        <DateInput value={since} onChange={setSince} label="From" />
        <DateInput value={until} onChange={setUntil} label="To" />

        {dateRangeError && (
          <p className="self-end rounded-md bg-red-500/10 border border-red-500/20 px-3 py-1.5 text-sm text-red-400" role="alert">
            {dateRangeError}
          </p>
        )}

        {tab === 'cost' && (
          <GroupBySelect value={costGroupBy} onChange={setCostGroupBy} options={['model', 'day', 'week', 'month']} />
        )}
        {tab === 'usage' && (
          <GroupBySelect value={usageGroupBy} onChange={setUsageGroupBy} options={['actor', 'day', 'week', 'month']} />
        )}

        <div className="flex gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="rounded-md border border-white/[0.08] px-3 py-1.5 text-sm text-zinc-300 hover:bg-white/[0.04]"
          >
            Export CSV
          </button>
          <button
            onClick={() => handleExport('json')}
            className="rounded-md border border-white/[0.08] px-3 py-1.5 text-sm text-zinc-300 hover:bg-white/[0.04]"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Cost Tab */}
      {tab === 'cost' && (
        <ErrorBoundary fallback={<ChartErrorFallback />}>
          <div className="space-y-4">
            {costReport.loading ? (
              <SkeletonTable rows={5} cols={4} />
            ) : costReport.error ? (
              <p className="text-red-400">{costReport.error}</p>
            ) : costReport.data ? (
              <>
                <div className="flex items-center gap-4">
                  <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-4 py-3">
                    <p className="text-xs text-zinc-400">Total Cost</p>
                    <p className="text-xl font-semibold text-white">${costReport.data.total_cost_usd.toFixed(2)}</p>
                  </div>
                </div>
                <ReportTable items={costReport.data.items} />
              </>
            ) : null}
          </div>
        </ErrorBoundary>
      )}

      {/* Usage Tab */}
      {tab === 'usage' && (
        <ErrorBoundary fallback={<ChartErrorFallback />}>
          <div className="space-y-4">
            {usageReport.loading ? (
              <SkeletonTable rows={5} cols={4} />
            ) : usageReport.error ? (
              <p className="text-red-400">{usageReport.error}</p>
            ) : usageReport.data ? (
              <ReportTable items={usageReport.data.items} />
            ) : null}
          </div>
        </ErrorBoundary>
      )}

      {/* LLM Tab */}
      {tab === 'llm' && (
        <ErrorBoundary fallback={<ChartErrorFallback />}>
          <div className="space-y-4">
            {llmReport.loading ? (
              <SkeletonTable rows={5} cols={4} />
            ) : llmReport.error ? (
              <p className="text-red-400">{llmReport.error}</p>
            ) : llmReport.data ? (
              <>
                <div className="flex items-center gap-4">
                  <div className="rounded-lg border border-white/[0.06] bg-white/[0.03] px-4 py-3">
                    <p className="text-xs text-zinc-400">Total LLM Cost</p>
                    <p className="text-xl font-semibold text-white">${llmReport.data.total_cost_usd.toFixed(4)}</p>
                  </div>
                </div>
                <h3 className="text-sm font-medium text-zinc-300">By Call Type</h3>
                <ReportTable items={llmReport.data.by_call_type} />
                <h3 className="text-sm font-medium text-zinc-300">By Day</h3>
                <ReportTable items={llmReport.data.by_time} />
              </>
            ) : null}
          </div>
        </ErrorBoundary>
      )}
    </div>
  );
}
