"use client";

// Shown over the graph when there's no data yet — explains what CodebaseOS is
// and what to do first, so a brand-new viewer is never staring at a blank canvas.
export function EmptyState() {
  return (
    <div className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none">
      <div className="max-w-md text-center px-6 font-mono">
        <div className="text-purple-400 text-lg font-bold mb-2">CodebaseOS</div>
        <p className="text-gray-300 text-sm leading-relaxed mb-4">
          Your codebase&rsquo;s memory — every commit, PR, issue, decision and
          person, linked in one graph and verified by a Merkle chain.
        </p>
        <p className="text-gray-500 text-xs leading-relaxed">
          Nothing ingested yet. In the editor run{" "}
          <span className="text-purple-300">CodebaseOS: Ingest this repo</span>,
          or from a terminal:
        </p>
        <pre className="mt-2 text-[11px] text-green-400 bg-gray-900/70 border border-gray-700 rounded px-3 py-2 inline-block">
          cbos ingest owner/repo --prs 5 --issues 5
        </pre>
      </div>
    </div>
  );
}
