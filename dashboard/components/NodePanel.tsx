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

interface Hop {
  order: number;
  type: string;
  title: string;
  detail: string;
  when: string;
}
interface VerifiedEdge {
  predicate: string;
  context: string;
  confidence: number;
}
interface ProvResult {
  chain: Hop[];
  verified_edges: VerifiedEdge[];
}

const HOP_COLOR: Record<string, string> = {
  Commit: "text-blue-400",
  PR: "text-purple-400",
  Issue: "text-amber-400",
  Decision: "text-cyan-400",
  Person: "text-pink-400",
  File: "text-green-400",
};

// Node label is "Type:payload" — strip the type prefix to recover the value.
function payload(label: string): string {
  const i = label.indexOf(":");
  return i >= 0 ? label.slice(i + 1) : label;
}

export function NodePanel({ node, repo, onClose }: NodePanelProps) {
  const [why, setWhy] = useState<WhyResult | null>(null);
  const [prov, setProv] = useState<ProvResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    setWhy(null);
    setProv(null);
    setErr("");
    if (!node) return;
    // Only File nodes carry a path we can build provenance for.
    if (node.nodeType !== "File") return;
    const file = payload(node.label);
    setLoading(true);
    const qs = (extra: Record<string, string>) => {
      const p = new URLSearchParams({ file, line: "1", ...extra });
      if (repo) p.set("repo", repo);
      return p.toString();
    };
    Promise.all([
      fetch(`/api/backend/why?${qs({})}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/backend/provenance?${qs({})}`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([w, p]) => {
        if (w) setWhy(w);
        if (p) setProv(p);
        if (!w && !p) setErr("backend error");
      })
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
          {err && <div className="text-red-400">backend error: {err}</div>}
          {why && (
            <div className="text-gray-200 leading-relaxed">{why.explanation}</div>
          )}

          {prov && prov.chain.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-gray-500 mt-4 mb-1">
                Origin story
              </div>
              <ol className="space-y-2">
                {prov.chain.map((h) => (
                  <li key={h.order} className="flex gap-2">
                    <span className="text-gray-600">{h.order}</span>
                    <div>
                      <span className={`uppercase text-[10px] ${HOP_COLOR[h.type] ?? "text-gray-400"}`}>
                        {h.type}
                      </span>
                      {h.when && <span className="text-gray-600 ml-1">{h.when}</span>}
                      <div className="text-gray-200">{h.title}</div>
                      {h.detail && <div className="text-gray-500">{h.detail}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}

          {prov && prov.verified_edges.length > 0 && (
            <>
              <div className="text-[10px] uppercase tracking-wider text-green-500/80 mt-4 mb-1">
                Verified graph edges
              </div>
              <ul className="space-y-1">
                {prov.verified_edges.map((e, i) => (
                  <li key={i} className="text-gray-400">
                    ✓ {e.context}{" "}
                    <span className="text-gray-600">({e.confidence})</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {why && (
            <div className="mt-3 pt-2 border-t border-gray-800/60 text-gray-600">
              {why.context_nodes} context nodes · ${why.cost_usd.toFixed(6)}
            </div>
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
