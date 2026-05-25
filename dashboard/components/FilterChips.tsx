"use client";

import { NODE_COLORS } from "@/lib/nodeColors";

// Types worth toggling in the demo (in display order).
const TYPES: (keyof typeof NODE_COLORS)[] = [
  "Repository",
  "Commit",
  "File",
  "PR",
  "Issue",
  "Decision",
  "Person",
  "Episode",
];

interface FilterChipsProps {
  hidden: Set<string>;
  onToggle: (type: string) => void;
}

export function FilterChips({ hidden, onToggle }: FilterChipsProps) {
  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-10 flex flex-wrap gap-1
                    bg-gray-900/85 backdrop-blur border border-gray-700 rounded-lg px-2 py-1.5
                    font-mono text-[10px]">
      {TYPES.map((t) => {
        const off = hidden.has(t);
        return (
          <button
            key={t}
            onClick={() => onToggle(t)}
            title={off ? `Show ${t}` : `Hide ${t}`}
            className={`flex items-center gap-1 px-1.5 py-0.5 rounded transition-opacity
                        ${off ? "opacity-35" : "opacity-100"} hover:bg-gray-800/60`}
          >
            <span className="w-2 h-2 rounded-full" style={{ background: NODE_COLORS[t] }} />
            <span className="text-gray-300">{t}</span>
          </button>
        );
      })}
    </div>
  );
}
