import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import PlanComparison from '../../src/components/PlanComparison';
import type { PlanStep, ModelAdvisory } from '../../src/api/types';

/* ------------------------------------------------------------------ */
/* Test data                                                           */
/* ------------------------------------------------------------------ */

const sampleSteps: PlanStep[] = [
  {
    step_id: 'step-1',
    model: 'fct_orders',
    run_type: 'FULL_REFRESH',
    input_range: null,
    depends_on: [],
    parallel_group: 0,
    reason: 'Breaking schema change detected',
    estimated_compute_seconds: 120,
    estimated_cost_usd: 2.5,
  },
  {
    step_id: 'step-2',
    model: 'dim_customers',
    run_type: 'INCREMENTAL',
    input_range: { start: '2026-01-01', end: '2026-01-31' },
    depends_on: ['step-1'],
    parallel_group: 1,
    reason: 'Downstream dependency changed',
    estimated_compute_seconds: 45,
    estimated_cost_usd: 0.75,
  },
];

const sampleAdvisory: Record<string, ModelAdvisory> = {
  fct_orders: {
    semantic_classification: {
      change_type: 'breaking',
      confidence: 0.92,
      requires_full_rebuild: true,
      impact_scope: 'All downstream revenue models impacted',
    },
    cost_prediction: {
      estimated_runtime_minutes: 3.5,
      estimated_cost_usd: 3.1,
      confidence: 0.85,
    },
    risk_score: {
      risk_score: 7.5,
      business_critical: true,
      approval_required: true,
      risk_factors: ['Breaking change in key columns', 'High downstream impact'],
    },
    suggestions: [
      {
        suggestion_type: 'partition_pruning',
        description: 'Add partition filter to reduce scan cost',
        rewritten_sql: null,
        confidence: 0.78,
      },
      {
        suggestion_type: 'materialization',
        description: 'Switch to incremental to save compute',
        rewritten_sql: null,
        confidence: 0.42,
      },
    ],
  },
  dim_customers: {
    semantic_classification: {
      change_type: 'non_breaking',
      confidence: 0.95,
      requires_full_rebuild: false,
      impact_scope: 'Limited to customer dimensions',
    },
    cost_prediction: {
      estimated_runtime_minutes: 1.0,
      estimated_cost_usd: 0.5,
      confidence: 0.9,
    },
    risk_score: {
      risk_score: 2.0,
      business_critical: false,
      approval_required: false,
      risk_factors: [],
    },
  },
};

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('PlanComparison', () => {
  it('renders plan steps with model names in headers', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.getByText('fct_orders')).toBeInTheDocument();
    expect(screen.getByText('dim_customers')).toBeInTheDocument();
  });

  it('shows "Plan vs. Advisory Comparison" heading', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.getByText('Plan vs. Advisory Comparison')).toBeInTheDocument();
  });

  it('displays original plan data for each step', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    // Run types
    expect(screen.getByText('FULL_REFRESH')).toBeInTheDocument();
    expect(screen.getByText('INCREMENTAL')).toBeInTheDocument();
    // Costs
    expect(screen.getByText('$2.50')).toBeInTheDocument();
    expect(screen.getByText('$0.75')).toBeInTheDocument();
  });

  it('displays AI advisory data including change type and predicted cost', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    // Semantic change type (breaking -> "breaking" with underscores replaced)
    expect(screen.getByText('breaking')).toBeInTheDocument();
    expect(screen.getByText('non breaking')).toBeInTheDocument();
    // Advisory predicted cost
    expect(screen.getByText('$3.10')).toBeInTheDocument();
    expect(screen.getByText('$0.50')).toBeInTheDocument();
  });

  it('shows cost difference between plan and advisory', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    // fct_orders: advisory cost ($3.10) - plan cost ($2.50) = +$0.60
    expect(screen.getByText('+$0.60')).toBeInTheDocument();
    // dim_customers: advisory cost ($0.50) - plan cost ($0.75) = -$0.25
    expect(screen.getByText('$0.25')).toBeInTheDocument();
  });

  it('shows the cost difference with correct color (red for increase, green for decrease)', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    const increase = screen.getByText('+$0.60');
    expect(increase.className).toContain('text-red-600');

    const decrease = screen.getByText('$0.25');
    expect(decrease.className).toContain('text-green-600');
  });

  it('displays impact scope text from semantic classification', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.getByText('All downstream revenue models impacted')).toBeInTheDocument();
    expect(screen.getByText('Limited to customer dimensions')).toBeInTheDocument();
  });

  it('displays the reason text from each plan step', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.getByText('Breaking schema change detected')).toBeInTheDocument();
    expect(screen.getByText('Downstream dependency changed')).toBeInTheDocument();
  });

  it('renders optimization suggestions when present', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.getByText(/partition_pruning/)).toBeInTheDocument();
    expect(screen.getByText(/Add partition filter to reduce scan cost/)).toBeInTheDocument();
    expect(screen.getByText(/materialization/)).toBeInTheDocument();
    expect(screen.getByText(/Switch to incremental to save compute/)).toBeInTheDocument();
  });

  it('shows "(low confidence)" for suggestions with confidence < 0.5', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    // The materialization suggestion has confidence 0.42 (< 0.5)
    expect(screen.getByText('(low confidence)')).toBeInTheDocument();
  });

  it('handles empty plan (no advisory data)', () => {
    render(<PlanComparison steps={[]} advisory={null} />);
    expect(
      screen.getByText(/No AI advisory data available for this plan/),
    ).toBeInTheDocument();
  });

  it('handles advisory as empty object', () => {
    render(<PlanComparison steps={sampleSteps} advisory={{}} />);
    expect(
      screen.getByText(/No AI advisory data available for this plan/),
    ).toBeInTheDocument();
  });

  it('does not render steps that have no matching advisory entry', () => {
    const partialAdvisory: Record<string, ModelAdvisory> = {
      fct_orders: sampleAdvisory['fct_orders'],
    };
    render(<PlanComparison steps={sampleSteps} advisory={partialAdvisory} />);
    expect(screen.getByText('fct_orders')).toBeInTheDocument();
    // dim_customers has no advisory entry so it should not render
    expect(screen.queryByText('dim_customers')).not.toBeInTheDocument();
  });

  it('renders accept/keep buttons when onAcceptSuggestions is provided', () => {
    const handler = vi.fn();
    render(
      <PlanComparison
        steps={sampleSteps}
        advisory={sampleAdvisory}
        onAcceptSuggestions={handler}
      />,
    );
    const acceptBtns = screen.getAllByText('Accept suggestion');
    expect(acceptBtns.length).toBeGreaterThan(0);
    const keepBtns = screen.getAllByText('Keep original');
    expect(keepBtns.length).toBeGreaterThan(0);
  });

  it('does not render accept/keep buttons when onAcceptSuggestions is not provided', () => {
    render(<PlanComparison steps={sampleSteps} advisory={sampleAdvisory} />);
    expect(screen.queryByText('Accept suggestion')).not.toBeInTheDocument();
    expect(screen.queryByText('Keep original')).not.toBeInTheDocument();
  });

  it('shows "Apply N suggestions" button after accepting suggestions', () => {
    const handler = vi.fn();
    render(
      <PlanComparison
        steps={sampleSteps}
        advisory={sampleAdvisory}
        onAcceptSuggestions={handler}
      />,
    );

    // Click "Accept suggestion" for the first step
    const acceptBtns = screen.getAllByText('Accept suggestion');
    fireEvent.click(acceptBtns[0]);

    expect(screen.getByText('Apply 1 suggestion')).toBeInTheDocument();
  });

  it('calls onAcceptSuggestions with accepted model names when Apply is clicked', () => {
    const handler = vi.fn();
    render(
      <PlanComparison
        steps={sampleSteps}
        advisory={sampleAdvisory}
        onAcceptSuggestions={handler}
      />,
    );

    // Accept suggestion for fct_orders
    const acceptBtns = screen.getAllByText('Accept suggestion');
    fireEvent.click(acceptBtns[0]);

    // Click Apply button
    fireEvent.click(screen.getByText('Apply 1 suggestion'));

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith(['fct_orders']);
  });

  it('toggles acceptance off when "Keep original" is clicked after accepting', () => {
    const handler = vi.fn();
    render(
      <PlanComparison
        steps={sampleSteps}
        advisory={sampleAdvisory}
        onAcceptSuggestions={handler}
      />,
    );

    // Accept first
    const acceptBtns = screen.getAllByText('Accept suggestion');
    fireEvent.click(acceptBtns[0]);
    expect(screen.getByText('Apply 1 suggestion')).toBeInTheDocument();

    // Now click "Keep original" to toggle it off
    const keepBtns = screen.getAllByText('Keep original');
    fireEvent.click(keepBtns[0]);

    // Apply button should disappear (acceptedCount is 0)
    expect(screen.queryByText(/Apply \d+ suggestion/)).not.toBeInTheDocument();
  });
});
