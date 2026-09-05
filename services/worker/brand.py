"""Brand profiles (PRD BRAND-1/2).

A profile is a versioned JSON fragment: locked swatches, char/para styles,
font whitelist, and rules (min type size, contrast floor, safe zones,
mandatory elements). merge_profile() injects profile definitions into a
document before compile — the profile is authoritative on name conflicts,
so a generator can reference brand swatches/styles by name without ever
defining them.
"""

import copy
import json
from pathlib import Path


def load_profile(path):
    return json.loads(Path(path).read_text())


def _merge_named(profile_items, document_items):
    """Profile entries first (authoritative); document extras appended."""
    taken = {it["name"] for it in profile_items}
    return list(profile_items) + [
        it for it in document_items if it.get("name") not in taken]


def merge_profile(document, profile):
    merged = copy.deepcopy(document)
    for key in ("swatches", "charStyles", "paraStyles"):
        merged[key] = _merge_named(profile.get(key, []),
                                   document.get(key, []))
    return merged


# --------------------------------------------------------------- overrides
# BRAND-6: a project may deviate from its pinned brand profile only through
# an explicit override set — the sanctioned campaign break-out. Shape:
#
#     {"add":      {"swatches": [...], "fonts": [...], "charStyles": [...],
#                   "paraStyles": [...], "logoAssets": [...]},
#      "restrict": {"swatches": [names], "fonts": [names]},
#      "rules":    {ruleName: {"value": ..., "reason": "why"}},
#      "designPrinciples": ["..."] | "..."}
#
# Brand-named entries are never redefined: additions must use new names, so
# a document referencing a brand swatch always gets the brand definition.
# Rule changes carry a mandatory reason (the audit trail). Restriction
# narrows the brand palette/font list; additions survive restriction.

_ADD_SECTIONS = ("swatches", "charStyles", "paraStyles", "fonts",
                 "logoAssets")
_RESTRICT_SECTIONS = ("swatches", "fonts")


def _section_names(profile, section):
    if section == "fonts":
        return {f for f in profile.get("fonts", []) if isinstance(f, str)}
    key = "role" if section == "logoAssets" else "name"
    return {it.get(key) for it in profile.get(section, [])
            if isinstance(it, dict)}


def _entry_name(section, entry):
    if section == "fonts":
        return entry if isinstance(entry, str) else None
    key = "role" if section == "logoAssets" else "name"
    return entry.get(key) if isinstance(entry, dict) else None


def validate_overrides(overrides, profile):
    """Errors in the shared {code, path, message} shape (GEN-3); empty list
    means the overrides are applicable to this profile."""
    errors = []

    def err(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    if overrides is None:
        return errors
    if not isinstance(overrides, dict):
        err("override-shape", "", "overrides must be an object")
        return errors
    for key in sorted(set(overrides)
                      - {"add", "restrict", "rules", "designPrinciples"}):
        err("override-shape", key, f"unknown override section {key!r}")

    add = overrides.get("add") or {}
    if not isinstance(add, dict):
        err("override-shape", "add", "'add' must be an object of lists")
        add = {}
    for section in sorted(add):
        entries = add[section]
        if section not in _ADD_SECTIONS:
            err("override-shape", f"add.{section}",
                f"cannot add to {section!r} — one of {sorted(_ADD_SECTIONS)}")
            continue
        if not isinstance(entries, list):
            err("override-shape", f"add.{section}", "must be a list")
            continue
        taken = _section_names(profile, section)
        for i, entry in enumerate(entries):
            name = _entry_name(section, entry)
            if not name:
                key = "role" if section == "logoAssets" else "name"
                err("override-shape", f"add.{section}[{i}]",
                    f"entry needs a {key!r}")
            elif name in taken:
                err("override-name-conflict", f"add.{section}[{i}]",
                    f'"{name}" is already defined by the brand — overrides '
                    f"may add new names, never redefine brand entries")
            else:
                taken.add(name)

    restrict = overrides.get("restrict") or {}
    if not isinstance(restrict, dict):
        err("override-shape", "restrict",
            "'restrict' must be an object of name lists")
        restrict = {}
    for section in sorted(restrict):
        names = restrict[section]
        if section not in _RESTRICT_SECTIONS:
            err("override-shape", f"restrict.{section}",
                f"cannot restrict {section!r} — one of"
                f" {sorted(_RESTRICT_SECTIONS)}")
            continue
        if not isinstance(names, list) or not names:
            err("override-shape", f"restrict.{section}",
                "must be a non-empty list of brand names")
            continue
        known = _section_names(profile, section)
        for i, name in enumerate(names):
            if name not in known:
                err("override-unknown-name", f"restrict.{section}[{i}]",
                    f'"{name}" is not a {section} entry of this brand'
                    f" version")

    rules = overrides.get("rules") or {}
    if not isinstance(rules, dict):
        err("override-shape", "rules", "'rules' must be an object")
        rules = {}
    for name in sorted(rules):
        spec = rules[name]
        if not isinstance(spec, dict) or "value" not in spec:
            err("override-shape", f"rules.{name}",
                'rule overrides take {"value": ..., "reason": "why"}')
        elif not str(spec.get("reason") or "").strip():
            err("override-missing-reason", f"rules.{name}",
                "every rule override must record a reason — the deviation"
                " is audited (BRAND-6)")

    principles = overrides.get("designPrinciples")
    if principles is not None and not (
            isinstance(principles, str)
            or (isinstance(principles, list)
                and all(isinstance(p, str) for p in principles))):
        err("override-shape", "designPrinciples",
            "must be a string or list of strings")
    return errors


def apply_overrides(profile, overrides):
    """Effective profile = pinned brand version + project overrides.
    Deterministic and pure; callers validate_overrides() first. The brand
    profile is never mutated — deviation exists only in the result."""
    if not overrides:
        return copy.deepcopy(profile)
    effective = copy.deepcopy(profile)

    restrict = overrides.get("restrict") or {}
    keep = restrict.get("swatches")
    if keep:
        effective["swatches"] = [sw for sw in effective.get("swatches", [])
                                 if sw.get("name") in set(keep)]
    keep = restrict.get("fonts")
    if keep:
        effective["fonts"] = [f for f in effective.get("fonts", [])
                              if f in set(keep)]

    add = overrides.get("add") or {}
    for section in _ADD_SECTIONS:
        entries = add.get(section)
        if entries:
            effective[section] = (list(effective.get(section, []))
                                  + copy.deepcopy(entries))

    rules = overrides.get("rules") or {}
    if rules:
        merged = dict(effective.get("rules", {}))
        for name, spec in rules.items():
            merged[name] = spec["value"]
        effective["rules"] = merged

    principles = overrides.get("designPrinciples")
    if principles:
        existing = effective.get("designPrinciples") or []
        if isinstance(existing, str):
            existing = [existing]
        extra = [principles] if isinstance(principles, str) else principles
        effective["designPrinciples"] = list(existing) + list(extra)
    return effective
