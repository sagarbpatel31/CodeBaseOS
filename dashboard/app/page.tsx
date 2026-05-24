"use client";

import { useGraphWS } from "@/hooks/useGraphWS";
import { TopBar } from "@/components/TopBar";
import { LeftRail } from "@/components/LeftRail";
import { RightRail } from "@/components/RightRail";
import { ForceGraph } from "@/components/ForceGraph";

export default function Home() {
  const { graphData, connected } = useGraphWS();

  return (
    <div className="flex flex-col h-full">
      <TopBar nodeCount={graphData.nodes.length} connected={connected} />
      <div className="flex flex-1 overflow-hidden">
        <LeftRail />
        <ForceGraph graphData={graphData} />
        <RightRail />
      </div>
    </div>
  );
}
