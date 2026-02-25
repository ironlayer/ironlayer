/* ------------------------------------------------------------------ */
/* Display formatting utilities                                        */
/* ------------------------------------------------------------------ */

import type { DateRange, RunStatus } from '../api/types';

/**
 * Format a USD amount for display.
 * Values under $0.01 show as "< $0.01".
 */
export function formatCost(usd: number): string {
  if (usd === 0) return '$0.00';
  if (usd > 0 && usd < 0.01) return '< $0.01';
  return `$${usd.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format a duration given in seconds into a human-readable string.
 * e.g. 135 -> "2m 15s", 3665 -> "1h 1m"
 */
export function formatDuration(seconds: number): string {
  if (seconds < 0) return '0s';
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;

  const minutes = Math.floor(s / 60);
  const remainingSec = s % 60;

  if (minutes < 60) {
    return remainingSec > 0 ? `${minutes}m ${remainingSec}s` : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMin = minutes % 60;
  return remainingMin > 0 ? `${hours}h ${remainingMin}m` : `${hours}h`;
}

/**
 * Format an ISO date/datetime string into a readable local representation.
 */
export function formatDate(isoString: string): string {
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return isoString;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

/**
 * Format a DateRange into a compact display string.
 * e.g. "Feb 1 - Feb 10, 2026"
 */
export function formatDateRange(range: DateRange): string {
  const start = new Date(range.start + 'T00:00:00');
  const end = new Date(range.end + 'T00:00:00');

  const sameYear = start.getFullYear() === end.getFullYear();
  const startFmt = start.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    ...(sameYear ? {} : { year: 'numeric' }),
  });
  const endFmt = end.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return `${startFmt} - ${endFmt}`;
}

/**
 * Map a run status to a Tailwind text/bg color class (dark mode friendly).
 */
export function statusColor(status: RunStatus | string): string {
  switch (status) {
    case 'SUCCESS':
      return 'text-emerald-400 bg-emerald-500/10';
    case 'RUNNING':
      return 'text-blue-400 bg-blue-500/10';
    case 'PENDING':
      return 'text-amber-400 bg-amber-500/10';
    case 'FAIL':
      return 'text-red-400 bg-red-500/10';
    case 'CANCELLED':
      return 'text-gray-400 bg-white/5';
    default:
      return 'text-gray-400 bg-white/5';
  }
}

/**
 * Truncate a SHA to a short display form.
 */
export function shortSha(sha: string): string {
  return sha.length > 8 ? sha.slice(0, 8) : sha;
}

/**
 * Format byte counts into human-readable form.
 */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const value = bytes / Math.pow(1024, i);
  return `${value.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

/**
 * Format large numbers with commas.
 */
export function formatNumber(n: number): string {
  return n.toLocaleString('en-US');
}

/**
 * Convert a local date string from an ``<input type="date">`` (YYYY-MM-DD)
 * to a UTC ISO-8601 date string (YYYY-MM-DD).
 *
 * HTML date inputs return values in the local calendar format but without
 * timezone info.  This function explicitly interprets the date as UTC to
 * avoid timezone-induced off-by-one errors when sending to the API.
 */
export function toUTCDateString(localDate: string): string {
  if (!localDate) return localDate;
  // Input format is "YYYY-MM-DD" which is already the ISO date format.
  // Ensure we parse it as UTC by appending T00:00:00Z.
  const d = new Date(`${localDate}T00:00:00Z`);
  if (isNaN(d.getTime())) return localDate;
  return d.toISOString().slice(0, 10);
}
