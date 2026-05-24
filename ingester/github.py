"""
GitHub ingestion source — Phase 1 minimal implementation.

Phase 1 scope: ingest a single commit, creating:
  - Repository node (if not exists)
  - Commit node
  - File nodes for changed files
  - Identity nodes for the author (pre-resolution)

Phase 2 will add: PR pagination, issue ingestion, review comments.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

import httpx

from graph.bitemporal import make_node, utc_now
from graph.client import HydraClient
from graph.merkle import extend_chain
from graph.schema import Commit, Episode, File, Identity, Issue, PR, Repository, ReviewComment


class GitHubIngester:
    """
    Ingests GitHub repository data into HydraDB.

    Uses GitHub REST API v3 with a PAT for authentication.
    """

    API_BASE = "https://api.github.com"

    def __init__(self, db: HydraClient, github_token: str) -> None:
        self.db = db
        self._http = httpx.AsyncClient(
            base_url=self.API_BASE,
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    @classmethod
    def from_env(cls, db: HydraClient) -> "GitHubIngester":
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            raise RuntimeError("GITHUB_TOKEN not set")
        return cls(db=db, github_token=token)

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Low-level GitHub API calls
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        resp = await self._http.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}")

    async def get_commit(self, owner: str, repo: str, sha: str) -> dict[str, Any]:
        return await self._get(f"/repos/{owner}/{repo}/commits/{sha}")

    async def get_pulls(self, owner: str, repo: str, limit: int) -> list[dict[str, Any]]:
        return await self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": "all", "per_page": limit, "sort": "updated", "direction": "desc"},
        )

    async def get_pull_review_comments(self, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
        return await self._get(f"/repos/{owner}/{repo}/pulls/{number}/comments", params={"per_page": 30})

    async def get_issues(self, owner: str, repo: str, limit: int) -> list[dict[str, Any]]:
        # NOTE: the issues endpoint also returns PRs; callers filter on "pull_request".
        # Over-fetch so that after skipping PRs we still have enough real issues.
        per_page = min(100, max(limit * 4, 30))
        return await self._get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": "all", "per_page": per_page, "sort": "updated", "direction": "desc"},
        )

    # ------------------------------------------------------------------
    # Episode management
    # ------------------------------------------------------------------

    async def _new_episode(
        self,
        action_type: str,
        repo_id: UUID,
        sequence_no: int,
        prev_hash: str = "",
    ) -> Episode:
        ep = make_node(
            Episode,
            episode_id=uuid4(),
            source="github",
            sequence_no=sequence_no,
            action_type=action_type,
            inputs_hash="",
            outputs_hash="",
            valid_time=utc_now(),
        )
        # Chain it
        ep = extend_chain(ep, prev_hash=prev_hash)
        return ep

    # ------------------------------------------------------------------
    # Repository ingestion
    # ------------------------------------------------------------------

    async def ensure_repository(
        self,
        owner: str,
        repo: str,
        episode_id: UUID,
    ) -> tuple[Repository, str]:
        """
        Create (or return existing) Repository node.
        Returns (Repository, source_id).
        """
        data = await self.get_repo(owner, repo)
        repo_node = make_node(
            Repository,
            episode_id=episode_id,
            source="github",
            name=f"{owner}/{repo}",
            github_id=data.get("id"),
            default_branch=data.get("default_branch", "main"),
        )
        sid = await self.db.write_node(repo_node)
        return repo_node, sid

    # ------------------------------------------------------------------
    # Single commit ingestion (Phase 1 goal)
    # ------------------------------------------------------------------

    async def ingest_one_commit(
        self,
        owner: str,
        repo: str,
        sha: str,
        repo_id: UUID,
        episode: Episode,
    ) -> dict[str, Any]:
        """
        Ingest one commit from GitHub, creating:
          - Commit node
          - File nodes for each changed file
          - Identity node for the author

        Returns a summary dict with node IDs.
        """
        data = await self.get_commit(owner, repo, sha)

        git_author = data.get("commit", {}).get("author", {})
        author_name = git_author.get("name", "")
        author_email = git_author.get("email", "")
        committed_at_str = git_author.get("date", "")
        committed_at = (
            datetime.fromisoformat(committed_at_str.replace("Z", "+00:00"))
            if committed_at_str
            else utc_now()
        )

        # --- Identity node (pre-resolution) ---
        identity = make_node(
            Identity,
            episode_id=episode.id,
            source="github",
            platform="git",
            username=author_name,
            email=author_email,
            valid_time=committed_at,
        )
        identity_id = await self.db.write_node(identity)

        # --- Commit node ---
        parents = [p["sha"] for p in data.get("parents", [])]
        stats = data.get("stats", {})
        commit_node = make_node(
            Commit,
            episode_id=episode.id,
            source="github",
            sha=sha,
            message=data.get("commit", {}).get("message", ""),
            author_name=author_name,
            author_email=author_email,
            parents=parents,
            files_changed=len(data.get("files", [])),
            additions=stats.get("additions", 0),
            deletions=stats.get("deletions", 0),
            repository_id=repo_id,
            valid_time=committed_at,
        )
        commit_id = await self.db.write_node(commit_node, relations=[identity_id])

        # --- File nodes ---
        file_ids = []
        for gh_file in data.get("files", []):
            file_path = gh_file.get("filename", "")
            ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
            lang_map = {"py": "python", "ts": "typescript", "js": "javascript", "rs": "rust", "go": "go"}
            lang = lang_map.get(ext, ext)
            file_hash = hashlib.sha256(file_path.encode()).hexdigest()[:16]

            file_node = make_node(
                File,
                episode_id=episode.id,
                source="github",
                repository_id=repo_id,
                path=file_path,
                current_hash=file_hash,
                language=lang,
                valid_time=committed_at,
            )
            fid = await self.db.write_node(file_node, relations=[commit_id])
            file_ids.append(fid)

        return {
            "commit_id": commit_id,
            "identity_id": identity_id,
            "file_ids": file_ids,
            "sha": sha,
            "author": author_name,
            "message": commit_node.message[:100],
            "files_changed": len(file_ids),
        }

    # ------------------------------------------------------------------
    # PR + Issue ingestion (Phase 2)
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_dt(value: Optional[str]) -> datetime:
        if not value:
            return utc_now()
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    async def ingest_pr(
        self,
        owner: str,
        repo: str,
        pr_data: dict[str, Any],
        repo_id: UUID,
        episode: Episode,
        with_reviews: bool = True,
    ) -> dict[str, Any]:
        """Ingest one PR: PR node + author Identity + review comments."""
        number = pr_data.get("number", 0)
        user = pr_data.get("user") or {}
        author_login = user.get("login", "")
        created_at = self._parse_dt(pr_data.get("created_at"))
        merged_at = self._parse_dt(pr_data.get("merged_at")) if pr_data.get("merged_at") else None
        state = "merged" if pr_data.get("merged_at") else pr_data.get("state", "open")

        # Author identity (github platform — distinct from git-author identity)
        identity = make_node(
            Identity,
            episode_id=episode.id,
            source="github",
            platform="github",
            platform_user_id=str(user.get("id", "")),
            username=author_login,
            email="",
            valid_time=created_at,
        )
        identity_id = await self.db.write_node(identity)

        pr_node = make_node(
            PR,
            episode_id=episode.id,
            source="github",
            number=number,
            title=pr_data.get("title", ""),
            description=(pr_data.get("body") or "")[:1000],
            state=state,
            author_name=author_login,
            merged_at=merged_at,
            repository_id=repo_id,
            valid_time=created_at,
        )
        pr_id = await self.db.write_node(pr_node, relations=[identity_id])

        review_ids: list[str] = []
        if with_reviews:
            try:
                comments = await self.get_pull_review_comments(owner, repo, number)
            except Exception:
                comments = []
            for c in comments[:20]:
                c_user = c.get("user") or {}
                rc = make_node(
                    ReviewComment,
                    episode_id=episode.id,
                    source="github",
                    pr_id=pr_node.id,
                    line_start=c.get("line") or 0,
                    line_end=c.get("line") or 0,
                    author_name=c_user.get("login", ""),
                    body=(c.get("body") or "")[:1000],
                    valid_time=self._parse_dt(c.get("created_at")),
                )
                rid = await self.db.write_node(rc, relations=[pr_id])
                review_ids.append(rid)

        return {
            "pr_id": pr_id,
            "number": number,
            "title": pr_node.title[:80],
            "author": author_login,
            "state": state,
            "review_count": len(review_ids),
        }

    async def ingest_issue(
        self,
        issue_data: dict[str, Any],
        repo_id: UUID,
        episode: Episode,
    ) -> dict[str, Any]:
        """Ingest one Issue: Issue node + author Identity."""
        number = issue_data.get("number", 0)
        user = issue_data.get("user") or {}
        author_login = user.get("login", "")
        created_at = self._parse_dt(issue_data.get("created_at"))
        labels = [lbl.get("name", "") for lbl in (issue_data.get("labels") or []) if isinstance(lbl, dict)]

        identity = make_node(
            Identity,
            episode_id=episode.id,
            source="github",
            platform="github",
            platform_user_id=str(user.get("id", "")),
            username=author_login,
            email="",
            valid_time=created_at,
        )
        identity_id = await self.db.write_node(identity)

        issue_node = make_node(
            Issue,
            episode_id=episode.id,
            source="github",
            number=number,
            title=issue_data.get("title", ""),
            body=(issue_data.get("body") or "")[:1000],
            state=issue_data.get("state", "open"),
            author_name=author_login,
            labels=labels,
            repository_id=repo_id,
            valid_time=created_at,
        )
        issue_id = await self.db.write_node(issue_node, relations=[identity_id])

        return {
            "issue_id": issue_id,
            "number": number,
            "title": issue_node.title[:80],
            "author": author_login,
            "state": issue_node.state,
        }
