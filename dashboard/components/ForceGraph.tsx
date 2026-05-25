"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef } from "react";
import type { GraphData, GraphNode } from "@/hooks/useGraphWS";
import { nodeColor } from "@/lib/nodeColors";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = dynamic<any>(
  () => import("react-force-graph-2d").then((m) => m.default),
  { ssr: false }
);

interface ForceGraphProps {
  graphData: GraphData;
  onNodeClick?: (node: GraphNode) => void;
  // Node ids to flag in red (chaos: orphaned authors + tampered episode).
  dangerIds?: Set<string>;
  // Node id to center + zoom on (set when a search result is clicked).
  focusId?: string | null;
}

type NodeWithPos = GraphNode & { x?: number; y?: number };

const DANGER_COLOR = "#EF4444";

export function ForceGraph({ graphData, onNodeClick, dangerIds, focusId }: ForceGraphProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  // First-seen timestamp per node id → drives the "new node" arrival glow.
  const seenAt = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    if (!focusId || !fgRef.current) return;
    const node = (graphData.nodes as NodeWithPos[]).find((n) => n.id === focusId);
    if (node && node.x != null && node.y != null) {
      fgRef.current.centerAt(node.x, node.y, 700);
      fgRef.current.zoom(4, 700);
    }
  }, [focusId, graphData.nodes]);

  useEffect(() => {
    const now = Date.now();
    const m = seenAt.current;
    for (const n of graphData.nodes) if (!m.has(n.id)) m.set(n.id, now);
  }, [graphData.nodes]);

  const nodeCanvasObject = useCallback(
    (node: NodeWithPos, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.label ?? node.id;
      // Clamp so labels never balloon at low zoom (avoids giant smeared text).
      const fontSize = Math.min(13, Math.max(7, 10 / globalScale));
      const danger = dangerIds?.has(node.id) ?? false;
      const r = danger ? 8 : node.superseded ? 4 : 6;
      const color = danger ? DANGER_COLOR : nodeColor(node.nodeType ?? "");
      const t = Date.now();

      ctx.save();
      ctx.globalAlpha = node.superseded && !danger ? 0.35 : 1;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      // Arrival glow: nodes seen <2.5s ago pulse a fading ring.
      const born = seenAt.current.get(node.id) ?? 0;
      const age = t - born;
      if (born && age < 2500) {
        const k = 1 - age / 2500; // 1 → 0
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, r + 4 + 6 * k, 0, 2 * Math.PI);
        ctx.strokeStyle = color;
        ctx.globalAlpha = 0.6 * k;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      if (danger) {
        // Pulsing red halo — makes a tampered node obvious on camera.
        const pulse = 3 + 3 * (0.5 + 0.5 * Math.sin(t / 180));
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, r + pulse, 0, 2 * Math.PI);
        ctx.strokeStyle = DANGER_COLOR;
        ctx.lineWidth = 2;
        ctx.stroke();
      }

      // Only label when zoomed in (or always for hub nodes), keeping the
      // overview clean and preventing overlapping-label blobs.
      const isHub = (node.val ?? 5) >= 10;
      if (globalScale > 1.6 || (isHub && globalScale > 0.6)) {
        ctx.font = `${fontSize}px monospace`;
        ctx.fillStyle = color;
        ctx.textAlign = "center";
        ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + fontSize);
      }
      ctx.restore();
    },
    [dangerIds]
  );

  return (
    <div className="flex-1 bg-gray-950 overflow-hidden">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        onNodeClick={(node: NodeWithPos) => onNodeClick?.(node)}
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={() => "replace"}
        linkColor={() => "#374151"}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        backgroundColor="#030712"
        cooldownTicks={100}
        autoPauseRedraw={false}
      />
    </div>
  );
}
