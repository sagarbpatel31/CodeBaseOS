"use client";

import { useEffect, useState } from "react";
import type { GraphNode } from "@/hooks/useGraphData";

interface NodePanelProps {
  node: GraphNode | null;
  repo: string;
  onClose: () => void;
}

interface WhyResult {
  explanation: string;
  context_nodes: number;
  cost_usd: number;
}

// Node label is "Type:payload" — strip the type prefix to recover the value.
function payload(label: string): string {
  const i = label.indexOf(":");
  return i >= 0 ? label.slice(i + 1) : label;
}

export function NodePanel({ node, repo, onClose }: NodePanelProps) {
  const [why, setWhy] = useState<WhyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setWhy(null);
    setErr("");
    if (!node) return;
    // Only File nodes carry a path we can ask /why about.
    if (node.nodeType !== "File") return;
    const file = payload(node.label);
    setLoading(true);
    const params = new URLSearchParams({ file, line: "1" });
    if (repo) params.set("repo", repo);
    fetch(`/api/backend/why?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => setWhy(d))
      .catch((e) => setErr(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  }, [node, repo]);

  if (!node) return null;

  return (
    <div className="absolute top-4 right-4 z-20 w-80 max-h-[80%] overflow-y-auto
                    bg-gray-900/95 backdrop-blur border border-gray-700 rounded-lg
                    shadow-xl font-mono text-xs">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-purple-400 uppercase tracking-wider">{node.nodeType}</span>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-200">✕</button>
      </div>

      <div className="px-3 py-2 text-gray-200 break-words border-b border-gray-800/60">
        {payload(node.label)}
      </div>

      {node.nodeType === "File" ? (
        <div className="px-3 py-3">
          <div className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">
            Why does this exist?
          </div>
          {loading && <div className="text-gray-500">synthesizing…</div>}
          {err && <div className="text-red-400">/why failed: {err}</div>}
          {why && (
            <>
              <div className="text-gray-200 leading-relaxed">{why.explanation}</div>
              <div className="mt-3 pt-2 border-t border-gray-800/60 text-gray-600">
                {why.context_nodes} context nodes · ${why.cost_usd.toFixed(6)}
              </div>
            </>
          )}
        </div>
      ) : (
        <div className="px-3 py-3 text-gray-600">
          Click a <span className="text-green-400">File</span> node to ask “why does this exist?”
        </div>
      )}
    </div>
  );
}
