import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ApprovalFlow from '../../src/components/ApprovalFlow';
import type { Approval } from '../../src/api/types';

/* ------------------------------------------------------------------ */
/* Test data                                                           */
/* ------------------------------------------------------------------ */

const existingApprovals: Approval[] = [
  {
    user: 'alice.eng',
    action: 'approved',
    comment: 'Looks good to me',
    timestamp: '2026-02-10T14:30:00Z',
  },
];

const rejectedApprovals: Approval[] = [
  {
    user: 'bob.reviewer',
    action: 'rejected',
    comment: 'Missing test coverage for edge cases',
    timestamp: '2026-02-11T09:00:00Z',
  },
];

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

function renderApprovalFlow(overrides?: Partial<React.ComponentProps<typeof ApprovalFlow>>) {
  const defaultProps = {
    approvals: [],
    autoApproved: false,
    onApprove: vi.fn<[string, string], Promise<void>>().mockResolvedValue(undefined),
    onReject: vi.fn<[string, string], Promise<void>>().mockResolvedValue(undefined),
    disabled: false,
  };
  const props = { ...defaultProps, ...overrides };
  return { ...render(<ApprovalFlow {...props} />), props };
}

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('ApprovalFlow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('status display', () => {
    it('shows "Pending Review" when no approvals and not auto-approved', () => {
      renderApprovalFlow();
      expect(screen.getByText('Pending Review')).toBeInTheDocument();
    });

    it('shows "Approved" when auto-approved is true', () => {
      renderApprovalFlow({ autoApproved: true });
      expect(screen.getByText(/Approved/)).toBeInTheDocument();
      expect(screen.getByText(/\(auto\)/)).toBeInTheDocument();
    });

    it('shows "Approved" when last approval action is approved', () => {
      renderApprovalFlow({ approvals: existingApprovals });
      expect(screen.getByText('Approved')).toBeInTheDocument();
    });

    it('shows "Rejected" when last approval action is rejected', () => {
      renderApprovalFlow({ approvals: rejectedApprovals });
      expect(screen.getByText('Rejected')).toBeInTheDocument();
    });
  });

  describe('approval history', () => {
    it('renders approval history entries with user names', () => {
      renderApprovalFlow({ approvals: existingApprovals });
      expect(screen.getByText('alice.eng')).toBeInTheDocument();
    });

    it('renders the action text (approved/rejected) for each history entry', () => {
      const mixed: Approval[] = [
        ...existingApprovals,
        ...rejectedApprovals,
      ];
      renderApprovalFlow({ approvals: mixed });
      expect(screen.getByText('alice.eng')).toBeInTheDocument();
      expect(screen.getByText('bob.reviewer')).toBeInTheDocument();
      // Action text appears alongside user names
      const approvedTexts = screen.getAllByText('approved');
      expect(approvedTexts.length).toBeGreaterThanOrEqual(1);
      const rejectedTexts = screen.getAllByText('rejected');
      expect(rejectedTexts.length).toBeGreaterThanOrEqual(1);
    });

    it('displays comment text in history entries', () => {
      renderApprovalFlow({ approvals: existingApprovals });
      expect(screen.getByText('Looks good to me')).toBeInTheDocument();
    });

    it('displays "History" section heading when approvals exist', () => {
      renderApprovalFlow({ approvals: existingApprovals });
      expect(screen.getByText('History')).toBeInTheDocument();
    });

    it('does not display "History" when approvals list is empty', () => {
      renderApprovalFlow({ approvals: [] });
      expect(screen.queryByText('History')).not.toBeInTheDocument();
    });
  });

  describe('approve/reject buttons', () => {
    it('renders Approve and Reject buttons when status is pending', () => {
      renderApprovalFlow();
      expect(screen.getByText('Approve')).toBeInTheDocument();
      expect(screen.getByText('Reject')).toBeInTheDocument();
    });

    it('does not render Approve/Reject buttons when already approved', () => {
      renderApprovalFlow({ approvals: existingApprovals });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });

    it('does not render Approve/Reject buttons when already rejected', () => {
      renderApprovalFlow({ approvals: rejectedApprovals });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });

    it('does not render Approve/Reject buttons when disabled', () => {
      renderApprovalFlow({ disabled: true });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });

    it('does not render buttons when auto-approved', () => {
      renderApprovalFlow({ autoApproved: true });
      expect(screen.queryByText('Approve')).not.toBeInTheDocument();
      expect(screen.queryByText('Reject')).not.toBeInTheDocument();
    });
  });

  describe('approve form', () => {
    it('shows name and comment fields after clicking Approve', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      expect(screen.getByLabelText('Your name')).toBeInTheDocument();
      expect(screen.getByLabelText('Comment (optional)')).toBeInTheDocument();
      expect(screen.getByText('Confirm Approval')).toBeInTheDocument();
      expect(screen.getByText('Cancel')).toBeInTheDocument();
    });

    it('calls onApprove with username and comment when form is submitted', async () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      const commentTextarea = screen.getByPlaceholderText('Optional comment...');
      fireEvent.change(commentTextarea, { target: { value: 'LGTM' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(props.onApprove).toHaveBeenCalledTimes(1);
        expect(props.onApprove).toHaveBeenCalledWith('test.user', 'LGTM');
      });
    });

    it('does not submit if username is empty', () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      // Username is empty, click Confirm
      fireEvent.click(screen.getByText('Confirm Approval'));

      expect(props.onApprove).not.toHaveBeenCalled();
    });

    it('allows approval with empty comment (comment is optional for approvals)', async () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(props.onApprove).toHaveBeenCalledWith('test.user', '');
      });
    });

    it('returns to idle state after cancel is clicked', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));
      expect(screen.getByText('Confirm Approval')).toBeInTheDocument();

      fireEvent.click(screen.getByText('Cancel'));
      // Should go back to showing Approve/Reject buttons
      expect(screen.getByText('Approve')).toBeInTheDocument();
      expect(screen.getByText('Reject')).toBeInTheDocument();
    });

    it('resets to idle mode after successful submission', async () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(screen.getByText('Approve')).toBeInTheDocument();
      });
    });
  });

  describe('reject form', () => {
    it('shows name and reason fields after clicking Reject', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      expect(screen.getByLabelText('Your name')).toBeInTheDocument();
      expect(screen.getByLabelText('Reason (required)')).toBeInTheDocument();
      expect(screen.getByText('Confirm Rejection')).toBeInTheDocument();
    });

    it('calls onReject with username and reason when form is submitted', async () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'reviewer.bob' } });

      const reasonTextarea = screen.getByPlaceholderText(
        'Please provide a reason for rejection...',
      );
      fireEvent.change(reasonTextarea, {
        target: { value: 'Missing test coverage' },
      });

      fireEvent.click(screen.getByText('Confirm Rejection'));

      await waitFor(() => {
        expect(props.onReject).toHaveBeenCalledTimes(1);
        expect(props.onReject).toHaveBeenCalledWith('reviewer.bob', 'Missing test coverage');
      });
    });

    it('does not submit rejection without a reason (reason is required)', () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'reviewer.bob' } });

      // Reason is empty
      fireEvent.click(screen.getByText('Confirm Rejection'));
      expect(props.onReject).not.toHaveBeenCalled();
    });

    it('does not submit rejection without a username', () => {
      const { props } = renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const reasonTextarea = screen.getByPlaceholderText(
        'Please provide a reason for rejection...',
      );
      fireEvent.change(reasonTextarea, { target: { value: 'Bad change' } });

      // Username is empty
      fireEvent.click(screen.getByText('Confirm Rejection'));
      expect(props.onReject).not.toHaveBeenCalled();
    });
  });

  describe('error handling', () => {
    it('displays error message when submission fails', async () => {
      const onApprove = vi.fn().mockRejectedValue(new Error('Network error'));
      renderApprovalFlow({ onApprove });

      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(screen.getByText('Network error')).toBeInTheDocument();
      });
    });

    it('displays generic error message for non-Error throws', async () => {
      const onApprove = vi.fn().mockRejectedValue('something went wrong');
      renderApprovalFlow({ onApprove });

      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(screen.getByText('Submission failed')).toBeInTheDocument();
      });
    });

    it('clears error when cancel is clicked after a failed submission', async () => {
      const onApprove = vi.fn().mockRejectedValue(new Error('Timeout'));
      renderApprovalFlow({ onApprove });

      fireEvent.click(screen.getByText('Approve'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'test.user' } });

      fireEvent.click(screen.getByText('Confirm Approval'));

      await waitFor(() => {
        expect(screen.getByText('Timeout')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('Cancel'));

      // Error should be gone and we should see the approve/reject buttons again
      expect(screen.queryByText('Timeout')).not.toBeInTheDocument();
      expect(screen.getByText('Approve')).toBeInTheDocument();
    });
  });

  describe('submit button disabled state', () => {
    it('Confirm Approval button is disabled when username is empty', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Approve'));

      const confirmBtn = screen.getByText('Confirm Approval');
      expect(confirmBtn).toBeDisabled();
    });

    it('Confirm Rejection button is disabled when username is empty', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const confirmBtn = screen.getByText('Confirm Rejection');
      expect(confirmBtn).toBeDisabled();
    });

    it('Confirm Rejection button is disabled when reason is empty but username is filled', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'reviewer' } });

      const confirmBtn = screen.getByText('Confirm Rejection');
      expect(confirmBtn).toBeDisabled();
    });

    it('Confirm Rejection button is enabled when both username and reason are filled', () => {
      renderApprovalFlow();
      fireEvent.click(screen.getByText('Reject'));

      const nameInput = screen.getByPlaceholderText('e.g. jane.doe');
      fireEvent.change(nameInput, { target: { value: 'reviewer' } });

      const reasonTextarea = screen.getByPlaceholderText(
        'Please provide a reason for rejection...',
      );
      fireEvent.change(reasonTextarea, { target: { value: 'Not good' } });

      const confirmBtn = screen.getByText('Confirm Rejection');
      expect(confirmBtn).not.toBeDisabled();
    });
  });
});
