import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchCostReport, fetchUsageReport, fetchLLMReport } from '../api/client';
import type { CostReport, UsageReport, LLMReport } from '../api/types';

export function useCostReport(since?: string, until?: string, groupBy = 'model') {
  const [data, setData] = useState<CostReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!since || !until) {
      setData(null);
      setLoading(false);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const result = await fetchCostReport(since, until, groupBy, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load cost report');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [since, until, groupBy]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useUsageReport(since?: string, until?: string, groupBy = 'actor') {
  const [data, setData] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!since || !until) {
      setData(null);
      setLoading(false);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const result = await fetchUsageReport(since, until, groupBy, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load usage report');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [since, until, groupBy]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useLLMReport(since?: string, until?: string) {
  const [data, setData] = useState<LLMReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!since || !until) {
      setData(null);
      setLoading(false);
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const result = await fetchLLMReport(since, until, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load LLM report');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [since, until]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}
