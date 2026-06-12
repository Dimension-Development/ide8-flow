"""Validation layer (PRD VAL-1..4, VAL-7): deterministic, ordered
cheapest-first. Schema conformance gates everything — later checks assume a
structurally sound document. Errors share the compiler's shape
({code, path, message}) so the GEN-3 repair loop consumes one format.

VAL-6 (overflow) is render-time and lives in the render service; the worker
folds its result into the same report after proofing.
"""

import sys
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from brand import merge_profile  # noqa: E402
from validation import (  # noqa: E402
    assets_check, brand_rules, contrast, geometry, schema_check)


def run_validation(document, profile, schema_path, asset_names=()):
    """Returns {ok, errors, warnings}. ok == no errors (warnings allowed)."""
    errors = schema_check.check(document, schema_path)
    if errors:
        return {"ok": False, "errors": errors, "warnings": []}

    errors, warnings = [], []

    e = brand_rules.check(document, profile)
    errors.extend(e)

    e = assets_check.check(document, asset_names)
    errors.extend(e)

    merged = merge_profile(document, profile)

    e, w = geometry.check(merged, profile)
    errors.extend(e)
    warnings.extend(w)

    e = contrast.check(merged, profile)
    errors.extend(e)

    return {"ok": not errors, "errors": errors, "warnings": warnings}
