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

  // Hover provider: shows symbol/file/line with stub message until backend is live
  const hoverProvider = vscode.languages.registerHoverProvider(
    { scheme: 'file' },
    {
      provideHover(document, position) {
        const wordRange = document.getWordRangeAtPosition(position);
        if (!wordRange) return undefined;
        const symbol = document.getText(wordRange);
        const file = document.fileName;
        const line = position.line + 1;
        const md = new vscode.MarkdownString(
          `**${symbol}** at \`${file}:${line}\` — backend not yet implemented`
        );
        md.isTrusted = true;
        return new vscode.Hover(md, wordRange);
      },
    }
  );
  context.subscriptions.push(hoverProvider);

  // Command: codebaseos.why — stub until Phase 2 webview is wired
  const whyCommand = vscode.commands.registerCommand('codebaseos.why', async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      void vscode.window.showInformationMessage('Open a file to use CodebaseOS: Why.');
      return;
    }
    const position = editor.selection.active;
    const wordRange = editor.document.getWordRangeAtPosition(position);
    const symbol = wordRange ? editor.document.getText(wordRange) : '(unknown)';
    const file = editor.document.fileName;
    const line = position.line + 1;

    try {
      const result = await client.why(file, line, symbol);
      void vscode.window.showInformationMessage(
        `Why: ${JSON.stringify(result).slice(0, 200)}`
      );
    } catch (_err) {
      void vscode.window.showInformationMessage(
        `**${symbol}** at \`${file}:${line}\` — backend not yet implemented`
      );
    }
  });
  context.subscriptions.push(whyCommand);

  // Stubs for other commands (Phase 4)
  context.subscriptions.push(
    vscode.commands.registerCommand('codebaseos.fiveWhys', () => {
      void vscode.window.showInformationMessage('CodebaseOS: Five Whys — coming in Phase 4');
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('codebaseos.counterfactual', () => {
      void vscode.window.showInformationMessage('CodebaseOS: Counterfactual — coming in Phase 4');
    })
  );
  context.subscriptions.push(
    vscode.commands.registerCommand('codebaseos.handoff', () => {
      void vscode.window.showInformationMessage('CodebaseOS: Handoff — coming in Phase 6');
    })
  );
}

export function deactivate(): void {
  // statusBar.stop() handled via context.subscriptions
}
