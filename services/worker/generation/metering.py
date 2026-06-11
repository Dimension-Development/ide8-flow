"""Token/cost metering (PRD GEN-5, ADM-1, usage_event shape).

Prices are USD per million tokens (input, output) — keep in sync with
platform.claude.com/docs/en/pricing. Cache reads bill at ~0.1x input,
cache writes at ~1.25x input.
"""

PRICES_PER_MTOK = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
}


class Meter:
    """Accumulates SDK usage objects across calls, priced per model."""

    def __init__(self):
        self.events = []

    def add(self, model, usage, purpose=""):
        self.events.append({
            "model": model,
            "purpose": purpose,
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "cache_read_input_tokens":
                getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_creation_input_tokens":
                getattr(usage, "cache_creation_input_tokens", 0) or 0,
        })

    @property
    def calls(self):
        return len(self.events)

    def cost_usd(self):
        total = 0.0
        for e in self.events:
            inp, outp = PRICES_PER_MTOK.get(e["model"], (5.00, 25.00))
            total += e["input_tokens"] * inp / 1e6
            total += e["output_tokens"] * outp / 1e6
            total += e["cache_read_input_tokens"] * inp * 0.1 / 1e6
            total += e["cache_creation_input_tokens"] * inp * 1.25 / 1e6
        return total

    def report(self):
        return {
            "calls": self.calls,
            "input_tokens": sum(e["input_tokens"] for e in self.events),
            "output_tokens": sum(e["output_tokens"] for e in self.events),
            "cache_read_input_tokens":
                sum(e["cache_read_input_tokens"] for e in self.events),
            "cache_creation_input_tokens":
                sum(e["cache_creation_input_tokens"] for e in self.events),
            "cost_usd": round(self.cost_usd(), 6),
            "events": self.events,
        }
