import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  ExternalLink,
  RefreshCw,
  Server,
} from 'lucide-react';
import { useRun } from '../hooks/useRuns';
import { fetchRunTelemetry } from '../api/client';
import type { RunTelemetry } from '../api/types';
import {
  formatBytes,
  formatDate,
  formatDateRange,
  formatDuration,
  formatNumber,
  shortSha,
  statusColor,
} from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Metadata row helper                                                 */
/* ------------------------------------------------------------------ */

function MetaItem({
  label,
  children,
  mono,
}: {
  label: string;
  children: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <span className="text-xs text-gray-400">{label}</span>
      <p className={`mt-0.5 text-sm text-gray-800 ${mono ? 'font-mono text-xs' : ''}`}>
        {children}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function RunDetail() {
  const { id } = useParams<{ id: string }>();
  const { run, loading, error, refetch } = useRun(id);

  const [telemetry, setTelemetry] = useState<RunTelemetry | null>(null);
  const [telemetryLoading, setTelemetryLoading] = useState(false);

  useEffect(() => {
    if (!id) return;
    setTelemetryLoading(true);
    fetchRunTelemetry(id)
      .then(setTelemetry)
      .finally(() => setTelemetryLoading(false));
  }, [id]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
        {error ?? 'Run not found.'}
      </div>
    );
  }

  const duration = (() => {
    if (!run.started_at) return '--';
    const start = new Date(run.started_at).getTime();
    const end = run.finished_at ? new Date(run.finished_at).getTime() : Date.now();
    return formatDuration((end - start) / 1000);
  })();

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-sm text-gray-500 transition-colors hover:text-gray-700"
      >
        <ArrowLeft size={14} />
        Back to Dashboard
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Run Detail</h1>
            <span
              className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${statusColor(
                run.status,
              )}`}
            >
              {run.status}
            </span>
          </div>
          <div className="mt-1 flex items-center gap-4 text-sm text-gray-500">
            <span className="font-mono">{shortSha(run.run_id)}</span>
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {duration}
            </span>
            <span>{run.model_name}</span>
          </div>
        </div>
        <button
          onClick={refetch}
          className="rounded-lg border border-gray-300 bg-white p-2 text-gray-600 transition-colors hover:bg-gray-50"
          title="Refresh"
        >
          <RefreshCw size={14} />
        </button>
      </div>

      {/* Metadata */}
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">Run Metadata</h2>
        </div>
        <div className="grid grid-cols-4 gap-4 p-4">
          <MetaItem label="Run ID" mono>
            {run.run_id}
          </MetaItem>
          <MetaItem label="Plan ID" mono>
            <Link
              to={`/plans/${run.plan_id}`}
              className="text-ironlayer-600 hover:text-ironlayer-700"
            >
              {shortSha(run.plan_id)}
            </Link>
          </MetaItem>
          <MetaItem label="Step ID" mono>
            {shortSha(run.step_id)}
          </MetaItem>
          <MetaItem label="Model">
            <Link
              to={`/models/${encodeURIComponent(run.model_name)}`}
              className="text-ironlayer-600 hover:text-ironlayer-700"
            >
              {run.model_name}
            </Link>
          </MetaItem>
          <MetaItem label="Cluster">
            <span className="flex items-center gap-1">
              <Server size={12} className="text-gray-400" />
              {run.cluster_used ?? '--'}
            </span>
          </MetaItem>
          <MetaItem label="Executor Version">{run.executor_version}</MetaItem>
          <MetaItem label="Retry Count">{run.retry_count}</MetaItem>
          <MetaItem label="Status">
            <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(run.status)}`}>
              {run.status}
            </span>
          </MetaItem>
        </div>
      </div>

      {/* Timing & input */}
      <div className="grid grid-cols-2 gap-6">
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Timing</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">Started</span>
              <span className="text-gray-800">
                {run.started_at ? formatDate(run.started_at) : '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Finished</span>
              <span className="text-gray-800">
                {run.finished_at ? formatDate(run.finished_at) : '--'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Duration</span>
              <span className="font-medium text-gray-900">{duration}</span>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">Input Range</h3>
          {run.input_range ? (
            <p className="text-sm text-gray-800">
              {formatDateRange(run.input_range)}
            </p>
          ) : (
            <p className="text-sm text-gray-500">
              No input range (full refresh).
            </p>
          )}
        </div>
      </div>

      {/* Error */}
      {run.error_message && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-center gap-2 text-sm font-medium text-red-800">
            <AlertTriangle size={16} />
            Error
          </div>
          <p className="mt-2 whitespace-pre-wrap font-mono text-xs text-red-700">
            {run.error_message}
          </p>
        </div>
      )}

      {/* Logs URI */}
      {run.logs_uri && (
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-2 text-sm font-semibold text-gray-900">Logs</h3>
          <a
            href={run.logs_uri}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm text-ironlayer-600 hover:text-ironlayer-700"
          >
            {run.logs_uri}
            <ExternalLink size={12} />
          </a>
        </div>
      )}

      {/* Telemetry */}
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">Telemetry</h2>
        </div>

        {telemetryLoading ? (
          <div className="flex items-center justify-center p-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
          </div>
        ) : telemetry ? (
          <div className="grid grid-cols-3 gap-4 p-4">
            <div className="rounded-lg bg-gray-50 p-3 text-center">
              <span className="text-xs text-gray-400">Runtime</span>
              <p className="mt-1 text-lg font-bold text-gray-900">
                {formatDuration(telemetry.runtime_seconds)}
              </p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-center">
              <span className="text-xs text-gray-400">Shuffle Bytes</span>
              <p className="mt-1 text-lg font-bold text-gray-900">
                {formatBytes(telemetry.shuffle_bytes)}
              </p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-center">
              <span className="text-xs text-gray-400">Rows In</span>
              <p className="mt-1 text-lg font-bold text-gray-900">
                {formatNumber(telemetry.input_rows)}
              </p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-center">
              <span className="text-xs text-gray-400">Rows Out</span>
              <p className="mt-1 text-lg font-bold text-gray-900">
                {formatNumber(telemetry.output_rows)}
              </p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3 text-center">
              <span className="text-xs text-gray-400">Partitions</span>
              <p className="mt-1 text-lg font-bold text-gray-900">
                {formatNumber(telemetry.partition_count)}
              </p>
            </div>
            {telemetry.cluster_id && (
              <div className="rounded-lg bg-gray-50 p-3 text-center">
                <span className="text-xs text-gray-400">Cluster</span>
                <p className="mt-1 text-sm font-medium text-gray-900">
                  {telemetry.cluster_id}
                </p>
              </div>
            )}
          </div>
        ) : (
          <div className="p-6 text-center text-sm text-gray-500">
            No telemetry data available for this run.
          </div>
        )}
      </div>
    </div>
  );
}

export default RunDetail;
