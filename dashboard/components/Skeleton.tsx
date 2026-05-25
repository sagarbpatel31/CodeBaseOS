"use client";

// Pulsing placeholder rows so panels never flash empty before their first fetch.
export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <div className="px-3 py-2 space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="h-2 bg-gray-800 rounded w-3/4 mb-1" />
          <div className="h-2 bg-gray-800/60 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}
