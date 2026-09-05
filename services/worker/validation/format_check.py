"""BRF-1: the output geometry must match the requested format, not just fit itself."""

import math

from validation.geometry import PAGE_SIZES, page_dims

PT_PER_MM = 72 / 25.4
EPS = 0.01  # tolerate rounding of explicit mm→point conversions


def _number(value, positive=False):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and (value > 0 if positive else value >= 0))


def _same(a, b):
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return abs(a - b) <= EPS


def normalize_format(spec):
    """Translate the existing brief/pilot units to document points.

    Returns only explicitly constrained fields. Conflicting aliases are errors,
    rather than silently preferring one of two production specifications.
    """
    if not isinstance(spec, dict):
        raise ValueError("format must be an object")
    out = {}
    orientation = spec.get("orientation", "portrait")
    if orientation not in ("portrait", "landscape"):
        raise ValueError("orientation must be portrait or landscape")
    if "orientation" in spec:
        out["orientation"] = orientation

    sizes = []
    for key, factor in (("size", 1), ("trimPt", 1), ("trimMm", PT_PER_MM)):
        if key not in spec:
            continue
        size = spec[key]
        if key == "size" and isinstance(size, str):
            if size.upper() not in PAGE_SIZES:
                raise ValueError(f"unknown named size {size!r}")
            size = list(PAGE_SIZES[size.upper()])
        if not isinstance(size, (list, tuple)) or len(size) != 2 or not all(
                _number(v, positive=True) for v in size):
            raise ValueError(f"{key} must contain two finite positive dimensions")
        sizes.append(tuple(page_dims({"size": [v * factor for v in size],
                                      "orientation": orientation})))
    if sizes:
        if not all(_same(sizes[0], s) for s in sizes[1:]):
            raise ValueError("size/trimPt/trimMm specify conflicting dimensions")
        out["size"] = list(sizes[0])

    for field, aliases in (
        ("bleed", (("bleed", 1), ("bleedPt", 1), ("bleedMm", PT_PER_MM))),
        ("margins", (("margins", 1), ("safeAreaPt", 1), ("safeAreaMm", PT_PER_MM))),
    ):
        values = []
        for key, factor in aliases:
            if key not in spec:
                continue
            value = spec[key]
            if field == "margins":
                if key != "margins":
                    value = [value] * 4
                if not isinstance(value, (list, tuple)) or len(value) != 4 or not all(
                        _number(v) for v in value):
                    raise ValueError(f"{key} must specify finite non-negative margins")
                values.append([v * factor for v in value])
            else:
                if not _number(value):
                    raise ValueError(f"{key} must be finite and non-negative")
                values.append(value * factor)
        if values:
            if not all(_same(values[0], v) for v in values[1:]):
                raise ValueError(f"conflicting {field} specifications")
            out[field] = values[0]
    return out


def check(document, spec):
    try:
        expected = normalize_format(spec)
    except ValueError as exc:
        return [{"code": "invalid-brief-format", "path": "format", "message": str(exc)}]
    page = document.get("page", {})
    actual_size = page_dims(page)
    errors = []

    def mismatch(field, actual, desired):
        errors.append({"code": "format-mismatch", "path": f"page.{field}",
                       "message": f"requested {field} {desired}, got {actual}; preserve the brief's format"})

    if "size" in expected and not _same(actual_size, expected["size"]):
        mismatch("size", list(actual_size), expected["size"])
    if "orientation" in expected and actual_size[0] != actual_size[1]:
        actual_orientation = "landscape" if actual_size[0] > actual_size[1] else "portrait"
        if actual_orientation != expected["orientation"]:
            mismatch("orientation", actual_orientation, expected["orientation"])
    for field, default in (("bleed", 0), ("margins", [10, 10, 10, 10])):
        if field in expected and not _same(page.get(field, default), expected[field]):
            mismatch(field, page.get(field, default), expected[field])
    return errors
