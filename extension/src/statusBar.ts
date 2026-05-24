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

    this.context.subscriptions.push(
      vscode.commands.registerCommand('codebaseos.openDashboard', () => {
        const url = vscode.workspace
          .getConfiguration('codebaseos')
          .get<string>('dashboardUrl', 'http://localhost:3000');
        void vscode.env.openExternal(vscode.Uri.parse(url));
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
    } catch (_err) {
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

    if (status.costSpent >= status.costCap) {
      this.item.text = 'CBOS: budget exhausted';
      this.item.color = new vscode.ThemeColor('errorForeground');
    } else {
      this.item.text = `CBOS: ${cost} · ${nodes} · ${merkle}${staleMarker}`;

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
    const headSnippet = status.merkleHead
      ? `\`${status.merkleHead.slice(0, 8)}…\``
      : '`(empty)`';
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
