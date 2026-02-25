import { useState } from 'react';
import { Check, X, Clock, User } from 'lucide-react';
import type { Approval } from '../api/types';
import { formatDate } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface ApprovalFlowProps {
  approvals: Approval[];
  autoApproved: boolean;
  onApprove: (user: string, comment: string) => Promise<void>;
  onReject: (user: string, reason: string) => Promise<void>;
  disabled?: boolean;
}

/* ------------------------------------------------------------------ */
/* Derived state                                                       */
/* ------------------------------------------------------------------ */

type PlanApprovalStatus = 'pending' | 'approved' | 'rejected';

function deriveStatus(approvals: Approval[], autoApproved: boolean): PlanApprovalStatus {
  if (autoApproved) return 'approved';
  if (approvals.length === 0) return 'pending';
  const last = approvals[approvals.length - 1];
  return last.action === 'approved' ? 'approved' : 'rejected';
}

const STATUS_DISPLAY: Record<PlanApprovalStatus, { label: string; classes: string }> = {
  pending:  { label: 'Pending Review', classes: 'bg-yellow-50 text-yellow-700 border-yellow-200' },
  approved: { label: 'Approved',       classes: 'bg-green-50 text-green-700 border-green-200' },
  rejected: { label: 'Rejected',       classes: 'bg-red-50 text-red-700 border-red-200' },
};

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function ApprovalFlow({
  approvals,
  autoApproved,
  onApprove,
  onReject,
  disabled,
}: ApprovalFlowProps) {
  const status = deriveStatus(approvals, autoApproved);
  const isTerminal = status === 'approved' || status === 'rejected';

  const [mode, setMode] = useState<'idle' | 'approve' | 'reject'>('idle');
  const [username, setUsername] = useState('');
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const handleSubmit = async () => {
    if (!username.trim()) return;
    if (mode === 'reject' && !comment.trim()) return;

    setSubmitting(true);
    setSubmitError(null);
    try {
      if (mode === 'approve') {
        await onApprove(username.trim(), comment.trim());
      } else {
        await onReject(username.trim(), comment.trim());
      }
      setMode('idle');
      setComment('');
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setSubmitting(false);
    }
  };

  const statusDisplay = STATUS_DISPLAY[status];

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      {/* Status header */}
      <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Approval</h3>
        <span
          className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusDisplay.classes}`}
        >
          {status === 'pending' && <Clock size={12} className="mr-1" />}
          {status === 'approved' && <Check size={12} className="mr-1" />}
          {status === 'rejected' && <X size={12} className="mr-1" />}
          {statusDisplay.label}
          {autoApproved && status === 'approved' && ' (auto)'}
        </span>
      </div>

      {/* Approval history */}
      {approvals.length > 0 && (
        <div className="border-b border-gray-100 px-4 py-3">
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
            History
          </h4>
          <ul className="space-y-2">
            {approvals.map((a, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <User size={14} className="mt-0.5 shrink-0 text-gray-400" />
                <div>
                  <span className="font-medium text-gray-800">{a.user}</span>{' '}
                  <span
                    className={
                      a.action === 'approved' ? 'text-green-600' : 'text-red-600'
                    }
                  >
                    {a.action}
                  </span>
                  {a.comment && (
                    <p className="mt-0.5 text-xs text-gray-500">{a.comment}</p>
                  )}
                  <p className="text-[11px] text-gray-400">
                    {formatDate(a.timestamp)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Action area */}
      {!isTerminal && !disabled && (
        <div className="p-4">
          {mode === 'idle' ? (
            <div className="flex gap-2">
              <button
                onClick={() => setMode('approve')}
                className="flex items-center gap-1.5 rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-green-700"
              >
                <Check size={14} />
                Approve
              </button>
              <button
                onClick={() => setMode('reject')}
                className="flex items-center gap-1.5 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
              >
                <X size={14} />
                Reject
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label htmlFor="approval-username" className="mb-1 block text-xs font-medium text-gray-700">
                  Your name
                </label>
                <input
                  id="approval-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="e.g. jane.doe"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
                />
              </div>

              <div>
                <label htmlFor="approval-comment" className="mb-1 block text-xs font-medium text-gray-700">
                  {mode === 'approve' ? 'Comment (optional)' : 'Reason (required)'}
                </label>
                <textarea
                  id="approval-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  rows={3}
                  placeholder={
                    mode === 'approve'
                      ? 'Optional comment...'
                      : 'Please provide a reason for rejection...'
                  }
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
                />
              </div>

              {submitError && (
                <p className="text-xs text-red-600">{submitError}</p>
              )}

              <div className="flex gap-2">
                <button
                  onClick={() => void handleSubmit()}
                  disabled={
                    submitting ||
                    !username.trim() ||
                    (mode === 'reject' && !comment.trim())
                  }
                  className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors disabled:opacity-50 ${
                    mode === 'approve'
                      ? 'bg-green-600 hover:bg-green-700'
                      : 'bg-red-600 hover:bg-red-700'
                  }`}
                >
                  {submitting
                    ? 'Submitting...'
                    : mode === 'approve'
                      ? 'Confirm Approval'
                      : 'Confirm Rejection'}
                </button>
                <button
                  onClick={() => {
                    setMode('idle');
                    setComment('');
                    setSubmitError(null);
                  }}
                  className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ApprovalFlow;
