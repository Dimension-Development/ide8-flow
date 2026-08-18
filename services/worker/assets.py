"""Asset handling (PRD RND-5, pulled forward from Phase 2).

Documents reference assets BY NAME in image `src` fields ("logo-primary").
Before compile, resolve_srcs() rewrites names to staged relative paths
("assets/logo-primary.png") and collects the bytes to ship alongside the
SLA; the render service writes them into the per-request workdir, where
Scribus resolves relative PFILE paths against the document location.
"""

import re

SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

EXT_BY_MIME = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/tiff": "tif",
}


def sniff(data):
    """Return (mime, width, height) or (None, None, None) if unrecognised."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return ("image/png",
                int.from_bytes(data[16:20], "big"),
                int.from_bytes(data[20:24], "big"))
    if data[:2] == b"\xff\xd8":  # JPEG: scan for a frame header (SOFn)
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3):
                return ("image/jpeg",
                        int.from_bytes(data[i + 7:i + 9], "big"),
                        int.from_bytes(data[i + 5:i + 7], "big"))
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
        return ("image/jpeg", None, None)
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return ("image/tiff", None, None)  # dims need full IFD walk — skip
    return (None, None, None)


def staged_relpath(name, mime):
    return f"assets/{name}.{EXT_BY_MIME.get(mime, 'bin')}"


def resolve_srcs(document, asset_map):
    """Rewrite image `src` asset names to staged relative paths.

    Returns (document_copy, files, image_meta) where files maps staged relpath
    -> bytes and image_meta maps the same path to its trusted source-image
    dimensions.  Dimensions travel to the compiler separately from canonical
    document JSON, so an author/model can choose a crop but cannot invent the
    source geometry it is cropped from.
    Unknown names are left untouched — validation has already failed them
    (missing-asset) before this runs.
    """
    import copy
    doc = copy.deepcopy(document)
    files = {}
    image_meta = {}
    for pg in doc.get("pages", []):
        for item in pg.get("items", []):
            if item.get("type") != "image":
                continue
            asset = asset_map.get(item.get("src"))
            if asset is None:
                continue
            relpath = staged_relpath(asset["name"], asset["mime"])
            item["src"] = relpath
            files[relpath] = asset["data"]
            image_meta[relpath] = {
                "width": asset.get("width"),
                "height": asset.get("height"),
            }
    return doc, files, image_meta
