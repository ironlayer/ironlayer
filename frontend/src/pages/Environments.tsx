import { useCallback, useEffect, useState } from 'react';
import {
  GitBranch,
  Globe,
  Plus,
  RefreshCw,
  Shield,
  Timer,
  Trash2,
  X,
} from 'lucide-react';
import type { Environment, EnvironmentPromotion } from '../api/types';
import {
  cleanupExpiredEnvironments,
  createEnvironment,
  deleteEnvironment,
  fetchEnvironmentPromotions,
  fetchEnvironments,
} from '../api/client';
import PromotionFlow from '../components/PromotionFlow';

/* ------------------------------------------------------------------ */
/* Badge component                                                     */
/* ------------------------------------------------------------------ */

function EnvBadge({
  label,
  color,
  bgColor,
}: {
  label: string;
  color: string;
  bgColor: string;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color} ${bgColor}`}
    >
      {label}
    </span>
  );
}

function envBadges(env: Environment) {
  const badges: { label: string; color: string; bgColor: string }[] = [];
  if (env.is_production) {
    badges.push({
      label: 'Production',
      color: 'text-red-700',
      bgColor: 'bg-red-50',
    });
  }
  if (env.is_default) {
    badges.push({
      label: 'Default',
      color: 'text-ironlayer-700',
      bgColor: 'bg-ironlayer-50',
    });
  }
  if (env.is_ephemeral) {
    badges.push({
      label: 'Ephemeral',
      color: 'text-amber-700',
      bgColor: 'bg-amber-50',
    });
  }
  return badges;
}

/* ------------------------------------------------------------------ */
/* Environment card                                                    */
/* ------------------------------------------------------------------ */

function EnvironmentCard({
  env,
  onDelete,
  onPromote,
}: {
  env: Environment;
  onDelete: (name: string) => void;
  onPromote: (env: Environment) => void;
}) {
  const badges = envBadges(env);
  const isExpired = env.expires_at && new Date(env.expires_at) < new Date();

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-5 transition-shadow hover:shadow-sm">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`flex h-10 w-10 items-center justify-center rounded-lg ${
              env.is_production
                ? 'bg-red-50'
                : env.is_ephemeral
                  ? 'bg-amber-50'
                  : 'bg-ironlayer-50'
            }`}
          >
            {env.is_production ? (
              <Shield
                className="h-5 w-5 text-red-600"
                size={20}
              />
            ) : env.is_ephemeral ? (
              <Timer
                className="h-5 w-5 text-amber-600"
                size={20}
              />
            ) : (
              <Globe
                className="h-5 w-5 text-ironlayer-600"
                size={20}
              />
            )}
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{env.name}</h3>
            <p className="text-xs text-gray-500">
              {env.catalog}.{env.schema_prefix}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {badges.map((b) => (
            <EnvBadge key={b.label} {...b} />
          ))}
        </div>
      </div>

      {/* Metadata */}
      <div className="mt-4 grid grid-cols-2 gap-3 text-xs text-gray-500">
        <div>
          <span className="font-medium text-gray-700">Created by</span>
          <p>{env.created_by}</p>
        </div>
        <div>
          <span className="font-medium text-gray-700">Created</span>
          <p>{new Date(env.created_at).toLocaleDateString()}</p>
        </div>
        {env.is_ephemeral && env.pr_number && (
          <div>
            <span className="font-medium text-gray-700">PR</span>
            <p className="flex items-center gap-1">
              <GitBranch className="h-3 w-3" size={12} />#{env.pr_number}
              {env.branch_name && (
                <span className="text-gray-400">({env.branch_name})</span>
              )}
            </p>
          </div>
        )}
        {env.expires_at && (
          <div>
            <span className="font-medium text-gray-700">Expires</span>
            <p className={isExpired ? 'text-red-600' : ''}>
              {new Date(env.expires_at).toLocaleString()}
              {isExpired && ' (expired)'}
            </p>
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2 border-t border-gray-100 pt-3">
        {!env.is_production && (
          <button
            onClick={() => onPromote(env)}
            className="flex items-center gap-1.5 rounded-md bg-ironlayer-50 px-3 py-1.5 text-xs font-medium text-ironlayer-700 hover:bg-ironlayer-100"
          >
            <RefreshCw className="h-3 w-3" size={12} />
            Promote
          </button>
        )}
        <button
          onClick={() => onDelete(env.name)}
          className="flex items-center gap-1.5 rounded-md bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-red-50 hover:text-red-700"
        >
          <Trash2 className="h-3 w-3" size={12} />
          Delete
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Create environment dialog                                           */
/* ------------------------------------------------------------------ */

function CreateEnvironmentDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [catalog, setCatalog] = useState('');
  const [schemaPrefix, setSchemaPrefix] = useState('');
  const [createdBy, setCreatedBy] = useState('');
  const [isEphemeral, setIsEphemeral] = useState(false);
  const [prNumber, setPrNumber] = useState('');
  const [branchName, setBranchName] = useState('');
  const [expiresAt, setExpiresAt] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = name && catalog && schemaPrefix && createdBy;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    try {
      await createEnvironment({
        name,
        catalog,
        schema_prefix: schemaPrefix,
        created_by: createdBy,
        is_ephemeral: isEphemeral,
        ...(prNumber ? { pr_number: parseInt(prNumber, 10) } : {}),
        ...(branchName ? { branch_name: branchName } : {}),
        ...(expiresAt ? { expires_at: new Date(expiresAt).toISOString() } : {}),
      });
      onCreated();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create environment');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-bold text-gray-900">New Environment</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" size={20} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. staging-v2"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Catalog
              </label>
              <input
                type="text"
                value={catalog}
                onChange={(e) => setCatalog(e.target.value)}
                placeholder="e.g. analytics"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Schema Prefix
              </label>
              <input
                type="text"
                value={schemaPrefix}
                onChange={(e) => setSchemaPrefix(e.target.value)}
                placeholder="e.g. stg_v2"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Created By
            </label>
            <input
              type="text"
              value={createdBy}
              onChange={(e) => setCreatedBy(e.target.value)}
              placeholder="your-username"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isEphemeral}
              onChange={(e) => setIsEphemeral(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-ironlayer-600 focus:ring-ironlayer-500"
            />
            <span className="text-gray-700">Ephemeral (PR environment)</span>
          </label>

          {isEphemeral && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  PR Number
                </label>
                <input
                  type="number"
                  value={prNumber}
                  onChange={(e) => setPrNumber(e.target.value)}
                  placeholder="e.g. 42"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">
                  Branch Name
                </label>
                <input
                  type="text"
                  value={branchName}
                  onChange={(e) => setBranchName(e.target.value)}
                  placeholder="e.g. feature/xyz"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
                />
              </div>
            </div>
          )}

          {isEphemeral && (
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Expires At
              </label>
              <input
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
              />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-gray-200 px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || submitting}
            className="rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white hover:bg-ironlayer-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? 'Creating...' : 'Create Environment'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

function Environments() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [promotions, setPromotions] = useState<EnvironmentPromotion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [promotionSource, setPromotionSource] = useState<Environment | null>(null);
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [envs, promos] = await Promise.all([
        fetchEnvironments(),
        fetchEnvironmentPromotions(10),
      ]);
      setEnvironments(envs);
      setPromotions(promos);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load environments');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleDelete = async (name: string) => {
    if (!confirm(`Delete environment "${name}"?`)) return;
    try {
      await deleteEnvironment(name);
      await loadData();
    } catch {
      setError('Failed to delete environment');
    }
  };

  const handleCleanup = async () => {
    try {
      const result = await cleanupExpiredEnvironments();
      if (result.deleted_count > 0) {
        await loadData();
      }
    } catch {
      setError('Failed to run cleanup');
    }
  };

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        {error}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 text-gray-400">
        Loading environments...
      </div>
    );
  }

  const productionEnvs = environments.filter((e) => e.is_production);
  const standardEnvs = environments.filter((e) => !e.is_production && !e.is_ephemeral);
  const ephemeralEnvs = environments.filter((e) => e.is_ephemeral);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Environments</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage deployment environments with catalog/schema isolation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleCleanup}
            className="flex items-center gap-1.5 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
          >
            <Timer className="h-4 w-4" size={16} />
            Cleanup Expired
          </button>
          <button
            onClick={() => setShowCreateDialog(true)}
            className="flex items-center gap-1.5 rounded-lg bg-ironlayer-600 px-3 py-2 text-sm font-medium text-white hover:bg-ironlayer-700"
          >
            <Plus className="h-4 w-4" size={16} />
            New Environment
          </button>
        </div>
      </div>

      {/* Production environments */}
      {productionEnvs.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Production
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {productionEnvs.map((env) => (
              <EnvironmentCard
                key={env.id}
                env={env}
                onDelete={handleDelete}
                onPromote={setPromotionSource}
              />
            ))}
          </div>
        </section>
      )}

      {/* Standard environments */}
      {standardEnvs.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Standard
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {standardEnvs.map((env) => (
              <EnvironmentCard
                key={env.id}
                env={env}
                onDelete={handleDelete}
                onPromote={setPromotionSource}
              />
            ))}
          </div>
        </section>
      )}

      {/* Ephemeral PR environments */}
      {ephemeralEnvs.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Ephemeral (PR Environments)
          </h2>
          <div className="grid gap-4 lg:grid-cols-2">
            {ephemeralEnvs.map((env) => (
              <EnvironmentCard
                key={env.id}
                env={env}
                onDelete={handleDelete}
                onPromote={setPromotionSource}
              />
            ))}
          </div>
        </section>
      )}

      {environments.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <Globe className="mx-auto h-12 w-12 text-gray-300" size={48} />
          <h3 className="mt-4 text-sm font-medium text-gray-900">No environments</h3>
          <p className="mt-1 text-sm text-gray-500">
            Create your first environment to enable catalog/schema isolation
          </p>
        </div>
      )}

      {/* Recent promotions */}
      {promotions.length > 0 && (
        <section>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-gray-500">
            Recent Promotions
          </h2>
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Source</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Target</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Snapshot</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Promoted By</th>
                  <th className="px-4 py-3 text-left font-medium text-gray-500">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {promotions.map((p) => (
                  <tr key={p.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium text-gray-900">
                      {p.source_environment}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{p.target_environment}</td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">
                      {p.source_snapshot_id.slice(0, 12)}
                    </td>
                    <td className="px-4 py-3 text-gray-700">{p.promoted_by}</td>
                    <td className="px-4 py-3 text-gray-500">
                      {new Date(p.promoted_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Promotion dialog */}
      {promotionSource && (
        <PromotionFlow
          sourceEnvironment={promotionSource}
          allEnvironments={environments}
          onClose={() => setPromotionSource(null)}
          onPromoted={loadData}
        />
      )}

      {/* Create environment dialog */}
      {showCreateDialog && (
        <CreateEnvironmentDialog
          onClose={() => setShowCreateDialog(false)}
          onCreated={loadData}
        />
      )}
    </div>
  );
}

export default Environments;
