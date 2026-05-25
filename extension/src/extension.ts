import * as vscode from 'vscode';
import { CodebaseOSClient } from './client';
import { StatusBar } from './statusBar';

let statusBar: StatusBar | undefined;

export function activate(context: vscode.ExtensionContext): void {
  const config = vscode.workspace.getConfiguration('codebaseos');
  const backendUrl = config.get<string>('backendUrl', 'http://localhost:8000');

  const client = new CodebaseOSClient(backendUrl);
  statusBar = new StatusBar(client, context);
  statusBar.start();

  // Hover provider: does NOT call the LLM (hover fires on every mouse move —
  // auto-calling /why would blow the cost cap). Instead it offers a command
  // link the user clicks to run the synthesis on demand.
  const hoverProvider = vscode.languages.registerHoverProvider(
    { scheme: 'file' },
    {
      provideHover(document, position) {
        const line = position.line + 1;
        const rel = vscode.workspace.asRelativePath(document.uri, false);
        const args = encodeURIComponent(JSON.stringify({ file: rel, line }));
        const md = new vscode.MarkdownString(
          `$(history) **CodebaseOS** — [Why does this line exist?](command:codebaseos.why?${args})\n\n` +
            `$(git-commit) [Origin story (provenance chain)](command:codebaseos.provenance?${args})\n\n` +
            `$(versions) [Compare: with vs without HydraDB](command:codebaseos.compare?${args})\n\n` +
            `\`${rel}:${line}\``
        );
        md.isTrusted = true;
        md.supportThemeIcons = true;
        return new vscode.Hover(md);
      },
    }
  );
  context.subscriptions.push(hoverProvider);

  // CodeLens: an inline "🧬 Why? · 📜 Origin" pair above each definition, so
  // provenance is one click away where developers actually work.
  const codeLensProvider = vscode.languages.registerCodeLensProvider(
    { scheme: 'file' },
    {
      provideCodeLenses(document) {
        const cfg = vscode.workspace.getConfiguration('codebaseos');
        if (!cfg.get<boolean>('enableCodeLens', true)) return [];
        const rel = vscode.workspace.asRelativePath(document.uri, false);
        // Match common definition keywords across languages.
        const defRe = /^\s*(?:pub\s+|export\s+|async\s+|public\s+|private\s+)*(?:fn|func|def|function|class|impl|struct|interface|trait|enum)\b/;
        const lenses: vscode.CodeLens[] = [];
        const max = 60; // cap to avoid clutter on huge files
        for (let i = 0; i < document.lineCount && lenses.length < max * 2; i++) {
          if (!defRe.test(document.lineAt(i).text)) continue;
          const range = new vscode.Range(i, 0, i, 0);
          const argsLine = i + 1;
          lenses.push(
            new vscode.CodeLens(range, {
              title: '🧬 Why?',
              command: 'codebaseos.why',
              arguments: [{ file: rel, line: argsLine }],
            }),
            new vscode.CodeLens(range, {
              title: '📜 Origin story',
              command: 'codebaseos.provenance',
              arguments: [{ file: rel, line: argsLine }],
            })
          );
        }
        return lenses;
      },
    }
  );
  context.subscriptions.push(codeLensProvider);

  // Command: codebaseos.why — call /why and render provenance in a webview.
  const whyCommand = vscode.commands.registerCommand(
    'codebaseos.why',
    async (arg?: { file: string; line: number }) => {
      const editor = vscode.window.activeTextEditor;
      let file = arg?.file;
      let line = arg?.line;
      if ((!file || !line) && editor) {
        file = vscode.workspace.asRelativePath(editor.document.uri, false);
        line = editor.selection.active.line + 1;
      }
      if (!file || !line) {
        void vscode.window.showInformationMessage('Open a file to use CodebaseOS: Why.');
        return;
      }

      const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `CodebaseOS: explaining ${file}:${line}…` },
        async () => {
          try {
            const result = await client.why(file!, line!, repo);
            showWhyPanel(context, result);
          } catch (err) {
            void vscode.window.showErrorMessage(
              `CodebaseOS /why failed: ${err instanceof Error ? err.message : String(err)}`
            );
          }
        }
      );
    }
  );
  context.subscriptions.push(whyCommand);

  // Command: codebaseos.provenance — the origin story (ordered, cited chain).
  const provenanceCommand = vscode.commands.registerCommand(
    'codebaseos.provenance',
    async (arg?: { file: string; line: number }) => {
      const editor = vscode.window.activeTextEditor;
      let file = arg?.file;
      let line = arg?.line;
      if ((!file || !line) && editor) {
        file = vscode.workspace.asRelativePath(editor.document.uri, false);
        line = editor.selection.active.line + 1;
      }
      if (!file || !line) {
        void vscode.window.showInformationMessage('Open a file to use CodebaseOS: Provenance.');
        return;
      }
      const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `CodebaseOS: tracing origin story for ${file}:${line}…` },
        async () => {
          try {
            const result = await client.provenance(file!, line!, repo);
            showProvenancePanel(context, result);
          } catch (err) {
            void vscode.window.showErrorMessage(
              `CodebaseOS Provenance failed: ${err instanceof Error ? err.message : String(err)}`
            );
          }
        }
      );
    }
  );
  context.subscriptions.push(provenanceCommand);

  // Command: codebaseos.busFactor — knowledge-risk ranking.
  const busFactorCommand = vscode.commands.registerCommand('codebaseos.busFactor', async () => {
    const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: 'CodebaseOS: computing bus factor…' },
      async () => {
        try {
          const r = await client.busFactor(repo);
          const top = r.contributors
            .slice(0, 8)
            .map((c) => `${c.name} (${c.commits})`)
            .join(', ');
          await vscode.window.showInformationMessage(
            `Bus factor: ${r.bus_factor} (${r.risk} risk) — ${r.unique_authors} authors, ${r.total_commits} commits. Top: ${top}`,
            { modal: false }
          );
        } catch (err) {
          void vscode.window.showErrorMessage(
            `CodebaseOS Bus-factor failed: ${err instanceof Error ? err.message : String(err)}`
          );
        }
      }
    );
  });
  context.subscriptions.push(busFactorCommand);

  // Command: codebaseos.compare — run /why (with graph) and /baseline-rag
  // (without graph) side by side to show the value of HydraDB provenance.
  const compareCommand = vscode.commands.registerCommand(
    'codebaseos.compare',
    async (arg?: { file: string; line: number }) => {
      const editor = vscode.window.activeTextEditor;
      let file = arg?.file;
      let line = arg?.line;
      if ((!file || !line) && editor) {
        file = vscode.workspace.asRelativePath(editor.document.uri, false);
        line = editor.selection.active.line + 1;
      }
      if (!file || !line) {
        void vscode.window.showInformationMessage('Open a file to use CodebaseOS: Compare.');
        return;
      }
      const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `CodebaseOS: comparing graph vs baseline for ${file}:${line}…` },
        async () => {
          try {
            const [withGraph, baseline] = await Promise.all([
              client.why(file!, line!, repo),
              client.baselineRag(file!, line!, repo),
            ]);
            showComparePanel(context, withGraph, baseline);
          } catch (err) {
            void vscode.window.showErrorMessage(
              `CodebaseOS compare failed: ${err instanceof Error ? err.message : String(err)}`
            );
          }
        }
      );
    }
  );
  context.subscriptions.push(compareCommand);

  // Command: codebaseos.fiveWhys — recursive root-cause chain.
  const fiveWhysCommand = vscode.commands.registerCommand(
    'codebaseos.fiveWhys',
    async (arg?: { file: string; line: number }) => {
      const editor = vscode.window.activeTextEditor;
      let file = arg?.file;
      let line = arg?.line;
      if ((!file || !line) && editor) {
        file = vscode.workspace.asRelativePath(editor.document.uri, false);
        line = editor.selection.active.line + 1;
      }
      if (!file || !line) {
        void vscode.window.showInformationMessage('Open a file to use CodebaseOS: Five Whys.');
        return;
      }
      const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: `CodebaseOS: tracing root cause for ${file}:${line}…` },
        async () => {
          try {
            const result = await client.fiveWhys(file!, line!, repo);
            showFiveWhysPanel(context, result);
          } catch (err) {
            void vscode.window.showErrorMessage(
              `CodebaseOS Five Whys failed: ${err instanceof Error ? err.message : String(err)}`
            );
          }
        }
      );
    }
  );
  context.subscriptions.push(fiveWhysCommand);

  // Command: codebaseos.counterfactual — "what if reversed?" reasoning.
  const counterfactualCommand = vscode.commands.registerCommand(
    'codebaseos.counterfactual',
    async () => {
      const decision = await vscode.window.showInputBox({
        prompt: 'CodebaseOS: describe the decision or change to reverse',
        placeHolder: 'e.g. reverting the create_dir_all fix that succeeds when the path exists',
      });
      if (!decision) return;
      await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: 'CodebaseOS: reasoning about counterfactual…' },
        async () => {
          try {
            const result = await client.counterfactual(decision);
            showCounterfactualPanel(context, result);
          } catch (err) {
            void vscode.window.showErrorMessage(
              `CodebaseOS Counterfactual failed: ${err instanceof Error ? err.message : String(err)}`
            );
          }
        }
      );
    }
  );
  context.subscriptions.push(counterfactualCommand);
  // Command: codebaseos.handoff — onboarding tour for a module.
  const handoffCommand = vscode.commands.registerCommand('codebaseos.handoff', async () => {
    const editor = vscode.window.activeTextEditor;
    const suggested = editor
      ? vscode.workspace.asRelativePath(editor.document.uri, false).split('/').slice(0, 3).join('/')
      : '';
    const moduleName = await vscode.window.showInputBox({
      prompt: 'CodebaseOS: module/path to generate an onboarding tour for',
      value: suggested,
      placeHolder: 'e.g. tokio/src/fs',
    });
    if (!moduleName) return;
    const repo = vscode.workspace.getConfiguration('codebaseos').get<string>('repo', '');
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `CodebaseOS: building onboarding tour for ${moduleName}…` },
      async () => {
        try {
          const result = await client.handoff(moduleName, repo);
          showHandoffPanel(context, result);
        } catch (err) {
          void vscode.window.showErrorMessage(
            `CodebaseOS Handoff failed: ${err instanceof Error ? err.message : String(err)}`
          );
        }
      }
    );
  });
  context.subscriptions.push(handoffCommand);
}

let whyPanel: vscode.WebviewPanel | undefined;

function showWhyPanel(
  context: vscode.ExtensionContext,
  result: import('./client').WhyResponse
): void {
  if (!whyPanel) {
    whyPanel = vscode.window.createWebviewPanel(
      'codebaseosWhy',
      'CodebaseOS — Why',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    whyPanel.onDidDispose(() => (whyPanel = undefined), null, context.subscriptions);
  }
  const esc = (s: string): string =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  whyPanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  .loc { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); font-size: 12px; }
  h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .08em; color: var(--vscode-descriptionForeground); margin: 18px 0 6px; }
  .explanation { font-size: 14px; line-height: 1.6; }
  .cites { display: flex; flex-direction: column; gap: 4px; }
  .cite { font-size: 12px; color: var(--vscode-textLink-foreground); text-decoration: none; }
  .cite:hover { text-decoration: underline; }
  .meta { margin-top: 22px; padding-top: 12px; border-top: 1px solid var(--vscode-panel-border); font-size: 12px; color: var(--vscode-descriptionForeground); display: flex; gap: 18px; }
  .badge { color: var(--vscode-charts-green); }
</style></head>
<body>
  <div class="loc">${esc(result.file)}:${result.line}</div>
  <h2>Why does this code exist?</h2>
  <div class="explanation">${esc(result.explanation)}</div>
  ${
    (result.citations ?? []).length
      ? `<h2>Sources</h2><div class="cites">${result.citations!
          .map((c) => `<a class="cite" href="${esc(c.url)}">${esc(c.type)}: ${esc(c.title)}</a>`)
          .join('')}</div>`
      : ''
  }
  <div class="meta">
    <span>context nodes: <span class="badge">${result.context_nodes}</span></span>
    <span>cost: <span class="badge">$${result.cost_usd.toFixed(6)}</span></span>
  </div>
</body></html>`;
  whyPanel.reveal(vscode.ViewColumn.Beside);
}

let comparePanel: vscode.WebviewPanel | undefined;

function showComparePanel(
  context: vscode.ExtensionContext,
  withGraph: import('./client').WhyResponse,
  baseline: import('./client').WhyResponse
): void {
  if (!comparePanel) {
    comparePanel = vscode.window.createWebviewPanel(
      'codebaseosCompare',
      'CodebaseOS — With vs Without HydraDB',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    comparePanel.onDidDispose(() => (comparePanel = undefined), null, context.subscriptions);
  }
  const esc = (s: string): string =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  comparePanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  .loc { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); font-size: 12px; margin-bottom: 14px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
  .card { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 14px 16px; }
  .card.graph { border-color: var(--vscode-charts-green); }
  .card.base { border-color: var(--vscode-charts-red); }
  h3 { margin: 0 0 4px; font-size: 13px; }
  .graph h3 { color: var(--vscode-charts-green); }
  .base h3 { color: var(--vscode-charts-red); }
  .sub { font-size: 11px; color: var(--vscode-descriptionForeground); margin-bottom: 10px; }
  .body { font-size: 13px; line-height: 1.55; }
  .meta { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--vscode-panel-border); font-size: 11px; color: var(--vscode-descriptionForeground); }
</style></head>
<body>
  <div class="loc">${esc(withGraph.file)}:${withGraph.line}</div>
  <div class="cols">
    <div class="card graph">
      <h3>With HydraDB</h3>
      <div class="sub">graph recall + Merkle provenance</div>
      <div class="body">${esc(withGraph.explanation)}</div>
      <div class="meta">context nodes: ${withGraph.context_nodes} · cost: $${withGraph.cost_usd.toFixed(6)}</div>
    </div>
    <div class="card base">
      <h3>Without HydraDB</h3>
      <div class="sub">plain LLM, no graph, no provenance</div>
      <div class="body">${esc(baseline.explanation)}</div>
      <div class="meta">context nodes: ${baseline.context_nodes} · cost: $${baseline.cost_usd.toFixed(6)}</div>
    </div>
  </div>
</body></html>`;
  comparePanel.reveal(vscode.ViewColumn.Beside);
}

const _esc = (s: string): string =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

let fiveWhysPanel: vscode.WebviewPanel | undefined;

function showFiveWhysPanel(
  context: vscode.ExtensionContext,
  result: import('./client').FiveWhysResponse
): void {
  if (!fiveWhysPanel) {
    fiveWhysPanel = vscode.window.createWebviewPanel(
      'codebaseosFiveWhys',
      'CodebaseOS — Five Whys',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    fiveWhysPanel.onDidDispose(() => (fiveWhysPanel = undefined), null, context.subscriptions);
  }
  const steps = result.chain
    .map(
      (s) => `
      <div class="step">
        <div class="num">${s.level}</div>
        <div class="qa">
          <div class="q">${_esc(s.question)}</div>
          <div class="a">${_esc(s.answer)}</div>
        </div>
      </div>`
    )
    .join('');
  fiveWhysPanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  .loc { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); font-size: 12px; }
  h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .08em; color: var(--vscode-descriptionForeground); margin: 16px 0 12px; }
  .step { display: flex; gap: 12px; margin-bottom: 14px; }
  .num { flex: 0 0 26px; height: 26px; border-radius: 50%; background: var(--vscode-badge-background); color: var(--vscode-badge-foreground); display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; }
  .qa { border-left: 2px solid var(--vscode-panel-border); padding-left: 12px; }
  .q { font-weight: 600; font-size: 13px; margin-bottom: 3px; }
  .a { font-size: 13px; line-height: 1.5; color: var(--vscode-descriptionForeground); }
  .meta { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--vscode-panel-border); font-size: 11px; color: var(--vscode-descriptionForeground); }
</style></head>
<body>
  <div class="loc">${_esc(result.file)}:${result.line}</div>
  <h2>5 Whys — root cause</h2>
  ${steps || '<p>No causal chain returned.</p>'}
  <div class="meta">context nodes: ${result.context_nodes} · cost: $${result.cost_usd.toFixed(6)}</div>
</body></html>`;
  fiveWhysPanel.reveal(vscode.ViewColumn.Beside);
}

let counterfactualPanel: vscode.WebviewPanel | undefined;

function showCounterfactualPanel(
  context: vscode.ExtensionContext,
  result: import('./client').CounterfactualResponse
): void {
  if (!counterfactualPanel) {
    counterfactualPanel = vscode.window.createWebviewPanel(
      'codebaseosCounterfactual',
      'CodebaseOS — Counterfactual',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    counterfactualPanel.onDidDispose(() => (counterfactualPanel = undefined), null, context.subscriptions);
  }
  counterfactualPanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  h2 { font-size: 14px; text-transform: uppercase; letter-spacing: .08em; color: var(--vscode-descriptionForeground); margin: 0 0 6px; }
  .decision { font-size: 13px; font-style: italic; color: var(--vscode-textLink-foreground); margin-bottom: 14px; }
  .analysis { font-size: 14px; line-height: 1.6; }
  .meta { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--vscode-panel-border); font-size: 11px; color: var(--vscode-descriptionForeground); }
</style></head>
<body>
  <h2>Counterfactual — what if reversed?</h2>
  <div class="decision">“${_esc(result.decision)}”</div>
  <div class="analysis">${_esc(result.analysis)}</div>
  <div class="meta">context nodes: ${result.context_nodes} · cost: $${result.cost_usd.toFixed(6)}</div>
</body></html>`;
  counterfactualPanel.reveal(vscode.ViewColumn.Beside);
}

let handoffPanel: vscode.WebviewPanel | undefined;

function showHandoffPanel(
  context: vscode.ExtensionContext,
  r: import('./client').HandoffResponse
): void {
  if (!handoffPanel) {
    handoffPanel = vscode.window.createWebviewPanel(
      'codebaseosHandoff',
      'CodebaseOS — Onboarding Tour',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    handoffPanel.onDidDispose(() => (handoffPanel = undefined), null, context.subscriptions);
  }
  const list = (items: string[]): string =>
    items.length ? `<ul>${items.map((x) => `<li>${_esc(x)}</li>`).join('')}</ul>` : '<p class="empty">—</p>';
  handoffPanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  .mod { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); font-size: 13px; margin-bottom: 12px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--vscode-descriptionForeground); margin: 18px 0 6px; }
  .overview { font-size: 14px; line-height: 1.6; }
  .start { font-size: 13px; line-height: 1.55; border-left: 2px solid var(--vscode-charts-green); padding-left: 10px; }
  ul { margin: 4px 0; padding-left: 18px; }
  li { font-size: 13px; line-height: 1.5; margin-bottom: 3px; }
  .empty { color: var(--vscode-descriptionForeground); }
  .meta { margin-top: 20px; padding-top: 12px; border-top: 1px solid var(--vscode-panel-border); font-size: 11px; color: var(--vscode-descriptionForeground); }
</style></head>
<body>
  <div class="mod">📍 ${_esc(r.module)}</div>
  <div class="overview">${_esc(r.overview)}</div>
  <h2>Start here</h2>
  <div class="start">${_esc(r.start_here)}</div>
  <h2>Key files</h2>${list(r.key_files)}
  <h2>Key people</h2>${list(r.key_people)}
  <h2>Key decisions</h2>${list(r.key_decisions)}
  <div class="meta">context nodes: ${r.context_nodes} · cost: $${r.cost_usd.toFixed(6)}</div>
</body></html>`;
  handoffPanel.reveal(vscode.ViewColumn.Beside);
}

let provenancePanel: vscode.WebviewPanel | undefined;

function showProvenancePanel(
  context: vscode.ExtensionContext,
  r: import('./client').ProvenanceResponse
): void {
  if (!provenancePanel) {
    provenancePanel = vscode.window.createWebviewPanel(
      'codebaseosProvenance',
      'CodebaseOS — Origin Story',
      vscode.ViewColumn.Beside,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    provenancePanel.onDidDispose(() => (provenancePanel = undefined), null, context.subscriptions);
  }
  const color: Record<string, string> = {
    Commit: 'var(--vscode-charts-blue)',
    PR: 'var(--vscode-charts-purple)',
    Issue: 'var(--vscode-charts-yellow)',
    Decision: 'var(--vscode-charts-green)',
    Person: 'var(--vscode-charts-red)',
    File: 'var(--vscode-charts-green)',
  };
  const hops = r.chain
    .map(
      (h) => `
      <li class="hop">
        <span class="dot" style="background:${color[h.type] ?? 'var(--vscode-descriptionForeground)'}"></span>
        <div>
          <span class="badge" style="color:${color[h.type] ?? 'inherit'}">${_esc(h.type)}</span>
          ${h.when ? `<span class="when">${_esc(h.when)}</span>` : ''}
          <div class="title">${
            h.url ? `<a class="hoplink" href="${_esc(h.url)}">${_esc(h.title)} ↗</a>` : _esc(h.title)
          }</div>
          ${h.detail ? `<div class="detail">${_esc(h.detail)}</div>` : ''}
        </div>
      </li>`
    )
    .join('');
  const edges = r.verified_edges
    .map((e) => `<li>✓ ${_esc(e.context)} <span class="conf">(${e.confidence})</span></li>`)
    .join('');
  provenancePanel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8" />
<style>
  body { font-family: var(--vscode-font-family); padding: 16px 20px; color: var(--vscode-foreground); }
  .loc { font-family: var(--vscode-editor-font-family); color: var(--vscode-textLink-foreground); font-size: 12px; margin-bottom: 12px; }
  h2 { font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: var(--vscode-descriptionForeground); margin: 18px 0 8px; }
  ul { list-style: none; padding: 0; margin: 0; }
  .hop { display: flex; gap: 10px; padding: 6px 0; border-left: 1px solid var(--vscode-panel-border); margin-left: 5px; padding-left: 14px; position: relative; }
  .dot { position: absolute; left: -5px; top: 11px; width: 10px; height: 10px; border-radius: 50%; }
  .badge { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
  .when { font-size: 11px; color: var(--vscode-descriptionForeground); margin-left: 6px; }
  .title { font-size: 13px; margin-top: 2px; }
  .hoplink { color: var(--vscode-textLink-foreground); text-decoration: none; }
  .hoplink:hover { text-decoration: underline; }
  .detail { font-size: 12px; color: var(--vscode-descriptionForeground); }
  .verified li { font-size: 12px; color: var(--vscode-charts-green); margin: 2px 0; }
  .conf { color: var(--vscode-descriptionForeground); }
  .meta { margin-top: 18px; padding-top: 12px; border-top: 1px solid var(--vscode-panel-border); font-size: 11px; color: var(--vscode-descriptionForeground); }
</style></head>
<body>
  <div class="loc">${_esc(r.file)}:${r.line}</div>
  <h2>Origin story</h2>
  <ul>${hops || '<li class="detail">No chain reconstructed.</li>'}</ul>
  ${edges ? `<h2>Verified graph edges</h2><ul class="verified">${edges}</ul>` : ''}
  <div class="meta">${r.context_nodes} context nodes · cost: $${r.cost_usd.toFixed(6)}</div>
</body></html>`;
  provenancePanel.reveal(vscode.ViewColumn.Beside);
}

export function deactivate(): void {
  // statusBar.stop() handled via context.subscriptions
}
