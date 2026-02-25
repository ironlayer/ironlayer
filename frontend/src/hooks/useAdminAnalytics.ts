import { useCallback, useEffect, useRef, useState } from 'react';
import {
  fetchAnalyticsOverview,
  fetchAnalyticsTenants,
  fetchAnalyticsRevenue,
  fetchAnalyticsCostBreakdown,
  fetchAnalyticsHealth,
} from '../api/client';
import type {
  AnalyticsOverview,
  TenantBreakdown,
  RevenueMetrics,
  CostBreakdown,
  HealthMetrics,
} from '../api/types';

export function useAnalyticsOverview(days = 30) {
  const [data, setData] = useState<AnalyticsOverview | null>(null);
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
      const result = await fetchAnalyticsOverview(days, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load overview');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useAnalyticsTenants(days = 30, limit = 50, offset = 0) {
  const [data, setData] = useState<TenantBreakdown | null>(null);
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
      const result = await fetchAnalyticsTenants(days, limit, offset, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load tenants');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [days, limit, offset]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useAnalyticsRevenue() {
  const [data, setData] = useState<RevenueMetrics | null>(null);
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
      const result = await fetchAnalyticsRevenue(controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load revenue');
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

export function useAnalyticsCostBreakdown(days = 30, groupBy = 'model') {
  const [data, setData] = useState<CostBreakdown | null>(null);
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
      const result = await fetchAnalyticsCostBreakdown(days, groupBy, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load cost breakdown');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [days, groupBy]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}

export function useAnalyticsHealth(days = 30) {
  const [data, setData] = useState<HealthMetrics | null>(null);
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
      const result = await fetchAnalyticsHealth(days, controller.signal);
      if (!controller.signal.aborted) setData(result);
    } catch (e: unknown) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : 'Failed to load health metrics');
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
    return () => { controllerRef.current?.abort(); };
  }, [load]);

  return { data, loading, error, refetch: load };
}
