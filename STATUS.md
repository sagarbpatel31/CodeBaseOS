# CodebaseOS Status

> Running log of where the build actually is. Read at the start of every session.

---

## Current phase

**Vertical slice complete + chaos layer + cost-discipline hardening.**

All three lanes (Backend/Graph, Extension, Dashboard) are past the Phase 6
feature set. Remaining work is polish, demo rehearsal, and Marketplace publish.

| Lane | State |
|---|---|
| Backend (B)   | ✅ ingestion, ER, `/why` family, time-travel, webhooks, chaos, single synthesizer chokepoint |
| Extension (E) | ✅ hover, why panel, compare (with vs without HydraDB), status bar; `.vsix` packaged |
| Dashboard (D) | ✅ live force graph, cost/Merkle top bar, NL search, ER queue, firehose, time slider, **chaos panel** |

---

## What works end-to-end

- **Ingestion** — `cbos ingest owner/repo --limit N --prs N --issues N` and
  `POST /repos`; commits/PRs/issues/files/identities as nodes, each its own
  Merkle Episode. Webhook receiver (`POST /webhook`) + `POST /webhook/simulate`.
- **Bi-temporal graph** — every node has `tx_time` + `valid_time`;
  `GET /graph?as_of=` returns a point-in-time snapshot (dashboard time slider).
- **Merkle chain** — `graph/merkle.py` (`evaluate_chain` pure check + `verify_chain`);
  `GET /verify`, `cbos verify`, `cbos rechain` / `POST /chain/resync` repair.
- **Entity resolution** — `graph/resolve.py` deterministic clustering;
  `GET /er-queue`, `POST /resolve` persists cross-repo Person nodes.
- **LLM surface** — `/why`, `/five-whys`, `/summary`, `/counterfactual`,
  `/handoff`, `/baseline-rag`. All route through the **single synthesizer
  chokepoint** (`synthesizer/synthesizer.py`): hard $5 cap, $0.05/call cap,
  ≤4K input / ≤500 output, response caching (repeat clicks free), CostEvent log.
- **NL search** — `/search-nl` (pure recall, no LLM, free).
- **Chaos layer (§10)** — `/chaos/tamper` (one corrupted hash → Merkle badge
  red via the real linkage check), `/chaos/restore`, `/chaos/nuclear` (orphaned
  author + suggested reviewers), `/chaos/revive`, `/chaos/state`. Dashboard
  `ChaosPanel` drives them live; orphaned/tampered nodes flash red in the graph.
- **Offline demo mode** — set `CBOS_OFFLINE_DEMO=1` to serve a deterministic
  bundled fixture with no HydraDB/OpenAI credentials, so the dashboard + chaos
  buttons render on any laptop (demo safety net).

---

## Cost discipline

Hard cap **$5**, enforced in `synthesizer/synthesizer.py` (fails closed → HTTP 402).
Every paid call logs a `CostEvent`; `/status` sums them. Live total shown in the
VS Code status bar and the dashboard top bar. Repeat queries are cache hits → $0.

Run `cbos cost` or `make cost` for the current spend.

---

## Merkle integrity

`make verify` / `cbos verify` walks the chain end-to-end. Badge is green when
linkage holds; `/chaos/tamper` injects a single bad hash and the same verifier
turns it red until `/chaos/restore`.

---

## Open issues

Format: `[severity] [lane] description (workaround if known)`

- [low] [backend] HydraDB `list_data` response shape is partly untyped in the
  SDK; we read defensively from `document_metadata` (HydraDB overwrites `content`).
- [low] [backend] `repair_merkle_chain` deletes + re-inserts Episodes under the
  same ids (the only place that mutates Episodes; recovery-only).
- [medium] [all] Live tests need `.env` (`HYDRADB_API_KEY` + `GITHUB_TOKEN`
  [+ `OPENAI_API_KEY`]). Unit tests (schema + merkle) pass without credentials.
  For a no-credential demo use `CBOS_OFFLINE_DEMO=1`.

---

## Demo

`make demo-cold` — kill stale ports, start backend + dashboard, ingest two repos,
verify the chain, print URLs. `make break` — drive the chaos endpoints in sequence.
See `DEMO.md` for the 5-minute script.

---

## VS Code Marketplace

- Extension packaged (`.vsix` build path via `make extension-pack`): YES
- Icon / README / CHANGELOG / LICENSE: YES
- Published: pending (run `make publish` at hour 42+)

---

## Backup video

- Recorded: NO (hard deadline: hour 44)

---

## Provenance OSS spinoff

- Extract `/ingester` + `/graph` + `/synthesizer` into `/provenance`: pending (target hour 44–45)
