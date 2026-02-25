import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RefreshCw } from 'lucide-react';
import type { RunRecord } from '../api/types';
import { formatDate, formatDuration, statusColor } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface RunHistoryProps {
  runs: RunRecord[];
  loading: boolean;
  onRefresh: () => void;
  autoRefresh: boolean;
  onToggleAutoRefresh: () => void;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function computeDuration(run: RunRecord): string {
  if (!run.started_at) return '--';
  const start = new Date(run.started_at).getTime();
  const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
  return formatDuration((end - start) / 1000);
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function RunHistory({
  runs,
  loading,
  onRefresh,
  autoRefresh,
  onToggleAutoRefresh,
}: RunHistoryProps) {
  const navigate = useNavigate();
  const [expandedRun, setExpandedRun] = useState<string | null>(null);

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Run History</h3>
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-1.5 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={onToggleAutoRefresh}
              className="h-3.5 w-3.5 rounded border-gray-300 text-ironlayer-600 focus:ring-ironlayer-500"
            />
            Auto-refresh
          </label>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="rounded p-1 text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 disabled:opacity-50"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Timeline */}
      {runs.length === 0 ? (
        <div className="p-6 text-center text-sm text-gray-500">
          No runs recorded yet.
        </div>
      ) : (
        <div className="divide-y divide-gray-100">
          {runs.map((run) => (
            <div key={run.run_id}>
              <button
                onClick={() =>
                  setExpandedRun((prev) =>
                    prev === run.run_id ? null : run.run_id,
                  )
                }
                className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50"
              >
                {/* Status dot */}
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                    run.status === 'SUCCESS'
                      ? 'bg-green-500'
                      : run.status === 'FAIL'
                        ? 'bg-red-500'
                        : run.status === 'RUNNING'
                          ? 'bg-blue-500 animate-pulse'
                          : run.status === 'PENDING'
                            ? 'bg-yellow-400'
                            : 'bg-gray-400'
                  }`}
                />

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-gray-900">
                      {run.model_name}
                    </span>
                    <span
                      className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${statusColor(
                        run.status,
                      )}`}
                    >
                      {run.status}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
                    <span>{computeDuration(run)}</span>
                    {run.input_range && (
                      <span>
                        {run.input_range.start} to {run.input_range.end}
                      </span>
                    )}
                    {run.started_at && <span>{formatDate(run.started_at)}</span>}
                  </div>
                </div>
              </button>

              {/* Expanded detail */}
              {expandedRun === run.run_id && (
                <div className="border-t border-gray-100 bg-gray-50 px-4 py-3">
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs">
                    <div>
                      <span className="text-gray-400">Run ID</span>
                      <p className="font-mono text-gray-700">
                        {run.run_id.slice(0, 12)}...
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-400">Plan ID</span>
                      <p className="font-mono text-gray-700">
                        {run.plan_id.slice(0, 12)}...
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-400">Cluster</span>
                      <p className="text-gray-700">{run.cluster_used ?? '--'}</p>
                    </div>
                    <div>
                      <span className="text-gray-400">Retries</span>
                      <p className="text-gray-700">{run.retry_count}</p>
                    </div>
                    {run.error_message && (
                      <div className="col-span-2">
                        <span className="text-gray-400">Error</span>
                        <p className="text-red-600">{run.error_message}</p>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => navigate(`/runs/${run.run_id}`)}
                    className="mt-2 text-xs font-medium text-ironlayer-600 hover:text-ironlayer-700"
                  >
                    View full details
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default RunHistory;
