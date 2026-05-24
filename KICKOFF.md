# CodebaseOS — Kickoff & Phase Prompts

This is the operator's handbook. Use it in order.

---

## Pre-flight (do these manually, ~45 minutes, before touching Claude Code)

1. **HydraDB:** sign up, generate API key. `.env`: `HYDRADB_API_KEY=...`, `HYDRADB_ENDPOINT=...`. **Check Discord for hackathon credits — ask if not visible.**
2. **OpenAI:** generate API key. `.env`: `OPENAI_API_KEY=...`. In the console, **set a hard spend cap of $5**.
3. **GitHub:** generate a personal access token with `repo:read` and `read:org` scopes. `.env`: `GITHUB_TOKEN=...`. Pick the demo repo you'll ingest (recommended: `tokio-rs/tokio`).
4. **VS Code Marketplace:** create a publisher account at https://marketplace.visualstudio.com/manage. You'll publish from this in Phase 5. (Process takes ~10 minutes once, account creation can have approval delay — start early.)
5. **ngrok:** install + auth (free tier is fine). You'll need it for the webhook demo.
6. **Slack (optional):** if you want the Slack ingestion source, create a workspace + bot, give it `channels:history` scope. **Skip if low on time.**
7. **Repo:**
   ```bash
   mkdir codebaseos && cd codebaseos
   git init && git checkout -b main
   ```
8. **Put four files at repo root:**
   - `CODEBASEOS_SPEC.md`
   - `AGENTS.md`
   - `KICKOFF.md` (this file)
   - `STATUS.md` (template at bottom of this file)
9. `git add . && git commit -m "init: spec + conventions"`
10. **Worktrees:**
    ```bash
    git branch wip/backend    && git worktree add ../codebaseos-backend    wip/backend
    git branch wip/extension  && git worktree add ../codebaseos-extension  wip/extension
    git branch wip/dashboard  && git worktree add ../codebaseos-dash       wip/dashboard
    ```
11. **Three terminals, one per worktree, title them B / E / D.**

---

## Every session starts with this prompt

> Read `AGENTS.md` and `CODEBASEOS_SPEC.md` in full before doing anything. Confirm you understand the invariants in AGENTS.md §INVARIANTS by listing them back, especially the cost discipline section. Then read `STATUS.md` for current state.

Then paste the phase prompt for the current phase + lane.

---

## Phase 0 — Setup (hour 0 to hour 1)

**Single session in main worktree.**

> Set up the CodebaseOS project skeleton per AGENTS.md §"Repo layout". Create:
>
> - All directories with stub READMEs
> - `STATUS.md` per template at bottom of KICKOFF.md
> - `STRETCH.md` empty
> - `docs/hydradb-notes.md` empty
> - `Makefile` with targets from AGENTS.md §"Make commands", all stubbed to print "TODO: implement"
> - `.env.example` with: `HYDRADB_API_KEY`, `HYDRADB_ENDPOINT`, `OPENAI_API_KEY`, `GITHUB_TOKEN`, `SLACK_BOT_TOKEN` (optional)
> - `pyproject.toml` for backend (Python 3.12; deps: fastapi, uvicorn, asyncio, pydantic, httpx, openai, tree-sitter, tree-sitter-rust, tree-sitter-python, tree-sitter-typescript, gitpython, click, ruff)
> - `extension/package.json` per VS Code extension scaffold (TypeScript strict, target node 18, vsce as devDependency)
> - `dashboard/package.json` (Next.js 15, Tailwind, react-force-graph-2d, framer-motion, ws)
> - `.gitignore` for Python, Node, .env, .vsix, target/
>
> Commit as `init: project skeleton`. Do not implement logic yet.

Merge to main when done.

---

## Phase 1 — Spikes (hour 1 to hour 3) — RUN IN PARALLEL, LANE B FIRST

### Lane B (Backend) — START THIS ONE FIRST

> Working in Lane B: `/backend`, `/graph`, `/ingester`, `/resolver`, `/synthesizer`, `/cli`.
>
> Read AGENTS.md and CODEBASEOS_SPEC.md §§4–6.
>
> **Phase 1 goal: HydraDB bi-temporal schema works; Merkle chain works; ingest one commit end-to-end.**
>
> Implement:
> 1. `graph/client.py` — HydraDB connection class wrapping their SDK, env-driven config
> 2. `graph/schema.py` — Pydantic models for every node type in CODEBASEOS_SPEC §5.2, every node having `tx_time`, `valid_time`, `valid_time_end`, `source`, `episode_id`, `merkle_hash`
> 3. `graph/merkle.py` — Merkle chain extension + verification (sha256 over canonical JSON, `merkle_next` edges)
> 4. `graph/bitemporal.py` — helpers to write a node with both timestamps; query "as of time T" using `valid_time` filtering. **Verify HydraDB supports this natively;** if not, document workaround in `docs/hydradb-notes.md`.
> 5. `cli/__init__.py` — `cbos decide` and `cbos verify` commands via click
> 6. `ingester/github.py` — minimal GitHub API client + ingest a single commit (just one) creating Commit + File + Identity nodes
> 7. Smoke test in `tests/test_phase1.py`: create Episode → ingest one commit from a tiny test repo → verify Merkle chain → print head hash
>
> Make `make hydradb-test` run the smoke test. Commit as `graph+ingester: bi-temporal schema + merkle + first commit`.
>
> Update STATUS.md and note any HydraDB API surprises in "Open issues".

### Lane E (Extension)

> Working in Lane E: `/extension`.
>
> Read AGENTS.md and CODEBASEOS_SPEC.md §7.
>
> **Phase 1 goal: VS Code extension scaffold + hello-world hover + status bar + connection to backend stub.**
>
> Use `yo code` or hand-scaffold an extension. Implement:
> 1. `extension/src/extension.ts` — activation function, registering: hover provider on `{ scheme: 'file' }`, status bar item, command `codebaseos.why`
> 2. `extension/src/client.ts` — TypeScript HTTP client targeting `http://localhost:8000` with methods `summary`, `why`, `status`, `fiveWhys`, `counterfactual`. For now, all return mock data when backend is unreachable.
> 3. Hover provider returns a markdown popup: `"**$symbol** at $file:$line — backend not yet implemented"`
> 4. Status bar shows: `CBOS: $0.00 / $5.00 · 0 nodes · Merkle ✓`. Polls `/status` every 5s, falls back to last-known on error.
> 5. F5 launch config so the extension can be debugged in an "Extension Development Host" window
>
> Commit as `extension/scaffold: hover + status bar + client stub`. Update STATUS.md.

### Lane D (Dashboard)

> Working in Lane D: `/dashboard`.
>
> Read AGENTS.md and CODEBASEOS_SPEC.md §11.
>
> **Phase 1 goal: Next.js scaffold with live force-directed graph fed by mock WebSocket data.**
>
> Implement:
> 1. Next.js 15 app router scaffold, Tailwind configured
> 2. Page `/` with `react-force-graph-2d` filling the viewport
> 3. WebSocket client connecting to `ws://localhost:8765`
> 4. `scripts/mock_graph_server.py` — WS server pushing a fake node every 500ms with random type/edges
> 5. Color-coded nodes per CODEBASEOS_SPEC §11.2 (Files blue, Symbols cyan, Commits green, PRs orange, Issues yellow, Discussions pink, Decisions amber, People white)
> 6. Top bar with placeholder for: cost meter, node count, Merkle integrity, webhook health
> 7. Three empty panels: ingested repos (left), entity resolution queue (right upper), webhook firehose (right lower)
>
> Make `make dash` start the dev server. Commit as `dash/scaffold: live force graph + layout`. Update STATUS.md.

**GATE at hour 3:** If any of the three lanes is broken (HydraDB bi-temporal doesn't work, VS Code extension won't load, etc.), escalate. Do not push past this gate with a broken foundation.

---

## Phase 2 — Vertical slice (hour 3 to hour 10)

### Lane B

> **Phase 2 goal: full ingestion of a small test repo (commits, PRs, issues, reviews) with deterministic entity resolution.**
>
> Implement:
> 1. `ingester/github.py` — full ingestion: paginate commits, PRs (all states), issues, review comments. Use GraphQL where possible for bulk efficiency. Create Commit, PR, Issue, ReviewComment, File, Identity nodes.
> 2. `ingester/git_local.py` — clone the repo as bare; walk commits with `gitpython`; decompose diffs into Symbol mutations via tree-sitter. Idempotent on re-run.
> 3. `resolver/deterministic.py` — exact email/username matching across platforms. Creates Person nodes; links Identities via `has_identity`.
> 4. `backend/api.py` — FastAPI app with endpoints stubbed per CODEBASEOS_SPEC §8.1; `/summary` and `/status` implemented for real (graph-only, no LLM yet).
> 5. `backend/ws_server.py` — WebSocket bridge pushing graph changes to dashboard.
> 6. Test on a small public repo (suggest `tokio-rs/loom` — small but real).
>
> Commit incrementally. Update STATUS.md after each major piece.

### Lane E

> **Phase 2 goal: real backend integration; hover and code lens work end-to-end.**
>
> Implement:
> 1. Real hover provider — calls `/summary?file=&line=&symbol=`, renders the response as markdown
> 2. Code lens provider — uses tree-sitter via WASM (or a Language Server proxy) to find function definitions in the active file; renders "🧬 Why?" lens above each
> 3. Command `codebaseos.why` — opens a webview panel; calls `/why`; renders the response with clickable links to PRs, commits, people
> 4. The webview is a static HTML template that gets its data injected via VS Code's webview message API
> 5. Status bar polls real `/status`
>
> Commit incrementally. Update STATUS.md.

### Lane D

> **Phase 2 goal: real WS feed from backend; ingested repos panel; entity resolution review queue UI.**
>
> Implement:
> 1. Real `/ws` connection to backend; graph reflects real ingested data
> 2. Left rail — ingested repos with stats (commits, PRs, people, last update)
> 3. Right upper — entity resolution review queue (a Person node may have multiple Identity candidates; user can approve/reject merges)
> 4. Cost meter — queries `/api/cost`, updates every 5s
> 5. Merkle integrity badge — queries `/api/verify`, updates every 30s
> 6. Click any node → details pane on the right with all properties
>
> Commit incrementally.

---

## Phase 3 — Sleep #1 (hour 10 to hour 14)

---

## Phase 4 — Full vertical + Why panel + heuristic resolution (hour 14 to hour 24)

### Lane B

> **Phase 4 goal: heuristic + LLM-assisted entity resolution; decision extraction on-demand; supersession inference; `/why` and `/five-whys` synthesized.**
>
> Implement:
> 1. `resolver/heuristic.py` — fuzzy name match + activity-window correlation. Confidence scoring. Auto-merges above threshold; queues below.
> 2. `resolver/llm_assist.py` — bounded to 100 calls per repo. Sends candidate pairs + corroborating evidence to GPT-5.4 Mini via the synthesizer. Caches results.
> 3. `synthesizer/synthesizer.py` — full implementation per CODEBASEOS_SPEC §8.2. **Single chokepoint for OpenAI**. Enforces 4K input cap, 500 output cap, per-call $0.05 cap, $5 hard cap, aggressive caching, `CostEvent` logging.
> 4. `backend/why.py` — implements `/why` endpoint per CODEBASEOS_SPEC Appendix A. 3-hop traversal + synthesis.
> 5. `backend/five_whys.py` — recursive `/five-whys`: traverses supersedes/caused_by upward 5 levels, one synthesis call per level (≤$0.015 total).
> 6. `backend/decision_extraction.py` — on-demand: when a query touches an un-extracted PR, run GPT-5.4 Mini to extract Decisions from PR body + top comments. Cache forever.

### Lane E

> **Phase 4 goal: webview panel polished; Five Whys + Counterfactual commands; status bar shows live cost.**
>
> Implement:
> 1. Webview rendering with clickable cross-references — clicking a PR link sends a message to extension which calls `/provenance?node=<id>` and re-renders
> 2. Five Whys command — opens panel showing 5 levels of recursive provenance
> 3. Counterfactual command — opens panel; user clicks a Decision in the provenance chain; backend returns alternate-timeline overlay
> 4. Settings panel — backend URL, GitHub repo selection, cost cap, "show me Slack data" toggle
> 5. Status bar tooltip — hover for breakdown of cost by source

### Lane D

> **Phase 4 goal: time-travel slider + Merkle badge + "Without HydraDB" toggle infrastructure.**
>
> Implement:
> 1. Time-travel slider fully wired — drag changes `as_of_time`; queries become bi-temporal
> 2. Merkle integrity badge full UX — click for a chain walk view; turns red on tamper
> 3. "Without HydraDB" toggle in top-right — flips backend mode; same queries route to vector-RAG instead
> 4. Webhook firehose right-lower with live updates
> 5. Better graph animations: pulse on new nodes, fade on superseded

---

## Phase 5 — Sleep #2 (hour 24 to hour 28)

---

## Phase 6 — Webhooks + multi-repo + chaos + Without HydraDB (hour 28 to hour 38)

### Lane B

> **Phase 6 goal: webhook subscriptions; multi-repo cross-linking; "Without HydraDB" vector-RAG baseline; chaos endpoints.**
>
> Implement:
> 1. `backend/webhooks.py` — GitHub webhook receiver behind ngrok; subscribes to push/pull_request/issues/review events; flows into same ingestion pipeline
> 2. Multi-repo support — ingest 2-3 repos with shared contributors; verify Person nodes link correctly across them
> 3. `backend/baseline_rag.py` — one-time embed all commit messages + PR descriptions with `text-embedding-3-small`; in-memory FAISS index; same `/why` interface but vector-only; visibly inferior answers (no entity resolution, no supersession, no bi-temporal)
> 4. `backend/chaos.py` — chaos endpoints corresponding to each dashboard button per CODEBASEOS_SPEC §10
> 5. `backend/handoff.py` — `/handoff?module=` endpoint; structured onboarding tour; one synthesis call

### Lane E

> **Phase 6 goal: Marketplace-ready packaging; auth flow; polish.**
>
> Implement:
> 1. Extension configuration UI (a webview "settings" panel) — backend URL, ngrok URL, repo bindings
> 2. First-launch onboarding — "connect your backend" → status indicator
> 3. Telemetry opt-out (just a config flag; we don't actually telemeter for the hackathon)
> 4. Icon, README, CHANGELOG, LICENSE for Marketplace submission
> 5. Try `vsce package` to produce a .vsix — verify it installs cleanly in a fresh VS Code

### Lane D

> **Phase 6 goal: 8 chaos buttons; live ingestion progress view; counterfactual UI.**
>
> Implement:
> 1. All 8 chaos buttons per CODEBASEOS_SPEC §10 with confirmation modals
> 2. Live ingestion progress view — for the demo. When a new repo is being ingested, show: commits/sec, PRs/sec, people resolved/sec, ETA. This is what plays under the narration in the demo opening.
> 3. Counterfactual UI — alternate-timeline overlay with different node colors and explanatory side panel
> 4. "Without HydraDB" toggle fully functional — same queries, visibly inferior answers
> 5. Polish all animations with framer-motion

---

## Phase 7 — Sleep #3 (hour 38 to hour 42)

---

## Phase 8 — Polish + Marketplace + OSS spinoff + Demo (hour 42 to hour 46)

> **Coordinated across all lanes. Polish only. No new features.**
>
> 1. Run `make demo-cold` end-to-end. Time each segment. Find worst paper cut. Fix.
> 2. Run again. Fix next worst.
> 3. Run a third time. Record video. This is the backup.
> 4. **Publish extension to VS Code Marketplace.** Process: `vsce login <publisher>`, `vsce publish`. Submission can take 30 min to a few hours to appear; submit by hour 43 at latest.
> 5. **Extract `/ingester` + `/graph` + `/synthesizer` to `/provenance` as standalone repo.** Push to GitHub with MIT license, README, examples, 30s GIF.
> 6. **Genesis README** finalized: pitch, GIF, architecture diagram, install instructions, "Without HydraDB" table, links to video, marketplace, ngrok demo.
> 7. Stretch if comfortably ahead: implement `/handoff` polish, multi-repo demo data.
>
> Stop adding features at hour 44. Polish only.

---

## Phase 9 — Submit (hour 46 to hour 48)

> 1. `make submit` produces: repo tarball, video, README, marketplace link, cost report, live demo URL
> 2. Submit on hackathon platform
> 3. Tweet thread drafted:
>    - Tweet 1: One-line pitch + 30s GIF
>    - Tweet 2: VS Code Marketplace install link
>    - Tweet 3: The four demo moments (live ingest, Why panel, chaos, Without HydraDB)
>    - Tweet 4: Total cost ($X.XX) + GitHub link + Provenance OSS spinoff link
>    - Tag host and HydraDB
> 4. Sleep at least 90 minutes before judging

---

## STATUS.md template (place at repo root)

```markdown
# CodebaseOS Status

## Current phase
Phase 0 — Setup

## Last commit per lane
- backend:   (none yet)
- extension: (none yet)
- dashboard: (none yet)

## Cross-lane changes pending
(none)

## Cost so far
$0.00 of $5.00 budget

## Node count
0

## Merkle integrity
OK (chain length: 0)

## Open issues
(none)

## Decisions log
(none yet)

## Marketplace publish
not submitted (target: hour 42–43)

## Backup video
not recorded (hard deadline: hour 44)
```

Update after every meaningful commit.

---

## Cross-cutting reminders

- **Update STATUS.md after every commit.**
- **Cross-lane schema changes go through STATUS.md "Cross-lane changes pending".**
- **Decisions for every non-trivial choice via `cbos decide`.**
- **Cost meter visible at all times.** Status bar in VS Code, top bar in dashboard.
- **No new features after hour 42.**
- **Backup video by hour 44.**
- **Marketplace publish by hour 43.**

---

## The first thing to paste into Claude Code

Open the main worktree, start Claude Code, paste:

> Read `AGENTS.md` and `CODEBASEOS_SPEC.md` in full. Confirm you understand the invariants in AGENTS.md §INVARIANTS by listing them back, especially the cost discipline section. Then execute Phase 0 from KICKOFF.md and commit.

Then open the three worktree sessions and paste each lane's Phase 1 spike prompt. **Start Lane B first** — Lanes E and D depend on the graph schema being settled.
