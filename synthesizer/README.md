# synthesizer

The ONLY OpenAI caller in the entire project. Single chokepoint for cost control.

**Enforces:** $5 hard cap, $0.05/call max, ≤4K input tokens, 500 output tokens, aggressive caching, CostEvent logging.

**Forbidden:** calling OpenAI from any other module. No exceptions.

Lane B owns this directory.
