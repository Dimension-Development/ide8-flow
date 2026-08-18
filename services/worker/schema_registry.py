"""One authoritative routing table for supported document-schema versions.

Documents are immutable: generation selects a version deliberately and a
mutation inherits its parent's routing.  This module keeps the schema, prompt
pack and exemplar inseparable so provenance cannot drift as versions accrue.
"""

import json
import os
from pathlib import Path

from generation import prompts

WORKER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = WORKER_ROOT.parents[1]

# Keep existing installations on the proven contract until Stage A is signed
# off.  A deployment or CLI may explicitly select 0.2 for the pilot.
DOCUMENT_SCHEMA_VERSION = os.environ.get("DOCUMENT_SCHEMA_VERSION", "0.1")

_ROUTES = {
    "0.1": {
        "schema_path": REPO_ROOT / "schema" / "document-0.1.schema.json",
        "prompt_pack": "0.1",
        "exemplar_path": (REPO_ROOT / "services" / "render" / "examples"
                          / "example.json"),
    },
    "0.2": {
        "schema_path": REPO_ROOT / "schema" / "document-0.2.schema.json",
        "prompt_pack": "0.2",
        "exemplar_path": (REPO_ROOT / "services" / "render" / "examples"
                          / "example-0.2.json"),
    },
}


class SchemaRoutingError(ValueError):
    pass


def route(version=DOCUMENT_SCHEMA_VERSION):
    """Return a copy of the known route or fail before any model call."""
    try:
        result = dict(_ROUTES[version])
    except KeyError:
        raise SchemaRoutingError(
            f"unsupported document schema version {version!r}; supported: "
            f"{sorted(_ROUTES)}") from None
    result["version"] = version
    return result


def load(version=DOCUMENT_SCHEMA_VERSION, *, schema_path=None, prompt_pack=None,
         exemplar_path=None):
    """Load one internally consistent runtime route.

    Explicit file overrides remain available to diagnose schemas/exemplars,
    while a prompt pack must still declare the selected document version.
    """
    selected = route(version)
    schema = Path(schema_path or selected["schema_path"])
    exemplar = Path(exemplar_path or selected["exemplar_path"])
    pack = prompts.load_pack(prompt_pack or selected["prompt_pack"])
    if pack.get("version") != version:
        raise SchemaRoutingError(
            f"prompt pack {pack.get('version')!r} does not match document "
            f"schema version {version!r}")
    try:
        schema_json = json.loads(schema.read_text())
        pack["exemplar"] = json.loads(exemplar.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaRoutingError(f"cannot load route for {version}: {exc}") from exc
    return {
        "version": version,
        "schema_path": str(schema),
        "schema_json": schema_json,
        "pack": pack,
        "exemplar_path": str(exemplar),
    }
