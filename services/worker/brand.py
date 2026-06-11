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
