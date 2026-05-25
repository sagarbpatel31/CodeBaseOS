"use client";

import { NODE_COLORS } from "@/lib/nodeColors";

// Plain-English labels for the node types that actually appear, in demo order.
const ITEMS: [keyof typeof NODE_COLORS, string][] = [
  ["Repository", "repository"],
  ["Commit", "commit"],
  ["File", "file"],
  ["PR", "pull request"],
  ["Issue", "issue"],
  ["Decision", "decision"],
  ["Person", "person"],
  ["Episode", "ingest step"],
];

export function Legend() {
  return (
    <div className="absolute bottom-4 right-4 z-10 bg-gray-900/85 backdrop-blur
                    border border-gray-700 rounded-lg px-3 py-2 font-mono text-[10px]">
      <div className="text-gray-500 uppercase tracking-wider mb-1.5">Legend</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1">
        {ITEMS.map(([type, label]) => (
          <div key={type} className="flex items-center gap-1.5">
            <span
              className="w-2 h-2 rounded-full shrink-0"
              style={{ background: NODE_COLORS[type] }}
            />
            <span className="text-gray-300">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
