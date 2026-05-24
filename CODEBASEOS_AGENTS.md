# CodebaseOS — Working Agreement with Claude Code

> Read this **every session**. Then read `CODEBASEOS_SPEC.md` for design context.
> If anything in this file contradicts the spec, this file wins (it's more current).

---

## Project in one paragraph

CodebaseOS is a VS Code extension backed by a bi-temporal HydraDB graph that ingests a repository's full history (commits, PRs, issues, reviews, Slack threads), performs multi-source entity resolution across platform identities, extracts decisions from PR discussions, maintains a cryptographic Merkle chain over its construction history, and answers "why is this code here?" in 200ms by traversing 14+ hops of provenance and synthesizing the result with GPT-5.4 Mini. Built solo + Claude Code in 48 hours for the HydraDB "Agents Under Pressure" hackathon. Total inference budget: **under $5**.

---

## Repo layout

```
/extension       TypeScript — VS Code extension (hover, code lens, webview, status bar)
/backend         Python 3.12 asyncio — FastAPI query API + ingestion + webhooks
/graph           HydraDB client, schema models, bi-temporal helpers, Merkle chain
/ingester        GitHub / git / Slack / Linear ingestion sources
/resolver        Multi-source entity resolution (deterministic + heuristic + LLM-assist)
/synthesizer     GPT-5.4 Mini wrapper — the ONLY OpenAI caller
/cli             `cbos decide`, `cbos ingest`, `cbos verify`, `cbos cost`
/dashboard       Next.js 15 + Tailwind — observability + demo theater
/provenance      OSS spinoff (extracted from /ingester + /graph + /synthesizer toward end)
/scripts         Helper scripts (demo cold start, chaos, fixtures, fake webhooks)
CODEBASEOS_SPEC.md  The full spec
AGENTS.md           This file
KICKOFF.md          Phase-by-phase bootstrap prompts
STATUS.md           Running log: phase, lane commits, cross-lane changes, cost, integrity
README.md           Public-facing pitch + GIF + install instructions
```

---

## INVARIANTS — Do not break these

1. **Every node has both `tx_time` and `valid_time`.** Never write a node without both. This is the bi-temporal contract.
2. **Episodes are append-only.** Never UPDATE or DELETE an Episode row.
3. **Decisions are immutable.** To change a decision, create a new Decision node with a `supersedes` edge to the prior one.
4. **Every Episode extends the Merkle chain.** No exceptions.
5. **Author fields are `Person` references, never raw username strings.** Usernames live on `Identity` nodes linked to People via `has_identity`. Single point of identity truth.
6. **Symbol ABI changes require a new Symbol node + a `supersedes` edge.** Old version stays with `valid_time_end` set.
7. **Every File node must trace to at least one Commit via `produced`.** Constraint engine enforces this.
8. **All OpenAI calls go through `synthesizer/synthesizer.py`.** That module enforces input truncation, output limits, caching, and cost logging. Never call OpenAI directly from anywhere else.
9. **Extension and backend run independently.** The extension must handle "backend offline" gracefully.
10. **HydraDB is the source of truth.** Caches are local and ephemeral; HydraDB is canonical.
11. **All Decisions made by humans go through `cbos decide`.** Including yours. No silent design changes.
12. **The build stays green on `main`.** All work-in-progress goes on `wip/<lane>-<topic>` branches.
13. **Entity resolution writes a `ResolutionDecision` Episode for every merge.** Tamper-evident.

---

## Cost discipline (HARD)

This is a **$5 inference-budget project**. Every LLM call counts.

- OpenAI console: spend cap set to **$5 hard**. If hit, the project fails closed.
- All synthesizer calls log to HydraDB as `CostEvent` nodes. Status bar in VS Code + dashboard top bar both show running total.
- Per-call budget: max **$0.05**. Anything larger requires `--expensive` flag and a comment.
- Input truncation: **≤4K tokens** sent to the model.
- Output cap: **500 tokens**.
- Caching: `(template_name, cache_key)` → response. Repeat clicks must be free.
- **Forbidden models:** Opus, GPT-5.5, GPT-5.4 Pro, any reasoning-tier model. Mini only.
- **Forbidden patterns:** background loops calling LLMs, agentic loops, re-summarization on every webhook, embedding entire source tree.
- **Entity resolution LLM tie-break is capped at 100 cases per repo.** Hard cap, not a guideline.
- **Decision extraction is on-demand only.** Triggered when a query touches a PR, not on every ingest.

If you find yourself writing code that loops over nodes calling the LLM, stop. The graph is the cognition; the LLM is the messenger.

---

## Make commands

```
make setup           Install deps, set up venv, install extension dev deps
make hydradb-test    Verify HydraDB connection + schema migrations
make backend         Start the FastAPI backend (foreground)
make ingest REPO=…   Ingest a repo by URL/path
make webhooks        Start ngrok tunnel + webhook receiver
make extension-dev   Launch VS Code with the extension loaded
make extension-pack  Package the .vsix for publishing
make dash            Start the dashboard dev server
make demo-cold       Clean DB, start everything, ingest Tokio
make break           Run the chaos test suite
make verify          Walk the Merkle chain end-to-end
make cost            Print current OpenAI spend
make publish         Publish extension to VS Code Marketplace (run only at hour 42+)
make submit          Generate final submission bundle
```

---

## Style

- **TypeScript:** strict mode. No `any`. ESLint + Prettier. VS Code API typed precisely.
- **Python:** `ruff` for lint/format. Full type hints. `asyncio` for all I/O. No bare `except:`.
- **Commits:** `<lane>/<area>: <verb> <object>` — examples:
  - `backend/ingester: paginate GitHub PRs via GraphQL`
  - `graph/merkle: chain extension + verification`
  - `extension/hover: render summary markdown with PR links`
  - `resolver/heuristic: activity-window correlation`
  - `synthesizer/cost: enforce per-call cap`

---

## Decision-making protocol

When you encounter a design question not answered by `CODEBASEOS_SPEC.md`:

1. Use the CLI: `cbos decide "<summary>" --rationale "<why>" --supersedes <prior_id_or_none> --actor "claude-code:<lane>"`
2. The CLI writes the Decision to HydraDB; Merkle chain extends automatically.
3. Continue with code that references the Decision ID in comments.

The graph captures *every* design decision. This is what makes "we know why every line is here" honest — including for our own code.

---

## Entity resolution rules — the moat

Entity resolution is the hardest part of the project and the biggest moat. Get it right.

- **Three-tier pipeline:** deterministic → heuristic → LLM-assisted. In that order, with budgets.
- **Deterministic** is free and exact: same email across platforms; GitHub-Slack OAuth linkage; commit author exactly matches PR author of a merged PR.
- **Heuristic** is free and confidence-scored: fuzzy name + activity-window correlation (within 15 minutes) + organization signal.
- **LLM-assisted** is bounded to 100 calls per repo. Used only when heuristic is ambiguous.
- **Manual review queue** in the dashboard for cases neither tier resolved. Human approves a merge → Identity gets `has_identity` edge to Person → ResolutionDecision Episode written.
- **Once resolved, always resolved.** Never re-run resolution against an already-resolved Identity unless the merge is explicitly reverted with a superseding ResolutionDecision.

---

## Parallel sessions

Solo + Claude Code = parallelism via `git worktree`.

```bash
git worktree add ../codebaseos-backend    wip/backend
git worktree add ../codebaseos-extension  wip/extension
git worktree add ../codebaseos-dash       wip/dashboard
```

**Lane boundaries:**
- **Lane B (Backend + Graph + Ingestion + Resolver + Synthesizer):** `/backend`, `/graph`, `/ingester`, `/resolver`, `/synthesizer`, `/cli`
- **Lane E (Extension):** `/extension`
- **Lane D (Dashboard):** `/dashboard`

Cross-lane changes (schema, API contracts, synthesizer prompts) require updating `STATUS.md` "Cross-lane changes pending" before resuming dependent sessions.

---

## What to do when stuck

1. **Build error you can't crack in 20 minutes?** Commit broken state on a `wip/` branch, write a Decision node via `cbos decide`, switch lanes.
2. **HydraDB API surprising you?** Append findings to `docs/hydradb-notes.md`.
3. **Spec ambiguous?** Pick simpler, `cbos decide`, move on.
4. **Tempted to add an LLM-powered feature outside the spec?** Add it to `STRETCH.md`. The graph is the cognition.
5. **Cost climbing fast?** Check the status bar / dashboard total. If past $2 before hour 30, an LLM is being called in a loop. Find it now.
6. **Entity resolution returning bad merges?** Lower the heuristic confidence threshold; route more to manual review. Bad merges destroy trust.

---

## Hard rules for the final 6 hours

- Hour 42–46: polish, demo rehearsal, video recording, Marketplace publish. **No new features.**
- Hour 46–48: submit, sleep, show up rested.
- If something is broken at hour 42, it ships broken, feature-flagged off, or with a safe-demo path. Do not "just fix one thing."
- **Backup video by hour 44. Non-negotiable.**
- **Marketplace publish at hour 42–43.** Approval can take 30 minutes to several hours. Submit early.

---

## Status bar (always visible while building)

The VS Code status bar shows three things at all times:

> **CBOS: $X.XX / $5.00** · **N nodes** · **Merkle ✓**

If `$X.XX` is climbing fast or `Merkle ✗`, stop new features and investigate.
