"use client";

import { useEffect, useRef, useState } from "react";

export interface GraphNode {
  id: string;
  nodeType: string;
  label: string;
  val?: number;
  superseded?: boolean;
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

const WS_URL = typeof window !== "undefined"
  ? `ws://${window.location.hostname}:8000/ws`
  : "ws://localhost:8000/ws";
const RECONNECT_MS = 3000;

export function useGraphWS() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const nodeIndex = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    function connect() {
      if (cancelled) return;
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data as string) as {
            nodes?: GraphNode[];
            links?: GraphLink[];
          };

          setGraphData((prev) => {
            const newNodes = (msg.nodes ?? []).filter(
              (n) => !nodeIndex.current.has(n.id)
            );
            newNodes.forEach((n) => nodeIndex.current.add(n.id));
            return {
              nodes: [...prev.nodes, ...newNodes],
              links: [...prev.links, ...(msg.links ?? [])],
            };
          });
        } catch {
          // malformed message — ignore
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) setTimeout(connect, RECONNECT_MS);
      };

      ws.onerror = () => ws.close();
    }

    connect();
    return () => {
      cancelled = true;
      wsRef.current?.close();
    };
  }, []);

  return { graphData, connected };
}
