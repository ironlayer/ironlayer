import { useCallback, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Calendar, RotateCcw, Server, Zap } from 'lucide-react';
import { useModels } from '../hooks/useModels';
import { useRuns } from '../hooks/useRuns';
import { createBackfill } from '../api/client';
import type { RunRecord } from '../api/types';
import { formatCost, formatDate, formatDateRange, statusColor, toUTCDateString } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Cluster options                                                     */
/* ------------------------------------------------------------------ */

const CLUSTER_OPTIONS = [
  { value: 'small', label: 'Small (4 cores)', costPerHour: 0.5 },
  { value: 'medium', label: 'Medium (8 cores)', costPerHour: 1.0 },
  { value: 'large', label: 'Large (16 cores)', costPerHour: 2.0 },
  { value: 'xlarge', label: 'X-Large (32 cores)', costPerHour: 4.0 },
] as const;

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function BackfillPage() {
  const navigate = useNavigate();
  const { models } = useModels();
  const { runs, loading: runsLoading } = useRuns({ limit: 50 });

  // Form state
  const [selectedModel, setSelectedModel] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [clusterSize, setClusterSize] = useState('medium');
  const [modelSearch, setModelSearch] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // Autocomplete filter
  const filteredModels = useMemo(() => {
    if (!modelSearch.trim()) return models.slice(0, 20);
    const q = modelSearch.toLowerCase();
    return models.filter((m) => m.model_name.toLowerCase().includes(q)).slice(0, 20);
  }, [models, modelSearch]);

  // Cost estimate
  const estimatedCost = useMemo(() => {
    if (!startDate || !endDate) return null;
    const start = new Date(startDate);
    const end = new Date(endDate);
    if (isNaN(start.getTime()) || isNaN(end.getTime()) || start > end) return null;

    const days = Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
    const cluster = CLUSTER_OPTIONS.find((c) => c.value === clusterSize);
    const costPerHour = cluster?.costPerHour ?? 1.0;
    // Rough estimate: ~5 minutes per day of data
    const estimatedHours = (days * 5) / 60;
    return estimatedHours * costPerHour;
  }, [startDate, endDate, clusterSize]);

  const partitionCount = useMemo(() => {
    if (!startDate || !endDate) return 0;
    const start = new Date(startDate);
    const end = new Date(endDate);
    if (isNaN(start.getTime()) || isNaN(end.getTime()) || start > end) return 0;
    return Math.ceil((end.getTime() - start.getTime()) / (1000 * 60 * 60 * 24)) + 1;
  }, [startDate, endDate]);

  // Active backfills
  const activeBackfills = useMemo(
    () =>
      runs.filter(
        (r: RunRecord) => r.status === 'RUNNING' || r.status === 'PENDING',
      ),
    [runs],
  );

  const handleSubmit = useCallback(async () => {
    if (!selectedModel || !startDate || !endDate) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const plan = await createBackfill(selectedModel, toUTCDateString(startDate), toUTCDateString(endDate), clusterSize);
      navigate(`/plans/${plan.plan_id}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Failed to create backfill');
    } finally {
      setSubmitting(false);
    }
  }, [selectedModel, startDate, endDate, clusterSize, navigate]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Backfills</h1>
        <p className="mt-1 text-sm text-gray-500">
          Create historical data backfill jobs for any model.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Form */}
        <div className="col-span-2 rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">
              Create Backfill
            </h2>
          </div>
          <div className="space-y-4 p-4">
            {/* Model select */}
            <div>
              <label htmlFor="backfill-model" className="mb-1 block text-xs font-medium text-gray-700">
                Model
              </label>
              <div className="relative">
                <input
                  id="backfill-model"
                  type="text"
                  value={selectedModel || modelSearch}
                  onChange={(e) => {
                    setModelSearch(e.target.value);
                    setSelectedModel('');
                  }}
                  placeholder="Search for a model..."
                  aria-describedby="backfill-model-hint"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
                />
                <span id="backfill-model-hint" className="sr-only">Search and select a model for backfill</span>
                {modelSearch && !selectedModel && filteredModels.length > 0 && (
                  <div className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded-lg border border-gray-200 bg-white shadow-lg">
                    {filteredModels.map((m) => (
                      <button
                        key={m.model_name}
                        onClick={() => {
                          setSelectedModel(m.model_name);
                          setModelSearch('');
                        }}
                        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-gray-50"
                      >
                        <RotateCcw size={12} className="shrink-0 text-gray-400" />
                        <span className="text-gray-800">{m.model_name}</span>
                        <span className="ml-auto text-[10px] text-gray-400">
                          {m.kind.replace(/_/g, ' ')}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Date range */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="backfill-start-date" className="mb-1 block text-xs font-medium text-gray-700">
                  <Calendar size={12} className="mr-1 inline" aria-hidden="true" />
                  Start Date
                </label>
                <input
                  id="backfill-start-date"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
                />
              </div>
              <div>
                <label htmlFor="backfill-end-date" className="mb-1 block text-xs font-medium text-gray-700">
                  <Calendar size={12} className="mr-1 inline" aria-hidden="true" />
                  End Date
                </label>
                <input
                  id="backfill-end-date"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
                />
              </div>
            </div>

            {/* Cluster size */}
            <div>
              <label htmlFor="backfill-cluster" className="mb-1 block text-xs font-medium text-gray-700">
                <Server size={12} className="mr-1 inline" aria-hidden="true" />
                Cluster Size
              </label>
              <select
                id="backfill-cluster"
                value={clusterSize}
                onChange={(e) => setClusterSize(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
              >
                {CLUSTER_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label} - {formatCost(opt.costPerHour)}/hr
                  </option>
                ))}
              </select>
            </div>

            {/* Preview */}
            {partitionCount > 0 && (
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                  Preview
                </h4>
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div>
                    <span className="text-xs text-gray-400">Partitions</span>
                    <p className="font-semibold text-gray-800">{partitionCount}</p>
                  </div>
                  <div>
                    <span className="text-xs text-gray-400">Date Range</span>
                    <p className="text-gray-800">
                      {formatDateRange({ start: startDate, end: endDate })}
                    </p>
                  </div>
                  <div>
                    <span className="text-xs text-gray-400">Est. Cost</span>
                    <p className="font-semibold text-gray-800">
                      {estimatedCost !== null ? formatCost(estimatedCost) : '--'}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Error */}
            {submitError && (
              <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                {submitError}
              </div>
            )}

            {/* Submit */}
            <button
              onClick={() => void handleSubmit()}
              disabled={
                submitting || !selectedModel || !startDate || !endDate
              }
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-ironlayer-600 py-2.5 text-sm font-medium text-white transition-colors hover:bg-ironlayer-700 disabled:opacity-50"
            >
              <Zap size={14} />
              {submitting ? 'Creating...' : 'Create Backfill'}
            </button>
          </div>
        </div>

        {/* Active backfills sidebar */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="border-b border-gray-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">
              Active Backfills
            </h2>
          </div>

          {runsLoading ? (
            <div className="flex items-center justify-center p-8">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" role="status" aria-label="Loading active backfills" />
            </div>
          ) : activeBackfills.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No active backfills.
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {activeBackfills.map((run) => (
                <div key={run.run_id} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-gray-900">
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
                  <div className="mt-1 text-xs text-gray-500">
                    {run.input_range && (
                      <span>
                        {formatDateRange(run.input_range)}
                      </span>
                    )}
                    {run.started_at && (
                      <span className="ml-2">Started {formatDate(run.started_at)}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default BackfillPage;
