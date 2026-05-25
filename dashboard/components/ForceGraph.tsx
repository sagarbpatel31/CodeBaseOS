"use client";

import dynamic from "next/dynamic";
import { useCallback } from "react";
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
}

type NodeWithPos = GraphNode & { x?: number; y?: number };

export function ForceGraph({ graphData, onNodeClick }: ForceGraphProps) {
  const nodeCanvasObject = useCallback(
    (node: NodeWithPos, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.label ?? node.id;
      const fontSize = Math.max(8, 12 / globalScale);
      const r = node.superseded ? 4 : 6;
      const color = nodeColor(node.nodeType ?? "");

      ctx.save();
      ctx.globalAlpha = node.superseded ? 0.35 : 1;
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
      ctx.fillStyle = color;
      ctx.fill();

      if (globalScale > 0.8) {
        ctx.font = `${fontSize}px monospace`;
        ctx.fillStyle = color;
        ctx.textAlign = "center";
        ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + r + fontSize);
      }
      ctx.restore();
    },
    []
  );

  return (
    <div className="flex-1 bg-gray-950 overflow-hidden">
      <ForceGraph2D
        graphData={graphData}
        onNodeClick={(node: NodeWithPos) => onNodeClick?.(node)}
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={() => "replace"}
        linkColor={() => "#374151"}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        backgroundColor="#030712"
        cooldownTicks={100}
      />
    </div>
  );
}
