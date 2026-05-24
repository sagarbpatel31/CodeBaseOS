"use client";

export function RightRail() {
  return (
    <aside className="w-64 shrink-0 bg-gray-900 border-l border-gray-700 flex flex-col overflow-hidden">
      {/* Entity resolution queue */}
      <div className="flex-1 flex flex-col border-b border-gray-700 overflow-hidden">
        <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 shrink-0">
          ER Queue
        </div>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-600 text-center px-4">
            No identity ambiguities pending.
          </p>
        </div>
      </div>

      {/* Webhook firehose */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="px-3 py-2 text-xs font-mono text-gray-500 uppercase tracking-wider border-b border-gray-800 shrink-0">
          Webhook Firehose
        </div>
        <div className="flex-1 flex items-center justify-center">
          <p className="text-xs text-gray-600 text-center px-4">
            Waiting for webhook events&hellip;
          </p>
        </div>
      </div>
    </aside>
  );
}
