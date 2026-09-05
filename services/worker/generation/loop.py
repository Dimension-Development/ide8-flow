"""Generation loop (PRD GEN-1): emit document -> validate -> render proof ->
vision self-critique -> mutate, until approved or iteration cap.

The model NEVER touches the renderer: it emits documents via the
emit_document tool; deterministic validation (VAL-1..4) and the render
service's overflow readback (VAL-6) gate every emission before a single
vision token is spent. All validation feedback uses the structured
{code, path, message} shape (GEN-3).

Model routing (GEN-5): fast model for fan-out; escalate to the strong model
after repeated validation failures or rejected self-critiques.

The Anthropic client and render client are injected, so the loop is testable
with fakes and the live CLI wires real ones.
"""

import copy
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
from generation.metering import Meter  # noqa: E402
from generation.render_client import CompileRejected  # noqa: E402


@dataclass
class GenConfig:
    fast_model: str = "claude-sonnet-4-6"
    strong_model: str = "claude-opus-4-8"
    max_iterations: int = 4          # GEN-1 cap
    escalate_after_failures: int = 2  # validation/repair failures -> strong
    escalate_after_critiques: int = 2  # rejected critiques -> strong
    proof_dpi: int = 120
    # A full document emission is typically 2-4k output tokens; 8k is
    # generous headroom while staying inside low-tier OTPM rate limits
    # (Tier 1 = 8k output tokens/min — a 16k request can never be admitted).
    max_tokens: int = 8000


@dataclass
class ConceptResult:
    document: dict = None
    proof_png_b64: str = None
    validation: dict = None
    critique: dict = None
    approved: bool = False
    iterations: int = 0
    model_history: list = field(default_factory=list)
    usage: dict = None
    error: str = None


def _critique_tool():
    return {
        "name": "submit_critique",
        "description": ("Submit your verdict on the rendered proof. Approve "
                        "only client-ready first-round concepts."),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["approve"],
            "properties": {
                "approve": {"type": "boolean"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["issue"],
                        "properties": {
                            "issue": {"type": "string"},
                            "fix": {"type": "string"},
                        },
                    },
                },
            },
        },
    }


def _emit_tool(schema_json):
    return {
        "name": "emit_document",
        "description": ("Emit the complete ide8.flow document JSON for this "
                        "concept. The input must conform to the document "
                        "schema provided in the system prompt. Put version, "
                        "page and pages directly at the top level of the tool "
                        "input. Do not wrap the document under document, input "
                        "or any other key."),
        "input_schema": schema_json,
    }


def _tool_use(resp, name):
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == name:
            return block
    return None


def _tool_result(tool_use_id, content, is_error=False):
    block = {"type": "tool_result", "tool_use_id": tool_use_id,
             "content": content}
    if is_error:
        block["is_error"] = True
    return block


def _emission_report(document, expected_version, stop_reason):
    """Reject transport/contract errors without guessing a document version."""
    if stop_reason == "max_tokens":
        return {"ok": False, "errors": [{"code": "incomplete-document", "path": "$",
                "message": "The response reached its output token limit. Emit a more concise COMPLETE document, with version, page and pages at the top level."}],
                "warnings": []}
    if (expected_version is not None and isinstance(document, dict)
            and document.get("version") != expected_version):
        return {"ok": False, "errors": [{
            "code": "document-version-mismatch", "path": "version",
            "message": (f'Expected top-level "version": "{expected_version}"; '
                        f'got {document.get("version")!r}. Received top-level keys: '
                        f'{sorted(document)}. Emit the COMPLETE document directly '
                        'as tool input with version, page and pages at the root; '
                        'do not nest it inside a document or input object.')}], "warnings": []}
    return None


def generate_concept(brief, profile, archetype, *, client, render,
                     pack, schema_json, schema_path, config=None,
                     assets=None, expected_version=None):
    """Run the full GEN-1 loop for one concept. Returns ConceptResult.

    `assets` is {name: {name, mime, width, height, data}} — advertised to
    the model, enforced by validation (missing-asset), staged to the render
    service with each proof (RND-5)."""
    cfg = config or GenConfig()
    meter = Meter()
    result = ConceptResult(model_history=[])
    assets = assets or {}

    system = prompts.build_system(
        pack, schema_json, profile,
        exemplar=pack.get("exemplar", {}))
    tools = [_emit_tool(schema_json), _critique_tool()]
    messages = [{"role": "user",
                 "content": prompts.build_brief_message(
                     brief, archetype, assets=list(assets.values()),
                     version=pack["version"], asset_notes=profile.get("assetNotes"))}]

    model = cfg.fast_model
    validation_failures = 0
    rejected_critiques = 0
    candidate = None
    attempts = []

    # Transport/renderer failures must not discard already metered calls or
    # detach an earlier valid document from its matching proof.
    try:
        for iteration in range(1, cfg.max_iterations + 1):
            result.iterations = iteration
            attempt = None
            stage = "emit"
            if validation_failures >= cfg.escalate_after_failures:
                model = cfg.strong_model

            # ---- emit (forced tool use) -------------------------------------
            resp = client.messages.create(
                model=model, max_tokens=cfg.max_tokens, system=system,
                tools=tools, messages=messages,
                tool_choice={"type": "tool", "name": "emit_document"})
            meter.add(model, resp.usage, "emit")
            result.model_history.append(model)

            emit = _tool_use(resp, "emit_document")
            if emit is None:
                result.error = ("model output reached its token limit before completing emit_document"
                                if getattr(resp, "stop_reason", None) == "max_tokens" else
                                "model did not call emit_document")
                break
            document = emit.input
            # Models reliably emit the version as a JSON number (0.1); the schema
            # demands the string "0.1". Normalising here is cheaper than burning
            # a repair iteration on JSON type trivia.
            if isinstance(document, dict) and isinstance(
                    document.get("version"), (int, float)):
                document = dict(document)
                document["version"] = str(document["version"])
            messages.append({"role": "assistant", "content": resp.content})

            # ---- deterministic gates (cheapest first, GEN-3 / VAL-1..4) -----
            stage = "validation"
            report = (_emission_report(document, expected_version, getattr(resp, "stop_reason", None))
                      or run_validation(document, profile, schema_path,
                                        asset_names=assets.keys(), brief=brief))
            result.validation = report
            attempt = {"iteration": iteration, "validation": report,
                       "emitted_document": copy.deepcopy(emit.input),
                       "stop_reason": getattr(resp, "stop_reason", None), "model": model}
            attempts.append(attempt)
            if not report["ok"]:
                validation_failures += 1
                messages.append({"role": "user", "content": [_tool_result(
                    emit.id, json.dumps(report), is_error=True)]})
                continue

            stage = "asset-staging"
            merged = merge_profile(document, profile)
            staged, files, image_meta = resolve_srcs(merged, assets)
            stage = "compile"
            try:
                sla = render.compile(staged, image_meta=image_meta or None)
            except CompileRejected as e:
                validation_failures += 1
                # keep the reject as the result's last-known validation state,
                # so an exhausted loop reports why it failed (ADM-2); a later
                # passing iteration overwrites it
                result.validation = {"ok": False, "errors": e.errors,
                                     "warnings": []}
                attempt["validation"] = result.validation
                messages.append({"role": "user", "content": [_tool_result(
                    emit.id, json.dumps({"ok": False, "errors": e.errors}),
                    is_error=True)]})
                continue

            stage = "proof"
            png_b64, overflows = render.proof_meta(sla, dpi=cfg.proof_dpi,
                                                   assets=files)
            if overflows:  # VAL-6: hard failure, deterministic, pre-vision
                validation_failures += 1
                overflow_report = {"ok": False, "errors": [
                    {"code": "overflow", "path": o.get("item", "?"),
                     "message": ("text frame '%s' on page %s overflows — "
                                 "shorten copy, reduce type size, or enlarge "
                                 "the frame" % (o.get("item"), o.get("page")))}
                    for o in overflows]}
                # Keep the failed attempt's evidence separate from any earlier
                # candidate's passing validation and matching proof.
                result.validation = {**overflow_report, "warnings": []}
                attempt["validation"] = result.validation
                messages.append({"role": "user", "content": [_tool_result(
                    emit.id, json.dumps(overflow_report), is_error=True)]})
                continue

            result.document = document
            result.proof_png_b64 = png_b64
            result.critique = None
            candidate = {"document": document, "proof_png_b64": png_b64,
                         "validation": report, "critique": None}

            # ---- vision self-critique (GEN-1) -------------------------------
            stage = "critique"
            messages.append({"role": "user", "content": [
                _tool_result(emit.id, json.dumps(
                    {"ok": True, "warnings": report["warnings"]})),
                {"type": "image", "source": {"type": "base64",
                                             "media_type": "image/png",
                                             "data": png_b64}},
                {"type": "text", "text": prompts.build_critique_message(
                    brief, profile=profile)},
            ]})
            resp = client.messages.create(
                model=model, max_tokens=cfg.max_tokens, system=system,
                tools=tools, messages=messages,
                tool_choice={"type": "tool", "name": "submit_critique"})
            meter.add(model, resp.usage, "critique")

            crit = _tool_use(resp, "submit_critique")
            if crit is None:
                result.error = "model did not call submit_critique"
                break
            result.critique = crit.input
            candidate["critique"] = crit.input
            messages.append({"role": "assistant", "content": resp.content})

            if crit.input.get("approve"):
                result.approved = True
                break

            rejected_critiques += 1
            if (rejected_critiques >= cfg.escalate_after_critiques
                    and model != cfg.strong_model):
                model = cfg.strong_model
            messages.append({"role": "user", "content": [_tool_result(
                crit.id, "Revise the document to address every issue, then "
                         "emit the corrected document.")]})

    except Exception as exc:  # noqa: BLE001 — finalize the paid attempt normally
        result.error = f"{type(exc).__name__}: {exc}"[:500]
        failure = {"ok": False, "errors": [{
            "code": "generation-exception", "path": stage,
            "message": result.error}], "warnings": []}
        if attempt is None:
            attempt = {"iteration": result.iterations, "model": model}
            attempts.append(attempt)
        elif attempt.get("validation") is not None:
            attempt["preflight_validation"] = attempt["validation"]
        attempt.update({"stage": stage, "error": result.error,
                        "validation": failure})
        result.validation = failure

    # Only a complete, render-valid candidate can become a version. Later
    # failed attempts retain diagnostics without changing its artifact pair.
    if candidate is not None:
        for key, value in candidate.items():
            setattr(result, key, value)
    result.validation = {**(result.validation or {"ok": False, "errors": [], "warnings": []}),
                         "attempts": attempts}
    result.usage = meter.report()
    return result
