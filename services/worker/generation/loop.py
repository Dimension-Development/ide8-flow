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
                        "schema provided in the system prompt."),
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


def generate_concept(brief, profile, archetype, *, client, render,
                     pack, schema_json, schema_path, config=None,
                     assets=None):
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
                     brief, archetype, assets=list(assets.values()))}]

    model = cfg.fast_model
    validation_failures = 0
    rejected_critiques = 0

    for iteration in range(1, cfg.max_iterations + 1):
        result.iterations = iteration

        # ---- emit (forced tool use) -------------------------------------
        resp = client.messages.create(
            model=model, max_tokens=cfg.max_tokens, system=system,
            tools=tools, messages=messages,
            tool_choice={"type": "tool", "name": "emit_document"})
        meter.add(model, resp.usage, "emit")
        result.model_history.append(model)

        emit = _tool_use(resp, "emit_document")
        if emit is None:
            result.error = "model did not call emit_document"
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
        report = run_validation(document, profile, schema_path,
                                asset_names=assets.keys(), brief=brief)
        result.validation = report
        if not report["ok"]:
            validation_failures += 1
            if (validation_failures >= cfg.escalate_after_failures
                    and model != cfg.strong_model):
                model = cfg.strong_model
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps(report), is_error=True)]})
            continue

        merged = merge_profile(document, profile)
        staged, files = resolve_srcs(merged, assets)
        try:
            sla = render.compile(staged)
        except CompileRejected as e:
            validation_failures += 1
            # keep the reject as the result's last-known validation state,
            # so an exhausted loop reports why it failed (ADM-2); a later
            # passing iteration overwrites it
            result.validation = {"ok": False, "errors": e.errors,
                                 "warnings": []}
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps({"ok": False, "errors": e.errors}),
                is_error=True)]})
            continue

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
            result.document = document
            # as with CompileRejected: if the cap lands here, the stored
            # version should carry the overflow errors, not the earlier
            # passing report
            result.validation = {**overflow_report, "warnings": []}
            messages.append({"role": "user", "content": [_tool_result(
                emit.id, json.dumps(overflow_report), is_error=True)]})
            continue

        result.document = document
        result.proof_png_b64 = png_b64

        # ---- vision self-critique (GEN-1) -------------------------------
        messages.append({"role": "user", "content": [
            _tool_result(emit.id, json.dumps(
                {"ok": True, "warnings": report["warnings"]})),
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png",
                                         "data": png_b64}},
            {"type": "text", "text": prompts.build_critique_message(brief)},
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

    result.usage = meter.report()
    return result
