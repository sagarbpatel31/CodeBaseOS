# Changelog

## 0.4.0

- **Ask the codebase** — conversational, graph-grounded Q&A with clickable
  sources (also a chat panel in the dashboard).
- **Knowledge-risk files** — surface files resting on a rare contributor.
- **Provenance report** — open a shareable Markdown audit (decisions, top
  contributors, bus-factor, risk, Merkle proof).

## 0.3.0

- **Explain this file** — plain-English overview of an entire file: what it
  does, who owns it, key points and decisions.
- **What changed** — everything that touched a file/repo in a date range
  (bi-temporal), no LLM.
- **Copy as Markdown** — export a Why / Origin-story answer (with citations) to
  paste into a PR or doc.

## 0.2.1

- **First-run walkthrough**: a guided "Get started with CodebaseOS" (start
  backend → ingest this repo → ask why → explore) shown on install.

## 0.2.0

- **Zero-config**: auto-detects the repo from your git remote — works on any
  checked-out project. New **"Ingest this repo"** command (one click, no CLI).
- **Clickable citations**: Why answers and Origin-story hops link to the real
  GitHub PR / commit / issue — verifiable, not just prose.
- **Inline CodeLens**: "🧬 Why? · 📜 Origin story" above every definition.
- **Origin story** (provenance chain) and **Bus factor** commands.
- Friendlier failures: errors offer "Ingest this repo" / "Open dashboard".

## 0.1.0

- **Why is this here?** — hover any line → graph-grounded provenance.
- **Five Whys** — recursive root-cause chain (code → intent → decision).
- **Counterfactual** — reason about reversing a change.
- **Compare (with vs without HydraDB)** — graph-grounded vs plain-LLM answer.
- **Onboarding tour** — module walkthrough: key files, people, decisions.
- **Status bar** — live cost ($X.XXXX / $5.00), node count, Merkle status.
- Cost-capped LLM calls ($5 hard limit); hovering never calls the LLM.

## 0.0.1

- Initial scaffold: hover stub, status bar, backend client.
