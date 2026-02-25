import { useCallback, useState } from 'react';
import { AlertTriangle, Trash2, Plus, Zap } from 'lucide-react';
import type {
  ColumnChange as ColumnChangeType,
  ImpactReport as ImpactReportType,
} from '../api/types';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface ImpactSimulatorProps {
  /** Available model names for the dropdown. */
  modelNames: string[];
  /** Callback to run the simulation via the API. */
  onSimulate: (
    sourceModel: string,
    changes: ColumnChangeType[],
  ) => Promise<ImpactReportType>;
}

type ChangeAction = 'ADD' | 'REMOVE' | 'RENAME' | 'TYPE_CHANGE';

interface EditableChange {
  id: number;
  action: ChangeAction;
  column_name: string;
  new_name: string;
  old_type: string;
  new_type: string;
}

const EMPTY_CHANGE: Omit<EditableChange, 'id'> = {
  action: 'REMOVE',
  column_name: '',
  new_name: '',
  old_type: '',
  new_type: '',
};

/* ------------------------------------------------------------------ */
/* Severity badge                                                      */
/* ------------------------------------------------------------------ */

function SeverityBadge({ severity }: { severity: string }) {
  const styles: Record<string, string> = {
    BREAKING: 'bg-red-100 text-red-800',
    WARNING: 'bg-yellow-100 text-yellow-800',
    INFO: 'bg-blue-100 text-blue-700',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        styles[severity] ?? 'bg-gray-100 text-gray-700'
      }`}
    >
      {severity}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export default function ImpactSimulator({
  modelNames,
  onSimulate,
}: ImpactSimulatorProps) {
  const [sourceModel, setSourceModel] = useState('');
  const [changes, setChanges] = useState<EditableChange[]>([
    { id: 1, ...EMPTY_CHANGE },
  ]);
  const [nextId, setNextId] = useState(2);
  const [report, setReport] = useState<ImpactReportType | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /* -- Change list management --------------------------------------- */

  const addChange = useCallback(() => {
    setChanges((prev) => [...prev, { id: nextId, ...EMPTY_CHANGE }]);
    setNextId((n) => n + 1);
  }, [nextId]);

  const removeChange = useCallback((id: number) => {
    setChanges((prev) => (prev.length > 1 ? prev.filter((c) => c.id !== id) : prev));
  }, []);

  const updateChange = useCallback(
    (id: number, field: keyof EditableChange, value: string) => {
      setChanges((prev) =>
        prev.map((c) => (c.id === id ? { ...c, [field]: value } : c)),
      );
    },
    [],
  );

  /* -- Simulation --------------------------------------------------- */

  const handleSimulate = useCallback(async () => {
    if (!sourceModel) return;
    setLoading(true);
    setError(null);
    try {
      const payload: ColumnChangeType[] = changes.map((c) => ({
        action: c.action,
        column_name: c.column_name,
        ...(c.new_name ? { new_name: c.new_name } : {}),
        ...(c.old_type ? { old_type: c.old_type } : {}),
        ...(c.new_type ? { new_type: c.new_type } : {}),
      }));
      const result = await onSimulate(sourceModel, payload);
      setReport(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Simulation failed');
    } finally {
      setLoading(false);
    }
  }, [sourceModel, changes, onSimulate]);

  /* -- Render ------------------------------------------------------- */

  return (
    <div className="space-y-6">
      {/* Source model selector */}
      <div>
        <label className="mb-1 block text-sm font-medium text-gray-700">
          Source Model
        </label>
        <select
          value={sourceModel}
          onChange={(e) => setSourceModel(e.target.value)}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-ironlayer-500 focus:outline-none focus:ring-1 focus:ring-ironlayer-500"
        >
          <option value="">Select a model...</option>
          {modelNames.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </div>

      {/* Column changes table */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h4 className="text-sm font-medium text-gray-700">Column Changes</h4>
          <button
            onClick={addChange}
            className="inline-flex items-center gap-1 rounded-md bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 hover:bg-gray-200"
          >
            <Plus size={12} />
            Add Change
          </button>
        </div>
        <div className="overflow-hidden rounded-lg border border-gray-200">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                  Action
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                  Column
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                  New Name
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                  Old Type
                </th>
                <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">
                  New Type
                </th>
                <th className="w-10 px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {changes.map((change) => (
                <tr key={change.id}>
                  <td className="px-3 py-2">
                    <select
                      value={change.action}
                      onChange={(e) =>
                        updateChange(change.id, 'action', e.target.value)
                      }
                      className="rounded border border-gray-200 px-2 py-1 text-xs"
                    >
                      <option value="ADD">ADD</option>
                      <option value="REMOVE">REMOVE</option>
                      <option value="RENAME">RENAME</option>
                      <option value="TYPE_CHANGE">TYPE_CHANGE</option>
                    </select>
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={change.column_name}
                      onChange={(e) =>
                        updateChange(change.id, 'column_name', e.target.value)
                      }
                      placeholder="column_name"
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={change.new_name}
                      onChange={(e) =>
                        updateChange(change.id, 'new_name', e.target.value)
                      }
                      placeholder="—"
                      disabled={change.action !== 'RENAME'}
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs disabled:bg-gray-50 disabled:text-gray-400"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={change.old_type}
                      onChange={(e) =>
                        updateChange(change.id, 'old_type', e.target.value)
                      }
                      placeholder="—"
                      disabled={change.action !== 'TYPE_CHANGE'}
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs disabled:bg-gray-50 disabled:text-gray-400"
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="text"
                      value={change.new_type}
                      onChange={(e) =>
                        updateChange(change.id, 'new_type', e.target.value)
                      }
                      placeholder="—"
                      disabled={change.action !== 'TYPE_CHANGE'}
                      className="w-full rounded border border-gray-200 px-2 py-1 text-xs disabled:bg-gray-50 disabled:text-gray-400"
                    />
                  </td>
                  <td className="px-3 py-2 text-center">
                    <button
                      onClick={() => removeChange(change.id)}
                      className="text-gray-400 hover:text-red-500"
                      title="Remove"
                    >
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Simulate button */}
      <button
        onClick={handleSimulate}
        disabled={loading || !sourceModel || !changes[0]?.column_name}
        className="inline-flex items-center gap-2 rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ironlayer-700 disabled:opacity-50"
      >
        <Zap size={14} />
        {loading ? 'Simulating...' : 'Run Simulation'}
      </button>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          <AlertTriangle size={14} className="mb-0.5 mr-1 inline" />
          {error}
        </div>
      )}

      {/* Results */}
      {report && (
        <div className="space-y-4">
          {/* Summary */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
            <h4 className="mb-1 text-sm font-semibold text-gray-900">
              Impact Summary
            </h4>
            <p className="text-sm text-gray-600">{report.summary}</p>
            <div className="mt-3 flex gap-4 text-xs">
              {report.breaking_count > 0 && (
                <span className="font-medium text-red-600">
                  {report.breaking_count} Breaking
                </span>
              )}
              {report.warning_count > 0 && (
                <span className="font-medium text-yellow-600">
                  {report.warning_count} Warning
                </span>
              )}
              {report.breaking_count === 0 && report.warning_count === 0 && (
                <span className="font-medium text-green-600">
                  No breaking changes
                </span>
              )}
            </div>
          </div>

          {/* Affected models */}
          {(report.directly_affected.length > 0 ||
            report.transitively_affected.length > 0) && (
            <div className="rounded-lg border border-gray-200 bg-white">
              <div className="border-b border-gray-100 px-4 py-3">
                <h4 className="text-sm font-semibold text-gray-900">
                  Affected Models
                </h4>
              </div>
              <div className="divide-y divide-gray-100">
                {[
                  ...report.directly_affected,
                  ...report.transitively_affected,
                ].map((model) => (
                  <div
                    key={model.model_name}
                    className="flex items-center justify-between px-4 py-3"
                  >
                    <div>
                      <span className="text-sm font-medium text-gray-900">
                        {model.model_name}
                      </span>
                      <span className="ml-2 text-xs text-gray-400">
                        ({model.reference_type})
                      </span>
                      {model.columns_affected.length > 0 && (
                        <span className="ml-2 text-xs text-gray-500">
                          columns: {model.columns_affected.join(', ')}
                        </span>
                      )}
                    </div>
                    <SeverityBadge severity={model.severity} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Contract violations */}
          {report.contract_violations.length > 0 && (
            <div className="rounded-lg border border-red-200 bg-white">
              <div className="border-b border-red-100 px-4 py-3">
                <h4 className="text-sm font-semibold text-red-800">
                  <AlertTriangle size={14} className="mb-0.5 mr-1 inline" />
                  Contract Violations ({report.contract_violations.length})
                </h4>
              </div>
              <div className="divide-y divide-red-50">
                {report.contract_violations.map((v, idx) => (
                  <div key={idx} className="px-4 py-3 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-900">
                        {v.model_name}.{v.column_name}
                      </span>
                      <SeverityBadge severity={v.severity} />
                    </div>
                    <p className="mt-1 text-xs text-gray-600">{v.message}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
