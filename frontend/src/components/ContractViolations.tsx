import { AlertTriangle, Info, ShieldAlert } from 'lucide-react';
import type { ContractViolation, PlanStep } from '../api/types';

/* ------------------------------------------------------------------ */
/* Severity badge                                                      */
/* ------------------------------------------------------------------ */

const SEVERITY_CONFIG = {
  BREAKING: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    icon: ShieldAlert,
  },
  WARNING: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    icon: AlertTriangle,
  },
  INFO: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
    icon: Info,
  },
} as const;

function SeverityBadge({ severity }: { severity: string }) {
  const config = SEVERITY_CONFIG[severity as keyof typeof SEVERITY_CONFIG] ?? SEVERITY_CONFIG.INFO;
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${config.bg} ${config.text}`}
    >
      <Icon size={10} />
      {severity}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Violation row                                                       */
/* ------------------------------------------------------------------ */

function ViolationRow({
  violation,
  modelName,
}: {
  violation: ContractViolation;
  modelName: string;
}) {
  return (
    <tr className="border-b border-gray-100 last:border-b-0">
      <td className="px-3 py-2 text-sm font-medium text-gray-900">{modelName}</td>
      <td className="px-3 py-2 font-mono text-sm text-gray-700">{violation.column_name}</td>
      <td className="px-3 py-2 text-sm text-gray-600">
        {violation.violation_type.replace(/_/g, ' ')}
      </td>
      <td className="px-3 py-2">
        <SeverityBadge severity={violation.severity} />
      </td>
      <td className="px-3 py-2 font-mono text-xs text-gray-500">{violation.expected || '-'}</td>
      <td className="px-3 py-2 font-mono text-xs text-gray-500">{violation.actual || '-'}</td>
    </tr>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

interface ContractViolationsProps {
  steps: PlanStep[];
  breakingCount: number;
  totalCount: number;
}

function ContractViolations({ steps, breakingCount, totalCount }: ContractViolationsProps) {
  if (totalCount === 0) return null;

  // Collect all violations with their model name.
  const allViolations: { violation: ContractViolation; modelName: string }[] = [];
  for (const step of steps) {
    for (const v of step.contract_violations ?? []) {
      allViolations.push({ violation: v, modelName: step.model });
    }
  }

  if (allViolations.length === 0) return null;

  return (
    <div className="space-y-3">
      {/* Summary banner */}
      {breakingCount > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <ShieldAlert size={16} className="shrink-0" />
          <span>
            <strong>{breakingCount}</strong> breaking contract violation{breakingCount > 1 ? 's' : ''}{' '}
            detected. Models with <code className="rounded bg-red-100 px-1 py-0.5 text-xs">STRICT</code>{' '}
            contracts will block plan apply.
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
                Column
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Violation
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Severity
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Expected
              </th>
              <th className="px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-gray-500">
                Actual
              </th>
            </tr>
          </thead>
          <tbody>
            {allViolations.map(({ violation, modelName }, idx) => (
              <ViolationRow
                key={`${modelName}-${violation.column_name}-${violation.violation_type}-${idx}`}
                violation={violation}
                modelName={modelName}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <p className="text-xs text-gray-500">
        {totalCount} violation{totalCount > 1 ? 's' : ''} across{' '}
        {new Set(allViolations.map((v) => v.modelName)).size} model
        {new Set(allViolations.map((v) => v.modelName)).size > 1 ? 's' : ''}
      </p>
    </div>
  );
}

export default ContractViolations;
