# Status Bar Contract

> **For Lane E (Extension).** This document defines the exact behavior of the VS Code status bar item. It is authoritative — if anything here contradicts other docs, this wins for the status bar specifically.
>
> The status bar is non-negotiable. It is the live conscience of the project. Every cost-incurring action during development and demo is reflected here in real time.

---

## Why it exists

Two reasons, both important:

1. **For the demo:** judges glance at the status bar throughout the 5-minute demo and see "$3.47 / $5.00 · 14,231 nodes · Merkle ✓" — concrete, live, verifiable proof of the cost discipline claim. This is one of the headline pitches; the status bar makes it visible.

2. **For you, during the build:** every time you click "Why?" while developing, the cost ticks up live. This makes the budget psychologically real. Developers who can't see the cost burn 5–10× more than developers who can. The status bar is the live conscience.

If the status bar isn't working, the project is fundamentally broken. Treat its implementation as Tier 1 (must ship Phase 1).

---

## Display format

```
CBOS: $0.34 / $5.00 · 12,847 nodes · Merkle ✓
```

Three segments, separated by middle dots (`·`, U+00B7), in that exact order. **No exceptions.** The format is intentional:

- Cost is first because it's the most important running metric.
- Node count is second to demonstrate scale and "the graph is real."
- Merkle is third with a single visible glyph for instant binary signal.

Do not add extra segments. Do not reorder. Do not abbreviate to "$0.34/$5.00" without the space — readability matters at glance distance.

---

## States

| State | Display | When |
|---|---|---|
| Connecting (first load) | `CBOS: connecting…` | Before first `/status` response |
| Healthy | `CBOS: $0.34 / $5.00 · 12,847 nodes · Merkle ✓` | Normal operation |
| Stale (last poll failed but backend was alive recently) | `CBOS: $0.34 / $5.00 · 12,847 nodes · Merkle ✓ ?` | One poll failed; show last-known with `?` suffix |
| Backend offline (no last-known data) | `CBOS: offline` | Polling has failed continuously since extension activation |
| Budget warning | (same content, **yellow** text) | `costSpent > $3.50` |
| Budget critical | (same content, **red** text) | `costSpent > $4.50` |
| Budget exhausted | `CBOS: budget exhausted` | `costSpent >= $5.00` — extension still works, but Why calls will return cached or empty |
| Merkle broken | `CBOS: $0.34 / $5.00 · 12,847 nodes · Merkle ✗` (**red**) | `merkleOk === false` |

The Merkle-broken state always wins over cost coloring (i.e., red trumps yellow). Budget exhausted wins over Merkle.

---

## Polling

- `/status` is polled every **5 seconds**.
- On failure, retry with exponential backoff: 5s, 10s, 20s, 40s, then steady at 60s.
- On the first successful poll after a failure streak, immediately resume 5s polling.
- Polling does not block the extension's main thread — all calls are async.
- The status bar must update within 100ms of receiving a `/status` response.

---

## Tooltip (on hover)

Multi-line markdown. Click-trusted (so the dashboard link works). Updates with each poll.

```markdown
**CodebaseOS**

$0.34 spent of $5.00 budget

12,847 nodes across 1 repository

Merkle chain intact (head: `a7b2c9e1…`)

Last updated: just now

Click to open dashboard →
```

When stale, replace "Last updated: just now" with "Last updated: >5s ago (stale)".
When offline, the tooltip becomes:

```markdown
**CodebaseOS** — offline

Backend unreachable at `http://localhost:8000`.

Last successful contact: 47 seconds ago.

Click to open dashboard (will fail until backend is up)
```

---

## Click behavior

Clicking the status bar item opens the dashboard in the system browser via `vscode.env.openExternal()`. The URL is configurable in the extension settings (`codebaseos.dashboardUrl`), defaulting to `http://localhost:3000`.

Implementation: bind `statusBarItem.command` to a registered command `codebaseos.openDashboard`.

---

## Implementation

Drop this file into `extension/src/statusBar.ts`. Lane E should follow it almost verbatim during Phase 1 — adjustments only for type definitions that change in Lane B's API.

```typescript
// extension/src/statusBar.ts
import * as vscode from 'vscode';
import { CodebaseOSClient, StatusResponse } from './client';

const POLL_INTERVAL_MS = 5_000;
const BACKOFF_SEQUENCE_MS = [5_000, 10_000, 20_000, 40_000, 60_000];

export class StatusBar {
  private item: vscode.StatusBarItem;
  private timer: NodeJS.Timeout | null = null;
  private lastKnown: StatusResponse | null = null;
  private consecutiveFailures = 0;
  private isStale = false;

  constructor(
    private client: CodebaseOSClient,
    private context: vscode.ExtensionContext
  ) {
    this.item = vscode.window.createStatusBarItem(
      vscode.StatusBarAlignment.Right,
      100
    );
    this.item.command = 'codebaseos.openDashboard';
    this.item.text = 'CBOS: connecting…';
    this.item.show();

    // Register the dashboard-open command
    this.context.subscriptions.push(
      vscode.commands.registerCommand('codebaseos.openDashboard', () => {
        const url = vscode.workspace
          .getConfiguration('codebaseos')
          .get<string>('dashboardUrl', 'http://localhost:3000');
        vscode.env.openExternal(vscode.Uri.parse(url));
      })
    );

    this.context.subscriptions.push(this.item);
  }

  start(): void {
    void this.tick();
    this.scheduleNext(POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.item.dispose();
  }

  private scheduleNext(delayMs: number): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.tick(), delayMs);
  }

  private async tick(): Promise<void> {
    try {
      const status = await this.client.status();
      this.lastKnown = status;
      this.consecutiveFailures = 0;
      this.isStale = false;
      this.render(status, false);
      this.scheduleNext(POLL_INTERVAL_MS);
    } catch (err) {
      this.consecutiveFailures += 1;

      if (this.lastKnown) {
        this.isStale = true;
        this.render(this.lastKnown, true);
      } else {
        this.renderOffline();
      }

      const backoffIndex = Math.min(
        this.consecutiveFailures - 1,
        BACKOFF_SEQUENCE_MS.length - 1
      );
      this.scheduleNext(BACKOFF_SEQUENCE_MS[backoffIndex]);
    }
  }

  private render(status: StatusResponse, stale: boolean): void {
    const cost = `$${status.costSpent.toFixed(2)} / $${status.costCap.toFixed(2)}`;
    const nodes = `${status.nodeCount.toLocaleString()} nodes`;
    const merkle = status.merkleOk ? 'Merkle ✓' : 'Merkle ✗';
    const staleMarker = stale ? ' ?' : '';

    // Budget-exhausted special case
    if (status.costSpent >= status.costCap) {
      this.item.text = 'CBOS: budget exhausted';
      this.item.color = new vscode.ThemeColor('errorForeground');
    } else {
      this.item.text = `CBOS: ${cost} · ${nodes} · ${merkle}${staleMarker}`;

      // Color precedence: Merkle broken > budget critical > budget warning > normal
      if (!status.merkleOk) {
        this.item.color = new vscode.ThemeColor('errorForeground');
      } else if (status.costSpent > 4.5) {
        this.item.color = new vscode.ThemeColor('errorForeground');
      } else if (status.costSpent > 3.5) {
        this.item.color = new vscode.ThemeColor('editorWarning.foreground');
      } else {
        this.item.color = undefined;
      }
    }

    this.item.tooltip = this.buildTooltip(status, stale);
  }

  private renderOffline(): void {
    this.item.text = 'CBOS: offline';
    this.item.color = new vscode.ThemeColor('descriptionForeground');

    const md = new vscode.MarkdownString(
      `**CodebaseOS** — offline\n\n` +
        `Backend unreachable at \`${this.client.baseUrl}\`.\n\n` +
        `Consecutive failures: ${this.consecutiveFailures}\n\n` +
        `Click to open dashboard (will fail until backend is up)`
    );
    md.isTrusted = true;
    this.item.tooltip = md;
  }

  private buildTooltip(status: StatusResponse, stale: boolean): vscode.MarkdownString {
    const repoLabel = status.repoCount === 1 ? 'repository' : 'repositories';
    const merkleStatus = status.merkleOk ? 'intact' : '**BROKEN**';
    const headSnippet = status.merkleHead ? `\`${status.merkleHead.slice(0, 8)}…\`` : '`(empty)`';
    const freshness = stale ? `>5s ago (stale)` : `just now`;

    const md = new vscode.MarkdownString(
      `**CodebaseOS**\n\n` +
        `$${status.costSpent.toFixed(2)} spent of $${status.costCap.toFixed(2)} budget\n\n` +
        `${status.nodeCount.toLocaleString()} nodes across ${status.repoCount} ${repoLabel}\n\n` +
        `Merkle chain ${merkleStatus} (head: ${headSnippet})\n\n` +
        `Last updated: ${freshness}\n\n` +
        `Click to open dashboard →`
    );
    md.isTrusted = true;
    return md;
  }
}
```

---

## Client interface

`extension/src/client.ts` must export this type and method:

```typescript
// extension/src/client.ts
export interface StatusResponse {
  costSpent: number;     // dollars, e.g., 0.34
  costCap: number;       // dollars, e.g., 5.00
  nodeCount: number;     // total nodes in HydraDB
  repoCount: number;     // number of ingested repositories
  merkleOk: boolean;     // is the Merkle chain intact?
  merkleHead: string;    // hex hash of current chain head (or empty string if no episodes yet)
}

export class CodebaseOSClient {
  constructor(public readonly baseUrl: string) {}

  async status(): Promise<StatusResponse> {
    const response = await fetch(`${this.baseUrl}/status`, {
      headers: { 'Accept': 'application/json' },
      // Short timeout so polls don't pile up on a slow/dead backend
      signal: AbortSignal.timeout(2_500),
    });
    if (!response.ok) {
      throw new Error(`Status request failed: ${response.status} ${response.statusText}`);
    }
    return (await response.json()) as StatusResponse;
  }

  // ... other methods: why(), summary(), fiveWhys(), etc.
}
```

---

## Backend contract

`backend/api.py` (Lane B) must serve `GET /status` returning JSON matching the `StatusResponse` interface exactly. The reference implementation:

```python
# backend/api.py
from fastapi import FastAPI
from graph.client import HydraClient
from graph.merkle import verify_chain

app = FastAPI()
db = HydraClient.from_env()

COST_CAP_USD = 5.00

@app.get("/status")
async def status():
    cost = await db.get_total_cost()
    node_count = await db.count_all_nodes()
    repo_count = await db.count_nodes_by_type("Repository")
    merkle = await verify_chain(db)
    return {
        "costSpent": round(cost, 4),
        "costCap": COST_CAP_USD,
        "nodeCount": node_count,
        "repoCount": repo_count,
        "merkleOk": merkle.ok,
        "merkleHead": merkle.head_hash or "",
    }
```

Performance: `/status` must respond in under 200ms. If any of the underlying queries are slow, cache the result for 2 seconds (which is shorter than the 5s poll interval, so the user never sees stale data the dashboard wouldn't also show).

---

## Settings

Add to `extension/package.json` under `contributes.configuration`:

```json
{
  "contributes": {
    "configuration": {
      "title": "CodebaseOS",
      "properties": {
        "codebaseos.backendUrl": {
          "type": "string",
          "default": "http://localhost:8000",
          "description": "URL of the CodebaseOS backend API."
        },
        "codebaseos.dashboardUrl": {
          "type": "string",
          "default": "http://localhost:3000",
          "description": "URL of the CodebaseOS dashboard (opened on status bar click)."
        }
      }
    }
  }
}
```

The `StatusBar` reads `codebaseos.dashboardUrl` on every click (not cached) so the user can change it mid-session if they tunnel through ngrok during the demo.

---

## Activation

In `extension/src/extension.ts`:

```typescript
import * as vscode from 'vscode';
import { CodebaseOSClient } from './client';
import { StatusBar } from './statusBar';

export function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration('codebaseos');
  const backendUrl = config.get<string>('backendUrl', 'http://localhost:8000');

  const client = new CodebaseOSClient(backendUrl);
  const statusBar = new StatusBar(client, context);
  statusBar.start();

  // Other registrations: hover provider, code lens, commands, webview, etc.
}

export function deactivate() {
  // statusBar.stop() handled via context.subscriptions
}
```

---

## Testing checklist

Before considering the status bar done, verify:

- [ ] On extension activation, status bar shows `CBOS: connecting…` immediately (before any network calls return).
- [ ] With backend running and healthy: status bar shows the full three-segment format within 2 seconds of activation.
- [ ] Kill the backend mid-session: status bar transitions to stale state (with `?` suffix), then offline state if failures continue.
- [ ] Restart the backend: status bar transitions back to healthy within one poll cycle.
- [ ] Set `costSpent` to $3.60 in HydraDB manually: status bar text turns yellow.
- [ ] Set `costSpent` to $4.60: status bar text turns red.
- [ ] Set `costSpent` to $5.00: status bar shows `CBOS: budget exhausted`.
- [ ] Tamper with the Merkle chain in HydraDB: status bar shows `Merkle ✗` in red within 30 seconds.
- [ ] Click the status bar: opens `http://localhost:3000` in the system browser.
- [ ] Hover the status bar: tooltip renders all five lines correctly.

These ten checks are the acceptance criteria for Phase 1's status bar implementation.

---

## Things to NOT do

- ❌ Do not poll faster than every 5 seconds. The backend's `/status` endpoint is cheap but not free, and polling at 1s contributes to noise during the demo.
- ❌ Do not display the cost without the cap (e.g., "CBOS: $0.34"). The whole point is the ratio against $5.00 — that's the discipline story.
- ❌ Do not abbreviate the Merkle status to a single character without a label. "Merkle ✓" is correct; bare "✓" is ambiguous.
- ❌ Do not hide the status bar item when offline. Always visible.
- ❌ Do not throw on transient errors and crash the extension. All `tick()` errors are caught and rendered as offline/stale states.
- ❌ Do not use animated/spinning icons in the status bar. They distract from the demo.
- ❌ Do not show a notification when the budget warning thresholds are crossed. The color change is enough; notifications would spam during normal usage.
