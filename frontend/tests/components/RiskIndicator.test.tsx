import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import RiskIndicator from '../../src/components/RiskIndicator';

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('RiskIndicator', () => {
  describe('full (non-compact) mode', () => {
    it('renders the risk score gauge with correct score text', () => {
      render(
        <RiskIndicator
          score={5.0}
          factors={['Upstream instability']}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('5.0')).toBeInTheDocument();
    });

    it('shows "Low Risk" label and green color for score <= 3', () => {
      render(
        <RiskIndicator
          score={2.5}
          factors={[]}
          approvalRequired={false}
        />,
      );
      expect(screen.getByText('Low Risk')).toBeInTheDocument();
      const label = screen.getByText('Low Risk');
      expect(label.className).toContain('text-green-700');
    });

    it('shows "Medium Risk" label and amber color for score > 3 and <= 7', () => {
      render(
        <RiskIndicator
          score={5.5}
          factors={['Some risk']}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('Medium Risk')).toBeInTheDocument();
      const label = screen.getByText('Medium Risk');
      expect(label.className).toContain('text-amber-700');
    });

    it('shows "High Risk" label and red color for score > 7', () => {
      render(
        <RiskIndicator
          score={8.5}
          factors={['Critical data pipeline']}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('High Risk')).toBeInTheDocument();
      const label = screen.getByText('High Risk');
      expect(label.className).toContain('text-red-700');
    });

    it('displays risk factor list items', () => {
      const factors = ['Upstream data quality issues', 'No rollback strategy', 'Peak traffic window'];
      render(
        <RiskIndicator
          score={6.0}
          factors={factors}
          approvalRequired={true}
        />,
      );
      // The <li> contains "• " + factor text as separate text nodes,
      // so use a substring matcher to find the factor text within the <li>.
      for (const factor of factors) {
        expect(screen.getByText((_content, el) =>
          el?.tagName === 'LI' && el.textContent?.includes(factor) === true
        )).toBeInTheDocument();
      }
    });

    it('does not render factor list when factors array is empty', () => {
      const { container } = render(
        <RiskIndicator
          score={1.0}
          factors={[]}
          approvalRequired={false}
        />,
      );
      const listItems = container.querySelectorAll('li');
      expect(listItems).toHaveLength(0);
    });

    it('shows "Manual review required" badge when approvalRequired is true', () => {
      render(
        <RiskIndicator
          score={7.5}
          factors={['Critical']}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('Manual review required')).toBeInTheDocument();
    });

    it('shows "Auto-approved" badge when approvalRequired is false', () => {
      render(
        <RiskIndicator
          score={1.5}
          factors={[]}
          approvalRequired={false}
        />,
      );
      expect(screen.getByText('Auto-approved')).toBeInTheDocument();
    });

    it('renders the SVG gauge with two circles', () => {
      const { container } = render(
        <RiskIndicator
          score={5.0}
          factors={[]}
          approvalRequired={true}
        />,
      );
      const circles = container.querySelectorAll('circle');
      // RiskGauge renders 2 circles: background ring + value ring
      expect(circles).toHaveLength(2);
    });

    it('clamps score display to 0-10 range', () => {
      // Score above 10 should be clamped to 10 for the gauge
      render(
        <RiskIndicator
          score={12.0}
          factors={[]}
          approvalRequired={true}
        />,
      );
      // The text still shows the raw score
      expect(screen.getByText('12.0')).toBeInTheDocument();
      // But the label should be High Risk since 12 > 7
      expect(screen.getByText('High Risk')).toBeInTheDocument();
    });

    it('displays score at boundary: exactly 3 is Low Risk', () => {
      render(
        <RiskIndicator
          score={3.0}
          factors={[]}
          approvalRequired={false}
        />,
      );
      expect(screen.getByText('Low Risk')).toBeInTheDocument();
    });

    it('displays score at boundary: exactly 7 is Medium Risk', () => {
      render(
        <RiskIndicator
          score={7.0}
          factors={[]}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('Medium Risk')).toBeInTheDocument();
    });

    it('displays score at boundary: 7.1 is High Risk', () => {
      render(
        <RiskIndicator
          score={7.1}
          factors={[]}
          approvalRequired={true}
        />,
      );
      expect(screen.getByText('High Risk')).toBeInTheDocument();
    });
  });

  describe('compact mode', () => {
    it('renders compact view with score text', () => {
      render(
        <RiskIndicator
          score={4.2}
          factors={['Some factor']}
          approvalRequired={false}
          compact
        />,
      );
      expect(screen.getByText('4.2')).toBeInTheDocument();
    });

    it('does not render "Low Risk" / "Medium Risk" / "High Risk" labels in compact mode', () => {
      render(
        <RiskIndicator
          score={2.0}
          factors={[]}
          approvalRequired={false}
          compact
        />,
      );
      expect(screen.queryByText('Low Risk')).not.toBeInTheDocument();
      expect(screen.queryByText('Medium Risk')).not.toBeInTheDocument();
      expect(screen.queryByText('High Risk')).not.toBeInTheDocument();
    });

    it('does not render the SVG gauge in compact mode', () => {
      const { container } = render(
        <RiskIndicator
          score={6.0}
          factors={['Factor A']}
          approvalRequired={true}
          compact
        />,
      );
      // Compact mode still renders Lucide icon SVGs (ShieldAlert/ShieldCheck)
      // but should NOT render the circular gauge (which has <circle> elements).
      const circles = container.querySelectorAll('circle');
      expect(circles).toHaveLength(0);
    });

    it('shows tooltip with risk factors on hover', () => {
      render(
        <RiskIndicator
          score={6.0}
          factors={['Upstream instability', 'No backfill plan']}
          approvalRequired={true}
          compact
        />,
      );

      // Factors should not be visible before hover
      expect(screen.queryByText('Risk Factors')).not.toBeInTheDocument();

      // Hover over the compact indicator
      const container = screen.getByText('6.0').closest('div')!;
      fireEvent.mouseEnter(container);

      // Now the tooltip should appear
      expect(screen.getByText('Risk Factors')).toBeInTheDocument();
      // Factors are inside <li> with "• " prefix as a separate text node
      expect(screen.getByText((_c, el) =>
        el?.tagName === 'LI' && el.textContent?.includes('Upstream instability') === true
      )).toBeInTheDocument();
      expect(screen.getByText((_c, el) =>
        el?.tagName === 'LI' && el.textContent?.includes('No backfill plan') === true
      )).toBeInTheDocument();
    });

    it('hides tooltip on mouse leave', () => {
      render(
        <RiskIndicator
          score={6.0}
          factors={['Upstream instability']}
          approvalRequired={true}
          compact
        />,
      );

      const container = screen.getByText('6.0').closest('div')!;
      fireEvent.mouseEnter(container);
      expect(screen.getByText('Risk Factors')).toBeInTheDocument();

      fireEvent.mouseLeave(container);
      expect(screen.queryByText('Risk Factors')).not.toBeInTheDocument();
    });

    it('does not show tooltip when factors are empty even on hover', () => {
      render(
        <RiskIndicator
          score={1.0}
          factors={[]}
          approvalRequired={false}
          compact
        />,
      );

      const container = screen.getByText('1.0').closest('div')!;
      fireEvent.mouseEnter(container);
      expect(screen.queryByText('Risk Factors')).not.toBeInTheDocument();
    });

    it('uses correct score text color for low risk in compact mode', () => {
      render(
        <RiskIndicator
          score={2.0}
          factors={[]}
          approvalRequired={false}
          compact
        />,
      );
      const scoreEl = screen.getByText('2.0');
      expect(scoreEl.className).toContain('text-green-700');
    });

    it('uses correct score text color for medium risk in compact mode', () => {
      render(
        <RiskIndicator
          score={5.0}
          factors={[]}
          approvalRequired={true}
          compact
        />,
      );
      const scoreEl = screen.getByText('5.0');
      expect(scoreEl.className).toContain('text-amber-700');
    });

    it('uses correct score text color for high risk in compact mode', () => {
      render(
        <RiskIndicator
          score={9.0}
          factors={[]}
          approvalRequired={true}
          compact
        />,
      );
      const scoreEl = screen.getByText('9.0');
      expect(scoreEl.className).toContain('text-red-700');
    });
  });
});
