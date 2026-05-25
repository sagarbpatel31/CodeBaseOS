#!/usr/bin/env python3
"""
Chaos driver for the CodebaseOS demo (`make break`).

Drives the live chaos endpoints in sequence so you can narrate the integrity
story from a terminal while the dashboard reacts on screen:

    1. verify the chain is intact
    2. tamper  → one corrupted hash → Merkle badge turns red
    3. verify  → confirm the break is detected (and where)
    4. restore → chain re-verifies clean
    5. nuclear → an author "leaves"; their nodes orphan; reviewers suggested
    6. revive  → back to normal

Pure stdlib (urllib) so it runs with no extra dependencies. Point it at a
running backend via CBOS_BACKEND (default http://localhost:8000).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("CBOS_BACKEND", "http://localhost:8000").rstrip("/")


def _req(method: str, path: str) -> dict:
    url = f"{BASE}{path}"
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        try:
            detail = json.loads(detail).get("detail", detail)
        except Exception:
            pass
        return {"_error": f"HTTP {exc.code}: {detail}"}
    except urllib.error.URLError as exc:
        print(f"\n✗ Cannot reach backend at {BASE} ({exc.reason}).")
        print("  Start it first:  make backend   (or set CBOS_BACKEND)")
        sys.exit(1)


def _step(title: str) -> None:
    print(f"\n\033[1m▸ {title}\033[0m")


def main() -> None:
    print(f"CodebaseOS chaos driver → {BASE}")

    _step("Verify chain (baseline)")
    v = _req("GET", "/verify")
    print(f"  merkleOk={v.get('ok')}  length={v.get('chain_length')}  head={str(v.get('head_hash'))[:16]}…")

    _step("Tamper with the graph")
    t = _req("POST", "/chaos/tamper")
    if t.get("_error"):
        print(f"  {t['_error']}")
    else:
        tam = t.get("tampered", {})
        print(f"  corrupted Episode #{tam.get('sequence_no')} ({tam.get('action_type')})")
        print(f"  merkleOk={t.get('merkleOk')}  → badge should now be RED")
    time.sleep(1)

    _step("Verify chain (after tamper)")
    v = _req("GET", "/verify")
    print(f"  merkleOk={v.get('ok')}  broken_at={v.get('broken_at')}  tampered={v.get('tampered')}")
    time.sleep(1)

    _step("Restore the chain")
    r = _req("POST", "/chaos/restore")
    print(f"  merkleOk={r.get('merkleOk')}  → badge back to GREEN")
    time.sleep(1)

    _step("Author goes nuclear")
    n = _req("POST", "/chaos/nuclear")
    if n.get("_error"):
        print(f"  {n['_error']}")
    else:
        print(f"  {n.get('person')} left → {n.get('orphaned_count')} nodes orphaned")
        by_type = n.get("by_type", {})
        if by_type:
            print("  " + " · ".join(f"{c} {t}" for t, c in by_type.items()))
        revs = n.get("suggested_reviewers", [])
        if revs:
            print("  suggested reviewers: " + ", ".join(f"{x['name']} ({x['activity']})" for x in revs))
    time.sleep(1)

    _step("Revive author")
    _req("POST", "/chaos/revive")
    print("  orphans cleared")

    print("\n\033[1m✓ Chaos sequence complete.\033[0m")


if __name__ == "__main__":
    main()
