"""Guard against price-map / routing drift (GEN-5, £2/brief NFR).

MODEL_PRESETS (app.py) and PRICES_PER_MTOK (generation/metering.py) are two
hand-maintained lists. If a preset routes to a model with no price entry,
cost_usd used to silently mis-bill it. These tests assert every routable model
is priced and that pricing now fails loudly rather than guessing a default.

    python3 -m unittest discover services/worker/tests
"""

import sys
import unittest
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from app import MODEL_PRESETS  # noqa: E402
from generation.loop import GenConfig  # noqa: E402
from generation.metering import (  # noqa: E402
    PRICES_PER_MTOK, Meter, UnknownModelError, assert_all_priced, price_for,
)


class PresetPricingTest(unittest.TestCase):
    def test_every_preset_model_is_priced(self):
        """Both the fast and strong model of every engine preset must have a
        price entry — the core anti-drift guarantee."""
        for preset, (fast, strong) in MODEL_PRESETS.items():
            for role, model in (("fast", fast), ("strong", strong)):
                self.assertIn(
                    model, PRICES_PER_MTOK,
                    f"{preset} {role} model {model!r} has no PRICES_PER_MTOK "
                    f"entry — cost_usd would mis-bill it")

    def test_genconfig_default_models_are_priced(self):
        """The loop's default routing pair is metered too, so it's a drift
        vector even when no preset is passed (e.g. /mutate)."""
        cfg = GenConfig()
        for model in (cfg.fast_model, cfg.strong_model):
            self.assertIn(model, PRICES_PER_MTOK)

    def test_assert_all_priced_raises_on_unpriced(self):
        with self.assertRaises(UnknownModelError):
            assert_all_priced({"claude-sonnet-4-6", "claude-made-up-9"})

    def test_assert_all_priced_passes_when_all_known(self):
        # Should not raise.
        assert_all_priced(set(PRICES_PER_MTOK))


class LoudPricingTest(unittest.TestCase):
    def test_price_for_raises_instead_of_silent_default(self):
        with self.assertRaises(UnknownModelError):
            price_for("claude-not-a-real-model")

    def test_cost_usd_raises_on_unpriced_metered_model(self):
        """The actual mis-billing path: metering an unknown model must surface
        loudly, not fall back to a guessed (5.00, 25.00)."""
        meter = Meter()
        meter.add("claude-ghost-model", _usage(), "emit")
        with self.assertRaises(UnknownModelError):
            meter.cost_usd()

    def test_cost_usd_prices_known_model(self):
        meter = Meter()
        meter.add("claude-haiku-4-5", _usage(inp=1_000_000, out=0), "emit")
        # 1M input tokens at $1.00/MTok = $1.00 exactly.
        self.assertAlmostEqual(meter.cost_usd(), 1.00, places=6)


class _Usage:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _usage(inp=1000, out=400):
    return _Usage(input_tokens=inp, output_tokens=out,
                  cache_read_input_tokens=0, cache_creation_input_tokens=0)


if __name__ == "__main__":
    unittest.main()
