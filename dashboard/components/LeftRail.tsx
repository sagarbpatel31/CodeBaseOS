"use client";

import { useEffect, useState } from "react";

interface Repo {
  id: string;
  name: string;
  defaultBranch?: string;
  txTime?: string;
}

interface Decision {
  decision_id: string;
  summary: string;
  confidence: string;
  url: string;
}

export function LeftRail() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  async function fetchRepos() {
    try {
      const res = await fetch("/api/backend/repos");
      if (res.ok) {
        const data = await res.json();
        setRepos(data.repos ?? []);
      }
    } catch {
      // backend offline — leave list empty
    }
    setLoaded(true);
  }

  async function fetchDecisions() {
    try {
      const res = await fetch("/api/backend/decisions");
      if (res.ok) setDecisions((await res.json()).decisions ?? []);
    } catch {
      /* offline */
    }
  }

  useEffect(() => {
    fetchRepos();
    fetchDecisions();
    const id = setInterval(() => {
      fetchRepos();
      fetchDecisions();
    }, 6000);
    return () => clearInterval(id);
  }, []);

  async function addRepo() {
    const repo = window.prompt("Ingest repo (owner/name):", "tokio-rs/mio");
    if (!repo || !repo.includes("/")) return;
    setIngesting(true);
    try {
      await fetch(
        `/api/backend/repos?repo=${encodeURIComponent(repo)}&commits=5&prs=3`,
        { method: "POST" }
      );
      await fetchRepos();
    } catch {
      // backend offline
    }
    setIngesting(false);
  }

  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col overflow-hidden">
      <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 flex items-center justify-between">
        <span>Ingested Repos</span>
        <div className="flex items-center gap-2">
          {repos.length > 0 && <span className="text-blue-400">{repos.length}</span>}
          <button
            onClick={addRepo}
            disabled={ingesting}
            title="Ingest a repository"
            className="text-purple-400 hover:text-purple-300 disabled:opacity-40"
          >
            {ingesting ? "…" : "+"}
          </button>
        </div>
      </div>
      <div className="px-3 py-1 text-[10px] text-gray-600 border-b border-gray-800/40">
        Repos whose history is in the graph. Click <span className="text-green-400">+</span> to add one.
      </div>

      {repos.length === 0 ? (
        <div className="px-4 py-6 text-center">
          <p className="text-xs text-gray-600">
            {loaded ? "No repos ingested yet." : "Loading…"}
            <br />
            Run <span className="text-purple-400">cbos ingest</span> to start.
          </p>
        </div>
      ) : (
        <ul className="max-h-[35%] overflow-y-auto py-1 font-mono text-xs shrink-0">
          {repos.map((repo) => (
            <li
              key={repo.id}
              className="px-3 py-2 border-b border-gray-800/60 hover:bg-gray-800/50 transition-colors"
            >
              <div className="flex items-center gap-1.5">
                <span className="text-green-400">▸</span>
                <span className="text-gray-200 truncate">{repo.name}</span>
              </div>
              {repo.defaultBranch && (
                <div className="text-gray-600 pl-3.5 mt-0.5">{repo.defaultBranch}</div>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Decisions spotlight — the headline "we mine decisions" feature. */}
      <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-y border-gray-800 flex items-center justify-between shrink-0">
        <span>Decisions</span>
        {decisions.length > 0 && <span className="text-cyan-400">{decisions.length}</span>}
      </div>
      <div className="px-3 py-1 text-[10px] text-gray-600 border-b border-gray-800/40 shrink-0">
        Architectural decisions mined from PRs.
      </div>
      <div className="flex-1 overflow-y-auto font-mono text-xs">
        {decisions.length === 0 ? (
          <p className="text-[11px] text-gray-600 px-3 py-2">
            None yet — run <span className="text-purple-400">CodebaseOS: Extract decisions</span> or{" "}
            <span className="text-purple-400">cbos</span> ingest with PRs.
          </p>
        ) : (
          <ul>
            {decisions.map((d) => (
              <li key={d.decision_id} className="px-3 py-2 border-b border-gray-800/50 hover:bg-gray-800/40">
                <div className="flex items-center gap-1.5">
                  <span className="text-cyan-400 text-[10px] uppercase">{d.decision_id}</span>
                  {d.confidence && <span className="text-gray-600 text-[10px]">{d.confidence}</span>}
                </div>
                <div className="text-gray-200 mt-0.5 leading-snug">{d.summary}</div>
                {d.url && (
                  <a href={d.url} target="_blank" rel="noreferrer" className="text-blue-300 hover:underline text-[10px]">
                    ↗ view PR
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
