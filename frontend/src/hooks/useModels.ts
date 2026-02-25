import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchModelLineage, fetchModels } from '../api/client';
import type { ModelFilters, ModelInfo, ModelLineage } from '../api/types';

export function useModels(filters?: ModelFilters) {
  const [models, setModels] = useState<ModelInfo[]>([]);
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
      const data = await fetchModels(filters, controller.signal);
      if (!controller.signal.aborted) {
        setModels(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load models');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [filters?.kind, filters?.owner, filters?.tag, filters?.search]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  return { models, loading, error, refetch: load };
}

export function useModelLineage(modelName: string | undefined) {
  const [lineage, setLineage] = useState<ModelLineage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    if (!modelName) return;

    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchModelLineage(modelName, controller.signal);
      if (!controller.signal.aborted) {
        setLineage(data);
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(err instanceof Error ? err.message : 'Failed to load lineage');
      }
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [modelName]);

  useEffect(() => {
    void load();
    return () => {
      controllerRef.current?.abort();
    };
  }, [load]);

  return { lineage, loading, error, refetch: load };
}
