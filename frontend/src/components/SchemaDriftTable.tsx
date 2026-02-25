import { useState } from 'react';
import { AlertTriangle, Check, Info, ShieldAlert } from 'lucide-react';
import type { SchemaDrift } from '../api/types';

/* ------------------------------------------------------------------ */
/* Drift type badge                                                    */
/* ------------------------------------------------------------------ */

const DRIFT_TYPE_CONFIG = {
  COLUMN_REMOVED: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    icon: ShieldAlert,
  },
  TYPE_CHANGED: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    icon: AlertTriangle,
  },
  COLUMN_ADDED: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    icon: Info,
  },
  NONE: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    icon: Check,
  },
} as const;

function DriftTypeBadge({ driftType }: { driftType: string }) {
  const config =
    DRIFT_TYPE_CONFIG[driftType as keyof typeof DRIFT_TYPE_CONFIG] ??
    DRIFT_TYPE_CONFIG.NONE;
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${config.bg} ${config.text}`}
    >
      <Icon size={10} />
      {driftType.replace(/_/g, ' ')}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Drift detail row                                                    */
/* ------------------------------------------------------------------ */

interface DriftDetail {
  column_name: string;
  expected: string;
  actual: string;
  message: string;
}

export function DriftDetailRow({
  detail,
  modelName,
  driftType,
}: {
  detail: DriftDetail;
  modelName: string;
  driftType: string;
}) {
  return (
    <tr className="border-b border-gray-100 last:border-b-0">
      <td className="px-3 py-2 text-sm font-medium text-gray-900">
        {modelName}
      </td>
      <td className="px-3 py-2">
        <DriftTypeBadge driftType={driftType} />
      </td>
      <td className="px-3 py-2 font-mono text-sm text-gray-700">
        {detail.column_name}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-gray-500">
        {detail.expected || '-'}
      </td>
      <td className="px-3 py-2 font-mono text-xs text-gray-500">
        {detail.actual || '-'}
      </td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

interface SchemaDriftTableProps {
  drifts: SchemaDrift[];
  onResolve?: (checkId: number) => void | Promise<void>;
}

function SchemaDriftTable({ drifts, onResolve }: SchemaDriftTableProps) {
  const [resolving, setResolving] = useState<number | null>(null);

  if (drifts.length === 0) {
    return (
      <div className="rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-800">
        <div className="flex items-center gap-2">
          <Check size={16} className="shrink-0" />
          <span>No unresolved schema drifts detected.</span>
        </div>
      </div>
    );
  }

  // Flatten all drift details from all drift records.
  const allDetails: {
    detail: DriftDetail;
    modelName: string;
    driftType: string;
    checkId: number;
  }[] = [];

  for (const drift of drifts) {
    const details: DriftDetail[] = drift.drift_details ?? [];
    for (const d of details) {
      allDetails.push({
        detail: d,
        modelName: drift.model_name,
        driftType: drift.drift_type,
        checkId: drift.id,
      });
    }
    // If there are no details but the drift exists, show a summary row.
    if (details.length === 0) {
      allDetails.push({
        detail: {
          column_name: '-',
          expected: '-',
          actual: '-',
          message: `Drift type: ${drift.drift_type}`,
        },
        modelName: drift.model_name,
        driftType: drift.drift_type,
        checkId: drift.id,
      });
    }
  }

  const removedCount = drifts.filter(
    (d) => d.drift_type === 'COLUMN_REMOVED'
  ).length;
  const changedCount = drifts.filter(
    (d) => d.drift_type === 'TYPE_CHANGED'
  ).length;
  const addedCount = drifts.filter(
    (d) => d.drift_type === 'COLUMN_ADDED'
  ).length;

  const handleResolve = async (checkId: number) => {
    if (!onResolve) return;
    setResolving(checkId);
    try {
      await onResolve(checkId);
    } finally {
      setResolving(null);
    }
  };

  return (
    <div className="space-y-3">
      {/* Summary banner */}
      {removedCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <ShieldAlert size={16} className="shrink-0" />
          <span>
            <strong>{removedCount}</strong> model
            {removedCount > 1 ? 's' : ''} with removed columns detected.
            This may indicate a breaking schema change.
          </span>
        </div>
      )}

      {changedCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <AlertTriangle size={16} className="shrink-0" />
          <span>
            <strong>{changedCount}</strong> model
            {changedCount > 1 ? 's' : ''} with type changes detected.
          </span>
        </div>
      )}

      {/* Table */}
      <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Model
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Drift Type
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Column
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Expected
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Actual
              </th>
              {onResolve && (
                <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody>
            {allDetails.map(({ detail, modelName, driftType, checkId }, idx) => (
              <tr
                key={`${modelName}-${detail.column_name}-${driftType}-${idx}`}
                className="border-b border-gray-100 last:border-b-0"
              >
                <td className="px-3 py-2 text-sm font-medium text-gray-900">
                  {modelName}
                </td>
                <td className="px-3 py-2">
                  <DriftTypeBadge driftType={driftType} />
                </td>
                <td className="px-3 py-2 font-mono text-sm text-gray-700">
                  {detail.column_name}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-500">
                  {detail.expected || '-'}
                </td>
                <td className="px-3 py-2 font-mono text-xs text-gray-500">
                  {detail.actual || '-'}
                </td>
                {onResolve && (
                  <td className="px-3 py-2">
                    <button
                      onClick={() => handleResolve(checkId)}
                      disabled={resolving === checkId}
                      className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-200 disabled:opacity-50"
                    >
                      <Check size={12} />
                      {resolving === checkId ? 'Resolving...' : 'Resolve'}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <p className="text-xs text-gray-500">
        {drifts.length} unresolved drift
        {drifts.length > 1 ? 's' : ''} across{' '}
        {new Set(drifts.map((d) => d.model_name)).size} model
        {new Set(drifts.map((d) => d.model_name)).size > 1 ? 's' : ''}
        {removedCount > 0 && (
          <span className="ml-2 text-red-600">
            ({removedCount} column removal{removedCount > 1 ? 's' : ''})
          </span>
        )}
        {changedCount > 0 && (
          <span className="ml-2 text-amber-600">
            ({changedCount} type change{changedCount > 1 ? 's' : ''})
          </span>
        )}
        {addedCount > 0 && (
          <span className="ml-2 text-blue-600">
            ({addedCount} column addition{addedCount > 1 ? 's' : ''})
          </span>
        )}
      </p>
    </div>
  );
}

export default SchemaDriftTable;
