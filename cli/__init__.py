"""
CodebaseOS CLI — `cbos` command.

Available commands:
  cbos decide   Record an architectural decision to HydraDB + Merkle chain.
  cbos verify   Walk the Merkle chain end-to-end and report integrity.
  cbos ingest   Ingest a GitHub repository.
  cbos cost     Print current OpenAI spend.
"""

from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import click
from dotenv import load_dotenv

load_dotenv()

from graph.bitemporal import make_node, utc_now
from graph.client import HydraClient
from graph.merkle import extend_chain, verify_chain
from graph.schema import Decision, Episode


def _get_db() -> HydraClient:
    return HydraClient.from_env()


# ---------------------------------------------------------------------------
# Main group
# ---------------------------------------------------------------------------

@click.group()
def main() -> None:
    """CodebaseOS CLI."""


# ---------------------------------------------------------------------------
# cbos decide
# ---------------------------------------------------------------------------

@main.command()
@click.argument("summary")
@click.option("--rationale", "-r", default="", help="Why this decision was made.")
@click.option("--actor", "-a", default="human", help="Who made the decision (e.g. claude-code:backend).")
@click.option("--supersedes", "-s", default="", help="Prior decision ID this supersedes (if any).")
@click.option("--confidence", "-c", default="medium", type=click.Choice(["low", "medium", "high"]), help="Confidence level.")
def decide(summary: str, rationale: str, actor: str, supersedes: str, confidence: str) -> None:
    """
    Record an architectural decision.

    Per AGENTS.md §"Decision-making protocol":
    Every design decision must go through cbos decide.
    The CLI writes the Decision to HydraDB; Merkle chain extends automatically.

    Example:
        cbos decide "Use HydraDB memories for node storage" \\
            --rationale "HydraDB is a memory/recall system, not a graph DB; memories with metadata best fit our node model" \\
            --actor "claude-code:backend"
    """

    async def _run() -> None:
        db = _get_db()
        await db.ensure_tenant()

        # Create Episode for this decision
        episodes = await db.get_episodes_ordered()
        prev_hash = episodes[-1]["merkle_hash"] if episodes else ""
        seq = len(episodes)

        ep = make_node(
            Episode,
            episode_id=uuid4(),
            source="manual",
            sequence_no=seq,
            action_type="decide",
            valid_time=utc_now(),
        )
        ep = extend_chain(ep, prev_hash=prev_hash)
        await db.write_node(ep)

        # Create Decision node
        decision_id = f"D{seq:04d}"
        decision = make_node(
            Decision,
            episode_id=ep.id,
            source="manual",
            summary=summary,
            rationale=rationale,
            actor=actor,
            confidence=confidence,
            decision_id=decision_id,
            valid_time=utc_now(),
        )
        sid = await db.write_node(decision)

        click.echo(f"Decision recorded: {decision_id}")
        click.echo(f"  Summary:    {summary}")
        click.echo(f"  Actor:      {actor}")
        click.echo(f"  Confidence: {confidence}")
        click.echo(f"  Merkle:     {ep.merkle_hash[:16]}…")
        click.echo(f"  source_id:  {sid}")
        if supersedes:
            click.echo(f"  Supersedes: {supersedes}  (add supersedes edge in Phase 2)")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# cbos verify
# ---------------------------------------------------------------------------

@main.command()
def rechain() -> None:
    """Repair the Merkle chain: re-link all Episodes by tx_time and recompute hashes."""

    async def _run() -> None:
        db = _get_db()
        await db.ensure_tenant()
        result = await db.repair_merkle_chain()
        click.echo(click.style("✓ Merkle chain rebuilt", fg="green"))
        click.echo(f"  Episodes re-linked: {result['repaired']}")
        click.echo(f"  New head hash:      {result['head_hash'][:32]}…")
        # Re-verify after a short pause for indexing.
        import asyncio as _aio
        await _aio.sleep(3)
        check = await verify_chain(db)
        status = click.style("intact", fg="green") if check.ok else click.style(f"BROKEN at {check.broken_at}", fg="red")
        click.echo(f"  Verify: {status} (length {check.chain_length})")

    asyncio.run(_run())


@main.command()
def verify() -> None:
    """Walk the Merkle chain end-to-end and report integrity."""

    async def _run() -> None:
        db = _get_db()
        result = await verify_chain(db)
        if result.ok:
            click.echo(click.style("✓ Merkle chain intact", fg="green"))
            click.echo(f"  Chain length: {result.chain_length}")
            click.echo(f"  Head hash:    {result.head_hash[:32] if result.head_hash else '(empty)'}…")
        else:
            click.echo(click.style("✗ Merkle chain BROKEN", fg="red"))
            click.echo(f"  Broken at episode: {result.broken_at}")
            click.echo(f"  Chain length:      {result.chain_length}")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# cbos ingest
# ---------------------------------------------------------------------------

@main.command()
@click.argument("repo", metavar="OWNER/REPO")
@click.option("--sha", default=None, help="Commit SHA to ingest (single commit; mutually exclusive with --limit > 1).")
@click.option("--limit", default=1, show_default=True, help="Number of recent commits to ingest (fetched from GitHub API).")
@click.option("--prs", default=0, show_default=True, help="Number of recent PRs to ingest (with review comments).")
@click.option("--issues", default=0, show_default=True, help="Number of recent issues to ingest.")
def ingest(repo: str, sha: str | None, limit: int, prs: int, issues: int) -> None:
    """
    Ingest a GitHub repository commit(s).

    By default ingests only the latest commit (HEAD).  Pass --limit N to
    ingest the N most-recent commits, each as its own Episode in the
    Merkle chain.

    Examples:

        cbos ingest tokio-rs/tokio

        cbos ingest tokio-rs/tokio --sha abc123

        cbos ingest tokio-rs/tokio --limit 10
    """
    from ingester.github import GitHubIngester

    if "/" not in repo:
        click.echo("Error: REPO must be in OWNER/REPO format", err=True)
        raise SystemExit(1)

    if sha is not None and limit > 1:
        click.echo("Error: --sha and --limit > 1 are mutually exclusive", err=True)
        raise SystemExit(1)

    owner, repo_name = repo.split("/", 1)

    async def _run() -> None:
        db = _get_db()
        ingester = GitHubIngester.from_env(db)
        try:
            click.echo(f"Repository: {owner}/{repo_name}")

            # Ensure the repository node exists (shared across all episodes).
            # We need a temporary episode reference for ensure_repository; we
            # will create real episodes per-commit below, but ensure_repository
            # only needs the episode id for the edge, so we pass the first
            # episode's id after we create it.  Instead, fetch commits first so
            # we can wire everything up properly.

            # --- Resolve the list of commit SHAs to ingest ---
            if sha is not None:
                # Single explicit SHA
                commits_meta = [{"sha": sha, "author": None, "message": None}]
            else:
                # Fetch `limit` commits from the GitHub API
                data = await ingester._get(
                    f"/repos/{owner}/{repo_name}/commits",
                    params={"per_page": limit},
                )
                if not data:
                    click.echo("No commits returned from GitHub API.", err=True)
                    raise SystemExit(1)
                # API returns newest-first; we ingest oldest-to-newest so the
                # Merkle chain grows in chronological order.
                commits_meta = list(reversed(data))

            total = len(commits_meta)

            # --- Fetch current chain tail once before the loop ---
            episodes = await db.get_episodes_ordered()
            prev_hash = episodes[-1]["merkle_hash"] if episodes else ""
            seq = len(episodes)

            # --- Ensure repository node (use a synthetic episode id for the
            #     edge; the ingester stores it as a foreign-key reference only)
            # We create the first real episode up-front so ensure_repository
            # has a valid episode id.
            first_commit_entry = commits_meta[0]
            first_sha = first_commit_entry["sha"] if isinstance(first_commit_entry, dict) and "sha" in first_commit_entry else first_commit_entry

            ep0 = make_node(
                Episode,
                episode_id=uuid4(),
                source="github",
                sequence_no=seq,
                action_type="ingest_commit",
                valid_time=utc_now(),
            )
            ep0 = extend_chain(ep0, prev_hash=prev_hash)
            await db.write_node(ep0)

            repo_node, _repo_sid = await ingester.ensure_repository(owner, repo_name, ep0.id)

            # --- Ingest loop ---
            episodes_created = [ep0]

            for idx, commit_entry in enumerate(commits_meta):
                if isinstance(commit_entry, dict):
                    target_sha = commit_entry["sha"]
                    # Extract author/message for progress display if available
                    author_raw = commit_entry.get("commit", {}).get("author", {}).get("name") \
                        or commit_entry.get("author") \
                        or "unknown"
                    msg_raw = commit_entry.get("commit", {}).get("message", "") \
                        or commit_entry.get("message", "")
                    msg_short = msg_raw.splitlines()[0][:72] if msg_raw else ""
                else:
                    target_sha = commit_entry
                    author_raw = "unknown"
                    msg_short = ""

                # Reuse ep0 for the first commit (already written); create new
                # episodes for subsequent commits.
                if idx == 0:
                    ep = ep0
                else:
                    prev_hash = episodes_created[-1].merkle_hash
                    seq_cur = seq + idx
                    ep = make_node(
                        Episode,
                        episode_id=uuid4(),
                        source="github",
                        sequence_no=seq_cur,
                        action_type="ingest_commit",
                        valid_time=utc_now(),
                    )
                    ep = extend_chain(ep, prev_hash=prev_hash)
                    await db.write_node(ep)
                    episodes_created.append(ep)

                # Progress line shown before ingestion
                progress_label = f"[{idx + 1}/{total}] Commit: {target_sha[:12]} by {author_raw}"
                if msg_short:
                    progress_label += f" — {msg_short}"
                click.echo(progress_label)

                result = await ingester.ingest_one_commit(
                    owner, repo_name, target_sha, repo_node.id, ep
                )
                click.echo(f"  Files:   {result['files_changed']}")
                click.echo(f"  Merkle:  {ep.merkle_hash[:16]}…")

            # --- PR ingestion (Phase 2) ---
            if prs > 0:
                click.echo(f"\nPRs: fetching {prs} most-recently-updated…")
                pr_list = await ingester.get_pulls(owner, repo_name, prs)
                for pr_data in pr_list[:prs]:
                    prev_hash = episodes_created[-1].merkle_hash
                    ep = make_node(
                        Episode, episode_id=uuid4(), source="github",
                        sequence_no=seq + len(episodes_created),
                        action_type="ingest_pr", valid_time=utc_now(),
                    )
                    ep = extend_chain(ep, prev_hash=prev_hash)
                    await db.write_node(ep)
                    episodes_created.append(ep)
                    r = await ingester.ingest_pr(owner, repo_name, pr_data, repo_node.id, ep)
                    click.echo(f"  PR #{r['number']} [{r['state']}] by {r['author']} — {r['title']} ({r['review_count']} reviews)")

            # --- Issue ingestion (Phase 2) ---
            if issues > 0:
                click.echo(f"\nIssues: fetching {issues} most-recently-updated…")
                issue_list = await ingester.get_issues(owner, repo_name, issues)
                count = 0
                for issue_data in issue_list:
                    if count >= issues:
                        break
                    # The issues endpoint also returns PRs — skip those.
                    if "pull_request" in issue_data:
                        continue
                    prev_hash = episodes_created[-1].merkle_hash
                    ep = make_node(
                        Episode, episode_id=uuid4(), source="github",
                        sequence_no=seq + len(episodes_created),
                        action_type="ingest_issue", valid_time=utc_now(),
                    )
                    ep = extend_chain(ep, prev_hash=prev_hash)
                    await db.write_node(ep)
                    episodes_created.append(ep)
                    r = await ingester.ingest_issue(issue_data, repo_node.id, ep)
                    click.echo(f"  Issue #{r['number']} [{r['state']}] by {r['author']} — {r['title']}")
                    count += 1

        finally:
            await ingester.close()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# cbos cost
# ---------------------------------------------------------------------------

@main.command()
def cost() -> None:
    """Print current OpenAI spend and remaining budget."""

    async def _run() -> None:
        db = _get_db()
        spent = await db.get_total_cost()
        cap = 5.00
        pct = (spent / cap) * 100 if cap > 0 else 0
        color = "green" if spent < 3.5 else ("yellow" if spent < 4.5 else "red")
        click.echo(click.style(f"${spent:.4f} / ${cap:.2f} ({pct:.1f}%)", fg=color))

    asyncio.run(_run())
