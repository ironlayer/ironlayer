import { useMemo } from 'react';
import { CheckCircle, XCircle } from 'lucide-react';
import type { TestResult } from '../api/types';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface TestResultsTableProps {
  results: TestResult[];
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function formatDurationMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTestType(t: string): string {
  return t.replace(/_/g, ' ');
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function TestResultsTable({ results }: TestResultsTableProps) {
  const sorted = useMemo(
    () =>
      [...results].sort((a, b) => {
        // Sort failing tests first, then by model name, then by test type.
        if (a.passed !== b.passed) return a.passed ? 1 : -1;
        const modelCmp = a.model_name.localeCompare(b.model_name);
        if (modelCmp !== 0) return modelCmp;
        return a.test_type.localeCompare(b.test_type);
      }),
    [results],
  );

  const passCount = useMemo(() => results.filter((r) => r.passed).length, [results]);
  const failCount = results.length - passCount;

  if (results.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-6 text-center text-sm text-gray-500">
        No test results available.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      {/* Summary bar */}
      <div className="flex items-center gap-4 border-b border-gray-200 bg-gray-50 px-4 py-3 text-sm">
        <span className="font-medium text-gray-700">
          {results.length} test{results.length !== 1 ? 's' : ''}
        </span>
        <span className="flex items-center gap-1 text-green-700">
          <CheckCircle size={14} />
          {passCount} passed
        </span>
        {failCount > 0 && (
          <span className="flex items-center gap-1 text-red-700">
            <XCircle size={14} />
            {failCount} failed
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Model</th>
              <th className="px-4 py-3">Test Type</th>
              <th className="px-4 py-3">Message</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Mode</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((r, idx) => (
              <tr
                key={`${r.test_id}-${idx}`}
                className={`transition-colors hover:bg-gray-50 ${
                  !r.passed ? 'bg-red-50/30' : ''
                }`}
              >
                <td className="whitespace-nowrap px-4 py-3">
                  {r.passed ? (
                    <CheckCircle size={16} className="text-green-600" />
                  ) : (
                    <XCircle size={16} className="text-red-600" />
                  )}
                </td>
                <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                  {r.model_name}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
                    {formatTestType(r.test_type)}
                  </span>
                </td>
                <td className="max-w-xs truncate px-4 py-3 text-gray-600">
                  {r.failure_message ?? '--'}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                  {formatDurationMs(r.duration_ms)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-gray-500">
                  {r.execution_mode}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default TestResultsTable;
