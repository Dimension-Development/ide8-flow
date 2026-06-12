"""RND-5: every image `src` must name a known asset — missing assets are a
hard validation failure, caught deterministically before any render."""


def check(document, asset_names):
    errors = []
    known = set(asset_names or ())
    for n, pg in enumerate(document.get("pages", [])):
        for j, item in enumerate(pg.get("items", [])):
            if item.get("type") != "image":
                continue
            src = item.get("src")
            if src not in known:
                errors.append({
                    "code": "missing-asset",
                    "path": f"pages[{n}].items[{j}].src",
                    "message": (
                        f'"{src}" is not an uploaded asset — available: '
                        f"{sorted(known) or 'none'}. Image items may only "
                        f"reference assets by name")})
    return errors
