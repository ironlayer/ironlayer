import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchTeamMembers,
  inviteTeamMember,
  removeTeamMember,
  updateTeamMemberRole,
} from '../api/client';
import type { TeamMembersInfo } from '../api/types';

export function useTeam() {
  const [data, setData] = useState<TeamMembersInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const result = await fetchTeamMembers(controller.signal);
      if (!controller.signal.aborted) {
        setData(result);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load team members');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  const invite = useCallback(
    async (email: string, role: string) => {
      const member = await inviteTeamMember(email, role);
      await load();
      return member;
    },
    [load],
  );

  const remove = useCallback(
    async (userId: string) => {
      const member = await removeTeamMember(userId);
      await load();
      return member;
    },
    [load],
  );

  const updateRole = useCallback(
    async (userId: string, role: string) => {
      const member = await updateTeamMemberRole(userId, role);
      await load();
      return member;
    },
    [load],
  );

  return {
    data,
    loading,
    error,
    refetch: load,
    invite,
    remove,
    updateRole,
  };
}
