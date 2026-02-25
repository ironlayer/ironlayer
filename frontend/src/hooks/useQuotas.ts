import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchQuotas } from '../api/client';
import type { QuotaInfo } from '../api/types';

export function useQuotas() {
  const [data, setData] = useState<QuotaInfo | null>(null);
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
      const result = await fetchQuotas(controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load quotas');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}
