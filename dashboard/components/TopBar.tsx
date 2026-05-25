"use client";

import { useEffect, useState } from "react";
import { SearchBar } from "@/components/SearchBar";

interface StatusData {
  costSpent: number;
  costCap: number;
  nodeCount: number;
  repoCount: number;
  merkleOk: boolean;
  merkleHead: string;
}

export function TopBar() {
  const [status, setStatus] = useState<StatusData | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const res = await fetch("/api/backend/status");
        if (res.ok) {
          setStatus(await res.json());
          setConnected(true);
        } else {
          setConnected(false);
        }
      } catch {
        setConnected(false);
      }
    }
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, []);

  const nodes = status?.nodeCount ?? 0;
  const merkleOk = status?.merkleOk ?? true;

  return (
    <header className="flex items-center justify-between bg-gray-900 border-b border-gray-700 px-4 py-2 text-sm font-mono shrink-0">
      <div className="flex items-center gap-3">
        <span className="text-purple-400 font-bold">CodebaseOS</span>
        <span className="text-gray-600">|</span>
        <span className="text-gray-400 hidden md:inline" title="Every commit, PR, issue, decision and person — graph-linked and Merkle-verified. Ask why any code exists.">
          codebase memory
        </span>
        <SearchBar />
      </div>

      <div className="flex items-center gap-5">
        {/* Cost is tracked + hard-capped in the backend (and shown in the VS Code
            status bar); intentionally not surfaced on the dashboard. */}
        <div className="flex items-center gap-1.5" title="Total nodes in the knowledge graph (commits, files, PRs, people, decisions…).">
          <span className="text-gray-500">nodes</span>
          <span className="text-blue-400">{nodes.toLocaleString()}</span>
        </div>

        <div className="flex items-center gap-1.5" title="Merkle chain integrity. ✓ = history is tamper-proof; ✗ = a node was altered.">
          <span className="text-gray-500">merkle</span>
          <span className={merkleOk ? "text-green-400" : "text-red-400"}>
            {merkleOk ? "✓ verified" : "✗ broken"}
          </span>
        </div>

        <div className="flex items-center gap-1.5" title="Backend connection status.">
          <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-red-500"}`} />
          <span className={connected ? "text-green-400" : "text-red-400"}>
            {connected ? "live" : "offline"}
          </span>
        </div>
      </div>
    </header>
  );
}
