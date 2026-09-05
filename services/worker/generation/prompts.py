"""Prompt pack assembly (PRD GEN-4).

A pack is a versioned directory under prompt_packs/<version>/ containing
pack.json (metadata + archetypes) and system.md (core instructions). The
system prompt assembles as: pack instructions -> document schema -> brand
profile -> exemplar, all stable per brief so the whole prefix is cacheable
(cache_control on the final block). Volatile content (brief, archetype)
goes in the user message.
"""

import json
from pathlib import Path

from validation.contrast import solid_pairings
from validation.format_check import normalize_format
from validation.geometry import page_dims
from workspace import model_design_principles

PACKS_ROOT = Path(__file__).resolve().parents[1] / "prompt_packs"


def _machine_profile(profile):
    """Project identity packages onto fields consumed by compiler/validators.

    The identity board, provenance and superseded trial notes are review data,
    never locked instructions. Strip metadata within named definitions too.
    Legacy profiles retain their original prompt shape until onboarded.
    """
    if not isinstance(profile.get('identity'), dict):
        return {k: v for k, v in profile.items() if k != 'designPrinciples'}
    projected = {key: profile[key] for key in ('name', 'version', 'fonts') if key in profile}
    definitions = {
        'swatches': {'name', 'space', 'values', 'spot'},
        'charStyles': {'name', 'font', 'size', 'color', 'tracking'},
        'paraStyles': {'name', 'charStyle', 'align', 'lineHeight', 'spaceBefore', 'spaceAfter', 'indent', 'firstIndent'},
    }
    for section, fields in definitions.items():
        if section in profile:
            projected[section] = [{key: value for key, value in entry.items() if key in fields}
                                  for entry in profile[section]]
    if 'rules' in profile:
        projected['rules'] = {key: value for key, value in profile['rules'].items()
                              if key in {'minTypeSize', 'contrastFloor', 'safeZone', 'mandatoryElements'}}
    return projected


def load_pack(version):
    root = PACKS_ROOT / version
    meta = json.loads((root / "pack.json").read_text())
    meta["system_text"] = (root / "system.md").read_text()
    return meta


def build_system(pack, schema_json, profile, exemplar):
    """Stable, cacheable system blocks. Order matters: never reorder —
    byte-stability of this prefix is what makes fan-out calls cache-share.

    profile.designPrinciples (a DESIGN.md-style markdown string) is the
    brand's *interpretive* layer — composition, hierarchy, imagery, taste.
    It's split out of the machine-rules JSON into its own prose block, and
    the critique rubric judges proofs against it. The division of labour is
    strict: anything machine-checkable (contrast, sizes, mandatories)
    belongs in profile.rules where validation enforces it, never here."""
    principles = model_design_principles(profile)
    machine_profile = _machine_profile(profile)
    blocks = [
        {"type": "text", "text": pack["system_text"]},
        {"type": "text", "text":
            "## Document schema (formal JSON Schema — emit_document input "
            "must conform)\n\n" + json.dumps(schema_json, sort_keys=True)},
        {"type": "text", "text":
            "## Brand profile (locked — reference swatches/styles/fonts by "
            "name; never redefine them)\n\n"
            + json.dumps(machine_profile, sort_keys=True)},
    ]
    if principles:
        blocks.append({"type": "text", "text":
            "## Brand design principles (interpretive — every composition "
            "choice should be defensible against these, and your critique "
            "must judge the rendered proof against them)\n\n" + principles})
    pairs = solid_pairings(profile)
    if pairs:
        lines = ["## Solid-fill contrast preflight\n",
                 "These pairings meet the app's contrast floor using its approximate "
                 "swatch calculation. Use them only where brand guidance permits. "
                 "This does not verify photography or print colour. For a gradient, "
                 "the text colour must pass against every stop. Do not assume a "
                 "swatch named Darkest is dark enough for white text.\n"]
        for background in dict.fromkeys(p['background'] for p in pairs):
            options = sorted((p for p in pairs if p['background'] == background),
                             key=lambda p: -p['ratio'])[:3]
            lines.append(f"- Background {background!r}: text " + ", ".join(
                f"{p['text']!r} ({p['ratio']:.2f}:1)" for p in options))
        blocks.append({"type": "text", "text": "\n".join(lines)})
    blocks.append(
        {"type": "text", "text":
            "## Exemplar document (style reference for structure, not "
            "content)\n\n" + json.dumps(exemplar, sort_keys=True),
         "cache_control": {"type": "ephemeral"}})
    return blocks


def assets_section(assets, version="0.1", asset_notes=None):
    """Available-assets block (RND-5). Volatile per brief — lives in the
    user message, never the cached system prefix."""
    if not assets:
        return ("\n\n# Available image assets\n"
                "None — do not emit any image items for this brief.")
    placement = ('Use fit "contain" to preserve the whole image or "cover" '
                 'for an intentional crop; use "stretch" only if distortion is intended.'
                 if version == "0.2" else
                 'Use fit "frame" and match the frame to the image aspect ratio.')
    lines = ["\n\n# Available image assets\n",
             "Image items may ONLY use these names as `src`. " + placement + "\n"]
    descriptions = {a['name']: a.get('description', '') for a in (asset_notes or [])}
    for a in assets:
        dims = (f" — {a['width']}x{a['height']}px, aspect "
                f"{a['width'] / a['height']:.2f}"
                if a.get("width") and a.get("height") else "")
        description = descriptions.get(a['name'])
        lines.append(f"- {a['name']}{dims}" + (f" — {description}" if description else "") + "\n")
    return "".join(lines)


def mandatories_section(brief):
    """Make the deterministic brief gates explicit so the model satisfies them
    first time: required named items (VAL-2/brief) and verbatim copy (VAL-5)."""
    lines = []
    names = brief.get("mandatoryElements") or []
    if names:
        lines.append("\n\n# Mandatory named items (hard requirement)\n")
        lines.append("Every concept MUST include an item whose `name` is "
                     "exactly each of these (the ANNAME anchor):\n")
        for n in names:
            lines.append(f"- {n}\n")
    copy = brief.get("copy", {}) or {}
    verbatim = [("headline", copy.get("headline")),
                ("legal", copy.get("legal"))]
    verbatim += [("mandatory", s) for s in (brief.get("mandatoryCopy") or [])]
    verbatim = [(k, v) for k, v in verbatim if v]
    if verbatim:
        lines.append("\n# Copy that must appear VERBATIM (hard requirement)\n")
        lines.append("Reproduce character-for-character — no paraphrase, no "
                     "truncation. The legal line especially must be unaltered:\n")
        for k, v in verbatim:
            lines.append(f"- {k}: {v}\n")
    return "".join(lines)


def geometry_section(spec):
    """Give the model the same arithmetic as preflight, including named sizes."""
    page = normalize_format(spec or {})
    w, h = page_dims(page)
    bleed = page.get("bleed", 0)
    left, right, top, bottom = page.get("margins", [10] * 4)
    return ("\n\n# Exact page geometry in points\n"
            "Use these resolved values, including the app's named-size rounding. "
            "A frame is [x, y, width, height], not [left, top, right, bottom].\n"
            + json.dumps({"trim_size": [w, h],
                          "full_bleed_frame": [-bleed, -bleed, w + 2 * bleed, h + 2 * bleed],
                          "bounds_left_top_right_bottom": [-bleed, -bleed, w + bleed, h + bleed],
                          "safe_text_frame": [left, top, w - left - right, h - top - bottom]})
            + "\nFor every item: x + width <= right bound and y + height <= bottom bound. "
              "A full-bleed background must reach all four bleed edges.")


def build_brief_message(brief, archetype, assets=None, version="0.1", asset_notes=None):
    parts = [
        "# Brief\n",
        json.dumps(brief, indent=2, sort_keys=True),
        "\n\n# Your layout archetype for THIS concept\n",
        archetype,
        assets_section(assets, version=version, asset_notes=asset_notes),
        geometry_section(brief.get("format")),
        mandatories_section(brief),
        "\n\nGenerate one complete document for this brief using the "
        "emit_document tool. Distinctness comes from layout archetype, "
        "composition and hierarchy — not from straying off-brand.",
    ]
    return "".join(parts)


def build_critique_message(brief, profile=None):
    principles = ("the brand design principles in the system prompt, "
                  if model_design_principles(profile or {}) else "")
    return (
        "Above is the rendered proof of your document. Critique it against "
        f"the brief, {principles}and brand rules: hierarchy, legibility, "
        "balance, use of bleed, copy fit, overall craft. Respond via the "
        "submit_critique tool only. Approve only if a designer would put "
        "this in front of a client as a first-round concept.\n\n"
        "Brief reminder: "
        + json.dumps({k: brief[k] for k in ("title", "copy")
                      if k in brief}, sort_keys=True)
    )
