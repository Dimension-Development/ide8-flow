"""Mutation loop (PRD GEN-7): natural-language instruction + current
document -> revised document -> diff -> new version.

Same deterministic gates as generation (VAL-1..4, compile, VAL-6 overflow)
with repair feedback; NO vision self-critique — the designer judges the
before/after proof pair, that's the point of a mutation.
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

WORKER_ROOT = Path(__file__).resolve().parents[1]
if str(WORKER_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKER_ROOT))

from assets import resolve_srcs  # noqa: E402
from brand import merge_profile  # noqa: E402
from validation import run_validation  # noqa: E402
from generation import prompts  # noqa: E402
from generation.loop import (  # noqa: E402
    GenConfig, _emit_tool, _tool_result, _tool_use)
from generation.metering import Meter  # noqa: E402
from generation.render_client import CompileRejected  # noqa: E402


@dataclass
class MutationResult:
    document: dict = None
    proof_png_b64: str = None
    validation: dict = None
    diff: list = field(default_factory=list)
    iterations: int = 0
    usage: dict = None
    error: str = None


def doc_diff(old, new, path=""):
    """Structural diff as [{path, change}] — the audit trail of a mutation."""
    changes = []
    if type(old) is not type(new):
        return [{"path": path or "$", "change": "changed"}]
    if isinstance(old, dict):
        for k in sorted(set(old) | set(new)):
            p = f"{path}.{k}" if path else k
            if k not in old:
                changes.append({"path": p, "change": "added"})
            elif k not in new:
                changes.append({"path": p, "change": "removed"})
            else:
                changes.extend(doc_diff(old[k], new[k], p))
    elif isinstance(old, list):
        for i in range(max(len(old), len(new))):
            p = f"{path}[{i}]"
            if i >= len(old):
                changes.append({"path": p, "change": "added"})
            elif i >= len(new):
                changes.append({"path": p, "change": "removed"})
            else:
                changes.extend(doc_diff(old[i], new[i], p))
    elif old != new:
        changes.append({"path": path or "$", "change": "changed"})
    return changes


def _mutation_message(document, instruction):
    return (
        "# Current document (the approved state — change ONLY what the "
        "instruction requires)\n\n"
        + json.dumps(document, sort_keys=True)
        + "\n\n# Mutation instruction\n\n" + instruction
        + "\n\nEmit the COMPLETE revised document via emit_document. "
          "Preserve every item, style and value the instruction does not "
          "touch — this is a surgical revision, not a redesign."
    )


def mutate_document(document, instruction, profile, *, client, render,
                    pack, schema_json, schema_path, config=None,
                    assets=None, expected_version=None):
    cfg = config or GenConfig(max_iterations=3)
    meter = Meter()
    result = MutationResult()
    assets = assets or {}

    system = prompts.build_system(pack, schema_json, profile,
                                  exemplar=pack.get("exemplar", {}))
    tools = [_emit_tool(schema_json)]
    messages = [{"role": "user",
                 "content": _mutation_message(document, instruction)
                 + prompts.assets_section(list(assets.values()))}]
    model = cfg.fast_model

    for iteration in range(1, cfg.max_iterations + 1):
        result.iterations = iteration
        resp = client.messages.create(
            model=model, max_tokens=cfg.max_tokens, system=system,
            tools=tools, messages=messages,
            tool_choice={"type": "tool", "name": "emit_document"})
        meter.add(model, resp.usage, "mutate")

        emit = _tool_use(resp, "emit_document")
        if emit is None:
            result.error = "model did not call emit_document"
            break
        revised = emit.input
        if isinstance(revised, dict) and isinstance(
                revised.get("version"), (int, float)):
            revised = dict(revised)
            revised["version"] = str(revised["version"])
        messages.append({"role": "assistant", "content": resp.content})

        if expected_version is not None and revised.get("version") != expected_version:
            result.validation = {"ok": False, "errors": [{
                "code": "document-version-mismatch", "path": "version",
                "message": (f'emitted version {revised.get("version")!r} does not '
                            f'match parent schema {expected_version!r}')}],
                "warnings": []}
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps(result.validation), is_error=True)]})
            continue

        report = run_validation(revised, profile, schema_path,
                                asset_names=assets.keys())
        result.validation = report
        if not report["ok"]:
            if model != cfg.strong_model:
                model = cfg.strong_model  # mutations escalate immediately
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps(report), is_error=True)]})
            continue

        staged, files, image_meta = resolve_srcs(
            merge_profile(revised, profile), assets)
        try:
            sla = render.compile(staged, image_meta=image_meta or None)
        except CompileRejected as e:
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps({"ok": False, "errors": e.errors}),
                is_error=True)]})
            continue

        png_b64, overflows = render.proof_meta(sla, dpi=cfg.proof_dpi,
                                               assets=files)
        if overflows:
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps({"ok": False, "errors": [
                    {"code": "overflow", "path": o.get("item", "?"),
                     "message": "text frame '%s' on page %s overflows"
                                % (o.get("item"), o.get("page"))}
                    for o in overflows]}), is_error=True)]})
            continue

        result.document = revised
        result.proof_png_b64 = png_b64
        result.diff = doc_diff(document, revised)
        break

    result.usage = meter.report()
    if result.document is None and result.error is None:
        result.error = "mutation failed validation within iteration cap"
    return result
