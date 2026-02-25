import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Database, GitBranch, Tag } from 'lucide-react';
import { fetchModel } from '../api/client';
import { useModelLineage } from '../hooks/useModels';
import { useRuns } from '../hooks/useRuns';
import type { ModelInfo } from '../api/types';
import DAGVisualization from '../components/DAGVisualization';
import type { DAGInputEdge, DAGInputNode, DAGNodeStatus } from '../components/DAGVisualization';
import RunHistory from '../components/RunHistory';
import { formatDate, formatDateRange, statusColor } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function ModelDetail() {
  const { name } = useParams<{ name: string }>();
  const decodedName = name ? decodeURIComponent(name) : '';

  const [model, setModel] = useState<ModelInfo | null>(null);
  const [modelLoading, setModelLoading] = useState(true);
  const [modelError, setModelError] = useState<string | null>(null);

  const loadModel = useCallback(async () => {
    if (!decodedName) return;
    setModelLoading(true);
    setModelError(null);
    try {
      const data = await fetchModel(decodedName);
      setModel(data);
    } catch (err) {
      setModelError(err instanceof Error ? err.message : 'Failed to load model');
    } finally {
      setModelLoading(false);
    }
  }, [decodedName]);

  useEffect(() => {
    void loadModel();
  }, [loadModel]);

  const { lineage, loading: lineageLoading } = useModelLineage(decodedName);

  const [autoRefresh, setAutoRefresh] = useState(false);
  const {
    runs,
    loading: runsLoading,
    refetch: refetchRuns,
  } = useRuns(
    { model_name: decodedName, limit: 20 },
    autoRefresh ? 10000 : undefined,
  );

  // Build DAG nodes/edges from lineage
  const dagData = useMemo((): { nodes: DAGInputNode[]; edges: DAGInputEdge[] } => {
    if (!lineage) return { nodes: [], edges: [] };

    const nodes: DAGInputNode[] = lineage.nodes.map((n) => {
      let status: DAGNodeStatus = 'unchanged';
      if (n.is_target) status = 'modified';
      if (n.kind === 'external') status = 'external';
      return {
        id: n.id,
        name: n.name,
        kind: n.kind,
        status,
      };
    });

    const edges: DAGInputEdge[] = lineage.edges.map((e) => ({
      source: e.source,
      target: e.target,
    }));

    return { nodes, edges };
  }, [lineage]);

  if (modelLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
      </div>
    );
  }

  if (modelError || !model) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
        {modelError ?? 'Model not found.'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <Database size={24} className="text-ironlayer-500" />
          <h1 className="text-2xl font-bold text-gray-900">{model.model_name}</h1>
          {model.last_run_status && (
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(
                model.last_run_status,
              )}`}
            >
              {model.last_run_status}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-gray-500">
          {model.kind.replace(/_/g, ' ')} &middot; {model.materialization}
          {model.owner && <> &middot; Owner: {model.owner}</>}
        </p>
      </div>

      {/* Metadata */}
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="border-b border-gray-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-gray-900">Model Metadata</h2>
        </div>
        <div className="grid grid-cols-3 gap-4 p-4 text-sm">
          <div>
            <span className="text-xs text-gray-400">Current Version</span>
            <p className="mt-0.5 font-mono text-xs text-gray-700">
              {model.current_version.slice(0, 16)}...
            </p>
          </div>
          <div>
            <span className="text-xs text-gray-400">Time Column</span>
            <p className="mt-0.5 text-gray-700">{model.time_column ?? '--'}</p>
          </div>
          <div>
            <span className="text-xs text-gray-400">Unique Key</span>
            <p className="mt-0.5 text-gray-700">{model.unique_key ?? '--'}</p>
          </div>
          <div>
            <span className="text-xs text-gray-400">Created</span>
            <p className="mt-0.5 text-gray-700">{formatDate(model.created_at)}</p>
          </div>
          <div>
            <span className="text-xs text-gray-400">Last Modified</span>
            <p className="mt-0.5 text-gray-700">{formatDate(model.last_modified_at)}</p>
          </div>
          {model.watermark_range && (
            <div>
              <span className="text-xs text-gray-400">Watermark</span>
              <p className="mt-0.5 text-gray-700">
                {formatDateRange(model.watermark_range)}
              </p>
            </div>
          )}
          {model.tags.length > 0 && (
            <div className="col-span-3">
              <span className="text-xs text-gray-400">Tags</span>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {model.tags.map((tag) => (
                  <span
                    key={tag}
                    className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                  >
                    <Tag size={10} />
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Lineage */}
      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="flex items-center gap-2 border-b border-gray-100 px-4 py-3">
          <GitBranch size={14} className="text-gray-400" />
          <h2 className="text-sm font-semibold text-gray-900">Lineage Graph</h2>
        </div>
        {lineageLoading ? (
          <div className="flex items-center justify-center p-12">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" />
          </div>
        ) : dagData.nodes.length === 0 ? (
          <div className="p-6 text-center text-sm text-gray-500">
            No lineage data available.
          </div>
        ) : (
          <div className="h-[400px] p-2">
            <DAGVisualization nodes={dagData.nodes} edges={dagData.edges} />
          </div>
        )}
      </div>

      {/* Run history */}
      <RunHistory
        runs={runs}
        loading={runsLoading}
        onRefresh={refetchRuns}
        autoRefresh={autoRefresh}
        onToggleAutoRefresh={() => setAutoRefresh((prev) => !prev)}
      />
    </div>
  );
}

export default ModelDetail;
