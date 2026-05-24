# resolver

Multi-source entity resolution: deterministic → heuristic → LLM-assisted (capped at 100 calls/repo).

**Three-tier pipeline:**
1. `deterministic.py` — exact email/username match (free)
2. `heuristic.py` — fuzzy name + activity-window correlation (free)
3. `llm_assist.py` — GPT-5.4 Mini tie-breaking, hard-capped at 100 cases (Phase 4)

Lane B owns this directory.
