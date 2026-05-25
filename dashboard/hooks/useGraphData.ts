"use client";

import { useEffect, useState } from "react";

export interface GraphNode {
  id: string;
  nodeType: string;
  label: string;
  val?: number;
}

export interface GraphLink {
  source: string;
  target: string;
  label?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

export interface TimeRange {
  min: string;
  max: string;
}

/**
 * Fetches the force-graph snapshot.
 *
 * When `asOf` is null the hook live-polls every 5s ("live" mode). When `asOf`
 * is an ISO string it fetches that bi-temporal snapshot once (time-travel mode)
 * and stops polling so the view is frozen at that instant.
 */
export function useGraphData(asOf: string | null) {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [timeRange, setTimeRange] = useState<TimeRange>({ min: "", max: "" });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function fetchGraph() {
      try {
        const url = asOf
          ? `/api/backend/graph?as_of=${encodeURIComponent(asOf)}`
          : "/api/backend/graph";
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          if (cancelled) return;
          const incoming: GraphData = { nodes: data.nodes ?? [], links: data.links ?? [] };
          // Time-travel = a distinct snapshot → replace. Live poll → MERGE,
          // reusing existing node objects so the force layout (their x/y) stays
          // put instead of re-simulating from scratch every 5s.
          setGraphData((prev) => {
            if (asOf) return incoming;
            const byId = new Map(prev.nodes.map((n) => [n.id, n]));
            const nodes = incoming.nodes.map((n) => {
              const old = byId.get(n.id);
              if (old) {
                old.label = n.label;
                old.nodeType = n.nodeType;
                old.val = n.val;
                return old; // keeps x/y from the running simulation
              }
              return n;
            });
            // Reuse the already-resolved link objects when the set is unchanged.
            const links = prev.links.length === incoming.links.length ? prev.links : incoming.links;
            return { nodes, links };
          });
          if (data.timeRange) setTimeRange(data.timeRange);
        }
      } catch {
        // backend offline
      }
      if (!cancelled) setLoading(false);
    }

    fetchGraph();
    // Live mode polls; time-travel mode is a frozen single fetch.
    if (asOf) return () => { cancelled = true; };
    const id = setInterval(fetchGraph, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [asOf]);

  return { graphData, loading, timeRange };
}
