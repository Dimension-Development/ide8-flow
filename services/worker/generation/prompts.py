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

PACKS_ROOT = Path(__file__).resolve().parents[1] / "prompt_packs"


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
    principles = profile.get("designPrinciples")
    machine_profile = {k: v for k, v in profile.items()
                       if k != "designPrinciples"}
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
    blocks.append(
        {"type": "text", "text":
            "## Exemplar document (style reference for structure, not "
            "content)\n\n" + json.dumps(exemplar, sort_keys=True),
         "cache_control": {"type": "ephemeral"}})
    return blocks


def assets_section(assets):
    """Available-assets block (RND-5). Volatile per brief — lives in the
    user message, never the cached system prefix."""
    if not assets:
        return ("\n\n# Available image assets\n"
                "None — do not emit any image items for this brief.")
    lines = ["\n\n# Available image assets\n",
             "Image items may ONLY use these names as `src` "
             "(fit \"frame\" recommended; match the frame to the aspect "
             "ratio):\n"]
    for a in assets:
        dims = (f" — {a['width']}x{a['height']}px, aspect "
                f"{a['width'] / a['height']:.2f}"
                if a.get("width") and a.get("height") else "")
        lines.append(f"- {a['name']}{dims}\n")
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


def build_brief_message(brief, archetype, assets=None):
    parts = [
        "# Brief\n",
        json.dumps(brief, indent=2, sort_keys=True),
        "\n\n# Your layout archetype for THIS concept\n",
        archetype,
        assets_section(assets),
        mandatories_section(brief),
        "\n\nGenerate one complete document for this brief using the "
        "emit_document tool. Distinctness comes from layout archetype, "
        "composition and hierarchy — not from straying off-brand.",
    ]
    return "".join(parts)


def build_critique_message(brief, profile=None):
    principles = ("the brand design principles in the system prompt, "
                  if (profile or {}).get("designPrinciples") else "")
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
