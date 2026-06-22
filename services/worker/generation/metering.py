"""Token/cost metering (PRD GEN-5, ADM-1, usage_event shape).

PRICES_PER_MTOK is the single source of truth for the models the worker knows
how to bill, in USD per million tokens (input, output). Every model the engine
can route to — MODEL_PRESETS in app.py and the GenConfig defaults in
generation/loop.py — must have an entry here. app.py calls assert_all_priced()
at startup and tests/test_metering_presets.py guards it in CI, so a preset
can't silently route to an unpriced model and mis-bill against the £2 NFR.

Prices verified against platform.claude.com/docs/en/pricing on 2026-06-22.
Cache reads bill at ~0.1x input, cache writes at ~1.25x input.
"""

#: model id -> (input $/MTok, output $/MTok)
PRICES_PER_MTOK = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-opus-4-8": (5.00, 25.00),
}


class UnknownModelError(LookupError):
    """A model was metered, or routed to, without a price entry.

    Raised loudly instead of falling back to a silent default — a wrong
    default mis-reports cost_usd for the whole generation with no warning.
    """


def price_for(model):
    """(input, output) $/MTok for `model`, or raise UnknownModelError.

    No silent default: an unpriced model is a bug (drift between the price
    map and the routing presets), not a billable event to guess at."""
    try:
        return PRICES_PER_MTOK[model]
    except KeyError:
        raise UnknownModelError(
            f"no price for model {model!r}; add it to PRICES_PER_MTOK in "
            f"generation/metering.py (known: {sorted(PRICES_PER_MTOK)})"
        ) from None


def assert_all_priced(models, context="models"):
    """Raise UnknownModelError if any id in `models` lacks a price entry.

    Called at worker startup over MODEL_PRESETS so drift fails fast at boot
    rather than mis-billing at metering time, after the spend has happened."""
    missing = sorted({m for m in models if m not in PRICES_PER_MTOK})
    if missing:
        raise UnknownModelError(
            f"{context} reference unpriced model(s) {missing}; add them to "
            f"PRICES_PER_MTOK in generation/metering.py "
            f"(known: {sorted(PRICES_PER_MTOK)})"
        )


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
            inp, outp = price_for(e["model"])
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
