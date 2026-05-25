"""
Deterministic entity resolution for Identity → Person.

Clusters Identity nodes into people using deterministic rules (no LLM):

  Strong (auto-merge):
    - identical, non-empty email
    - identical, non-empty (platform, platform_user_id)

  Weak (review queue, not auto-merged):
    - a git-author name that, normalized, equals a github login
      (e.g. git "Mattia Pitossi" ↔ github "mattiapitossi")

Pure functions over identity dicts so they can be reused by both the
/er-queue read endpoint and the `cbos resolve` write command.
"""

from __future__ import annotations

import re
from typing import Any


def _norm_name(s: str) -> str:
    """Lowercase, strip non-alphanumerics. 'Mattia Pitossi' -> 'mattiapitossi'."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class _UnionFind:
    def __init__(self, items: list[str]) -> None:
        self.parent = {i: i for i in items}

    def find(self, x: str) -> str:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def resolve_identities(identities: list[dict[str, Any]]) -> dict[str, Any]:
    """
    identities: list of {id, dm:{username,email,platform,platform_user_id}}

    Returns:
      {
        "clusters": [ {person_name, primary_email, identity_ids:[...],
                       members:[{id,username,email,platform}]} ],
        "pending":  [ {a:{...}, b:{...}, reason, confidence} ],
        "stats": {identities, people, auto_merged, pending}
      }
    """
    ids = [i["id"] for i in identities if i.get("id")]
    uf = _UnionFind(ids)
    by_id = {i["id"]: i for i in identities if i.get("id")}

    # --- Strong signals -> union ---
    by_email: dict[str, list[str]] = {}
    by_platform_uid: dict[str, list[str]] = {}
    by_platform_user: dict[str, list[str]] = {}
    for i in identities:
        nid = i.get("id")
        if not nid:
            continue
        dm = i.get("dm") or {}
        email = (dm.get("email") or "").strip().lower()
        platform = (dm.get("platform") or "").strip().lower()
        puid = (dm.get("platform_user_id") or "").strip()
        uname = (dm.get("username") or "").strip().lower()
        if email:
            by_email.setdefault(email, []).append(nid)
        if platform and puid:
            by_platform_uid.setdefault(f"{platform}:{puid}", []).append(nid)
        # Same login on the same platform = same account = same person.
        # (Repeated ingests create one Identity node per event for the same user.)
        if platform and uname:
            by_platform_user.setdefault(f"{platform}:{uname}", []).append(nid)

    for group in (
        list(by_email.values())
        + list(by_platform_uid.values())
        + list(by_platform_user.values())
    ):
        for other in group[1:]:
            uf.union(group[0], other)

    # --- Build clusters ---
    cluster_map: dict[str, list[str]] = {}
    for nid in ids:
        cluster_map.setdefault(uf.find(nid), []).append(nid)

    clusters = []
    for root, members in cluster_map.items():
        names: dict[str, int] = {}
        emails: list[str] = []
        member_objs = []
        for nid in members:
            dm = by_id[nid].get("dm") or {}
            uname = dm.get("username") or ""
            email = dm.get("email") or ""
            if uname:
                names[uname] = names.get(uname, 0) + 1
            if email and email not in emails:
                emails.append(email)
            member_objs.append({
                "id": nid,
                "username": uname,
                "email": email,
                "platform": dm.get("platform") or "",
            })
        person_name = max(names, key=names.get) if names else (emails[0] if emails else "unknown")
        clusters.append({
            "person_name": person_name,
            "primary_email": emails[0] if emails else "",
            "identity_ids": members,
            "members": member_objs,
        })

    # --- Weak signals -> review queue (cross-cluster name ~ login) ---
    # Map normalized name -> representative cluster index for git identities;
    # propose merges with github logins that normalize to the same token.
    norm_to_clusters: dict[str, set[int]] = {}
    for idx, c in enumerate(clusters):
        for m in c["members"]:
            for token in (m["username"],):
                n = _norm_name(token)
                if n:
                    norm_to_clusters.setdefault(n, set()).add(idx)

    pending = []
    seen_pairs: set[tuple[int, int]] = set()
    for norm, idxs in norm_to_clusters.items():
        if len(idxs) < 2:
            continue
        idx_list = sorted(idxs)
        for a in range(len(idx_list)):
            for b in range(a + 1, len(idx_list)):
                ia, ib = idx_list[a], idx_list[b]
                key = (ia, ib)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                pending.append({
                    "a": {"person_name": clusters[ia]["person_name"],
                          "primary_email": clusters[ia]["primary_email"]},
                    "b": {"person_name": clusters[ib]["person_name"],
                          "primary_email": clusters[ib]["primary_email"]},
                    "reason": f"name~login match: '{norm}'",
                    "confidence": "medium",
                })

    auto_merged = sum(1 for c in clusters if len(c["identity_ids"]) > 1)
    return {
        "clusters": clusters,
        "pending": pending,
        "stats": {
            "identities": len(ids),
            "people": len(clusters),
            "auto_merged": auto_merged,
            "pending": len(pending),
        },
    }
