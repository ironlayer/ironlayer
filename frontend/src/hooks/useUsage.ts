import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchUsageSummary, fetchUsageEvents } from '../api/client';
import type { UsageSummary, UsageEvent, UsageEventsResponse } from '../api/types';

export function useUsageSummary(days = 30) {
  const [summary, setSummary] = useState<UsageSummary | null>(null);
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
      const data = await fetchUsageSummary(days, controller.signal);
      if (!controller.signal.aborted) {
        setSummary(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load usage summary');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [days]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  return { summary, loading, error, refetch: load };
}

export function useUsageEvents(eventType?: string, limit = 50, offset = 0) {
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [total, setTotal] = useState(0);
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
      const data: UsageEventsResponse = await fetchUsageEvents(eventType, limit, offset, controller.signal);
      if (!controller.signal.aborted) {
        setEvents(data.events);
        setTotal(data.total);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load usage events');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [eventType, limit, offset]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  return { events, total, loading, error, refetch: load };
}
