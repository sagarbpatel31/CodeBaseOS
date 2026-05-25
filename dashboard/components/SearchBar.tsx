"use client";

import { useEffect, useRef, useState } from "react";

interface SearchResult {
  id: string;
  nodeType: string;
  title: string;
  score: number;
}

const TYPE_COLOR: Record<string, string> = {
  Commit: "text-blue-400",
  PR: "text-purple-400",
  Issue: "text-amber-400",
  File: "text-green-400",
  Repository: "text-pink-400",
  Decision: "text-cyan-400",
  chunk: "text-gray-400",
};

export function SearchBar() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function run() {
    const query = q.trim();
    if (!query) return;
    setLoading(true);
    setOpen(true);
    try {
      const res = await fetch(`/api/backend/search-nl?q=${encodeURIComponent(query)}&limit=12`);
      if (res.ok) {
        const data = await res.json();
        setResults(data.results ?? []);
      }
    } catch {
      setResults([]);
    }
    setLoading(false);
  }

  return (
    <div ref={boxRef} className="relative">
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && run()}
        onFocus={() => results.length && setOpen(true)}
        placeholder="ask the graph…"
        className="w-64 bg-gray-800/70 border border-gray-700 rounded px-2 py-1
                   text-xs font-mono text-gray-200 placeholder:text-gray-600
                   focus:outline-none focus:border-purple-500"
      />

      {open && (
        <div className="absolute top-full mt-1 w-80 max-h-80 overflow-y-auto z-50
                        bg-gray-900 border border-gray-700 rounded-lg shadow-xl font-mono text-xs">
          {loading ? (
            <div className="px-3 py-3 text-gray-500">searching…</div>
          ) : results.length === 0 ? (
            <div className="px-3 py-3 text-gray-600">no matches</div>
          ) : (
            <ul>
              {results.map((r, i) => (
                <li
                  key={`${r.id}-${i}`}
                  className="px-3 py-2 border-b border-gray-800/60 hover:bg-gray-800/50"
                >
                  <div className="flex items-center gap-1.5">
                    <span className={`uppercase text-[10px] ${TYPE_COLOR[r.nodeType] ?? "text-gray-400"}`}>
                      {r.nodeType || "node"}
                    </span>
                  </div>
                  <div className="text-gray-200 truncate mt-0.5">{r.title}</div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
