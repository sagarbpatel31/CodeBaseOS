"use client";

import { useEffect, useState } from "react";

interface ClusterMember {
  id: string;
  username: string;
  email: string;
  platform: string;
}
interface Cluster {
  person_name: string;
  primary_email: string;
  identity_ids: string[];
  members: ClusterMember[];
}
interface Pending {
  a: { person_name: string; primary_email: string };
  b: { person_name: string; primary_email: string };
  reason: string;
  confidence: string;
}
interface ERData {
  clusters: Cluster[];
  pending: Pending[];
  stats: { identities: number; people: number; auto_merged: number; pending: number };
}

interface FirehoseEvent {
  ts: number;
  kind: string;
  title: string;
  author?: string;
  state?: string;
  sha?: string;
  merkle?: string;
}

const KIND_COLOR: Record<string, string> = {
  commit: "text-blue-400",
  pr: "text-purple-400",
  issue: "text-amber-400",
  webhook: "text-gray-400",
};

export function RightRail() {
  const [er, setEr] = useState<ERData | null>(null);
  const [events, setEvents] = useState<FirehoseEvent[]>([]);
  const [firing, setFiring] = useState(false);

  useEffect(() => {
    async function fetchEr() {
      try {
        const res = await fetch("/api/backend/er-queue");
        if (res.ok) setEr(await res.json());
      } catch {
        // backend offline
      }
    }
    async function fetchEvents() {
      try {
        const res = await fetch("/api/backend/events?limit=30");
        if (res.ok) {
          const data = await res.json();
          setEvents(data.events ?? []);
        }
      } catch {
        // backend offline
      }
    }
    fetchEr();
    fetchEvents();
    const id = setInterval(() => {
      fetchEr();
      fetchEvents();
    }, 4000);
    return () => clearInterval(id);
  }, []);

  const [resolving, setResolving] = useState(false);

  async function simulate(kind: string) {
    setFiring(true);
    try {
      await fetch(`/api/backend/webhook/simulate?kind=${kind}&count=3`, { method: "POST" });
      const res = await fetch("/api/backend/events?limit=30");
      if (res.ok) setEvents((await res.json()).events ?? []);
    } catch {
      // backend offline
    }
    setFiring(false);
  }

  async function resolve() {
    setResolving(true);
    try {
      await fetch("/api/backend/resolve", { method: "POST" });
      const res = await fetch("/api/backend/er-queue");
      if (res.ok) setEr(await res.json());
    } catch {
      // backend offline
    }
    setResolving(false);
  }

  const stats = er?.stats;
  const merged = (er?.clusters ?? []).filter((c) => c.identity_ids.length > 1);
  const pending = er?.pending ?? [];

  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-l border-gray-700 flex flex-col overflow-hidden">
      {/* Entity resolution */}
      <div className="flex-1 flex flex-col border-b border-gray-700 overflow-hidden">
        <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 shrink-0 flex items-center justify-between">
          <span>Entity Resolution</span>
          <div className="flex items-center gap-2">
            {stats && (
              <span className="text-blue-400">
                {stats.identities}→{stats.people}
              </span>
            )}
            <button
              onClick={resolve}
              disabled={resolving}
              title="Persist Person nodes for merged identities"
              className="text-purple-400 hover:text-purple-300 disabled:opacity-40 normal-case"
            >
              {resolving ? "…" : "resolve"}
            </button>
          </div>
        </div>
        <div className="px-3 py-1 text-[10px] text-gray-600 border-b border-gray-800/40">
          Merging duplicate identities of the same person across repos.
        </div>

        <div className="flex-1 overflow-y-auto font-mono text-xs">
          {!er ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-gray-600">Loading&hellip;</p>
            </div>
          ) : (
            <>
              {/* Review queue */}
              <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-amber-500/80 border-b border-gray-800/60">
                Review Queue ({pending.length})
              </div>
              {pending.length === 0 ? (
                <p className="text-xs text-gray-600 px-3 py-2">
                  No ambiguities pending.
                </p>
              ) : (
                <ul>
                  {pending.map((p, i) => (
                    <li
                      key={i}
                      className="px-3 py-2 border-b border-gray-800/60 hover:bg-gray-800/40"
                    >
                      <div className="flex items-center gap-1 text-gray-200">
                        <span className="text-amber-400 truncate">{p.a.person_name}</span>
                        <span className="text-gray-600">≟</span>
                        <span className="text-amber-400 truncate">{p.b.person_name}</span>
                      </div>
                      <div className="text-gray-600 mt-0.5">{p.reason}</div>
                    </li>
                  ))}
                </ul>
              )}

              {/* Auto-merged clusters */}
              <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-green-500/80 border-b border-gray-800/60 mt-1">
                Auto-merged ({stats?.auto_merged ?? 0})
              </div>
              <ul>
                {merged.map((c) => (
                  <li
                    key={c.identity_ids[0]}
                    className="px-3 py-2 border-b border-gray-800/60 hover:bg-gray-800/40"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-gray-200 truncate">{c.person_name}</span>
                      <span className="text-green-400 shrink-0 ml-1">
                        ×{c.identity_ids.length}
                      </span>
                    </div>
                    {c.primary_email && (
                      <div className="text-gray-600 truncate">{c.primary_email}</div>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      {/* Webhook firehose */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 shrink-0 flex items-center justify-between">
          <span>Webhook Firehose</span>
          {events.length > 0 && <span className="text-blue-400">{events.length}</span>}
        </div>
        <div className="px-3 py-1 text-[10px] text-gray-600 border-b border-gray-800/40 shrink-0">
          Live ingestion — click +commit/+pr/+issue to stream new nodes in.
        </div>

        {/* Simulate triggers (demo stand-in for real GitHub webhooks) */}
        <div className="flex gap-1 px-2 py-2 border-b border-gray-800/60 shrink-0">
          {["commit", "pr", "issue"].map((k) => (
            <button
              key={k}
              onClick={() => simulate(k)}
              disabled={firing}
              className="flex-1 font-mono text-[10px] uppercase tracking-wider rounded
                         border border-gray-700 py-1 text-gray-300
                         hover:bg-gray-800/60 disabled:opacity-40 transition-colors"
            >
              +{k}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto font-mono text-xs">
          {events.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-xs text-gray-600 text-center px-4">
                {firing ? "Ingesting&hellip;" : "Waiting for webhook events&hellip;"}
              </p>
            </div>
          ) : (
            <ul>
              {events.map((e, i) => (
                <li
                  key={`${e.ts}-${i}`}
                  className="px-3 py-2 border-b border-gray-800/50 hover:bg-gray-800/40"
                >
                  <div className="flex items-center gap-1.5">
                    <span className={`uppercase text-[10px] ${KIND_COLOR[e.kind] ?? "text-gray-400"}`}>
                      {e.kind}
                    </span>
                    {e.merkle && <span className="text-gray-700">{e.merkle}</span>}
                  </div>
                  <div className="text-gray-200 truncate mt-0.5">{e.title}</div>
                  {e.author && <div className="text-gray-600">{e.author}</div>}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </aside>
  );
}
