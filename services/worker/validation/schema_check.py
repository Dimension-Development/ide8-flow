"""VAL-1: document-schema conformance via the formal JSON Schema."""

import json
from functools import lru_cache
from pathlib import Path

import jsonschema


@lru_cache(maxsize=4)
def _validator(schema_path):
    schema = json.loads(Path(schema_path).read_text())
    return jsonschema.Draft202012Validator(schema)


def _fmt_path(parts):
    out = ""
    for p in parts:
        if isinstance(p, int):
            out += f"[{p}]"
        else:
            out += ("." if out else "") + str(p)
    return out or "$"


def check(document, schema_path):
    errors = []
    seen = set()
    for e in sorted(_validator(str(schema_path)).iter_errors(document),
                    key=lambda e: list(map(str, e.absolute_path))):
        path = _fmt_path(e.absolute_path)
        message = e.message if len(e.message) <= 300 else e.message[:297] + "..."
        # const/enum mismatches caused by a TYPE difference are invisible in
        # jsonschema's default message ("'0.1' was expected" when the model
        # sent the number 0.1) — spell the type out so repair loops converge.
        if (e.validator == "const"
                and type(e.instance) is not type(e.validator_value)):
            message += (f" — you sent {e.instance!r} "
                        f"({type(e.instance).__name__}); the value must be "
                        f"the {type(e.validator_value).__name__} "
                        f"{e.validator_value!r}")
        if (path, message) in seen:
            continue
        seen.add((path, message))
        errors.append({"code": "schema", "path": path, "message": message})
    return errors
