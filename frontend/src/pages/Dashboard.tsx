import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Activity,
  ArrowRight,
  BarChart3,
  Clock,
  Database,
  Plus,
  RotateCcw,
} from 'lucide-react';
import { usePlans } from '../hooks/usePlans';
import { useRuns } from '../hooks/useRuns';
import { useModels } from '../hooks/useModels';
import { formatCost, formatDate, shortSha, statusColor } from '../utils/formatting';
import type { RunRecord } from '../api/types';

/* ------------------------------------------------------------------ */
/* Stat card                                                           */
/* ------------------------------------------------------------------ */

function StatCard({
  label,
  value,
  icon: Icon,
  color,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  color: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-gray-500">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
        </div>
        <div className={`rounded-lg p-2.5 ${color}`}>
          <Icon size={20} className="text-white" />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Dashboard                                                           */
/* ------------------------------------------------------------------ */

function Dashboard() {
  const navigate = useNavigate();
  const { plans, loading: plansLoading } = usePlans(10, 0);
  const { runs, loading: runsLoading } = useRuns({ limit: 20 });
  const { models } = useModels();

  // Compute metrics
  const successRate = useMemo(() => {
    const completed = runs.filter(
      (r: RunRecord) => r.status === 'SUCCESS' || r.status === 'FAIL',
    );
    if (completed.length === 0) return '--';
    const successes = completed.filter((r: RunRecord) => r.status === 'SUCCESS').length;
    return `${Math.round((successes / completed.length) * 100)}%`;
  }, [runs]);

  const activeBackfills = runs.filter(
    (r: RunRecord) => r.status === 'RUNNING' || r.status === 'PENDING',
  );

  const [showNewPlanForm, setShowNewPlanForm] = useState(false);
  const [repoPath, setRepoPath] = useState('');
  const [baseSha, setBaseSha] = useState('');
  const [targetSha, setTargetSha] = useState('');

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Overview of plans, models, and execution status.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowNewPlanForm((prev) => !prev)}
            className="flex items-center gap-1.5 rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ironlayer-700"
          >
            <Plus size={14} />
            New Plan
          </button>
          <Link
            to="/backfills"
            className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
          >
            <RotateCcw size={14} />
            New Backfill
          </Link>
        </div>
      </div>

      {/* New plan form */}
      {showNewPlanForm && (
        <div className="rounded-lg border border-ironlayer-200 bg-ironlayer-50 p-4">
          <h3 className="mb-3 text-sm font-semibold text-ironlayer-800">
            Generate Plan
          </h3>
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              value={repoPath}
              onChange={(e) => setRepoPath(e.target.value)}
              placeholder="Repository path"
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
            />
            <input
              type="text"
              value={baseSha}
              onChange={(e) => setBaseSha(e.target.value)}
              placeholder="Base SHA"
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
            />
            <input
              type="text"
              value={targetSha}
              onChange={(e) => setTargetSha(e.target.value)}
              placeholder="Target SHA"
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
            />
          </div>
          <div className="mt-3 flex justify-end">
            <button
              onClick={async () => {
                try {
                  const { generatePlan } = await import('../api/client');
                  const plan = await generatePlan(repoPath, baseSha, targetSha);
                  navigate(`/plans/${plan.plan_id}`);
                } catch {
                  /* error handled via toast in production */
                }
              }}
              disabled={!repoPath || !baseSha || !targetSha}
              className="rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ironlayer-700 disabled:opacity-50"
            >
              Generate
            </button>
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Success Rate"
          value={successRate}
          icon={Activity}
          color="bg-green-500"
        />
        <StatCard
          label="Total Plans"
          value={plansLoading ? '--' : String(plans.length)}
          icon={BarChart3}
          color="bg-ironlayer-500"
        />
        <StatCard
          label="Active Runs"
          value={runsLoading ? '--' : String(activeBackfills.length)}
          icon={Clock}
          color="bg-amber-500"
        />
        <StatCard
          label="Models"
          value={String(models.length)}
          icon={Database}
          color="bg-purple-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-6">
        {/* Recent plans */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Recent Plans</h2>
          </div>

          {plansLoading ? (
            <div className="flex items-center justify-center p-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" role="status" aria-label="Loading plans" />
            </div>
          ) : plans.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No plans generated yet.
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {plans.map((p) => (
                <Link
                  key={p.plan_id}
                  to={`/plans/${p.plan_id}`}
                  className="flex items-center justify-between px-4 py-3 transition-colors hover:bg-gray-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-mono text-xs text-gray-700">
                        {shortSha(p.plan_id)}
                      </span>
                      <span className="text-xs text-gray-400">
                        {shortSha(p.base_sha)} <ArrowRight size={10} className="inline" />{' '}
                        {shortSha(p.target_sha)}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
                      <span>{p.total_steps} step{p.total_steps !== 1 ? 's' : ''}</span>
                      <span>{formatCost(p.estimated_cost_usd)}</span>
                      {p.created_at && <span>{formatDate(p.created_at)}</span>}
                    </div>
                  </div>
                  <ArrowRight size={14} className="shrink-0 text-gray-300" />
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* Active runs */}
        <div className="rounded-lg border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Active Runs</h2>
          </div>

          {runsLoading ? (
            <div className="flex items-center justify-center p-8">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" role="status" aria-label="Loading runs" />
            </div>
          ) : activeBackfills.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No active runs at this time.
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {activeBackfills.slice(0, 10).map((run) => (
                <Link
                  key={run.run_id}
                  to={`/runs/${run.run_id}`}
                  className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-gray-50"
                >
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${
                      run.status === 'RUNNING'
                        ? 'animate-pulse bg-blue-500'
                        : 'bg-yellow-400'
                    }`}
                  />
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-medium text-gray-900">
                      {run.model_name}
                    </span>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span
                        className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${statusColor(run.status)}`}
                      >
                        {run.status}
                      </span>
                      {run.started_at && <span>{formatDate(run.started_at)}</span>}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
