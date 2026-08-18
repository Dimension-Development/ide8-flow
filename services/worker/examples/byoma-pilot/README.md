# BYOMA pilot intake (design-team handoff)

This is a neutral intake scaffold, not a representation of BYOMA’s current
brand rules. Do not add public-web guesses, scraped assets or substitute fonts.
Only place approved, licensed material here after the design team supplies it.

## Expected delivery tree

```text
byoma-pilot/
  brand/
    manifest.json              approved copy of manifest.template.json
    profile.json               approved copy of profile.template.json
    fonts/                     licensed server-embedding candidates (ignored)
    logos/                     approved vector/raster masters (ignored)
    imagery/                   approved product/model imagery (ignored)
  brief.json                   approved copy deck and card constraints
  DESIGN-REVIEW.md             completed design-team scorecards
```

## Naming and intake

- Use lower-case kebab-case asset names: `byoma-hero-model-01.png`.
- Preserve originals. Record each file's role, version, owner, licence,
  server-embedding permission, colour space, dimensions/resolution and SHA-256
  in `brand/manifest.json` before upload.
- Confirm fonts are licensed for container/server embedding; record the exact
  approved fallback if they are not.
- Confirm source imagery usage rights, expiry/territory restrictions and the
  named approver. Do not convert, recolour or crop originals during intake.
- Validate the approved profile and brief against the document schema only
  after a design owner signs them off.

Templates are intentionally safe to commit. The `.gitignore` keeps client
fonts, imagery, logos and resulting approved files out of Git by default.
