"use client";

interface TopBarProps {
  nodeCount: number;
  connected: boolean;
}

export function TopBar({ nodeCount, connected }: TopBarProps) {
  return (
    <header className="flex items-center justify-between bg-gray-900 border-b border-gray-700 px-4 py-2 text-sm font-mono shrink-0">
      <div className="flex items-center gap-2">
        <span className="text-purple-400 font-bold">CodebaseOS</span>
        <span className="text-gray-600">|</span>
        <span className="text-gray-400">Observability</span>
      </div>

      <div className="flex items-center gap-6">
        {/* Cost meter */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">cost</span>
          <span className="text-green-400">$0.00</span>
          <span className="text-gray-600">/</span>
          <span className="text-gray-400">$5.00</span>
        </div>

        {/* Node count */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">nodes</span>
          <span className="text-blue-400">{nodeCount}</span>
        </div>

        {/* Merkle integrity */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">merkle</span>
          <span className="text-green-400">✓</span>
        </div>

        {/* Webhook health */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-500">webhooks</span>
          <span className="text-gray-500">—</span>
        </div>

        {/* WS connection dot */}
        <div className="flex items-center gap-1.5">
          <div
            className={`w-2 h-2 rounded-full ${
              connected ? "bg-green-400" : "bg-red-500"
            }`}
          />
          <span className={connected ? "text-green-400" : "text-red-400"}>
            {connected ? "live" : "disconnected"}
          </span>
        </div>
      </div>
    </header>
  );
}
