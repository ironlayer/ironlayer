import { useState } from 'react';
import { ArrowRight, AlertTriangle, X } from 'lucide-react';
import type { Environment } from '../api/types';
import { promoteEnvironment } from '../api/client';

interface PromotionFlowProps {
  sourceEnvironment: Environment;
  allEnvironments: Environment[];
  onClose: () => void;
  onPromoted: () => void;
}

function PromotionFlow({
  sourceEnvironment,
  allEnvironments,
  onClose,
  onPromoted,
}: PromotionFlowProps) {
  const [targetName, setTargetName] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [promotedBy, setPromotedBy] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const targets = allEnvironments.filter(
    (e) => e.name !== sourceEnvironment.name && !e.is_ephemeral,
  );

  const selectedTarget = targets.find((e) => e.name === targetName);
  const isToProduction = selectedTarget?.is_production ?? false;
  const canSubmit = targetName && snapshotId && promotedBy && confirmed;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);

    try {
      await promoteEnvironment(sourceEnvironment.name, {
        target_environment: targetName,
        snapshot_id: snapshotId,
        promoted_by: promotedBy,
      });

      onPromoted();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Promotion failed');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-bold text-gray-900">Promote Snapshot</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            <X className="h-5 w-5" size={20} />
          </button>
        </div>

        {/* Body */}
        <div className="space-y-5 px-6 py-5">
          {/* Flow visualization */}
          <div className="flex items-center justify-center gap-3 rounded-lg bg-gray-50 px-4 py-3">
            <div className="text-center">
              <p className="text-xs text-gray-500">Source</p>
              <p className="font-semibold text-gray-900">{sourceEnvironment.name}</p>
              <p className="text-xs text-gray-400">
                {sourceEnvironment.catalog}.{sourceEnvironment.schema_prefix}
              </p>
            </div>
            <ArrowRight className="h-5 w-5 text-gray-400" size={20} />
            <div className="text-center">
              <p className="text-xs text-gray-500">Target</p>
              <p className="font-semibold text-gray-900">
                {targetName || '(select)'}
              </p>
              {selectedTarget && (
                <p className="text-xs text-gray-400">
                  {selectedTarget.catalog}.{selectedTarget.schema_prefix}
                </p>
              )}
            </div>
          </div>

          {/* Target selector */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Target Environment
            </label>
            <select
              value={targetName}
              onChange={(e) => {
                setTargetName(e.target.value);
                setConfirmed(false);
              }}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            >
              <option value="">Select target...</option>
              {targets.map((t) => (
                <option key={t.name} value={t.name}>
                  {t.name}
                  {t.is_production ? ' (production)' : ''}
                </option>
              ))}
            </select>
          </div>

          {/* Snapshot ID */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Snapshot ID
            </label>
            <input
              type="text"
              value={snapshotId}
              onChange={(e) => setSnapshotId(e.target.value)}
              placeholder="e.g. abc123def456..."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm font-mono focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
          </div>

          {/* Promoted by */}
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Promoted By
            </label>
            <input
              type="text"
              value={promotedBy}
              onChange={(e) => setPromotedBy(e.target.value)}
              placeholder="your-username"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
            />
          </div>

          {/* Production warning */}
          {isToProduction && (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" size={20} />
              <div className="text-sm">
                <p className="font-medium text-amber-800">
                  You are promoting to a production environment
                </p>
                <p className="mt-1 text-amber-700">
                  This will make the snapshot state available in the production
                  catalog/schema. Snapshot references will be copied, not data.
                </p>
              </div>
            </div>
          )}

          {/* Confirmation checkbox */}
          {targetName && (
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-ironlayer-600 focus:ring-ironlayer-500"
              />
              <span className="text-gray-700">
                I confirm this promotion from{' '}
                <span className="font-medium">{sourceEnvironment.name}</span> to{' '}
                <span className="font-medium">{targetName}</span>
              </span>
            </label>
          )}

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
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
            {submitting ? 'Promoting...' : 'Promote Snapshot'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default PromotionFlow;
