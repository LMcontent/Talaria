"""Track token usage — and optionally its estimated $ cost — across a
whole session, including any sub-agents spawned via delegate_task (they
share the same UsageTracker instance, so a limit/estimate reflects the
true session total, not just the top-level agent's own calls).

Cost estimation is opt-in and manual (TOKEN_PRICE_INPUT_PER_M /
TOKEN_PRICE_OUTPUT_PER_M in .env): there's no reliable way to look up a
model's price automatically, since it varies by provider, router, and
model, and routers like OrcaRouter/OpenRouter serve a large, changing
catalog. Left at 0 (default), no cost is shown — only the raw token count.
"""

from dataclasses import dataclass


@dataclass
class UsageTracker:
    max_tokens: int = 0
    input_price_per_m: float = 0.0
    output_price_per_m: float = 0.0

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def estimated_cost(self) -> float | None:
        if not self.input_price_per_m and not self.output_price_per_m:
            return None
        return (
            self.input_tokens * self.input_price_per_m
            + self.output_tokens * self.output_price_per_m
        ) / 1_000_000

    def over_limit(self) -> bool:
        return self.max_tokens > 0 and self.total_tokens >= self.max_tokens

    def summary(self) -> str:
        parts = [
            f"{self.total_tokens:,} tokens "
            f"({self.input_tokens:,} in / {self.output_tokens:,} out) "
            f"across {self.calls} model call{'s' if self.calls != 1 else ''}"
        ]
        cost = self.estimated_cost
        if cost is not None:
            parts.append(f"≈ ${cost:.4f} estimated")
        if self.max_tokens:
            parts.append(f"limit {self.max_tokens:,}")
        return ", ".join(parts)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "calls": self.calls,
            "estimated_cost": self.estimated_cost,
            "max_tokens": self.max_tokens,
            "over_limit": self.over_limit(),
        }
