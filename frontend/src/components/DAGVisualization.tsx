import { useCallback, useEffect, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from 'reactflow';
import dagre from 'dagre';
import { useNavigate } from 'react-router-dom';
import { Maximize2 } from 'lucide-react';
import { formatCost } from '../utils/formatting';
import 'reactflow/dist/style.css';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type DAGNodeStatus =
  | 'unchanged'
  | 'modified'
  | 'blocked'
  | 'added'
  | 'external';

export interface DAGNodeData {
  label: string;
  kind: string;
  status: DAGNodeStatus;
  costUsd?: number;
}

export interface DAGInputNode {
  id: string;
  name: string;
  kind: string;
  status: DAGNodeStatus;
  costUsd?: number;
}

export interface DAGInputEdge {
  source: string;
  target: string;
}

interface DAGVisualizationProps {
  nodes: DAGInputNode[];
  edges: DAGInputEdge[];
  onNodeClick?: (modelName: string) => void;
  fitViewOnInit?: boolean;
}

/* ------------------------------------------------------------------ */
/* Color mapping                                                       */
/* ------------------------------------------------------------------ */

const STATUS_COLORS: Record<DAGNodeStatus, { bg: string; border: string; text: string }> = {
  unchanged: { bg: '#f0fdf4', border: '#86efac', text: '#15803d' },
  modified:  { bg: '#fffbeb', border: '#fcd34d', text: '#b45309' },
  blocked:   { bg: '#fef2f2', border: '#fca5a5', text: '#b91c1c' },
  added:     { bg: '#eff6ff', border: '#93c5fd', text: '#1d4ed8' },
  external:  { bg: '#f9fafb', border: '#d1d5db', text: '#6b7280' },
};

/* ------------------------------------------------------------------ */
/* Custom node                                                         */
/* ------------------------------------------------------------------ */

function ModelNode({ data }: NodeProps<DAGNodeData>) {
  const colors = STATUS_COLORS[data.status] ?? STATUS_COLORS.external;

  return (
    <div
      className="rounded-lg px-4 py-3 shadow-sm"
      style={{
        background: colors.bg,
        border: `2px solid ${colors.border}`,
        minWidth: 180,
      }}
    >
      <div className="flex items-center justify-between gap-2">
        <span
          className="truncate text-sm font-semibold"
          style={{ color: colors.text }}
        >
          {data.label}
        </span>
      </div>
      <div className="mt-1 flex items-center gap-2">
        <span
          className="inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase"
          style={{
            background: colors.border + '33',
            color: colors.text,
          }}
        >
          {data.kind}
        </span>
        {data.costUsd !== undefined && data.costUsd > 0 && (
          <span className="text-[10px] text-gray-500">
            {formatCost(data.costUsd)}
          </span>
        )}
      </div>
    </div>
  );
}

const nodeTypes = { model: ModelNode };

/* ------------------------------------------------------------------ */
/* Fit-to-view panel (rendered inside ReactFlow to access its context) */
/* ------------------------------------------------------------------ */

function FitViewButton() {
  const { fitView } = useReactFlow();

  return (
    <div className="react-flow__panel absolute right-4 top-4">
      <button
        onClick={() => fitView({ padding: 0.2 })}
        className="rounded-lg border border-gray-200 bg-white p-2 shadow-sm transition-colors hover:bg-gray-50"
        title="Fit to view"
      >
        <Maximize2 size={14} className="text-gray-500" />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* dagre layout                                                        */
/* ------------------------------------------------------------------ */

function layoutGraph(
  inputNodes: DAGInputNode[],
  inputEdges: DAGInputEdge[],
): { nodes: Node<DAGNodeData>[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: 'TB', nodesep: 60, ranksep: 80 });

  for (const n of inputNodes) {
    g.setNode(n.id, { width: 200, height: 70 });
  }
  for (const e of inputEdges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  const nodes: Node<DAGNodeData>[] = inputNodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: 'model',
      position: { x: (pos?.x ?? 0) - 100, y: (pos?.y ?? 0) - 35 },
      data: {
        label: n.name,
        kind: n.kind,
        status: n.status,
        costUsd: n.costUsd,
      },
    };
  });

  const isModified = new Set(
    inputNodes.filter((n) => n.status === 'modified' || n.status === 'added').map((n) => n.id),
  );

  const edges: Edge[] = inputEdges.map((e, i) => {
    const animated = isModified.has(e.source) || isModified.has(e.target);
    return {
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      animated,
      style: {
        stroke: animated ? '#f59e0b' : '#d1d5db',
        strokeWidth: animated ? 2 : 1,
        strokeDasharray: animated ? undefined : '5 5',
      },
    };
  });

  return { nodes, edges };
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

function DAGVisualization({
  nodes: inputNodes,
  edges: inputEdges,
  onNodeClick,
  fitViewOnInit = true,
}: DAGVisualizationProps) {
  const navigate = useNavigate();

  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(
    () => layoutGraph(inputNodes, inputEdges),
    [inputNodes, inputEdges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges);

  useEffect(() => {
    setNodes(layoutNodes);
    setEdges(layoutEdges);
  }, [layoutNodes, layoutEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node<DAGNodeData>) => {
      if (onNodeClick) {
        onNodeClick(node.data.label);
      } else {
        navigate(`/models/${encodeURIComponent(node.data.label)}`);
      }
    },
    [navigate, onNodeClick],
  );

  return (
    <div className="relative h-full w-full rounded-lg border border-gray-200 bg-white">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        nodeTypes={nodeTypes}
        fitView={fitViewOnInit}
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
      >
        <Background color="#e5e7eb" gap={20} size={1} />
        <MiniMap
          nodeColor={(node) => {
            const status = (node.data as DAGNodeData).status;
            return STATUS_COLORS[status]?.border ?? '#d1d5db';
          }}
          className="rounded-lg border border-gray-200"
        />
        <Controls showInteractive={false} />
        <FitViewButton />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute bottom-4 left-4 flex gap-3 rounded-lg border border-gray-200 bg-white/90 px-3 py-2 text-[11px] backdrop-blur-sm">
        {Object.entries(STATUS_COLORS).map(([status, colors]) => (
          <div key={status} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ background: colors.border }}
            />
            <span className="capitalize text-gray-600">{status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default DAGVisualization;
