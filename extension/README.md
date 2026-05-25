# CodebaseOS

**Right-click any line. Ask why. Get the real answer.**

CodebaseOS turns your repository's history into a queryable knowledge graph
(commits, PRs, issues, reviews, files, people, decisions) backed by HydraDB +
a Merkle-verified provenance chain — then answers questions about *why* your
code exists, grounded in that graph.

## Features

- **Why is this here?** — hover any line → synthesized provenance from the
  commits, PRs, and decisions that shaped it.
- **Five Whys** — recursive root-cause chain from code → intent → decision.
- **Counterfactual** — "what would happen if this change were reversed?"
- **Compare (with vs without HydraDB)** — side-by-side of a graph-grounded
  answer vs a plain LLM with no provenance.
- **Onboarding tour** — generate a module walkthrough: key files, people,
  decisions, and where to start.
- **Status bar** — live cost (`$X.XXXX / $5.00`), node count, Merkle status.

All synthesis runs through a single cost-capped path ($5 hard limit); hovering
never triggers an LLM call.

## Commands

| Command | What it does |
|---|---|
| `CodebaseOS: Why is this here?` | Provenance for the current line |
| `CodebaseOS: Five Whys` | Recursive root-cause analysis |
| `CodebaseOS: Counterfactual` | Reason about reversing a decision |
| `CodebaseOS: Compare (with vs without HydraDB)` | Graph vs plain-LLM answer |
| `CodebaseOS: Generate onboarding tour for current module` | Module tour |
| `CodebaseOS: Open Dashboard` | Open the live graph dashboard |

## Settings

| Setting | Default | Description |
|---|---|---|
| `codebaseos.backendUrl` | `http://localhost:8000` | CodebaseOS backend API |
| `codebaseos.dashboardUrl` | `http://localhost:3000` | Dashboard URL |
| `codebaseos.repo` | `` | `owner/name` to scope provenance queries |
| `codebaseos.enableCodeLens` | `true` | Show "🧬 Why?" code lens |

## Requirements

A running CodebaseOS backend (`backendUrl`). The extension degrades gracefully
when the backend is offline.
