import { useState } from 'react';
import { ArrowRight, Check, X } from 'lucide-react';
import type { PlanStep, ModelAdvisory } from '../api/types';
import { formatCost, formatDuration } from '../utils/formatting';
import RiskIndicator from './RiskIndicator';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface PlanComparisonProps {
  steps: PlanStep[];
  advisory: Record<string, ModelAdvisory> | null;
  onAcceptSuggestions?: (modelNames: string[]) => void;
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function PlanComparison({ steps, advisory, onAcceptSuggestions }: PlanComparisonProps) {
  const [accepted, setAccepted] = useState<Record<string, boolean>>({});

  if (!advisory || Object.keys(advisory).length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
        No AI advisory data available for this plan. Click "Generate Advisory" to
        request AI analysis.
      </div>
    );
  }

  const toggleAcceptance = (model: string) => {
    setAccepted((prev) => ({ ...prev, [model]: !prev[model] }));
  };

  const handleApplyAll = () => {
    const acceptedModels = Object.entries(accepted)
      .filter(([, v]) => v)
      .map(([k]) => k);
    onAcceptSuggestions?.(acceptedModels);
  };

  const acceptedCount = Object.values(accepted).filter(Boolean).length;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900">
          Plan vs. Advisory Comparison
        </h3>
        {onAcceptSuggestions && acceptedCount > 0 && (
          <button
            onClick={handleApplyAll}
            className="rounded-lg bg-ironlayer-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-ironlayer-700"
          >
            Apply {acceptedCount} suggestion{acceptedCount !== 1 ? 's' : ''}
          </button>
        )}
      </div>

      {/* Step rows */}
      {steps.map((step) => {
        const adv = advisory[step.model];
        if (!adv) return null;

        const isAccepted = accepted[step.model] ?? false;
        const costDiff =
          adv.cost_prediction
            ? adv.cost_prediction.estimated_cost_usd - step.estimated_cost_usd
            : null;

        return (
          <div
            key={step.step_id}
            className="rounded-lg border border-gray-200 bg-white overflow-hidden"
          >
            {/* Model header */}
            <div className="flex items-center justify-between border-b border-gray-100 bg-gray-50 px-4 py-2.5">
              <span className="text-sm font-medium text-gray-900">
                {step.model}
              </span>
              {adv.risk_score && (
                <RiskIndicator
                  score={adv.risk_score.risk_score}
                  factors={adv.risk_score.risk_factors}
                  approvalRequired={adv.risk_score.approval_required}
                  compact
                />
              )}
            </div>

            {/* Two-column comparison */}
            <div className="grid grid-cols-2 divide-x divide-gray-100">
              {/* Left: Original plan */}
              <div className="p-4">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Original Plan
                </h4>
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-500">Run type</span>
                    <span className="font-medium text-gray-700">
                      {step.run_type}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Est. runtime</span>
                    <span className="font-medium text-gray-700">
                      {formatDuration(step.estimated_compute_seconds)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-500">Est. cost</span>
                    <span className="font-medium text-gray-700">
                      {formatCost(step.estimated_cost_usd)}
                    </span>
                  </div>
                  {step.reason && (
                    <p className="mt-2 text-xs text-gray-500">{step.reason}</p>
                  )}
                </div>
              </div>

              {/* Right: Advisory */}
              <div className="p-4">
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  AI Advisory
                </h4>
                <div className="space-y-1.5 text-sm">
                  {adv.semantic_classification && (
                    <div className="flex justify-between">
                      <span className="text-gray-500">Change type</span>
                      <span className="font-medium text-gray-700">
                        {adv.semantic_classification.change_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                  )}
                  {adv.cost_prediction && (
                    <>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Predicted runtime</span>
                        <span className="font-medium text-gray-700">
                          {formatDuration(adv.cost_prediction.estimated_runtime_minutes * 60)}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-gray-500">Predicted cost</span>
                        <div className="flex items-center gap-1.5">
                          <span className="font-medium text-gray-700">
                            {formatCost(adv.cost_prediction.estimated_cost_usd)}
                          </span>
                          {costDiff !== null && costDiff !== 0 && (
                            <span
                              className={`text-xs font-medium ${
                                costDiff > 0 ? 'text-red-600' : 'text-green-600'
                              }`}
                            >
                              {costDiff > 0 ? '+' : ''}
                              {formatCost(Math.abs(costDiff))}
                            </span>
                          )}
                        </div>
                      </div>
                    </>
                  )}
                  {adv.semantic_classification && (
                    <p className="mt-2 text-xs text-gray-500">
                      {adv.semantic_classification.impact_scope}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Suggestions */}
            {adv.suggestions && adv.suggestions.length > 0 && (
              <div className="border-t border-gray-100 px-4 py-3">
                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Optimization Suggestions
                </h4>
                <ul className="space-y-1">
                  {adv.suggestions.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs text-gray-600">
                      <ArrowRight size={12} className="mt-0.5 shrink-0 text-ironlayer-500" />
                      <span>
                        <strong className="text-gray-700">{s.suggestion_type}:</strong>{' '}
                        {s.description}
                        {s.confidence < 0.5 && (
                          <span className="ml-1 text-gray-400">(low confidence)</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Accept / Keep toggle */}
            {onAcceptSuggestions && (
              <div className="flex items-center justify-end gap-2 border-t border-gray-100 bg-gray-50 px-4 py-2">
                <button
                  onClick={() => {
                    if (isAccepted) toggleAcceptance(step.model);
                  }}
                  className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    !isAccepted
                      ? 'bg-white text-gray-700 shadow-sm ring-1 ring-gray-200'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <X size={12} />
                  Keep original
                </button>
                <button
                  onClick={() => {
                    if (!isAccepted) toggleAcceptance(step.model);
                  }}
                  className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs font-medium transition-colors ${
                    isAccepted
                      ? 'bg-ironlayer-600 text-white'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Check size={12} />
                  Accept suggestion
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default PlanComparison;
