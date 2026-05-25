"use client";

import { useState } from "react";
import { useGraphData, type GraphNode } from "@/hooks/useGraphData";
import { TopBar } from "@/components/TopBar";
import { LeftRail } from "@/components/LeftRail";
import { RightRail } from "@/components/RightRail";
import { ForceGraph } from "@/components/ForceGraph";
import { ChaosPanel } from "@/components/ChaosPanel";
import { TimeSlider } from "@/components/TimeSlider";
import { NodePanel } from "@/components/NodePanel";

export default function Home() {
  const [asOf, setAsOf] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [dangerIds, setDangerIds] = useState<Set<string>>(new Set());
  const { graphData, timeRange } = useGraphData(asOf);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden">
      <TopBar />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <LeftRail />
        {/* min-w-0 lets the canvas column shrink instead of pushing the
            right rail off-screen (flexbox min-width:auto trap). */}
        <div className="relative flex-1 flex min-w-0 overflow-hidden">
          <ForceGraph graphData={graphData} onNodeClick={setSelected} dangerIds={dangerIds} />
          <ChaosPanel onHighlightChange={(ids) => setDangerIds(new Set(ids))} />
          <NodePanel node={selected} repo="" onClose={() => setSelected(null)} />
          <TimeSlider
            timeRange={timeRange}
            asOf={asOf}
            onChange={setAsOf}
            nodeCount={graphData.nodes.length}
          />
        </div>
        <RightRail />
      </div>
    </div>
  );
}
