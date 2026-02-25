import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react';
import type { PlanStep } from '../api/types';
import { formatCost, formatDateRange, formatDuration } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface CostTableProps {
  steps: PlanStep[];
}

type SortField =
  | 'model'
  | 'run_type'
  | 'input_range'
  | 'estimated_compute_seconds'
  | 'estimated_cost_usd'
  | 'parallel_group';

type SortDirection = 'asc' | 'desc';

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function CostTable({ steps }: CostTableProps) {
  const [sortField, setSortField] = useState<SortField>('estimated_cost_usd');
  const [sortDir, setSortDir] = useState<SortDirection>('desc');

  const sorted = useMemo(() => {
    return [...steps].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'model':
          cmp = a.model.localeCompare(b.model);
          break;
        case 'run_type':
          cmp = a.run_type.localeCompare(b.run_type);
          break;
        case 'input_range': {
          const aStart = a.input_range?.start ?? '';
          const bStart = b.input_range?.start ?? '';
          cmp = aStart.localeCompare(bStart);
          break;
        }
        case 'estimated_compute_seconds':
          cmp = a.estimated_compute_seconds - b.estimated_compute_seconds;
          break;
        case 'estimated_cost_usd':
          cmp = a.estimated_cost_usd - b.estimated_cost_usd;
          break;
        case 'parallel_group':
          cmp = a.parallel_group - b.parallel_group;
          break;
      }
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [steps, sortField, sortDir]);

  const totalCost = useMemo(
    () => steps.reduce((sum, s) => sum + s.estimated_cost_usd, 0),
    [steps],
  );

  const totalRuntime = useMemo(
    () => steps.reduce((sum, s) => sum + s.estimated_compute_seconds, 0),
    [steps],
  );

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDir('desc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) return <ArrowUpDown size={12} className="text-gray-300" />;
    return sortDir === 'asc' ? (
      <ArrowUp size={12} className="text-ironlayer-600" />
    ) : (
      <ArrowDown size={12} className="text-ironlayer-600" />
    );
  };

  const HIGH_COST_THRESHOLD = totalCost > 0 ? totalCost / steps.length * 2 : Infinity;

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
              {(
                [
                  ['model', 'Model'],
                  ['run_type', 'Run Type'],
                  ['input_range', 'Input Range'],
                  ['estimated_compute_seconds', 'Est. Runtime'],
                  ['estimated_cost_usd', 'Est. Cost'],
                  ['parallel_group', 'Cluster Group'],
                ] as const
              ).map(([field, label]) => (
                <th
                  key={field}
                  className="cursor-pointer select-none px-4 py-3 transition-colors hover:bg-gray-100"
                  onClick={() => handleSort(field)}
                >
                  <div className="flex items-center gap-1.5">
                    {label}
                    <SortIcon field={field} />
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((step) => {
              const isHighCost = step.estimated_cost_usd > HIGH_COST_THRESHOLD;
              return (
                <tr
                  key={step.step_id}
                  className={`transition-colors hover:bg-gray-50 ${
                    isHighCost ? 'bg-amber-50/50' : ''
                  }`}
                >
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-gray-900">
                    {step.model}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        step.run_type === 'FULL_REFRESH'
                          ? 'bg-purple-50 text-purple-700'
                          : 'bg-blue-50 text-blue-700'
                      }`}
                    >
                      {step.run_type.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                    {step.input_range ? formatDateRange(step.input_range) : '--'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                    {formatDuration(step.estimated_compute_seconds)}
                  </td>
                  <td
                    className={`whitespace-nowrap px-4 py-3 font-medium ${
                      isHighCost ? 'text-amber-700' : 'text-gray-900'
                    }`}
                  >
                    {formatCost(step.estimated_cost_usd)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-gray-600">
                    Group {step.parallel_group}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="border-t-2 border-gray-200 bg-gray-50 font-semibold">
              <td className="px-4 py-3 text-gray-900">
                Total ({steps.length} step{steps.length !== 1 ? 's' : ''})
              </td>
              <td className="px-4 py-3" />
              <td className="px-4 py-3" />
              <td className="px-4 py-3 text-gray-700">
                {formatDuration(totalRuntime)}
              </td>
              <td className="px-4 py-3 text-gray-900">{formatCost(totalCost)}</td>
              <td className="px-4 py-3" />
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}

export default CostTable;
