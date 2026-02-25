import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchCustomerHealthList, fetchCustomerHealthDetail } from '../api/client';
import type { CustomerHealthList, CustomerHealth } from '../api/types';

export function useCustomerHealthList(
  status?: string,
  sortBy = 'health_score',
  limit = 50,
  offset = 0,
) {
  const [data, setData] = useState<CustomerHealthList | null>(null);
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
      const result = await fetchCustomerHealthList(status, sortBy, limit, offset, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load health data');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [status, sortBy, limit, offset]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useCustomerHealthDetail(tenantId: string) {
  const [data, setData] = useState<CustomerHealth | null>(null);
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
      const result = await fetchCustomerHealthDetail(tenantId, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load health detail');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [tenantId]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}
