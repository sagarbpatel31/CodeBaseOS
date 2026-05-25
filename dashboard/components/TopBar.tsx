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

  const cost = status?.costSpent ?? 0;
  const cap = status?.costCap ?? 5;
  const nodes = status?.nodeCount ?? 0;
  const merkleOk = status?.merkleOk ?? true;

  return (
    <header className="flex items-center justify-between bg-gray-900 border-b border-gray-700 px-4 py-2 text-sm font-mono shrink-0">
      <div className="flex items-center gap-3">
        <span className="text-purple-400 font-bold">CodebaseOS</span>
        <span className="text-gray-600">|</span>
        <span className="text-gray-400">Observability</span>
        <SearchBar />
      </div>

      <div className="flex items-center gap-6">
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">cost</span>
          <span className="text-green-400">${cost.toFixed(4)}</span>
          <span className="text-gray-600">/</span>
          <span className="text-gray-400">${cap.toFixed(2)}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">nodes</span>
          <span className="text-blue-400">{nodes.toLocaleString()}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">merkle</span>
          <span className={merkleOk ? "text-green-400" : "text-red-400"}>
            {merkleOk ? "✓" : "✗"}
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">webhooks</span>
          <span className="text-gray-500">—</span>
        </div>

        <div className="flex items-center gap-1.5">
          <div className={`w-2 h-2 rounded-full ${connected ? "bg-green-400" : "bg-red-500"}`} />
          <span className={connected ? "text-green-400" : "text-red-400"}>
            {connected ? "live" : "offline"}
          </span>
        </div>
      </div>
    </header>
  );
}
