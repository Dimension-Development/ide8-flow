"""Template binding (PRD TPL-1..3, pulled forward from Phase 3).

A template is an approved document plus a bindings map. Bindings anchor on
item `name` (the schema's stable identifier — same anchor as comment pins),
never on positional paths, so a template survives cosmetic reordering.

    {
      "slots": {
        "headline":  {"kind": "text",   "item": "headline"},
        "hero":      {"kind": "image",  "item": "hero-image"},
        "band":      {"kind": "swatch", "item": "accent-band",
                      "target": "fill"}
      },
      "locked": ["logo-lockup", "cutpath-tab"]
    }

Slot kinds: `text` replaces paragraph text (styles preserved); `image`
swaps the asset name; `swatch` rebinds an item's fill or stroke to another
swatch already named in the document. Swatch slots deliberately do NOT
accept raw colour values — profile merge is authoritative (BRAND-2), so
only re-referencing existing brand swatches is meaningful.

Binding is deterministic — no LLM anywhere on this path. Bound documents
still pass the full validation stack (VAL-1..4) plus the overflow gate, so
a template can never emit artwork the generation loop would have rejected.

Errors share the compiler's {code, path, message} shape (GEN-3).
"""

import copy

KINDS = ("text", "image", "swatch")


def _err(code, path, message):
    return {"code": code, "path": path, "message": message}


def _items_by_name(document):
    out = {}
    for p, page in enumerate(document.get("pages", [])):
        for i, item in enumerate(page.get("items", [])):
            name = item.get("name")
            if name:
                out[name] = (f"pages/{p}/items/{i}", item)
    return out


def _swatches_by_name(document):
    return {s.get("name"): s for s in document.get("swatches", [])
            if s.get("name")}


def validate_bindings(document, bindings):
    """Promotion-time check (TPL-1): every slot and lock must resolve
    against this document. Returns a {code, path, message} error list."""
    errors = []
    if not isinstance(bindings, dict) or \
            not isinstance(bindings.get("slots"), dict):
        return [_err("bindings-shape", "bindings",
                     "bindings must be {slots: {...}, locked?: [...]}")]
    items = _items_by_name(document)
    swatches = _swatches_by_name(document)
    locked = bindings.get("locked", [])
    if not isinstance(locked, list):
        return [_err("bindings-shape", "bindings/locked",
                     "locked must be a list of item names")]

    for name in locked:
        if name not in items:
            errors.append(_err(
                "locked-unknown-item", "bindings/locked",
                f'locked item "{name}" does not exist in the document'))

    for slot, spec in bindings["slots"].items():
        where = f"bindings/slots/{slot}"
        kind = (spec or {}).get("kind")
        if kind not in KINDS:
            errors.append(_err("slot-kind", where,
                               f"kind must be one of {list(KINDS)}"))
            continue
        target = spec.get("item")
        if target not in items:
            errors.append(_err(
                "slot-unknown-item", where,
                f'item "{target}" does not exist in the document '
                f"(slots bind by item name)"))
            continue
        _, item = items[target]
        if kind == "swatch":
            prop = spec.get("target", "fill")
            if prop not in ("fill", "stroke"):
                errors.append(_err(
                    "slot-swatch-target", where,
                    'swatch slot target must be "fill" or "stroke"'))
        elif item.get("type") != kind:
            errors.append(_err(
                "slot-kind-mismatch", where,
                f'item "{target}" is a {item.get("type")} item, '
                f"slot kind is {kind}"))
        if target in locked:
            errors.append(_err(
                "slot-locked", where,
                f'item "{target}" is locked and cannot also be a slot'))
    return errors


def _bind_text(item, value, path):
    """Replace paragraph text, preserving the template's styles: line i of
    the value takes the style of the template's paragraph i (last style
    repeats when the value has more lines than the template)."""
    if not isinstance(value, str) or not value.strip():
        return [_err("bind-text-value", path,
                     "text slot value must be a non-empty string")]
    styles = [p.get("style") for p in item.get("paragraphs", [])] or [None]
    paras = []
    for i, line in enumerate(value.split("\n")):
        style = styles[min(i, len(styles) - 1)]
        paras.append({"style": style, "text": line} if style
                     else {"text": line})
    item["paragraphs"] = paras
    return []


def apply_bindings(document, bindings, values, asset_names=()):
    """Bind `values` (slot -> value) into a copy of the document (TPL-2).

    Unbound slots keep the template's content. Returns (document, errors);
    any error means the row must not render."""
    doc = copy.deepcopy(document)
    errors = []
    slots = bindings.get("slots", {})
    items = _items_by_name(doc)
    swatches = _swatches_by_name(doc)

    for slot, value in values.items():
        path = f"values/{slot}"
        spec = slots.get(slot)
        if spec is None:
            errors.append(_err("unknown-slot", path,
                               f'"{slot}" is not a slot on this template'))
            continue
        kind = spec["kind"]
        if kind == "text":
            _, item = items[spec["item"]]
            errors.extend(_bind_text(item, value, path))
        elif kind == "image":
            if value not in asset_names:
                errors.append(_err(
                    "bind-unknown-asset", path,
                    f'asset "{value}" is not in the asset library'))
                continue
            _, item = items[spec["item"]]
            item["src"] = value
        elif kind == "swatch":
            if value not in swatches:
                errors.append(_err(
                    "bind-unknown-swatch", path,
                    f'"{value}" is not a swatch in this document — swatch '
                    f"slots re-reference existing brand swatches by name"))
                continue
            _, item = items[spec["item"]]
            if spec.get("target", "fill") == "stroke":
                item.setdefault("stroke", {})["color"] = value
            else:
                item["fill"] = value
    return doc, errors
