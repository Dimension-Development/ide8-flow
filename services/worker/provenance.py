"""Resolve historical render inputs without consulting mutable project defaults."""

from brand import apply_overrides
from store import content_hash


class MissingProfileSnapshot(ValueError):
    pass


def profile_for_version(store, version):
    if version and version.get("effective_profile") is not None:
        return version["effective_profile"]

    # The project-layer prototype recorded exact job evidence before per-version
    # snapshots existed. Recover only when every piece is still verifiable.
    concept = store.get_concept(version["concept_id"]) if version else None
    job = store.get_job(concept["job_id"]) if concept and concept.get("job_id") else None
    evidence = (job or {}).get("brand") or {}
    if (version and version.get("origin") == "generation"
            and evidence.get("brand_version_id") and evidence.get("effective_sha256")):
        brand = store.get_brand_version(evidence["brand_version_id"])
        if brand:
            profile = apply_overrides(brand["profile"], evidence.get("overrides"))
            if content_hash(profile) == evidence["effective_sha256"]:
                return profile
    raise MissingProfileSnapshot(
        "This version has no verifiable original brand profile. Its saved proof "
        "and JSON remain available, but exporting or refining it with today's "
        "brand could change the artwork. Generate a new concept with the chosen "
        "brand to establish a reproducible version.")
