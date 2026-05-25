"use client";

import { useEffect, useState } from "react";
import type { GraphNode } from "@/hooks/useGraphData";

interface NodePanelProps {
  node: GraphNode | null;
  repo: string;
  onClose: () => void;
}

interface Citation {
  type: string;
  title: string;
  url: string;
}
interface WhyResult {
  explanation: string;
  citations?: Citation[];
  context_nodes: number;
  cost_usd: number;
}
interface Hop {
  order: number;
  type: string;
  title: string;
  detail: string;
  when: string;
  url?: string;
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
interface ExplainResult {
  summary: string;
  owner: string;
  key_points: string[];
  key_decisions: string[];
}
interface DiffChange {
  type: string;
  title: string;
  when: string;
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

function SectionLabel({ text, color = "text-gray-500" }: { text: string; color?: string }) {
  return <div className={`text-[10px] uppercase tracking-wider ${color} mt-4 mb-1`}>{text}</div>;
}

export function NodePanel({ node, repo, onClose }: NodePanelProps) {
  const [why, setWhy] = useState<WhyResult | null>(null);
  const [prov, setProv] = useState<ProvResult | null>(null);
  const [explain, setExplain] = useState<ExplainResult | null>(null);
  const [diff, setDiff] = useState<DiffChange[] | null>(null);
  const [busy, setBusy] = useState<string>(""); // which action is loading
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  const file = node && node.nodeType === "File" ? payload(node.label) : "";

  function qs(extra: Record<string, string> = {}) {
    const p = new URLSearchParams({ file, ...extra });
    if (repo) p.set("repo", repo);
    return p.toString();
  }

  useEffect(() => {
    setWhy(null);
    setProv(null);
    setExplain(null);
    setDiff(null);
    setErr("");
    setCopied(false);
    if (!node || node.nodeType !== "File") return;
    setLoading(true);
    Promise.all([
      fetch(`/api/backend/why?${qs({ line: "1" })}`).then((r) => (r.ok ? r.json() : null)),
      fetch(`/api/backend/provenance?${qs({ line: "1" })}`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([w, p]) => {
        if (w) setWhy(w);
        if (p) setProv(p);
        if (!w && !p) setErr("backend error");
      })
      .catch((e) => setErr(String(e?.message ?? e)))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [node, repo]);

  async function loadExplain() {
    setBusy("explain");
    try {
      const res = await fetch(`/api/backend/explain-file?${qs()}`);
      if (res.ok) setExplain(await res.json());
    } catch {
      /* ignore */
    }
    setBusy("");
  }

  async function loadDiff() {
    setBusy("diff");
    try {
      const since = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
      const until = new Date().toISOString().slice(0, 10);
      const res = await fetch(`/api/backend/diff?${qs({ since, until })}`);
      if (res.ok) setDiff((await res.json()).changes ?? []);
    } catch {
      /* ignore */
    }
    setBusy("");
  }

  function copyMarkdown() {
    const lines: string[] = [`## ${file}`, ""];
    if (why) lines.push(why.explanation, "");
    if (why?.citations?.length) {
      lines.push("### Sources");
      why.citations.forEach((c) => lines.push(`- [${c.type}] ${c.title} — ${c.url}`));
      lines.push("");
    }
    if (prov?.chain.length) {
      lines.push("### Origin story");
      prov.chain.forEach((h) =>
        lines.push(`${h.order}. **${h.type}**${h.when ? ` (${h.when})` : ""} — ${h.title}${h.url ? ` (${h.url})` : ""}`)
      );
    }
    navigator.clipboard.writeText(lines.join("\n")).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  if (!node) return null;

  const btn =
    "flex-1 text-[10px] uppercase tracking-wider rounded border border-gray-700 py-1 " +
    "text-gray-300 hover:bg-gray-800/60 disabled:opacity-40 transition-colors";

  return (
    <div className="absolute top-4 right-4 z-20 w-80 max-h-[82%] overflow-y-auto
                    bg-gray-900/95 backdrop-blur border border-gray-700 rounded-lg
                    shadow-xl font-mono text-xs">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-purple-400 uppercase tracking-wider">{node.nodeType}</span>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-200">✕</button>
      </div>

      <div className="px-3 py-2 text-gray-200 break-words border-b border-gray-800/60">
        {payload(node.label)}
      </div>

      {node.nodeType !== "File" ? (
        <div className="px-3 py-3 text-gray-600">
          Click a <span className="text-green-400">File</span> node to inspect its
          provenance.
        </div>
      ) : (
        <div className="px-3 py-3">
          {/* Actions */}
          <div className="flex gap-1 mb-3">
            <button onClick={loadExplain} disabled={busy === "explain"} className={btn}>
              {busy === "explain" ? "…" : "explain file"}
            </button>
            <button onClick={loadDiff} disabled={busy === "diff"} className={btn}>
              {busy === "diff" ? "…" : "what changed"}
            </button>
            <button onClick={copyMarkdown} disabled={!why && !prov} className={btn}>
              {copied ? "copied ✓" : "copy ↗"}
            </button>
          </div>

          <SectionLabel text="Why does this exist?" color="text-gray-500 mt-0" />
          {loading && <div className="text-gray-500">synthesizing…</div>}
          {err && <div className="text-red-400">backend error: {err}</div>}
          {why && <div className="text-gray-200 leading-relaxed">{why.explanation}</div>}
          {why?.citations?.length ? (
            <div className="mt-2 flex flex-col gap-1">
              {why.citations.map((c, i) => (
                <a key={i} href={c.url} target="_blank" rel="noreferrer"
                   className="text-blue-300 hover:underline truncate">
                  ↗ {c.type}: {c.title}
                </a>
              ))}
            </div>
          ) : null}

          {explain && (
            <>
              <SectionLabel text="File overview" color="text-cyan-400/80" />
              <div className="text-gray-200 leading-relaxed">{explain.summary}</div>
              {explain.owner && (
                <div className="text-gray-500 mt-1">owner: <span className="text-pink-300">{explain.owner}</span></div>
              )}
              {explain.key_points.length > 0 && (
                <ul className="list-disc list-inside text-gray-300 mt-1 space-y-0.5">
                  {explain.key_points.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              )}
            </>
          )}

          {prov && prov.chain.length > 0 && (
            <>
              <SectionLabel text="Origin story" />
              <ol className="space-y-2">
                {prov.chain.map((h) => (
                  <li key={h.order} className="flex gap-2">
                    <span className="text-gray-600">{h.order}</span>
                    <div>
                      <span className={`uppercase text-[10px] ${HOP_COLOR[h.type] ?? "text-gray-400"}`}>
                        {h.type}
                      </span>
                      {h.when && <span className="text-gray-600 ml-1">{h.when}</span>}
                      <div className="text-gray-200">
                        {h.url ? (
                          <a href={h.url} target="_blank" rel="noreferrer"
                             className="text-blue-300 hover:underline">{h.title} ↗</a>
                        ) : (
                          h.title
                        )}
                      </div>
                      {h.detail && <div className="text-gray-500">{h.detail}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            </>
          )}

          {diff && (
            <>
              <SectionLabel text={`What changed (last year) · ${diff.length}`} color="text-amber-400/80" />
              {diff.length === 0 ? (
                <div className="text-gray-600">No changes in window.</div>
              ) : (
                <ul className="space-y-1">
                  {diff.slice(0, 12).map((c, i) => (
                    <li key={i} className="flex gap-2">
                      <span className={`uppercase text-[10px] ${HOP_COLOR[c.type] ?? "text-gray-400"}`}>{c.type}</span>
                      <span className="text-gray-600">{c.when.slice(0, 10)}</span>
                      <span className="text-gray-300 truncate">{c.title}</span>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {prov && prov.verified_edges.length > 0 && (
            <>
              <SectionLabel text="Verified graph edges" color="text-green-500/80" />
              <ul className="space-y-1">
                {prov.verified_edges.map((e, i) => (
                  <li key={i} className="text-gray-400">✓ {e.context} <span className="text-gray-600">({e.confidence})</span></li>
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
      )}
    </div>
  );
}
