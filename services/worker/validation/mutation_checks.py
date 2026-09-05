"""GEN-7: preserve parent content/production structure during layout refinement."""

from collections import Counter

from validation.brief_checks import _norm, _document_text
from validation.format_check import check as check_format
from validation.geometry import page_dims


def items(document):
    return [item for page in document.get("pages", []) for item in page.get("items", [])]


def text(item):
    return _document_text({"pages": [{"items": [item]}]})


def validate_text_changes(document, changes):
    if changes is None:
        return []
    if not isinstance(changes, dict):
        return [{"code": "invalid-text-change", "path": "text_changes", "message": "text_changes must map unique text-item names to exact replacement text"}]
    errors = []
    original = items(document)
    for name, value in changes.items():
        matches = [item for item in original if item.get("name") == name]
        if (not name or len(matches) != 1 or matches[0].get("type") != "text"
                or not isinstance(value, str) or not value.strip()):
            errors.append({"code": "invalid-text-change", "path": f"text_changes.{name}",
                           "message": "supply non-empty replacement text for one uniquely named text item"})
    return errors


def check(original, revised, profile, brief=None, text_changes=None):
    changes = text_changes or {}
    errors = validate_text_changes(original, changes)
    if errors:
        return errors
    page = original.get("page", {})
    locked_format = {"size": list(page_dims(page)),
                     "bleed": page.get("bleed", 0),
                     "margins": page.get("margins", [10, 10, 10, 10])}
    errors.extend(check_format(revised, locked_format))
    if len(original.get("pages", [])) != len(revised.get("pages", [])):
        errors.append({"code": "protected-geometry", "path": "pages",
                       "message": "a refinement must preserve the number of pages"})
    old_items, new_items = items(original), items(revised)
    name_counts = Counter(item.get("name") for item in old_items)
    named = {name for name, count in name_counts.items() if name and count == 1}
    loose_text = Counter(text(item) for item in new_items
                         if item.get("type") == "text" and item.get("name") not in named)
    for item in old_items:
        if item.get("type") != "text":
            continue
        name = item.get("name")
        expected = _norm(changes[name]) if name in changes else text(item)
        if name and name_counts[name] == 1:
            matches = [candidate for candidate in new_items if candidate.get("name") == name]
            valid = len(matches) == 1 and matches[0].get("type") == "text" and text(matches[0]) == expected
        else:
            valid = loose_text[expected] > 0
            loose_text[expected] -= 1
        if not valid:
            errors.append({"code": "protected-copy", "path": name or "pages",
                           "message": f"preserve text exactly: {expected!r}; only explicit text_changes may replace it"})

    mandatory = set((brief or {}).get("mandatoryElements") or [])
    mandatory.update(profile.get("rules", {}).get("mandatoryElements") or [])
    spots = {sw["name"] for sw in profile.get("swatches", []) + original.get("swatches", []) if sw.get("spot")}
    for item in old_items:
        name = item.get("name")
        production = item.get("type") == "path" and item.get("stroke", {}).get("color") in spots
        if production:
            if item not in new_items:
                errors.append({"code": "protected-production-path", "path": name or "pages",
                               "message": "preserve spot production paths and their placement exactly"})
        if name in mandatory:
            matches = [candidate for candidate in new_items if candidate.get("name") == name]
            if (len(matches) != 1 or matches[0].get("type") != item.get("type")
                    or (item.get("type") == "image" and matches[0].get("src") != item.get("src"))):
                errors.append({"code": "protected-mandatory", "path": name,
                               "message": "preserve the mandatory element and its asset identity"})
    for name in mandatory - {item.get("name") for item in new_items}:
        errors.append({"code": "missing-mandatory", "path": name,
                       "message": "restore this required brief element"})
    return errors
