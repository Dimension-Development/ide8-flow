"""VAL-2: brand conformance — swatch whitelist, font whitelist, minimum type
size, mandatory elements. Runs against the RAW document (pre-merge) so
off-brand definitions are caught at their source."""


def check(document, profile):
    errors = []

    def err(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    prof_swatches = {sw["name"]: sw for sw in profile.get("swatches", [])}
    for i, sw in enumerate(document.get("swatches", [])):
        name = sw.get("name")
        ref = prof_swatches.get(name)
        if ref is None:
            err("off-brand-swatch", f"swatches[{i}]",
                f'"{name}" is not in the brand profile — reference profile '
                f"swatches by name instead of defining new colours")
        elif (sw.get("space", "cmyk") != ref.get("space", "cmyk")
              or list(sw.get("values", [])) != list(ref.get("values", []))
              or bool(sw.get("spot")) != bool(ref.get("spot"))):
            err("off-brand-swatch", f"swatches[{i}]",
                f'"{name}" redefines the profile swatch with different values')

    fonts = set(profile.get("fonts", []))
    min_size = profile.get("rules", {}).get("minTypeSize")
    for i, st in enumerate(document.get("charStyles", [])):
        font = st.get("font")
        if fonts and font not in fonts:
            err("off-brand-font", f"charStyles[{i}].font",
                f'"{font}" is not in the brand font list {sorted(fonts)}')
        size = st.get("size", 12)
        if min_size is not None and size < min_size:
            err("type-too-small", f"charStyles[{i}].size",
                f"{size}pt is below the brand minimum {min_size}pt")

    mandatory = set(profile.get("rules", {}).get("mandatoryElements", []))
    if mandatory:
        present = {item.get("name")
                   for pg in document.get("pages", [])
                   for item in pg.get("items", [])}
        for name in sorted(mandatory - present):
            err("missing-mandatory", "pages",
                f'mandatory element "{name}" is missing — every concept must '
                f"include it as a named item")

    return errors
