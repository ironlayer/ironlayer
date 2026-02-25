import { useRef, useState } from 'react';
import { ShieldCheck, ShieldAlert } from 'lucide-react';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface RiskIndicatorProps {
  score: number;        // 0-10
  factors: string[];
  approvalRequired: boolean;
  compact?: boolean;
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function riskColor(score: number): { ring: string; fill: string; text: string; label: string } {
  if (score <= 3) {
    return {
      ring: 'stroke-green-500',
      fill: 'text-green-500',
      text: 'text-green-700',
      label: 'Low Risk',
    };
  }
  if (score <= 7) {
    return {
      ring: 'stroke-amber-500',
      fill: 'text-amber-500',
      text: 'text-amber-700',
      label: 'Medium Risk',
    };
  }
  return {
    ring: 'stroke-red-500',
    fill: 'text-red-500',
    text: 'text-red-700',
    label: 'High Risk',
  };
}

/* ------------------------------------------------------------------ */
/* Circular gauge                                                      */
/* ------------------------------------------------------------------ */

function RiskGauge({ score, size = 56 }: { score: number; size?: number }) {
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const normalised = Math.min(Math.max(score, 0), 10) / 10;
  const offset = circumference * (1 - normalised);
  const colors = riskColor(score);

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        {/* Background ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#e5e7eb"
          strokeWidth={4}
        />
        {/* Value ring */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          className={colors.ring}
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: 'stroke-dashoffset 0.5s ease' }}
        />
      </svg>
      <span
        className={`absolute inset-0 flex items-center justify-center text-sm font-bold ${colors.fill}`}
      >
        {score.toFixed(1)}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Main component                                                      */
/* ------------------------------------------------------------------ */

function RiskIndicator({ score, factors, approvalRequired, compact }: RiskIndicatorProps) {
  const [tooltipOpen, setTooltipOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const colors = riskColor(score);

  if (compact) {
    return (
      <div
        ref={containerRef}
        className="relative flex items-center gap-1.5"
        onMouseEnter={() => setTooltipOpen(true)}
        onMouseLeave={() => setTooltipOpen(false)}
      >
        <span className={`text-xs font-semibold ${colors.text}`}>
          {score.toFixed(1)}
        </span>
        {approvalRequired ? (
          <ShieldAlert size={14} className="text-amber-500" />
        ) : (
          <ShieldCheck size={14} className="text-green-500" />
        )}

        {/* Tooltip */}
        {tooltipOpen && factors.length > 0 && (
          <div className="absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-lg border border-gray-200 bg-white p-3 shadow-lg">
            <p className="mb-1.5 text-xs font-semibold text-gray-700">Risk Factors</p>
            <ul className="space-y-0.5">
              {factors.map((f, i) => (
                <li key={i} className="text-xs text-gray-600">
                  &bull; {f}
                </li>
              ))}
            </ul>
            <div className="absolute -bottom-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 border-b border-r border-gray-200 bg-white" />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex items-start gap-4 rounded-lg border border-gray-200 bg-white p-4">
      <RiskGauge score={score} />

      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className={`text-sm font-semibold ${colors.text}`}>
            {colors.label}
          </span>
          {approvalRequired ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
              <ShieldAlert size={11} />
              Manual review required
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 rounded-full bg-green-50 px-2 py-0.5 text-[11px] font-medium text-green-700">
              <ShieldCheck size={11} />
              Auto-approved
            </span>
          )}
        </div>

        {factors.length > 0 && (
          <ul className="mt-2 space-y-0.5">
            {factors.map((f, i) => (
              <li key={i} className="text-xs text-gray-600">
                &bull; {f}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default RiskIndicator;
