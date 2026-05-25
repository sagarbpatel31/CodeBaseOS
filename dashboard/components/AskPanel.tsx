"use client";

import { useState } from "react";
import { Typewriter } from "@/components/Typewriter";

interface Citation {
  type: string;
  title: string;
  url: string;
}
interface Turn {
  q: string;
  answer: string;
  citations: Citation[];
}

// Conversational "ask the codebase anything" overlay — the live, unscripted
// demo moment. Plain questions → graph-grounded answers with clickable sources.
export function AskPanel() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [loading, setLoading] = useState(false);

  async function ask() {
    const query = q.trim();
    if (!query || loading) return;
    setLoading(true);
    setQ("");
    try {
      const res = await fetch(`/api/backend/ask?q=${encodeURIComponent(query)}`);
      const d = res.ok ? await res.json() : null;
      setTurns((t) => [
        ...t,
        { q: query, answer: d?.answer ?? "(no answer — is the backend up?)", citations: d?.citations ?? [] },
      ]);
    } catch {
      setTurns((t) => [...t, { q: query, answer: "(request failed)", citations: [] }]);
    }
    setLoading(false);
  }

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="absolute bottom-4 left-4 z-20 bg-purple-600/90 hover:bg-purple-500
                   text-white rounded-full px-4 py-2 font-mono text-xs shadow-lg"
      >
        ✦ Ask the codebase
      </button>

      {open && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/50"
             onClick={() => setOpen(false)}>
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-[min(560px,90%)] max-h-[80%] flex flex-col bg-gray-900 border
                       border-gray-700 rounded-xl shadow-2xl font-mono text-xs overflow-hidden"
          >
            <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
              <span className="text-purple-400 font-bold">✦ Ask the codebase</span>
              <button onClick={() => setOpen(false)} className="text-gray-500 hover:text-gray-200">✕</button>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
              {turns.length === 0 && (
                <div className="text-gray-500 leading-relaxed">
                  Ask anything about this codebase — grounded in the graph, with
                  clickable sources.
                  <div className="mt-2 space-y-1">
                    {[
                      "who works on the timer code?",
                      "why was create_dir_all changed?",
                      "what decisions shaped the scheduler?",
                    ].map((ex) => (
                      <button key={ex} onClick={() => setQ(ex)}
                              className="block text-purple-300 hover:underline">→ {ex}</button>
                    ))}
                  </div>
                </div>
              )}
              {turns.map((t, i) => (
                <div key={i}>
                  <div className="text-gray-400">› {t.q}</div>
                  <div className="text-gray-100 leading-relaxed mt-1">
                    {i === turns.length - 1 ? <Typewriter text={t.answer} /> : t.answer}
                  </div>
                  {t.citations.length > 0 && (
                    <div className="mt-1.5 flex flex-col gap-0.5">
                      {t.citations.map((c, j) => (
                        <a key={j} href={c.url} target="_blank" rel="noreferrer"
                           className="text-blue-300 hover:underline truncate">↗ {c.type}: {c.title}</a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              {loading && <div className="text-gray-500">thinking…</div>}
            </div>

            <div className="flex gap-2 px-4 py-3 border-t border-gray-800">
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && ask()}
                autoFocus
                placeholder="ask a question…"
                className="flex-1 bg-gray-800/70 border border-gray-700 rounded px-2 py-1.5
                           text-gray-200 placeholder:text-gray-600 focus:outline-none focus:border-purple-500"
              />
              <button onClick={ask} disabled={loading}
                      className="bg-purple-600 hover:bg-purple-500 disabled:opacity-40 text-white rounded px-3">
                ask
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
