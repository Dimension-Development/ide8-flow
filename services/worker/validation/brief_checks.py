"""Brief-derived checks: things only the BRIEF knows, not the brand profile.

- VAL-5 copy integrity: the copy deck must appear in the document verbatim.
  Legal text and the headline (plus anything in `mandatoryCopy`) are HARD
  errors — a dropped or paraphrased legal line is a compliance failure.
  Subhead and body are warnings (supporting copy: present-verbatim preferred,
  not gating, to avoid repair-loop churn on long passages).
- Brief mandatory elements: names listed in `brief.mandatoryElements` must
  exist as named items (complements the profile's own mandatory list in
  brand_rules — the brief can require campaign-specific items like a QR).

Only runs when a brief is supplied (generation). Mutations don't re-check copy
integrity — a mutation may legitimately be an instruction to change the copy.
"""

import re

_QUOTES = {"‘": "'", "’": "'", "“": '"', "”": '"'}
_DASHES = {"–": "-", "—": "-", "−": "-"}


def _norm(s):
    """Canonicalise for verbatim comparison: fold typographic quotes/dashes and
    non-breaking spaces, collapse whitespace. Catches genuine omission and
    paraphrase without false-failing on smart-quote substitution."""
    if not isinstance(s, str):
        return ""
    s = s.replace(" ", " ")
    for a, b in {**_QUOTES, **_DASHES}.items():
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


def _document_text(document):
    """All text the document renders, as one normalised corpus."""
    parts = []
    for pg in document.get("pages", []):
        for item in pg.get("items", []):
            if item.get("type") != "text":
                continue
            for para in item.get("paragraphs", []):
                if isinstance(para.get("text"), str):
                    parts.append(para["text"])
                for run in para.get("runs", []) or []:
                    if isinstance(run.get("text"), str):
                        parts.append(run["text"])
    return _norm(" ".join(parts))


def check(document, brief):
    errors, warnings = [], []
    if not isinstance(brief, dict):
        return errors, warnings

    # ---- brief mandatory elements (named items) --------------------------
    present = {item.get("name")
               for pg in document.get("pages", [])
               for item in pg.get("items", [])}
    for name in brief.get("mandatoryElements", []) or []:
        if name not in present:
            errors.append({
                "code": "missing-mandatory", "path": "pages",
                "message": (f'brief mandatory element "{name}" is missing — '
                            f"add it as a named item (ANNAME)")})

    # ---- VAL-5 copy integrity -------------------------------------------
    corpus = _document_text(document)
    copy = brief.get("copy", {}) or {}

    def required(label, value, hard):
        v = _norm(value)
        if not v:
            return
        if v not in corpus:
            entry = {
                "code": "missing-copy", "path": f"copy.{label}",
                "message": (f"{label} copy is not present verbatim — reproduce "
                            f'it exactly: "{value}"')}
            (errors if hard else warnings).append(entry)

    required("headline", copy.get("headline"), hard=True)
    required("legal", copy.get("legal"), hard=True)
    for s in brief.get("mandatoryCopy", []) or []:
        required("mandatory", s, hard=True)
    required("subhead", copy.get("subhead"), hard=False)
    for i, para in enumerate(copy.get("body", []) or []):
        required(f"body[{i}]", para, hard=False)

    return errors, warnings
