"use client";

import { useEffect, useState } from "react";

interface Repo {
  id: string;
  name: string;
  defaultBranch?: string;
  txTime?: string;
}

export function LeftRail() {
  const [repos, setRepos] = useState<Repo[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
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
    fetchRepos();
    const id = setInterval(fetchRepos, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col overflow-hidden">
      <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 flex items-center justify-between">
        <span>Ingested Repos</span>
        {repos.length > 0 && (
          <span className="text-blue-400">{repos.length}</span>
        )}
      </div>

      {repos.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-600 text-center px-4">
            {loaded ? "No repos ingested yet." : "Loading…"}
            <br />
            Run <span className="text-purple-400">cbos ingest</span> to start.
          </p>
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto py-1 font-mono text-xs">
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
                <div className="text-gray-600 pl-3.5 mt-0.5">
                  {repo.defaultBranch}
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
