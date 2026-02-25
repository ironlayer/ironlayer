import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DAGVisualization from '../../src/components/DAGVisualization';
import type { DAGInputNode, DAGInputEdge } from '../../src/components/DAGVisualization';

/* ------------------------------------------------------------------ */
/* Mock reactflow - it relies on browser layout APIs unavailable in    */
/* jsdom (getBoundingClientRect, ResizeObserver, etc.)                 */
/* ------------------------------------------------------------------ */

const mockOnNodeClick = vi.fn();

vi.mock('reactflow', () => {
  const ReactFlowMock = (props: {
    nodes: Array<{ id: string; data: { label: string; kind: string; status: string; costUsd?: number } }>;
    edges: Array<{ id: string }>;
    onNodeClick?: (event: React.MouseEvent, node: { data: { label: string } }) => void;
    nodeTypes?: Record<string, React.ComponentType<{ data: { label: string; kind: string; status: string; costUsd?: number } }>>;
    children?: React.ReactNode;
  }) => {
    const ModelNode = props.nodeTypes?.model;
    return (
      <div data-testid="reactflow-container">
        {props.nodes.map((node) => (
          <div
            key={node.id}
            data-testid={`rf-node-${node.id}`}
            onClick={(e) => props.onNodeClick?.(e, node as never)}
          >
            {ModelNode && <ModelNode data={node.data} />}
          </div>
        ))}
        {props.edges.map((edge) => (
          <div key={edge.id} data-testid={`rf-edge-${edge.id}`} />
        ))}
        {props.children}
      </div>
    );
  };

  return {
    __esModule: true,
    default: ReactFlowMock,
    Background: () => <div data-testid="rf-background" />,
    Controls: () => <div data-testid="rf-controls" />,
    MiniMap: () => <div data-testid="rf-minimap" />,
    ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
    useReactFlow: () => ({ fitView: vi.fn(), getNodes: vi.fn(() => []), getEdges: vi.fn(() => []) }),
    Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
    MarkerType: { ArrowClosed: 'arrowclosed' },
  };
});

vi.mock('dagre', () => {
  const mockGraph = {
    setDefaultEdgeLabel: vi.fn(),
    setGraph: vi.fn(),
    setNode: vi.fn(),
    setEdge: vi.fn(),
    node: (id: string) => ({ x: 100, y: 100, width: 200, height: 70 }),
  };
  return {
    __esModule: true,
    default: {
      graphlib: {
        Graph: vi.fn(() => mockGraph),
      },
      layout: vi.fn(),
    },
  };
});

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

/* ------------------------------------------------------------------ */
/* Test data                                                           */
/* ------------------------------------------------------------------ */

const sampleNodes: DAGInputNode[] = [
  { id: 'stg_orders', name: 'stg_orders', kind: 'INCREMENTAL_BY_TIME_RANGE', status: 'unchanged', costUsd: 0 },
  { id: 'fct_orders', name: 'fct_orders', kind: 'FULL_REFRESH', status: 'modified', costUsd: 1.25 },
  { id: 'dim_customers', name: 'dim_customers', kind: 'TABLE', status: 'added', costUsd: 0.50 },
  { id: 'ext_raw_events', name: 'ext_raw_events', kind: 'external', status: 'external' },
  { id: 'fct_revenue', name: 'fct_revenue', kind: 'MERGE_BY_KEY', status: 'blocked', costUsd: 3.00 },
];

const sampleEdges: DAGInputEdge[] = [
  { source: 'ext_raw_events', target: 'stg_orders' },
  { source: 'stg_orders', target: 'fct_orders' },
  { source: 'fct_orders', target: 'fct_revenue' },
  { source: 'dim_customers', target: 'fct_revenue' },
];

/* ------------------------------------------------------------------ */
/* Helper                                                              */
/* ------------------------------------------------------------------ */

function renderDAG(props?: Partial<React.ComponentProps<typeof DAGVisualization>>) {
  return render(
    <MemoryRouter>
      <DAGVisualization
        nodes={props?.nodes ?? sampleNodes}
        edges={props?.edges ?? sampleEdges}
        onNodeClick={props?.onNodeClick}
        fitViewOnInit={props?.fitViewOnInit}
      />
    </MemoryRouter>,
  );
}

/* ------------------------------------------------------------------ */
/* Tests                                                               */
/* ------------------------------------------------------------------ */

describe('DAGVisualization', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders without crashing with empty data', () => {
    const { container } = renderDAG({ nodes: [], edges: [] });
    expect(container).toBeTruthy();
    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
  });

  it('renders the ReactFlow container and sub-components', () => {
    renderDAG();
    expect(screen.getByTestId('reactflow-container')).toBeInTheDocument();
    expect(screen.getByTestId('rf-background')).toBeInTheDocument();
    expect(screen.getByTestId('rf-minimap')).toBeInTheDocument();
    expect(screen.getByTestId('rf-controls')).toBeInTheDocument();
  });

  it('renders a node for each model in the input', () => {
    renderDAG();
    for (const node of sampleNodes) {
      expect(screen.getByTestId(`rf-node-${node.id}`)).toBeInTheDocument();
    }
  });

  it('renders edges between nodes', () => {
    renderDAG();
    expect(screen.getByTestId('rf-edge-e-0')).toBeInTheDocument();
    expect(screen.getByTestId('rf-edge-e-1')).toBeInTheDocument();
    expect(screen.getByTestId('rf-edge-e-2')).toBeInTheDocument();
    expect(screen.getByTestId('rf-edge-e-3')).toBeInTheDocument();
  });

  it('displays the model label text for each node', () => {
    renderDAG();
    expect(screen.getByText('stg_orders')).toBeInTheDocument();
    expect(screen.getByText('fct_orders')).toBeInTheDocument();
    expect(screen.getByText('dim_customers')).toBeInTheDocument();
    expect(screen.getByText('ext_raw_events')).toBeInTheDocument();
    expect(screen.getByText('fct_revenue')).toBeInTheDocument();
  });

  it('displays the kind badge for each node', () => {
    renderDAG();
    expect(screen.getByText('INCREMENTAL_BY_TIME_RANGE')).toBeInTheDocument();
    expect(screen.getByText('FULL_REFRESH')).toBeInTheDocument();
    expect(screen.getByText('TABLE')).toBeInTheDocument();
    // "external" appears in both the node kind badge and the legend
    expect(screen.getAllByText('external').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('MERGE_BY_KEY')).toBeInTheDocument();
  });

  // Helper: jsdom normalizes hex (#rrggbb) to rgb() in style attributes.
  // Accept either format so the test works across environments.
  function expectBorderColor(nodeTestId: string, hex: string) {
    const el = screen.getByTestId(nodeTestId);
    const styledDiv = el.querySelector('.rounded-lg');
    expect(styledDiv).toBeTruthy();
    const style = styledDiv!.getAttribute('style') ?? '';
    // Convert hex to rgb for comparison
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const containsHex = style.includes(hex);
    const containsRgb = style.includes(`rgb(${r}, ${g}, ${b})`);
    expect(containsHex || containsRgb).toBe(true);
  }

  it('color codes nodes by status - added nodes use blue border', () => {
    renderDAG();
    // added = { border: '#93c5fd' }
    expectBorderColor('rf-node-dim_customers', '#93c5fd');
  });

  it('color codes nodes by status - modified nodes use yellow border', () => {
    renderDAG();
    // modified = { border: '#fcd34d' }
    expectBorderColor('rf-node-fct_orders', '#fcd34d');
  });

  it('color codes nodes by status - unchanged nodes use green border', () => {
    renderDAG();
    // unchanged = { border: '#86efac' }
    expectBorderColor('rf-node-stg_orders', '#86efac');
  });

  it('color codes nodes by status - blocked nodes use red border', () => {
    renderDAG();
    // blocked = { border: '#fca5a5' }
    expectBorderColor('rf-node-fct_revenue', '#fca5a5');
  });

  it('color codes nodes by status - external nodes use gray border', () => {
    renderDAG();
    // external = { border: '#d1d5db' }
    expectBorderColor('rf-node-ext_raw_events', '#d1d5db');
  });

  it('calls the onNodeClick handler with the model name when a node is clicked', () => {
    const handler = vi.fn();
    renderDAG({ onNodeClick: handler });

    const nodeEl = screen.getByTestId('rf-node-fct_orders');
    fireEvent.click(nodeEl);

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith('fct_orders');
  });

  it('renders the legend with all status labels', () => {
    renderDAG();
    expect(screen.getByText('unchanged')).toBeInTheDocument();
    expect(screen.getByText('modified')).toBeInTheDocument();
    expect(screen.getByText('blocked')).toBeInTheDocument();
    expect(screen.getByText('added')).toBeInTheDocument();
    // "external" appears in both node badge and legend, so use getAllByText
    expect(screen.getAllByText(/external/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders the fit-to-view button', () => {
    renderDAG();
    const fitBtn = screen.getByTitle('Fit to view');
    expect(fitBtn).toBeInTheDocument();
  });

  it('shows cost for nodes with costUsd > 0', () => {
    renderDAG();
    // fct_orders has costUsd 1.25 -> "$1.25"
    expect(screen.getByText('$1.25')).toBeInTheDocument();
    // dim_customers has costUsd 0.50 -> "$0.50"
    expect(screen.getByText('$0.50')).toBeInTheDocument();
    // fct_revenue has costUsd 3.00 -> "$3.00"
    expect(screen.getByText('$3.00')).toBeInTheDocument();
  });

  it('does not render cost text for nodes with costUsd=0 or undefined', () => {
    renderDAG();
    // stg_orders has costUsd=0, ext_raw_events has no costUsd
    // These nodes should NOT render a cost span
    const stgNode = screen.getByTestId('rf-node-stg_orders');
    const extNode = screen.getByTestId('rf-node-ext_raw_events');
    expect(stgNode.querySelector('.text-gray-500')).toBeNull();
    expect(extNode.querySelector('.text-gray-500')).toBeNull();
  });
});
