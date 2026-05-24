# CodebaseOS Status

> This file is the spine that keeps three parallel Claude Code sessions coherent.
> Update after every meaningful commit. Read at the start of every session.

---

## Current phase

**Phase 1 — Spikes (Lane B)** 🟡 IN PROGRESS

Phase 0 completed: 2026-05-23 21:15 PDT
Phase 1 Lane B started: 2026-05-23 21:30 PDT
Target completion: hour 3

---

## Last commit per lane

| Lane | Branch | Last commit | Timestamp |
|---|---|---|---|
| Backend (B)   | wip/backend   | graph+ingester: bi-temporal schema + merkle + /status | 2026-05-23 21:45 PDT |
| Extension (E) | wip/extension | (none yet) | — |
| Dashboard (D) | wip/dashboard | (none yet) | — |

---

## Cross-lane changes pending


- [Phase 1] Backend (Lane B) must serve `GET /status` returning `{costSpent, costCap, nodeCount, repoCount, merkleOk, merkleHead}`. Spec: docs/status-bar-contract.md §"Backend contract". Required for Lane E status bar.

---

## Cost so far

**$0.00 of $5.00 budget**

| Source | Calls | Tokens (in/out) | Cost |
|---|---|---|---|
| Why panel queries           | 0 | 0 / 0 | $0.00 |
| Five Whys queries           | 0 | 0 / 0 | $0.00 |
| Counterfactual              | 0 | 0 / 0 | $0.00 |
| Decision extraction         | 0 | 0 / 0 | $0.00 |
| Entity resolution LLM-assist| 0 | 0 / 0 | $0.00 |
| Embeddings (baseline)       | 0 | 0 / 0 | $0.00 |
| Handoff tour                | 0 | 0 / 0 | $0.00 |
| **Total**                   | **0** | **0 / 0** | **$0.00** |

Last updated: (timestamp)

---

## Node count

Total: 0

| Type | Count |
|---|---|
| Repository    | 0 |
| Commit        | 0 |
| PR            | 0 |
| Issue         | 0 |
| File          | 0 |
| Symbol        | 0 |
| ReviewComment | 0 |
| Decision      | 0 |
| Discussion    | 0 |
| Person        | 0 |
| Identity      | 0 |
| Episode       | 0 |

---

## Merkle integrity

**OK** (chain length: 0)

Last verified: (timestamp)
Head hash: (none yet)

---

## Ingestion source health

| Source        | Status      | Last activity | Node count |
|---|---|---|---|
| github_api    | not started | — | 0 |
| git_local     | not started | — | 0 |
| github_webhook| not started | — | 0 |
| slack         | not started | — | 0 |
| linear        | not started | — | 0 |
| manual_cli    | not started | — | 0 |

---

## Entity resolution review queue

Pending merges awaiting human approval: 0

---

## Open issues

Format: `[severity] [lane] description (workaround if known)`

- [low] [backend] HydraDB SourceListResponse = Any — list_data response shape for knowledge sources is untyped in SDK. We access as dict; needs live API validation with real credentials.
- [low] [backend] ContentFilter on knowledge sources needs live test — uncertain if source_fields={"type":"..."} filtering works for knowledge (not memories).
- [medium] [all] .env not created — HYDRADB_API_KEY + GITHUB_TOKEN needed to run live tests (tests/test_phase1.py::test_hydradb_*). Unit tests (schema + merkle) pass without credentials.

---

## Decisions log

Format: `[timestamp] [decision_id] [actor] summary`

(none yet — first Decision will come from Phase 1, Lane B's smoke test)

---

## Sleep blocks

| Block | Planned | Actual start | Actual end |
|---|---|---|---|
| Sleep #1 | hour 10–14 | — | — |
| Sleep #2 | hour 24–28 | — | — |
| Sleep #3 | hour 38–42 | — | — |

---

## Phase gates

| Gate | Hour | Status | Notes |
|---|---|---|---|
| Foundation works            | 3  | not reached | — |
| Vertical slice (small repo) | 10 | not reached | — |
| Why panel + heuristic ER    | 24 | not reached | — |
| Webhooks + multi-repo + chaos | 38 | not reached | — |
| Marketplace published       | 43 | not reached | — |
| Demo polished               | 44 | not reached | — |
| Submitted                   | 48 | not reached | — |

---

## Demo rehearsals

| # | Hour | Duration | Worst paper cut | Fixed? |
|---|---|---|---|---|
| 1 | — | — | — | — |
| 2 | — | — | — | — |
| 3 | — | — | — | — |

---

## VS Code Marketplace

- Publisher account created: NO
- Extension packaged: NO
- Submitted: NO
- Approved: NO
- Public URL: —

**Hard deadline for submission: hour 43.** (Approval can take hours; submit early.)

---

## Backup video

- Recorded: NO
- Hour: —
- File path: —
- Length: —

**Hard deadline: hour 44.**

---

## Provenance OSS spinoff

- Repo created: NO
- Public URL: —
- README + LICENSE: NO
- Examples: NO

**Target: hour 44–45.**
