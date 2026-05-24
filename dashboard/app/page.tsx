"use client";

import { useState } from "react";
import { useGraphData } from "@/hooks/useGraphData";
import { TopBar } from "@/components/TopBar";
import { LeftRail } from "@/components/LeftRail";
import { RightRail } from "@/components/RightRail";
import { ForceGraph } from "@/components/ForceGraph";
import { TimeSlider } from "@/components/TimeSlider";

export default function Home() {
  const [asOf, setAsOf] = useState<string | null>(null);
  const { graphData, timeRange } = useGraphData(asOf);

  return (
    <div className="flex flex-col h-full">
      <TopBar />
      <div className="flex flex-1 overflow-hidden">
        <LeftRail />
        <div className="relative flex-1 flex">
          <ForceGraph graphData={graphData} />
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
