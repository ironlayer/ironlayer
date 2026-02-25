/**
 * Loading skeleton components for progressive content loading.
 *
 * Variants:
 * - SkeletonLine: a single line placeholder (text, labels)
 * - SkeletonCard: a card-shaped placeholder
 * - SkeletonTable: a table-shaped placeholder with rows
 * - SkeletonChart: a chart-sized placeholder
 */

function shimmerClass(className?: string): string {
  return `animate-pulse rounded bg-white/[0.06] ${className ?? ''}`.trim();
}

export function SkeletonLine({
  width = 'w-full',
  height = 'h-4',
  className,
}: {
  width?: string;
  height?: string;
  className?: string;
}) {
  return <div className={shimmerClass(`${width} ${height} ${className ?? ''}`)} />;
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={`rounded-lg border border-white/[0.06] bg-white/[0.02] p-4 ${className ?? ''}`}>
      <SkeletonLine width="w-1/3" height="h-3" className="mb-3" />
      <SkeletonLine width="w-2/3" height="h-6" className="mb-2" />
      <SkeletonLine width="w-1/2" height="h-3" />
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="overflow-hidden rounded-lg border border-white/[0.06]">
      {/* Header */}
      <div className="flex gap-4 bg-white/[0.03] px-4 py-3">
        {Array.from({ length: cols }).map((_, i) => (
          <SkeletonLine key={i} width="flex-1" height="h-3" />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, ri) => (
        <div key={ri} className="flex gap-4 border-t border-white/[0.04] px-4 py-3">
          {Array.from({ length: cols }).map((_, ci) => (
            <SkeletonLine key={ci} width="flex-1" height="h-3" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = 'h-64' }: { height?: string }) {
  return (
    <div className={`rounded-lg border border-white/[0.06] bg-white/[0.02] p-6 ${height}`}>
      <SkeletonLine width="w-1/4" height="h-4" className="mb-4" />
      <div className="flex h-[calc(100%-2rem)] items-end gap-2">
        {[40, 65, 30, 80, 55, 70, 45].map((h, i) => (
          <div
            key={i}
            className="flex-1 animate-pulse rounded-t bg-white/[0.06]"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function SkeletonStatCards({ count = 4 }: { count?: number }) {
  return (
    <div className={`grid gap-4 grid-cols-${Math.min(count, 4)}`}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
