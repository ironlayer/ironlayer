import { useCallback, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  Play,
  Sparkles,
} from 'lucide-react';
import { usePlan } from '../hooks/usePlans';
import {
  augmentPlan,
  applyPlan,
  approvePlan,
  rejectPlan,
  simulateColumnChange,
} from '../api/client';
import type { PlanStep, PlanWithAdvisory, ModelAdvisory, TestSummary, ColumnChange } from '../api/types';
import ContractViolations from '../components/ContractViolations';
import TestResultsTable from '../components/TestResultsTable';
import DAGVisualization from '../components/DAGVisualization';
import type { DAGInputNode, DAGInputEdge, DAGNodeStatus } from '../components/DAGVisualization';
import CostTable from '../components/CostTable';
import PlanComparison from '../components/PlanComparison';
import ApprovalFlow from '../components/ApprovalFlow';
import RiskIndicator from '../components/RiskIndicator';
import ImpactSimulator from '../components/ImpactSimulator';
import {
  formatCost,
  formatDateRange,
  formatDuration,
  shortSha,
} from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Tabs                                                                */
/* ------------------------------------------------------------------ */

type PlanTab = 'dag' | 'steps' | 'cost' | 'contracts' | 'tests' | 'advisory' | 'whatif';

const BASE_TABS: { key: PlanTab; label: string }[] = [
  { key: 'dag', label: 'DAG View' },
  { key: 'steps', label: 'Steps List' },
  { key: 'cost', label: 'Cost Breakdown' },
  { key: 'advisory', label: 'Advisory' },
  { key: 'whatif', label: 'What-If' },
];

/* ------------------------------------------------------------------ */
/* Build DAG data from steps                                           */
/* ------------------------------------------------------------------ */

function buildDAGFromSteps(
  steps: PlanStep[],
  advisory: Record<string, ModelAdvisory> | null,
): { nodes: DAGInputNode[]; edges: DAGInputEdge[] } {
  const stepByModel = new Map<string, PlanStep>();
  const stepById = new Map<string, PlanStep>();

  for (const s of steps) {
    stepByModel.set(s.model, s);
    stepById.set(s.step_id, s);
  }

  const nodes: DAGInputNode[] = steps.map((s) => {
    let status: DAGNodeStatus = 'modified';
    if (advisory?.[s.model]?.risk_score?.risk_score !== undefined) {
      const score = advisory[s.model].risk_score!.risk_score;
      if (score >= 7) status = 'blocked';
    }
    if (s.run_type === 'FULL_REFRESH') status = 'added';

    return {
      id: s.step_id,
      name: s.model,
      kind: s.run_type,
      status,
      costUsd: s.estimated_cost_usd,
    };
  });

  const edges: DAGInputEdge[] = [];
  for (const s of steps) {
    for (const dep of s.depends_on) {
      if (stepById.has(dep)) {
        edges.push({ source: dep, target: s.step_id });
      }
    }
  }

  return { nodes, edges };
}

/* ------------------------------------------------------------------ */
/* Step row (expandable)                                               */
/* ------------------------------------------------------------------ */

function StepRow({ step, advisory }: { step: PlanStep; advisory?: ModelAdvisory }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-gray-50"
      >
        {expanded ? (
          <ChevronDown size={14} className="shrink-0 text-gray-400" />
        ) : (
          <ChevronRight size={14} className="shrink-0 text-gray-400" />
        )}
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-gray-900">
          {step.model}
        </span>
        <span
          className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${
            step.run_type === 'FULL_REFRESH'
              ? 'bg-purple-50 text-purple-700'
              : 'bg-blue-50 text-blue-700'
          }`}
        >
          {step.run_type.replace('_', ' ')}
        </span>
        <span className="text-xs text-gray-500">
          {formatCost(step.estimated_cost_usd)}
        </span>
        {advisory?.risk_score && (
          <RiskIndicator
            score={advisory.risk_score.risk_score}
            factors={advisory.risk_score.risk_factors}
            approvalRequired={advisory.risk_score.approval_required}
            compact
          />
        )}
      </button>

      {expanded && (
        <div className="border-t border-gray-100 bg-gray-50 px-4 py-3">
          <div className="grid grid-cols-3 gap-4 text-xs">
            <div>
              <span className="text-gray-400">Step ID</span>
              <p className="font-mono text-gray-700">{step.step_id.slice(0, 16)}...</p>
            </div>
            <div>
              <span className="text-gray-400">Parallel Group</span>
              <p className="text-gray-700">Group {step.parallel_group}</p>
            </div>
            <div>
              <span className="text-gray-400">Est. Runtime</span>
              <p className="text-gray-700">
                {formatDuration(step.estimated_compute_seconds)}
              </p>
            </div>
            {step.input_range && (
              <div>
                <span className="text-gray-400">Input Range</span>
                <p className="text-gray-700">{formatDateRange(step.input_range)}</p>
              </div>
            )}
            {step.depends_on.length > 0 && (
              <div className="col-span-2">
                <span className="text-gray-400">Depends On</span>
                <p className="font-mono text-gray-700">
                  {step.depends_on.map((d) => d.slice(0, 8)).join(', ')}
                </p>
              </div>
            )}
            {step.reason && (
              <div className="col-span-3">
                <span className="text-gray-400">Reason</span>
                <p className="text-gray-700">{step.reason}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main page                                                           */
/* ------------------------------------------------------------------ */

function PlanDetail() {
  const { id } = useParams<{ id: string }>();
  const { plan, loading, error, refetch } = usePlan(id);

  const [activeTab, setActiveTab] = useState<PlanTab>('dag');
  const [advisory, setAdvisory] = useState<Record<string, ModelAdvisory> | null>(null);
  const [augmenting, setAugmenting] = useState(false);
  const [applying, setApplying] = useState(false);
  // Test summary: populated when test results are fetched (future feature).
  const [testSummary] = useState<TestSummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const isApproved =
    plan?.auto_approved ||
    ((plan?.approvals.length ?? 0) > 0 &&
      plan?.approvals[plan.approvals.length - 1].action === 'approved');

  const hasContractViolations = (plan?.summary.contract_violations_count ?? 0) > 0;

  const hasTestResults = testSummary !== null && testSummary.total > 0;

  const tabs = useMemo(() => {
    let result = [...BASE_TABS];
    // Insert "Contracts" tab before "Advisory" when violations exist.
    if (hasContractViolations) {
      result = [
        ...result.slice(0, 3),
        { key: 'contracts' as PlanTab, label: 'Contracts' },
        ...result.slice(3),
      ];
    }
    // Insert "Tests" tab before "Advisory" when test results exist.
    if (hasTestResults) {
      const advisoryIdx = result.findIndex((t) => t.key === 'advisory');
      result = [
        ...result.slice(0, advisoryIdx),
        { key: 'tests' as PlanTab, label: 'Tests' },
        ...result.slice(advisoryIdx),
      ];
    }
    return result;
  }, [hasContractViolations, hasTestResults]);

  const dagData = useMemo(() => {
    if (!plan) return { nodes: [], edges: [] };
    return buildDAGFromSteps(plan.steps, advisory);
  }, [plan, advisory]);

  const handleAugment = useCallback(async () => {
    if (!id) return;
    setAugmenting(true);
    setActionError(null);
    try {
      const result: PlanWithAdvisory = await augmentPlan(id);
      setAdvisory(result.advisory);
      setActiveTab('advisory');
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'An unexpected error occurred',
      );
    } finally {
      setAugmenting(false);
    }
  }, [id]);

  const handleApply = useCallback(async () => {
    if (!id) return;
    setApplying(true);
    setActionError(null);
    try {
      await applyPlan(id);
      await refetch();
    } catch (err) {
      setActionError(
        err instanceof Error ? err.message : 'An unexpected error occurred',
      );
    } finally {
      setApplying(false);
    }
  }, [id, refetch]);

  const handleApprove = useCallback(
    async (user: string, comment: string) => {
      if (!id) return;
      // Identity comes from JWT token server-side; user is display-name only
      await approvePlan(id, user || undefined, comment);
      await refetch();
    },
    [id, refetch],
  );

  const handleReject = useCallback(
    async (user: string, reason: string) => {
      if (!id) return;
      // Identity comes from JWT token server-side; user is display-name only
      await rejectPlan(id, reason, user || undefined);
      await refetch();
    },
    [id, refetch],
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
      </div>
    );
  }

  if (error || !plan) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
        {error ?? 'Plan not found.'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {actionError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {actionError}
        </div>
      )}

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Plan Detail</h1>
          <div className="mt-1 flex items-center gap-3 text-sm text-gray-500">
            <span className="font-mono">{shortSha(plan.plan_id)}</span>
            <span className="flex items-center gap-1">
              <GitBranch size={12} />
              {shortSha(plan.base)} &rarr; {shortSha(plan.target)}
            </span>
            <span>{plan.summary.total_steps} steps</span>
            <span>{formatCost(plan.summary.estimated_cost_usd)}</span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleAugment}
            disabled={augmenting}
            className="flex items-center gap-1.5 rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50"
          >
            <Sparkles size={14} className={augmenting ? 'animate-pulse text-amber-500' : ''} />
            {augmenting ? 'Augmenting...' : 'Generate Advisory'}
          </button>
          {isApproved && (
            <button
              onClick={() => void handleApply()}
              disabled={applying}
              className="flex items-center gap-1.5 rounded-lg bg-ironlayer-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ironlayer-700 disabled:opacity-50"
            >
              <Play size={14} />
              {applying ? 'Applying...' : 'Apply Plan'}
            </button>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg border border-gray-200 bg-gray-100 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }${
              tab.key === 'contracts' && (plan?.summary.breaking_contract_violations ?? 0) > 0
                ? ' text-red-600'
                : ''
            }`}
          >
            {tab.label}
            {tab.key === 'contracts' && (plan?.summary.contract_violations_count ?? 0) > 0 && (
              <span className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-red-100 px-1 text-[10px] font-semibold text-red-700">
                {plan?.summary.contract_violations_count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'dag' && (
        <div className="h-[500px]">
          <DAGVisualization nodes={dagData.nodes} edges={dagData.edges} />
        </div>
      )}

      {activeTab === 'steps' && (
        <div className="rounded-lg border border-gray-200 bg-white">
          {plan.steps.length === 0 ? (
            <div className="p-6 text-center text-sm text-gray-500">
              No steps in this plan.
            </div>
          ) : (
            plan.steps.map((step) => (
              <StepRow
                key={step.step_id}
                step={step}
                advisory={advisory?.[step.model]}
              />
            ))
          )}
        </div>
      )}

      {activeTab === 'cost' && <CostTable steps={plan.steps} />}

      {activeTab === 'contracts' && (
        <ContractViolations
          steps={plan.steps}
          breakingCount={plan.summary.breaking_contract_violations}
          totalCount={plan.summary.contract_violations_count}
        />
      )}

      {activeTab === 'tests' && testSummary && (
        <TestResultsTable results={testSummary.results} />
      )}

      {activeTab === 'advisory' && (
        <div className="space-y-6">
          {/* Aggregate risk */}
          {advisory && Object.values(advisory).some((a) => a.risk_score) && (
            <div>
              <h3 className="mb-3 text-sm font-semibold text-gray-900">
                Risk Overview
              </h3>
              <div className="grid grid-cols-3 gap-4">
                {plan.steps
                  .filter((s) => advisory[s.model]?.risk_score)
                  .map((s) => (
                    <RiskIndicator
                      key={s.step_id}
                      score={advisory[s.model].risk_score!.risk_score}
                      factors={advisory[s.model].risk_score!.risk_factors}
                      approvalRequired={advisory[s.model].risk_score!.approval_required}
                    />
                  ))}
              </div>
            </div>
          )}

          <PlanComparison steps={plan.steps} advisory={advisory} />
        </div>
      )}

      {activeTab === 'whatif' && (
        <ImpactSimulator
          modelNames={plan.steps.map((s) => s.model)}
          onSimulate={(sourceModel: string, changes: ColumnChange[]) =>
            simulateColumnChange(sourceModel, changes)
          }
        />
      )}

      {/* Approval */}
      <ApprovalFlow
        approvals={plan.approvals}
        autoApproved={plan.auto_approved}
        onApprove={handleApprove}
        onReject={handleReject}
      />
    </div>
  );
}

export default PlanDetail;
