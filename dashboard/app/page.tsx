"use client";

import { useEffect, useMemo, useState } from "react";
import { useGraphData, type GraphNode } from "@/hooks/useGraphData";
import { TopBar } from "@/components/TopBar";
import { LeftRail } from "@/components/LeftRail";
import { RightRail } from "@/components/RightRail";
import { ForceGraph } from "@/components/ForceGraph";
import { ChaosPanel } from "@/components/ChaosPanel";
import { TimeSlider } from "@/components/TimeSlider";
import { NodePanel } from "@/components/NodePanel";
import { Legend } from "@/components/Legend";
import { EmptyState } from "@/components/EmptyState";
import { FilterChips } from "@/components/FilterChips";
import { AskPanel } from "@/components/AskPanel";

export default function Home() {
  const [asOf, setAsOf] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [dangerIds, setDangerIds] = useState<Set<string>>(new Set());
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const { graphData, timeRange } = useGraphData(asOf);

  // Search-result click → center the graph on the node + open its inspector.
  useEffect(() => {
    function onFocus(e: Event) {
      const d = (e as CustomEvent).detail as { id: string; nodeType: string; title: string };
      setSelected({ id: d.id, nodeType: d.nodeType, label: d.title });
      setFocusId(d.id);
    }
    window.addEventListener("cbos-focus", onFocus);
    return () => window.removeEventListener("cbos-focus", onFocus);
  }, []);

  // Apply node-type filters (drop hidden-type nodes and any links touching them).
  const filtered = useMemo(() => {
    if (hidden.size === 0) return graphData;
    const keep = new Set(
      graphData.nodes.filter((n) => !hidden.has(n.nodeType)).map((n) => n.id)
    );
    return {
      nodes: graphData.nodes.filter((n) => keep.has(n.id)),
      links: graphData.links.filter((l) => {
        const s = typeof l.source === "string" ? l.source : (l.source as { id: string })?.id;
        const t = typeof l.target === "string" ? l.target : (l.target as { id: string })?.id;
        return keep.has(s) && keep.has(t);
      }),
    };
  }, [graphData, hidden]);

  function toggleType(t: string) {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  }

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden">
      <TopBar />
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <LeftRail />
        <div className="relative flex-1 flex min-w-0 overflow-hidden">
          <ForceGraph
            graphData={filtered}
            onNodeClick={setSelected}
            dangerIds={dangerIds}
            focusId={focusId}
          />
          {graphData.nodes.length === 0 ? <EmptyState /> : <Legend />}
          {graphData.nodes.length > 0 && <FilterChips hidden={hidden} onToggle={toggleType} />}
          <ChaosPanel onHighlightChange={(ids) => setDangerIds(new Set(ids))} />
          {graphData.nodes.length > 0 && <AskPanel />}
          <NodePanel node={selected} repo="" onClose={() => setSelected(null)} />
          <TimeSlider
            timeRange={timeRange}
            asOf={asOf}
            onChange={setAsOf}
            nodeCount={filtered.nodes.length}
          />
        </div>
        <RightRail />
      </div>
    </div>
  );
}
