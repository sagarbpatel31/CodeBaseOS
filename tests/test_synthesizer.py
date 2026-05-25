"""
Synthesizer chokepoint tests (no credentials — uses a fake OpenAI client).

Covers the cost-discipline guarantees that make AGENTS.md invariant #8 real:
caching, output cap, and the hard budget gate.
"""

from __future__ import annotations

import types

import pytest

from synthesizer.synthesizer import BudgetExceeded, Synthesizer


class _FakeUsage:
    prompt_tokens = 1000
    completion_tokens = 200


def _fake_client():
    calls = {"n": 0, "last_kwargs": None}

    class _Completions:
        async def create(self, **kwargs):
            calls["n"] += 1
            calls["last_kwargs"] = kwargs
            msg = types.SimpleNamespace(content=f"answer-{calls['n']}")
            choice = types.SimpleNamespace(message=msg)
            return types.SimpleNamespace(choices=[choice], usage=_FakeUsage())

    client = types.SimpleNamespace(chat=types.SimpleNamespace(completions=_Completions()))
    return client, calls


async def test_cache_hit_is_free_and_skips_api():
    syn = Synthesizer(db=None)
    client, calls = _fake_client()
    syn._client = client

    r1 = await syn.complete(call_source="why", system="s", user="u", cache_key="k")
    assert r1.cached is False and r1.cost_usd > 0

    r2 = await syn.complete(call_source="why", system="s", user="u", cache_key="k")
    assert r2.cached is True and r2.cost_usd == 0.0
    assert r2.text == r1.text
    assert calls["n"] == 1  # only one real API call for two requests


async def test_output_tokens_capped_at_500():
    syn = Synthesizer(db=None)
    client, calls = _fake_client()
    syn._client = client

    await syn.complete(call_source="handoff", system="s", user="u", max_tokens=700, cache_key="k")
    assert calls["last_kwargs"]["max_tokens"] == 500


async def test_budget_gate_fails_closed():
    class _CapDB:
        async def get_total_cost(self):
            return 5.0

    syn = Synthesizer(db=_CapDB())
    client, _ = _fake_client()
    syn._client = client

    with pytest.raises(BudgetExceeded):
        await syn.complete(call_source="why", system="s", user="u", cache_key="x")


async def test_cache_key_none_never_caches():
    syn = Synthesizer(db=None)
    client, calls = _fake_client()
    syn._client = client

    await syn.complete(call_source="why", system="s", user="u")
    await syn.complete(call_source="why", system="s", user="u")
    assert calls["n"] == 2  # no cache_key → two real calls
