"use client";

import type { TimeRange } from "@/hooks/useGraphData";

interface TimeSliderProps {
  timeRange: TimeRange;
  asOf: string | null;
  onChange: (asOf: string | null) => void;
  nodeCount: number;
}

function fmt(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

export function TimeSlider({ timeRange, asOf, onChange, nodeCount }: TimeSliderProps) {
  const minMs = timeRange.min ? new Date(timeRange.min).getTime() : 0;
  const maxMs = timeRange.max ? new Date(timeRange.max).getTime() : 0;
  const hasRange = maxMs > minMs;

  const current = asOf ? new Date(asOf).getTime() : maxMs;

  function handleSlide(e: React.ChangeEvent<HTMLInputElement>) {
    const ms = Number(e.target.value);
    // Sliding to the far right re-enters live mode.
    if (ms >= maxMs) {
      onChange(null);
    } else {
      onChange(new Date(ms).toISOString());
    }
  }

  return (
    <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 w-[min(640px,80%)]
                    bg-gray-900/90 backdrop-blur border border-gray-700 rounded-lg
                    px-4 py-3 font-mono text-xs shadow-xl">
      <div className="flex items-center justify-between mb-2">
        <span className="text-gray-500 uppercase tracking-wider">Time Travel</span>
        <span className={asOf ? "text-amber-400" : "text-green-400"}>
          {asOf ? `as of ${fmt(asOf)}` : "● live (now)"}
        </span>
      </div>

      <input
        type="range"
        min={minMs}
        max={maxMs}
        step={Math.max(1, Math.floor((maxMs - minMs) / 500))}
        value={current}
        onChange={handleSlide}
        disabled={!hasRange}
        className="w-full accent-amber-400 cursor-pointer"
      />

      <div className="flex items-center justify-between mt-1.5 text-gray-600">
        <span>{fmt(timeRange.min)}</span>
        <span className="text-blue-400">{nodeCount.toLocaleString()} nodes</span>
        <span>{fmt(timeRange.max)}</span>
      </div>

      {asOf && (
        <button
          onClick={() => onChange(null)}
          className="mt-2 w-full text-center text-green-400 hover:text-green-300
                     border border-gray-700 rounded py-1 transition-colors"
        >
          ⟲ Return to live
        </button>
      )}
    </div>
  );
}
