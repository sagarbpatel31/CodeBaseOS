"""
The single OpenAI chokepoint for CodebaseOS (AGENTS.md INVARIANT #8).

EVERY OpenAI call in the system goes through `Synthesizer.complete()`. Nothing
else may import `openai`. This is the module that makes the cost-discipline
pitch true rather than aspirational. It enforces:

  - Hard $5 budget — fails closed (BudgetExceeded) once total spend hits the cap.
  - Per-call $0.05 cap — worst-case cost of a single call is bounded.
  - Input truncation — at most ~4K tokens of prompt are sent to the model.
  - Output cap — at most 500 completion tokens.
  - Response caching — keyed by (call_source, cache_key); repeat clicks are free.
  - Cost logging — a CostEvent node is written to the graph for every paid call.

Pricing constants are for gpt-4o-mini (the only permitted model).
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

# gpt-4o-mini pricing, USD per token.
_INPUT_RATE = 0.00000015
_OUTPUT_RATE = 0.0000006

MODEL = "gpt-4o-mini"
COST_CAP_USD = 5.00
PER_CALL_CAP_USD = 0.05
MAX_INPUT_TOKENS = 4000
MAX_OUTPUT_TOKENS = 500

# Cache bounds. The TTL caps how long a cached answer can lag the graph (so new
# ingests/decisions for the same location are eventually reflected); the max
# entry count bounds memory since several endpoints pass free-form cache keys.
CACHE_TTL_SECONDS = 300.0
CACHE_MAX_ENTRIES = 512


class BudgetExceeded(Exception):
    """Hard cost cap reached. The backend maps this to HTTP 402."""

    def __init__(self, spent: float, cap: float = COST_CAP_USD) -> None:
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"Cost cap reached: ${spent:.4f} / ${cap:.2f}. LLM calls disabled."
        )


@dataclass
class SynthesisResult:
    text: str
    cost_usd: float
    cached: bool
    input_tokens: int
    output_tokens: int


def _approx_tokens(text: str) -> int:
    """~4 chars/token heuristic — avoids a tokenizer dependency."""
    return max(1, len(text) // 4)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    limit = max(0, max_tokens) * 4
    return text if len(text) <= limit else text[:limit]


class Synthesizer:
    """Owns the one AsyncOpenAI client, the response cache, and cost logging.

    `db` is a graph.client.HydraClient (or None when offline). It is used to
    read total spend (budget gate) and to persist CostEvent nodes.
    """

    def __init__(
        self,
        db: Any = None,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
        cache_max_entries: int = CACHE_MAX_ENTRIES,
    ) -> None:
        self._db = db
        self._client: Any = None
        # (call_source, cache_key) -> (result, expires_at). OrderedDict gives LRU.
        self._cache: "OrderedDict[tuple[str, str], tuple[SynthesisResult, float]]" = OrderedDict()
        self._cache_ttl = cache_ttl_seconds
        self._cache_max = max(1, cache_max_entries)

    def _cache_get(self, key: tuple[str, str]) -> Optional[SynthesisResult]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, expires_at = entry
        if self._cache_ttl > 0 and time.monotonic() >= expires_at:
            self._cache.pop(key, None)  # stale → drop, forces a fresh synthesis
            return None
        self._cache.move_to_end(key)  # mark most-recently-used
        return result

    def _cache_put(self, key: tuple[str, str], result: SynthesisResult) -> None:
        self._cache[key] = (result, time.monotonic() + self._cache_ttl)
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_max:
            self._cache.popitem(last=False)  # evict least-recently-used

    def _oai(self) -> Any:
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        return self._client

    async def _spent(self) -> float:
        if self._db is None:
            return 0.0
        return await self._db.get_total_cost()

    async def complete(
        self,
        *,
        call_source: str,
        system: str,
        user: str,
        max_tokens: int = MAX_OUTPUT_TOKENS,
        response_format: Optional[dict] = None,
        cache_key: Optional[str] = None,
    ) -> SynthesisResult:
        """Run one bounded, budgeted, cached completion.

        Raises BudgetExceeded if the hard cap is already reached.
        """
        # 1. Cache hit (fresh) → free, no API call, no new CostEvent.
        ck = (call_source, cache_key) if cache_key is not None else None
        if ck is not None:
            hit = self._cache_get(ck)
            if hit is not None:
                return SynthesisResult(hit.text, 0.0, True, hit.input_tokens, hit.output_tokens)

        # 2. Hard budget gate — fail closed.
        spent = await self._spent()
        if spent >= COST_CAP_USD:
            raise BudgetExceeded(spent)

        # 3. Bound the request: truncate input, cap output.
        out_cap = max(1, min(max_tokens, MAX_OUTPUT_TOKENS))
        budget_for_user = MAX_INPUT_TOKENS - _approx_tokens(system)
        user = _truncate_to_tokens(user, budget_for_user)

        # 4. Per-call worst-case guard (defensive; trivially satisfied by mini).
        worst_case = (MAX_INPUT_TOKENS * _INPUT_RATE) + (out_cap * _OUTPUT_RATE)
        if worst_case > PER_CALL_CAP_USD:
            raise BudgetExceeded(spent)

        kwargs: dict[str, Any] = {
            "model": MODEL,
            "max_tokens": out_cap,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        chat = await self._oai().chat.completions.create(**kwargs)
        usage = chat.usage
        text = chat.choices[0].message.content or ""
        cost = (usage.prompt_tokens * _INPUT_RATE) + (usage.completion_tokens * _OUTPUT_RATE)
        await self._log_cost(usage, cost, call_source)

        result = SynthesisResult(
            text=text,
            cost_usd=cost,
            cached=False,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
        )
        if ck is not None:
            self._cache_put(ck, result)
        return result

    async def _log_cost(self, usage: Any, cost: float, call_source: str) -> None:
        if self._db is None:
            return
        from graph.bitemporal import make_node
        from graph.schema import CostEvent

        node = make_node(
            CostEvent,
            episode_id=uuid4(),
            source="openai",
            model=MODEL,
            cost_usd=cost,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            call_source=call_source,
        )
        await self._db.write_node(node)
