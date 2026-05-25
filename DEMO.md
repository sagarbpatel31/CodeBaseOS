# CodebaseOS — Demo Script

Bi-temporal code provenance on HydraDB. "Right-click any line. Ask why. Get the
real answer." Every fact is Merkle-verified; every LLM call is cost-capped at $5.

## Setup (4 terminals)

```bash
# Always clear stale ports first
lsof -ti:8000,3000 | xargs kill -9 2>/dev/null

# T1 — backend
python3 -m uvicorn backend.api:app --host 0.0.0.0 --port 8000

# T2 — dashboard
cd dashboard && npx next dev -p 3000

# T3 — ingest (seed the graph)
cbos ingest tokio-rs/tokio --limit 10 --prs 5 --issues 5
cbos ingest tokio-rs/bytes --limit 8 --prs 3      # 2nd repo → cross-repo people

# T4 — integrity
cbos verify          # ✓ Merkle chain intact
cbos cost            # spend vs $5 cap
```

Dashboard: http://localhost:3000 · Backend: http://localhost:8000

## Demo flow (~5 min)

1. **The graph is real** — open the dashboard. Two repo hubs (tokio, bytes),
   files clustering around commits, authors, the Merkle episode chain trailing
   out. Top bar: live cost / node count / `Merkle ✓` / `live`.

2. **Ask the graph** — type a question in the search box
   (`why was create_dir_all changed`). Ranked nodes appear instantly — pure
   recall, no LLM, no cost.

3. **Why does this code exist?** — click a green **File** node → a panel
   synthesizes the provenance from the actual commits/PRs/decisions that shaped
   it (with the context-node count + the exact cost of that one call).

4. **With vs without HydraDB** — in VS Code, hover a line →
   *Compare (with vs without HydraDB)*. Left (graph-grounded) cites real
   commits; right (plain LLM) admits it has no history. That's the pitch.

5. **Five Whys** — recursive root cause from code → intent → decision.

6. **Entity resolution** — right rail: `34 identities → 28 people`. Alice Ryhl's
   identities auto-merged **across both repos** by shared email; ambiguous
   name↔login matches sit in the review queue.

7. **Time travel** — drag the bottom slider back. The graph collapses to only
   what was valid at that instant (bi-temporal `as_of`). Slide to "now" → live.

8. **Live ingestion** — right rail firehose: click `+commit` / `+pr`. New nodes
   stream in, the graph grows, and **`Merkle ✓` holds** (in-memory chain tip
   prevents stale-tail forks under concurrency).

9. **Onboarding tour** — VS Code *Generate onboarding tour for current module*:
   overview, where to start, key files / people / decisions for a module.

## Integrity & cost story

- `cbos verify` — walks the Merkle chain end-to-end, recomputes every hash.
- Single cost chokepoint: every LLM call logs a `CostEvent`; `_check_budget`
  hard-stops at $5 (HTTP 402). Hovering never calls the LLM.
- `cbos rechain` / `POST /chain/resync` — chain repair + tip resync utilities.
