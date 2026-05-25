"use client";

import { useCallback, useEffect, useState } from "react";

interface TamperState {
  episode_id: string;
  sequence_no: number | string;
  action_type: string;
  original_hash: string;
  corrupted_hash: string;
}

interface NuclearState {
  person: string;
  orphaned_count: number;
  orphaned_ids: string[];
  by_type: Record<string, number>;
  suggested_reviewers: { name: string; activity: number }[];
}

interface ChaosState {
  tamper: TamperState | null;
  nuclear: NuclearState | null;
}

interface ChaosPanelProps {
  // Lifts the set of node ids to highlight as "danger" (orphaned + tampered).
  onHighlightChange?: (ids: string[]) => void;
}

export function ChaosPanel({ onHighlightChange }: ChaosPanelProps) {
  const [state, setState] = useState<ChaosState>({ tamper: null, nuclear: null });
  const [busy, setBusy] = useState<string | null>(null);

  const applyHighlights = useCallback(
    (s: ChaosState) => {
      const ids: string[] = [];
      if (s.nuclear) ids.push(...s.nuclear.orphaned_ids);
      if (s.tamper) ids.push(s.tamper.episode_id);
      onHighlightChange?.(ids);
    },
    [onHighlightChange]
  );

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch("/api/backend/chaos/state");
      if (res.ok) {
        const s = (await res.json()) as ChaosState;
        setState(s);
        applyHighlights(s);
      }
    } catch {
      // backend offline
    }
  }, [applyHighlights]);

  useEffect(() => {
    fetchState();
    const id = setInterval(fetchState, 3000);
    return () => clearInterval(id);
  }, [fetchState]);

  async function trigger(path: string, label: string) {
    setBusy(label);
    try {
      const res = await fetch(`/api/backend/chaos/${path}`, { method: "POST" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        window.alert(`Chaos ${label} failed: ${body.detail ?? res.status}`);
      }
      await fetchState();
    } catch {
      // backend offline
    }
    setBusy(null);
  }

  const tampered = !!state.tamper;
  const nuked = !!state.nuclear;

  return (
    <div
      className="absolute top-4 left-4 z-20 w-64 bg-gray-900/95 backdrop-blur
                 border border-gray-700 rounded-lg shadow-xl font-mono text-xs"
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-800">
        <span className="text-red-400 uppercase tracking-wider">Chaos Layer</span>
        <span className="text-gray-600">press live</span>
      </div>

      {/* Tamper / restore */}
      <div className="px-3 py-2 border-b border-gray-800/60">
        <button
          onClick={() => trigger(tampered ? "restore" : "tamper", tampered ? "restore" : "tamper")}
          disabled={busy !== null}
          className={`w-full rounded py-1.5 uppercase tracking-wider transition-colors
                      disabled:opacity-40 border ${
                        tampered
                          ? "border-green-600 text-green-400 hover:bg-green-900/30"
                          : "border-red-700 text-red-400 hover:bg-red-900/30"
                      }`}
        >
          {busy === "tamper" || busy === "restore"
            ? "…"
            : tampered
              ? "⟲ Restore chain"
              : "⚠ Tamper with graph"}
        </button>
        {state.tamper && (
          <div className="mt-2 text-[11px] text-red-300/90 leading-relaxed">
            Merkle broken at Episode #{state.tamper.sequence_no} (
            {state.tamper.action_type || "episode"}). Stored hash{" "}
            <span className="text-gray-500">{state.tamper.original_hash.slice(0, 8)}…</span>{" "}
            overwritten → linkage fails verification.
          </div>
        )}
      </div>

      {/* Author goes nuclear / revive */}
      <div className="px-3 py-2">
        <button
          onClick={() => trigger(nuked ? "revive" : "nuclear", nuked ? "revive" : "nuclear")}
          disabled={busy !== null}
          className={`w-full rounded py-1.5 uppercase tracking-wider transition-colors
                      disabled:opacity-40 border ${
                        nuked
                          ? "border-green-600 text-green-400 hover:bg-green-900/30"
                          : "border-amber-700 text-amber-400 hover:bg-amber-900/30"
                      }`}
        >
          {busy === "nuclear" || busy === "revive"
            ? "…"
            : nuked
              ? "⟲ Revive author"
              : "☢ Author goes nuclear"}
        </button>
        {state.nuclear && (
          <div className="mt-2 text-[11px] leading-relaxed">
            <div className="text-amber-300">
              <span className="text-gray-400">{state.nuclear.person}</span> left the company —{" "}
              <span className="text-red-400 font-bold">{state.nuclear.orphaned_count}</span> nodes
              orphaned.
            </div>
            <div className="text-gray-500 mt-0.5">
              {Object.entries(state.nuclear.by_type)
                .map(([t, c]) => `${c} ${t}`)
                .join(" · ")}
            </div>
            {state.nuclear.suggested_reviewers.length > 0 && (
              <div className="mt-1.5 pt-1.5 border-t border-gray-800/60">
                <div className="text-[10px] uppercase tracking-wider text-gray-500">
                  Suggested reviewers
                </div>
                {state.nuclear.suggested_reviewers.map((r) => (
                  <div key={r.name} className="flex justify-between text-gray-300">
                    <span className="truncate">{r.name}</span>
                    <span className="text-gray-600 ml-2">{r.activity}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
