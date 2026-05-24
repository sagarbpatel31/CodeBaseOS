"use client";

export function LeftRail() {
  return (
    <aside className="w-56 shrink-0 bg-gray-900 border-r border-gray-700 flex flex-col overflow-hidden">
      <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800">
        Ingested Repos
      </div>
      <div className="flex-1 flex items-center justify-center">
        <p className="text-xs text-gray-600 text-center px-4">
          No repos ingested yet.
          <br />
          Run <span className="text-purple-400">cbos ingest</span> to start.
        </p>
      </div>
    </aside>
  );
}
