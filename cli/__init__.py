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
@click.option("--sha", default="HEAD", help="Commit SHA to ingest (Phase 1: single commit).")
def ingest(repo: str, sha: str) -> None:
    """
    Ingest a GitHub repository (Phase 1: single commit).

    Example:
        cbos ingest tokio-rs/tokio --sha abc123
    """
    from ingester.github import GitHubIngester

    if "/" not in repo:
        click.echo("Error: REPO must be in OWNER/REPO format", err=True)
        raise SystemExit(1)

    owner, repo_name = repo.split("/", 1)

    async def _run() -> None:
        db = _get_db()
        ingester = GitHubIngester.from_env(db)
        try:
            # Episode
            episodes = await db.get_episodes_ordered()
            prev_hash = episodes[-1]["merkle_hash"] if episodes else ""
            seq = len(episodes)

            ep = make_node(
                Episode,
                episode_id=uuid4(),
                source="github",
                sequence_no=seq,
                action_type="ingest_commit",
                valid_time=utc_now(),
            )
            ep = extend_chain(ep, prev_hash=prev_hash)
            await db.write_node(ep)

            # Repository
            repo_node, _repo_sid = await ingester.ensure_repository(owner, repo_name, ep.id)
            click.echo(f"Repository: {owner}/{repo_name}")

            # Resolve SHA if HEAD
            target_sha = sha
            if sha == "HEAD":
                data = await ingester._get(f"/repos/{owner}/{repo_name}/commits", params={"per_page": 1})
                target_sha = data[0]["sha"] if data else sha
                click.echo(f"Resolved HEAD → {target_sha[:12]}")

            result = await ingester.ingest_one_commit(
                owner, repo_name, target_sha, repo_node.id, ep
            )
            click.echo(f"Commit: {result['sha'][:12]} by {result['author']}")
            click.echo(f"  Message: {result['message']}")
            click.echo(f"  Files:   {result['files_changed']}")
            click.echo(f"  Merkle:  {ep.merkle_hash[:16]}…")
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
