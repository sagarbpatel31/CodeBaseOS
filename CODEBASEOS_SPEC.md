# Project CodebaseOS
### The First Code Provenance System That Actually Knows Why Every Line Exists

> **Hackathon:** Agents Under Pressure (HydraDB, 48 hours)
> **Team:** 1 human + Claude Code in parallel sessions
> **Total inference budget:** Under $5
> **Frontend:** VS Code extension
> **Tagline:** "Right-click any line. Ask why. Get the real answer."

---

## 0. The Two-Sentence Pitch

**Technical:** A VS Code extension backed by a bi-temporal HydraDB graph that ingests a repository's entire history (commits, PRs, issues, code review threads, linked discussions, people) with cryptographic Merkle provenance, performs deterministic multi-source entity resolution across GitHub/Slack/Jira identities, and answers "why is this code here?" through 14-hop graph traversal explained by a cheap GPT-5.4 Mini synthesizer.

**Non-technical:** Every engineer has asked "why is this code here?" and gotten silence. CodebaseOS finally answers — with the full origin story, in your editor, in 200 milliseconds, from a graph that remembers every decision your team ever made.

---

## 1. The North Star

Every codebase has tribal knowledge. The senior engineer who chose Redis over Postgres in 2022 has left. The PR thread debating that choice is buried under 8,000 newer PRs. The Slack message explaining why is in a deleted channel. The original ticket is closed and unsearchable. Two years later, a junior asks "why don't we use Postgres?" and nobody knows.

GitHub does *some* of this — blame, PR history, issue links. But the graph is incomplete: there's no link from a *line of code* to the *Slack thread* that motivated it, to the *vendor email* that triggered the rewrite, to the *person* who made the decision (who has since left). The pieces exist; nothing connects them.

CodebaseOS connects them. It is a **bi-temporal, multi-source, cryptographically-provenanced graph** of your entire codebase's history. Click any line → 14-hop provenance chain → "this exists because Decision #482 chose JWT over sessions in March 2023, which superseded the earlier OAuth-only design after the audit findings in #1872, championed by Alice (who is no longer at the company) and reviewed by Bob (who is)."

Vector DBs cannot do this. Most graph DBs do not have bi-temporal queries or fast supersession traversal. HydraDB has both, sub-200ms, multi-tenant. The product *requires* HydraDB. The market wants this product.

---

## 2. What Makes This Win

| Dimension | Why we score high |
|---|---|
| **Sponsor utilization** | HydraDB's bi-temporal + supersession + multi-tenant + sub-200ms is genuinely irreplaceable. Vector DBs categorically cannot do entity resolution + temporal correctness + supersession traversal. |
| **Originality** | "Right-click any line, get its full origin story" is unclaimed territory. GitHub doesn't do it. Sourcegraph doesn't do it. AI coding assistants don't do it. |
| **Theme fit ("under pressure")** | Chaos: ingest a repo with 10,000 commits live on stage. Webhook firing during demo. Adversarial mutation attempting to rewrite history (Merkle catches it). |
| **Demo wow** | Live ingestion of Tokio's GitHub history streams in real-time. Right-click any function in the editor. Provenance panel populates in 200ms. |
| **Technical depth** | Bi-temporal graph + Merkle chain + multi-source entity resolution + decision extraction + LSP integration + webhook pipeline. Real engineering work. |
| **Cost discipline** | Under $5 total inference. Caching makes repeat queries free. Cost meter visible during demo. |
| **Real user value** | Every engineer alive has this pain. The hackathon demo doubles as a product launch. |
| **Post-hackathon traction** | This is a real product. Engineers will install it. You walk away with something to ship. |

**Target ceiling: 9.4/10 weighted.** Same hackathon-win ceiling as Genesis with a real product underneath.

---

## 3. System Architecture

```
╔═══════════════════════════════════════════════════════════════════════╗
║                    VS CODE EXTENSION (TypeScript)                      ║
║                                                                        ║
║   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    ║
║   │ Hover    │  │ Code     │  │ Webview  │  │ Status bar:        │    ║
║   │ provider │  │ lens     │  │ panel    │  │ cost / nodes /     │    ║
║   │          │  │ (inline) │  │ ("Why?") │  │ merkle status      │    ║
║   └──────────┘  └──────────┘  └──────────┘  └────────────────────┘    ║
║                              │                                         ║
║                       REST + WS to backend                            ║
║                              │                                         ║
╠══════════════════════════════▼════════════════════════════════════════╣
║                         BACKEND (Python asyncio)                       ║
║                                                                        ║
║   ┌────────────────┐ ┌─────────────────┐ ┌────────────────────────┐   ║
║   │ Query API      │ │ Ingestion       │ │ Synthesizer            │   ║
║   │ (FastAPI)      │ │ Pipeline        │ │ (GPT-5.4 Mini)         │   ║
║   │                │ │                 │ │ - cost cap             │   ║
║   │ - /why         │ │ - GitHub API    │ │ - 4K input / 500 out   │   ║
║   │ - /five-whys   │ │ - git mirror    │ │ - aggressive cache     │   ║
║   │ - /provenance  │ │ - PR threads    │ │ - per-call logging     │   ║
║   │ - /search-nl   │ │ - issues        │ │                        │   ║
║   │ - /counter-    │ │ - Slack (opt)   │ └────────────────────────┘   ║
║   │   factual      │ │ - Linear (opt)  │                              ║
║   │ - /handoff     │ │                 │ ┌────────────────────────┐   ║
║   │ - /verify      │ │ + entity res    │ │ Entity Resolver        │   ║
║   │                │ │ + merkle chain  │ │ (deterministic +       │   ║
║   │                │ │ + decision      │ │  rare-case LLM-assist) │   ║
║   │                │ │   extraction    │ │                        │   ║
║   └────────────────┘ └─────────────────┘ └────────────────────────┘   ║
║                              │                                         ║
╠══════════════════════════════▼════════════════════════════════════════╣
║                    HYDRADB BI-TEMPORAL GRAPH                           ║
║                                                                        ║
║   ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────┐    ║
║   │ Files +    │ │ Commits  │ │ PRs +      │ │ Decisions +      │    ║
║   │ Symbols    │ │ + diffs  │ │ Reviews    │ │ supersession     │    ║
║   └────────────┘ └──────────┘ └────────────┘ └──────────────────┘    ║
║   ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────────────┐    ║
║   │ Issues +   │ │ People + │ │ Discussions│ │ Episodes +       │    ║
║   │ labels     │ │ identities│ │ + threads │ │ Merkle chain     │    ║
║   └────────────┘ └──────────┘ └────────────┘ └──────────────────┘    ║
║                                                                        ║
╠════════════════════════════════════════════════════════════════════════╣
║                   WEBHOOK SUBSCRIPTIONS                                ║
║       GitHub (push, PR, issue, review, comment)                       ║
║       Slack (optional; channel messages mentioning repo)              ║
║       Linear/Jira (optional; tickets linked to PRs)                   ║
╚════════════════════════════════════════════════════════════════════════╝

         ┌────────────────────────────────────────────────────┐
         │           OBSERVABILITY DASHBOARD                   │
         │  (Next.js + react-force-graph + Tailwind)           │
         │                                                     │
         │  • Live ingestion progress (used for the demo)      │
         │  • Multi-repo cross-link graph                      │
         │  • Time-travel slider                               │
         │  • Entity resolution review queue                   │
         │  • Merkle chain integrity badge                     │
         │  • Cost meter ($X.XX of $5.00)                      │
         │  • "Without HydraDB" baseline toggle                │
         │  • Live webhook firehose                            │
         └────────────────────────────────────────────────────┘
```

---

## 4. Conceptual Model

### 4.1 What the graph captures

| Aspect of codebase history | Captured as |
|---|---|
| A file at a moment in time | `File` node + `valid_time` range |
| A symbol (function/struct/global) | `Symbol` node + `abi_version` |
| A commit | `Commit` node + `derived_from` edge to parents |
| A pull request | `PR` node + `produced` edges to commits |
| A code review comment | `ReviewComment` node + `references` edge to file/line |
| A merged decision | `Decision` node, extracted from PR description/discussion |
| A rejected approach | Prior `Decision` linked via `supersedes` |
| An issue / ticket | `Issue` node, linked to PRs via `closes`/`mentions` |
| A Slack/Discord thread | `Discussion` node + `mentions` edges |
| A person | `Person` node + multiple `Identity` edges across services |
| When we knew vs when it was true | bi-temporal: `tx_time` + `valid_time` on every node |
| Tamper resistance | Merkle chain over Episodes |

### 4.2 Multi-source entity resolution

The hardest, most valuable part. "Alice on GitHub" must be linked to "alice.smith@company.com on Slack" to "@alice in Linear" to "Alice Smith in commit author field" to "alice-s on Discord."

We do this with three layers:

1. **Deterministic matching** (free, fast): exact email match, identical name + corroborating signal (same org, same timezone), GitHub-Slack OAuth linkage, commit-author-to-email match.
2. **Heuristic matching** (free, near-instant): fuzzy name match + activity correlation (Alice commented on Slack message at 14:31, Alice merged PR at 14:33 — likely same person).
3. **LLM-assisted ambiguous review** (~$0.01 per case, ~100 cases per large repo = $1): when the heuristic returns multiple candidates, queue for review. Send the candidates + corroborating evidence to GPT-5.4 Mini for tie-breaking. Human can override via dashboard.

Result: a `Person` node with multiple `Identity` edges to platform-specific accounts. Every other node (Commit, Comment, Decision) links to a Person, not a username. Query "show me every architectural decision Alice made across all repos" works.

### 4.3 Decision extraction

PRs are where decisions get made and explained, then forgotten. CodebaseOS extracts them.

When ingesting a PR:
1. Concatenate the description + top-level comments (truncated to ~3K tokens)
2. Send to GPT-5.4 Mini with a structured extraction prompt:
   ```
   Extract decisions made in this PR. For each:
   - One-sentence summary
   - Rationale (one sentence)
   - Alternatives that were rejected (if mentioned)
   - Confidence (low/medium/high)

   Return JSON. If no clear decision was made, return [].
   ```
3. Parse JSON; create `Decision` nodes; link to PR; if "supersedes" relation can be inferred from text ("this replaces our previous approach of X"), traverse the graph to find the prior Decision and create a `supersedes` edge.

Cost: ~$0.01 per PR. For a large repo with 3,000 PRs: ~$30. **Too expensive.**

**The trick:** extract only on demand. When a user queries "why is X here?" — and the answer involves PR #482 — *then* run extraction on PR #482. Cache forever. In practice, demos and real usage touch maybe 100 PRs total, so cost stays at ~$1.

### 4.4 The honesty principle

CodebaseOS makes one claim: "we know why every line is here." This is true only if:
- The graph is **comprehensive** (multi-source ingestion is real)
- Entity resolution is **correct** (Alice-the-person is one node, not three)
- Decisions are **attributed** (every line traces to a decision and a person)
- History is **tamper-evident** (Merkle chain catches mutation)

These four properties are what make the product trustworthy. They are also what HydraDB uniquely enables.

---

## 5. HydraDB Schema (Bi-Temporal)

Build in hour 1.

### 5.1 Universal properties (every node)

| Property | Type | Meaning |
|---|---|---|
| `id` | UUID | stable identifier |
| `tx_time` | timestamp | when we ingested/wrote this |
| `valid_time` | timestamp | when this is true in the world |
| `valid_time_end` | timestamp \| null | when this stopped being true |
| `source` | string | what produced this (github, slack, manual, etc.) |
| `episode_id` | UUID | the Episode that created this node |
| `merkle_hash` | hex | cryptographic chain link |

### 5.2 Node types

| Type | Key properties |
|---|---|
| `Episode` | sequence_no, action_type, source, inputs_hash, outputs_hash |
| `Repository` | name, github_id, default_branch, language_breakdown |
| `Commit` | sha, message, author_id, parents, files_changed, additions, deletions |
| `File` | repository_id, path, current_hash, language |
| `Symbol` | name, kind (fn/struct/class/global), defining_file, signature, language, abi_version |
| `PR` | number, title, description, state (open/merged/closed), author_id, merged_at |
| `ReviewComment` | pr_id, file_id, line_range, author_id, body, in_reply_to |
| `Issue` | number, title, body, state, author_id, labels |
| `Decision` | summary, rationale, alternatives_rejected, confidence, made_by_id |
| `Discussion` | platform (slack/discord/email), channel, thread_id, summary |
| `Person` | canonical_name, primary_email, current_employer |
| `Identity` | platform, platform_user_id, username, email, valid_time_range |
| `CostEvent` | call_id, model, input_tokens, output_tokens, cost_usd, source |

### 5.3 Relation types

- `produced` (Commit → File mutation, PR → Commits, Decision → File/Symbol/Module)
- `defines` (File → Symbol), `imports` (File → Symbol)
- `supersedes` (Decision → Decision) — the temporal versioning superpower
- `caused_by` (Decision → Issue, PR → Discussion, etc.)
- `references` (ReviewComment → File:line, Discussion → PR/Issue, etc.)
- `mentions` (Discussion → Person/File/Symbol, anywhere → anywhere)
- `authored_by` (Commit/PR/Issue/Comment → Person)
- `has_identity` (Person → Identity)
- `closes` (PR → Issue), `merged_into` (PR → branch/commit)
- `merkle_next` (Episode → Episode)

### 5.4 Schema invariants

1. Every Author field is a `Person` reference, never a raw username string. Username strings live on `Identity` nodes.
2. Decisions are immutable. Supersession is a relation.
3. Episodes are append-only.
4. Every Episode extends the Merkle chain.
5. Every File node has at least one `produced` edge from a Commit (constraint-enforced).
6. Symbol ABI changes create a new Symbol node + `supersedes` edge; old node gets `valid_time_end`.

---

## 6. The Ingestion Pipeline

### 6.1 Sources

| Source | Auth | Real-time | Backfill | Implementation |
|---|---|---|---|---|
| **GitHub commits + PRs + issues + reviews** | PAT or App | Webhook | API pagination | mandatory |
| **Local git mirror** | none | git hook | full history walk | mandatory |
| **Slack** | Bot token | Events API | conversations.history | optional, recommended |
| **Linear / Jira** | API token | Webhook | API pagination | optional |
| **Manual decisions** | n/a | CLI (`cbos decide`) | n/a | mandatory (humans recording reasoning) |
| **Discord** | Bot token | Gateway | API | optional |

### 6.2 Ingestion flow per repo

```
1. User clicks "Ingest" in dashboard
2. Backend creates a Repository node, an initial Episode
3. Parallel asyncio tasks:
   a) git clone --bare; walk all commits → Commit + File + Symbol nodes
   b) GitHub API: paginate PRs (state=all), for each: PR + ReviewComment nodes
   c) GitHub API: paginate Issues, link to PRs via "closes"
   d) (if connected) Slack: channels mentioning repo name, threads → Discussion nodes
4. After all 4 streams complete: entity resolution pass
5. Webhook subscriptions set up; future events flow into the same pipeline
6. Dashboard shows "Ready"
```

Performance target: a 10K-commit / 3K-PR repo (~Tokio scale) ingests in **under 5 minutes** on a single backend. This is your demo budget — must be achievable.

### 6.3 Entity resolution pass

After raw ingestion:

```python
async def resolve_identities(repo_id: UUID, db: HydraClient):
    # 1. Collect all unresolved Identity-like records (commit authors, comment authors, etc.)
    candidates = await db.query("""
        MATCH (i:Identity {resolved: false})
        WHERE i.repository_id = $repo
        RETURN i
    """, repo=repo_id)

    # 2. Deterministic pass: exact email/username match across platforms
    deterministic_merges = group_by_exact_match(candidates)
    for group in deterministic_merges:
        await create_person_node(group)

    # 3. Heuristic pass: fuzzy name + activity correlation
    fuzzy_candidates = remaining_after_deterministic(candidates)
    for cand in fuzzy_candidates:
        matches = find_likely_persons(cand, activity_window_minutes=15)
        if len(matches) == 1 and matches[0].confidence > 0.85:
            await link_identity_to_person(cand, matches[0].person_id)
        else:
            await queue_for_review(cand, matches)

    # 4. Review queue: ambiguous cases for LLM-assisted tie-breaking
    review_queue = await db.query("MATCH (r:ResolutionReview) WHERE r.resolved = false RETURN r")
    for case in review_queue[:50]:  # cap to control cost
        await llm_assisted_resolve(case)
```

LLM-assisted resolution: bounded at ~100 calls per repo at ~$0.01 each = $1 absolute ceiling per repo. Demo on one repo for the hackathon.

---

## 7. The VS Code Extension

### 7.1 What the engineer sees

- **Hover provider:** hover a symbol → a small popup with "Last changed 6 days ago by Alice (PR #482). Click for full provenance."
- **Code lens:** above every function definition, an inline link "🧬 Why?" — click to open the Why panel.
- **Webview panel ("Why is this here?")**: opens in a side panel. Shows the 14-hop provenance chain rendered by the synthesizer, with clickable references to PRs, commits, people, decisions.
- **Status bar:** running cost (`$0.34 / $5.00`), graph integrity (`✓` or `✗`), connection status.
- **Command palette:** "CodebaseOS: Five Whys" (recursive provenance), "CodebaseOS: Counterfactual" (what if this Decision had gone the other way?), "CodebaseOS: Generate onboarding tour for current module."

### 7.2 Implementation outline

```typescript
// extension.ts
export function activate(context: vscode.ExtensionContext) {
  const client = new CodebaseOSClient(getConfig().backendUrl);

  // Hover provider
  context.subscriptions.push(
    vscode.languages.registerHoverProvider({ scheme: 'file' }, {
      provideHover: async (doc, pos) => {
        const symbol = resolveSymbolAt(doc, pos);
        if (!symbol) return null;
        const summary = await client.summary(doc.uri.fsPath, pos.line, symbol.name);
        return new vscode.Hover(renderHoverMarkdown(summary));
      }
    })
  );

  // Code lens
  context.subscriptions.push(
    vscode.languages.registerCodeLensProvider({ scheme: 'file' }, new WhyLensProvider(client))
  );

  // Webview panel
  context.subscriptions.push(
    vscode.commands.registerCommand('codebaseos.why', async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) return;
      const panel = vscode.window.createWebviewPanel(
        'codebaseos.why', 'Why is this here?', vscode.ViewColumn.Beside,
        { enableScripts: true }
      );
      const provenance = await client.why(editor.document.uri.fsPath, editor.selection.active.line);
      panel.webview.html = renderProvenancePanel(provenance);
    })
  );

  // Status bar
  const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  context.subscriptions.push(statusItem);
  setInterval(async () => {
    const status = await client.status();
    statusItem.text = `CBOS: $${status.cost.toFixed(2)} ${status.merkleOk ? '✓' : '✗'}`;
  }, 5000);
}
```

### 7.3 The "Why" webview

Markdown rendered into the panel, with clickable cross-references:

```
## auth.py:142 (function `verify_token`)

This function exists because:

1. **Decision #482** (Mar 14, 2023): Adopt JWT-based auth.
   - Made by: Alice Smith (no longer at company)
   - Rationale: "Stateless verification needed for the multi-region rollout"
   - Superseded: Decision #361 (OAuth-session hybrid)

2. Decision #482 was made in **PR #1872** ("Replace session auth with JWT").
   - Reviewed by: Bob Chen, Carol Patel
   - 14 comments, ~3 days of discussion
   - [View PR]

3. PR #1872 was triggered by **Issue #1645** ("Session affinity breaks on region failover").

4. Issue #1645 was filed after **Slack discussion** in #infra-alerts on Mar 9, 2023
   (post-incident, 87 messages, summary: "regional failover lost all logged-in users").

5. The original session-based design was **Decision #189** (Jan 2022, Alice Smith).
   - It was sound for single-region.

[Five Whys ↓]  [Counterfactual: what if Decision #482 had gone the other way?]  [Verify chain integrity]
```

This is the product moment. Every engineer who sees this wants it.

---

## 8. The Backend Query API

FastAPI, async, behind the extension.

### 8.1 Endpoints

| Path | Method | Purpose | Cost per call |
|---|---|---|---|
| `/repos` | GET | List ingested repos | $0 |
| `/repos` | POST | Start ingesting a new repo | $0 ingestion + $1 ER one-time |
| `/why?file=&line=` | GET | Provenance for a file:line | ~$0.003 |
| `/five-whys?file=&line=` | GET | Recursive 5-deep provenance | ~$0.015 |
| `/summary?file=&line=` | GET | Cheap hover summary (graph-only, no LLM) | $0 |
| `/search-nl?q=` | POST | Natural-language → graph query | ~$0.005 |
| `/counterfactual?decision=` | POST | "What if this Decision had been different?" | ~$0.05 |
| `/handoff?module=` | POST | New-hire onboarding tour for a module | ~$0.02 |
| `/verify` | GET | Walk Merkle chain end-to-end | $0 |
| `/status` | GET | Cost, node count, integrity, webhook health | $0 |
| `/baseline-rag?file=&line=` | GET | Vector-RAG fallback (for "Without HydraDB" demo) | ~$0.005 |

### 8.2 The synthesizer

All LLM calls go through one module. Single point of cost control.

```python
# synthesizer.py
class Synthesizer:
    HARD_CAP_USD = 5.00
    PER_CALL_CAP_USD = 0.05
    INPUT_TOKEN_CAP = 4000
    OUTPUT_TOKEN_CAP = 500

    def __init__(self, openai_client, db):
        self.openai = openai_client
        self.db = db
        self.cache = {}  # (entity_id, template_version) -> response

    async def synthesize(
        self,
        template_name: str,
        graph_payload: dict,
        cache_key: str,
    ) -> str:
        if cache_key in self.cache:
            return self.cache[cache_key]

        total_spent = await self.db.get_total_cost()
        if total_spent >= self.HARD_CAP_USD:
            return "[Budget cap reached. See dashboard.]"

        prompt = render_template(template_name, graph_payload)
        prompt = truncate_to_tokens(prompt, self.INPUT_TOKEN_CAP)

        response = await self.openai.chat.completions.create(
            model="gpt-5.4-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=self.OUTPUT_TOKEN_CAP,
            temperature=0.2,
        )

        cost = compute_cost(response.usage)
        if cost > self.PER_CALL_CAP_USD:
            raise BudgetError(f"Call exceeded per-call cap: ${cost}")

        await self.db.log_cost(cost, template_name, cache_key)
        result = response.choices[0].message.content
        self.cache[cache_key] = result
        return result
```

This is the only place OpenAI is called from. Nothing bypasses this module.

---

## 9. The "Without HydraDB" Baseline

Crucial demo flex. We implement a vector-RAG baseline using the same source data:

- Embed every commit message + PR description + issue body with `text-embedding-3-small` (one-time, ~$1 for a large repo)
- Store in a simple in-memory FAISS index
- "Why is this here?" → embedding search over commit messages + PR descriptions → top 5 → synthesize answer with same model, same prompt template

Click any line. Same query. Vector-RAG answer is visibly inferior:
- Cannot traverse supersession (returns the original decision, not the superseded current one)
- Cannot resolve "Alice the person" — only mentions "Alice" as a string
- Cannot find Slack-thread evidence (different vector space, no entity links)
- Cannot do bi-temporal queries (no concept of "as of when")
- Returns plausible-sounding but wrong attributions

**This side-by-side is half the pitch.** Same hardware, same source material, same synthesis model. The only difference is the graph layer underneath. The gap is dramatic and obvious.

---

## 10. The Chaos Layer

Eight buttons in the dashboard. Judge presses live.

| Button | Action | Audience sees |
|---|---|---|
| **Ingest a huge repo live** | Start ingesting Tokio (~10K commits) | Graph fills in real-time on screen |
| **Fire fake webhook** | Simulate a new PR coming in | Live update; "Why" panel for affected file refreshes |
| **Tamper with the graph** | Mutate a Decision text directly in HydraDB | Merkle chain breaks; integrity badge goes red; click to inspect |
| **Author goes nuclear** | Mark a Person as "left company" — their decisions are highlighted as orphaned | Suddenly 47 functions trace to someone unreachable; system suggests reviewers from `mentions` graph |
| **Rewind 6 months** | Time-travel slider | Whole graph rewinds; click anything, get the historical answer |
| **Counterfactual** | "What if PR #482 had not merged?" | Alternate-timeline overlay |
| **Force entity merge** | Manually link two ambiguous identities | Graph reshapes; queries reflect new linkage |
| **Without HydraDB** | Switch backend to vector-RAG | Same queries; visibly inferior answers; you can flip back |

Every event leaves a graph trace. Replayable. Inspectable.

---

## 11. Observability Dashboard

Separate from VS Code, for the live demo and ingestion monitoring.

### 11.1 Layout
- **Top bar:** cost meter · node count · Merkle integrity · webhook health · 8 chaos buttons
- **Left rail:** ingested repos, each with stats (commits, PRs, people, last update)
- **Center:** live force-directed graph (react-force-graph-2d), color-coded by node type, optionally filtered by repo
- **Right rail upper:** entity resolution review queue (ambiguous identities awaiting decision)
- **Right rail lower:** live webhook firehose
- **Bottom strip:** time-travel slider with chapter markers (initial ingest, major decisions)

### 11.2 Color language

- Files: blue
- Symbols: cyan
- Commits: green
- PRs: orange
- Issues: yellow
- Discussions: pink
- Decisions: amber
- People: white (with platform-icon overlays)
- Superseded nodes: faded with strikethrough

---

## 12. Demo Script (5 minutes)

**0:00–0:30 — Hook.**
> "Every engineer has asked 'why is this code here?' and gotten silence. Today, that ends."

**0:30–1:30 — Live ingestion.**
- Dashboard: hit "Ingest Tokio" live on stage.
- Graph fills with thousands of nodes in real-time. People nodes resolve across GitHub + Slack data. PRs link to commits link to files link to symbols.
- ~3 minutes wall time; we narrate during it.

**1:30–3:00 — The Why panel (the product).**
- Open VS Code. Open Tokio's source. Click into `task::spawn` in `runtime/src/task/spawn.rs`.
- Right-click → "CodebaseOS: Why is this here?"
- Webview panel opens. 14-hop provenance chain renders.
- Click a referenced PR. New panel opens with that PR's full context including the linked issue, discussions, the deciding Decision.
- Click a Person. See every Decision they ever made across Tokio.

**3:00–4:00 — Chaos.**
- Judge presses "Author goes nuclear" — 47 functions now trace to someone unreachable; system suggests reviewers from `mentions` graph.
- Judge presses "Tamper with graph" — integrity badge turns red; click to find the broken Episode.
- Judge presses "Rewind 6 months" — slide back; click `task::spawn` again; provenance is what it was historically.

**4:00–4:30 — Without HydraDB.**
- Flip the toggle. Same line, same question. Vector-RAG returns a plausible-sounding but wrong attribution to a deprecated PR.
- "The kernel of difference is the graph underneath. Same source data. Same model. Different substrate."

**4:30–5:00 — Close.**
- Status bar: total spend, $3.47. "Real product. Real codebase. Real time. Three dollars."
- "Tokio was the demo. Your codebase is next. CodebaseOS launches today on the VS Code Marketplace."
- (If you actually publish: show the marketplace link. This is the moment that turns the hackathon into a product launch.)

---

## 13. 48-Hour Plan (Solo + Claude Code, 3 Parallel Sessions)

### Lanes
- **Lane B (Backend + Graph):** `/backend`, `/graph`, `/ingester`, `/cli`. The brain.
- **Lane E (Extension):** `/extension`. The product surface.
- **Lane D (Dashboard):** `/dashboard`, `/query`. The demo theater.

### Hour 0–3 — Foundation
- All: HydraDB account; schema implemented; smoke test passing
- Lane B: GitHub API client; ingest one commit + create Commit/File/Person/Identity nodes; Merkle chain extended
- Lane E: VS Code extension scaffold via `yo code`; hello-world hover provider; status bar
- Lane D: Next.js scaffold; force graph rendering mock nodes
- **Gate at hour 3:** if HydraDB doesn't support bi-temporal queries or entity resolution is going to be a multi-day rabbit hole, escalate

### Hour 3–10 — Vertical slice
- Lane B: full GitHub ingestion (commits, PRs, issues, reviews) for a small test repo. Deterministic entity resolution. First Decision extracted from a PR.
- Lane E: hover provider hitting `/summary` endpoint; code lens above functions; webview panel for `/why`
- Lane D: live graph reflecting real ingested data; entity resolution review queue UI

### Hour 10–14 — Sleep #1

### Hour 14–24 — Full ingestion + Why panel polished
- Lane B: tree-sitter symbol decomposition; supersession inference from PR text; heuristic entity resolution; constraint engine
- Lane E: webview panel formatting; clickable cross-references; "Five Whys" command; counterfactual command
- Lane D: cost meter wired; Merkle integrity badge; time-travel slider working; "Without HydraDB" toggle prep

### Hour 24–28 — Sleep #2

### Hour 28–38 — Webhooks + chaos + multi-repo + handoff
- Lane B: GitHub webhook endpoint receiving real-time updates; multi-repo cross-linking; `/handoff` endpoint
- Lane E: status bar polish; settings panel; auth flow with backend
- Lane D: 8 chaos buttons; live webhook firehose view; multi-repo graph visualization

### Hour 38–42 — Sleep #3

### Hour 42–46 — Polish + demo + publish
- 3 full demo rehearsals (ingest Tokio, run the script end-to-end, time each segment)
- Backup video by hour 44
- **Publish extension to VS Code Marketplace** (this is huge — it converts the demo into a real product launch). Process: package with `vsce package`; submit; takes minutes.
- Provenance OSS spinoff: extract `/ingester` + `/graph` as a standalone package, publish on GitHub with MIT license
- README polish, GIF, architecture diagram, comparison table

### Hour 46–48 — Submit, hydrate, sleep

---

## 14. Tech Stack

| Layer | Choice |
|---|---|
| Extension | VS Code Extension API + TypeScript |
| Backend | Python 3.12 + FastAPI + asyncio |
| Graph | HydraDB (bi-temporal + supersession) |
| LLM | OpenAI GPT-5.4 Mini (synthesizer + entity resolution + decision extraction) |
| Embeddings (baseline only) | OpenAI `text-embedding-3-small` |
| Vector baseline | FAISS (in-memory) |
| Tree parser | tree-sitter (rust, python, typescript, go bindings) |
| GitHub | PyGithub or raw httpx + GraphQL for performance |
| Webhooks | FastAPI endpoint behind ngrok for demo |
| Dashboard | Next.js 15 + Tailwind + react-force-graph-2d + framer-motion |
| Realtime | FastAPI WebSockets |
| Hosting | local + ngrok for live demo |

---

## 15. Cost Budget & Controls

### 15.1 Hard ceiling: $5

| Bucket | Estimate |
|---|---|
| Why panel queries (300 × $0.003) | $0.90 |
| Five-whys queries (50 × $0.015) | $0.75 |
| Counterfactual (20 × $0.05) | $1.00 |
| NL search queries (50 × $0.005) | $0.25 |
| Decision extraction (on-demand, ~50 PRs × $0.01) | $0.50 |
| Entity resolution LLM tie-break (~100 × $0.01) | $1.00 |
| Embedding for baseline (one-time per repo) | $0.30 |
| Handoff tour (10 × $0.02) | $0.20 |
| **Total** | **$4.90** |

### 15.2 Controls
- OpenAI console: hard cap **$5**.
- Synthesizer module is the only OpenAI caller. Single chokepoint.
- All calls write a `CostEvent` node. Dashboard top bar polls every 5s.
- Per-call cap: $0.05 default; raising requires `--expensive` flag + comment.
- Aggressive caching by (template_name, cache_key).
- Forbidden: Opus, GPT-5.5, any reasoning-tier model. Mini only.

### 15.3 What you don't spend on
- ❌ No background autonomous agents
- ❌ No continuous re-summarization
- ❌ No embedding the full codebase (only commit messages + PR descriptions for the baseline)
- ❌ No fine-tuning, no RAG with re-ranking, no agentic loops

---

## 16. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| HydraDB lacks native bi-temporal | Medium | High | Hour 1 spike. Fall back to `valid_time`/`valid_time_end` properties + manual indexing. Slower but works. |
| Entity resolution is harder than expected | High | Medium | Cap LLM-assisted to 100 cases per repo. Ship deterministic-only if heuristics fail. |
| GitHub API rate limit | Medium | Medium | Use GraphQL for bulk; authenticate; cache hard. For demo repo, pre-ingest and avoid live re-ingest. |
| Tokio is too big to ingest live | Medium | Medium | Pre-ingest 90% offline; do "live" ingest of the last 1K commits on stage. Honest framing. |
| VS Code extension activation slow | Low | Medium | Defer all work to user action; lazy-load. |
| Webhook demo flakes | Medium | Low | Pre-recorded webhook fixtures; replay through the live pipeline if real GitHub doesn't cooperate. |
| Cost overrun | Low | Medium | Hard $5 cap. Cost meter visible. Caching enforced. |
| Marketplace publish takes >30min | Low | Low | Publish at hour 42, not hour 47. |
| Solo burnout | High | Catastrophic | 3 enforced sleep blocks. No new features after hour 42. |

---

## 17. The Provenance OSS Spinoff

Lift `/ingester` + `/graph` + `/query` into a standalone framework.

```
provenance/
  README.md
  provenance/
    ingester/   git, github, slack, jira, etc.
    schema/     the bi-temporal schema
    cli/        cbos decide / ingest / why / verify
    synthesizer/ GPT-5.4 Mini wrapper with cost cap
    resolver/   entity resolution module
  examples/
    codebaseos/      link to CodebaseOS (the reference application)
    sample-repo/     a small example
  docs/
    schema.md
    bitemporal.md
    entity-resolution.md
```

This single move: hackathon → infrastructure contribution. Cost: ~4 hours by Lane B near the end.

---

## 18. Submission Checklist

- [ ] **VS Code extension published** to Marketplace (the product launch)
- [ ] **README.md** at root: pitch, 30s GIF of the Why panel, architecture diagram, install instructions
- [ ] **5-minute demo video** uploaded
- [ ] **Live demo URL** (ngrok'd dashboard)
- [ ] **HydraDB usage write-up**: which APIs, what schema, why vectors fail
- [ ] **"Without HydraDB" side-by-side** with concrete examples
- [ ] **Cost report**: actual inference spend (will be ~$3–4)
- [ ] **Public GitHub repo** (the main project)
- [ ] **Provenance OSS spinoff** repo published, MIT-licensed
- [ ] **Tweet thread** drafted, host and HydraDB tagged, link to Marketplace

---

## 19. The Pitch (memorize)

> "Every engineer has asked 'why is this code here?' and gotten silence. GitHub doesn't know. AI coding assistants don't know. The senior who decided it left two years ago. The Slack thread is gone.
>
> CodebaseOS is a VS Code extension that finally knows. We ingest your entire repo's history — commits, PRs, issues, reviews, Slack threads — into a bi-temporal HydraDB graph with multi-source entity resolution and cryptographic provenance. Right-click any line, get the full 14-hop origin story in 200 milliseconds.
>
> Live: I'll ingest Tokio's history on stage. Then I'll right-click `task::spawn` and you'll see why every piece of it exists, who decided it, what was rejected, when the original author left. Same query on a vector database — wrong answer. The graph is the moat.
>
> Three dollars in inference. Real product. Available on the Marketplace today. Want to try breaking it?"

---

## Appendix A — Sample "Why" Query Implementation

```python
# backend/query/why.py
async def why(file_path: str, line: int, repo_id: UUID, db, synthesizer) -> str:
    # 1. Find the symbol at this file:line
    symbol = await db.query("""
        MATCH (f:File {path: $path, repository_id: $repo})-[:defines]->(s:Symbol)
        WHERE s.line_range_start <= $line AND s.line_range_end >= $line
          AND s.valid_time_end IS NULL
        RETURN s
        LIMIT 1
    """, path=file_path, repo=repo_id, line=line)

    if not symbol:
        return await why_for_file(file_path, repo_id, db, synthesizer)

    # 2. Traverse provenance: 3 hops via produced/caused_by/supersedes/references/mentions
    traversal = await db.traverse(
        start=symbol.id,
        edges=["produced", "caused_by", "supersedes", "references", "mentions"],
        reverse=True,  # we want "what produced this"
        max_hops=3,
        max_nodes=30,
    )

    # 3. Identify the latest Decision(s) and the People
    decisions = [n for n in traversal.nodes if n.type == "Decision"]
    people = [n for n in traversal.nodes if n.type == "Person"]

    # 4. Resolve any unextracted decisions on-demand
    for prs_referenced in [n for n in traversal.nodes if n.type == "PR"]:
        if not prs_referenced.decisions_extracted:
            await extract_decisions_from_pr(prs_referenced.id, db, synthesizer)

    # 5. Synthesize a human-readable provenance chain
    cache_key = f"why:{symbol.id}:{traversal.head_hash}"
    payload = traversal.to_synthesizer_payload()  # compact JSON, ≤3K tokens
    answer = await synthesizer.synthesize(
        template_name="why_v1",
        graph_payload=payload,
        cache_key=cache_key,
    )

    return answer
```

## Appendix B — Things to NOT Do

- ❌ Don't try to ingest the entire GitHub on stage. Pick one repo. Tokio. That's it.
- ❌ Don't build a custom UI framework. VS Code's webview API is fine.
- ❌ Don't fine-tune. The Mini synthesizer is enough.
- ❌ Don't run autonomous agents. The graph is the cognition.
- ❌ Don't skip entity resolution — it's the moat. But cap it cleanly.
- ❌ Don't skip the Marketplace publish. It converts hackathon to product launch.
- ❌ Don't demo without a backup video.
- ❌ Don't go past hour 42 without polish-only mode.
- ❌ Don't skip sleep. A foggy demo loses to a rested one.

---

**The first code provenance system that actually knows. Real product. Real codebase. Three dollars.**

**Now go ship it.**
