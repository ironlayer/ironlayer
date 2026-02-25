import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchRun, fetchRuns } from '../api/client';
import type { RunFilters, RunRecord } from '../api/types';

export function useRuns(filters?: RunFilters, autoRefreshMs?: number) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const serializedFilters = JSON.stringify(filters);

  const load = useCallback(async () => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const parsed = JSON.parse(serializedFilters) as RunFilters | undefined;
      const data = await fetchRuns(parsed, controller.signal);
      if (!controller.signal.aborted) {
        setRuns(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load runs');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [serializedFilters]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  useEffect(() => {
    if (autoRefreshMs && autoRefreshMs > 0) {
      intervalRef.current = setInterval(() => void load(), autoRefreshMs);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    }
  }, [autoRefreshMs, load]);

  return { runs, loading, error, refetch: load };
}

export function useRun(runId: string | undefined) {
  const [run, setRun] = useState<RunRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!runId) return;

    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchRun(runId, controller.signal);
      if (!controller.signal.aborted) {
        setRun(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load run');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [runId]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  return { run, loading, error, refetch: load };
}
