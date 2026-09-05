**Integrity fixes — GEN-6/7, BRAND-4/6, VAL-5/6 and BRF-1**

Checkpoint note: the test counts and remaining-work list below describe this
initial slice. The full worker suite now has 280 passing tests. Local client
review/approval was subsequently implemented; see the
[PDF/client-review guide](PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md).

Scope agreed 5 September 2026: fix historical brand drift, copy loss in mutations,
mixed generation artifacts and unchecked requested formats, then test real brand
assets. Also repair schema 0.2 packaging and missing overflow evidence at those
boundaries. Raster/vector generation and provider/evaluation additions remain in
the delivery review; they are not implemented by this slice.

New versions snapshot their effective brand profile. Export, mutation and template
rendering use that snapshot. Historical generation versions may recover the profile
only from an original job's exact brand-version/override/hash evidence. Legacy
mutations cannot assume their generation job's settings were still in use. Otherwise export and
mutation return an explicit conflict; stored JSON and proofs remain readable. No
historical document is rewritten or assigned guessed provenance.

Mutations preserve existing text, page format, mandatory asset identities and spot
production paths. Intentional text edits use an exact `text_changes` map keyed by
unique text-item name, exposed in the refinement UI and saved with the immutable
child version for audit. Copy checks follow the renderer's actual run concatenation
and precedence, so hidden paragraph text cannot satisfy a missing-copy gate. Each resulting version becomes
the content baseline for subsequent edits. This is not a general document patch
system; other layout changes still use the existing model loop.

Generation keeps each attempt's document/proof/report/critique together. Failed
attempts cannot contaminate a previously complete candidate. A wholly failed run
has no publishable version and retains its failure explanation.

Requested size, orientation, bleed and margins are deterministic checks. Existing
point-based brief formats and the pilot's explicit mm/pt format fields are accepted;
conflicting or invalid specifications fail explicitly. Multi-format orchestration
remains separate work.

The No7 supplied-asset test also exposed a false contrast failure: photography was
treated as paper white. Image backdrops now produce `image-contrast-review` warnings;
known solid fills keep the numerical gate. Warnings are visible in the version
review panel. AI approval badges now read "AI check passed" to distinguish them
from studio/client approval. Pixel-aware contrast remains subsequent work.

Verified locally on 5 September 2026:

- Worker: 178 tests passed, including migration, preserved historical exports,
  template and mutation inheritance, copy replacement, failed-attempt isolation,
  requested formats and image-background contrast.
- Renderer: 42 tests passed, including missing/invalid overflow reports and
  package rejection; UI typecheck and production build passed.
- Built worker image loads complete 0.1 and 0.2 schema routes. CI now repeats that
  packaging check. Local trial assets are excluded from the build context.
- Real Scribus synthetic proof/package run repeated twice: byte-identical SLA and
  proofs, clean overflow, expected named separation and PDF/X/output-intent markers.
- No7: supplied CMYK JPEG, transparent proof derivative of the supplied white logo
  and actual Effra font rendered into an A4 control. Downloaded bundle reproduced
  the stored proof byte-for-byte; PDF package embeds Effra Bold and carries PDF/X-4
  and output-intent markers. This is a technical control, not an AI-quality result.
- Review UI manually checked: stored No7 proof, exact-copy fields, blank-replacement
  rejection, clean reset and visible review warnings.

Full creative quality, native vector masters, font/renderer version pinning,
independent judging, client approval and external PitStop acceptance remain in the
delivery plan. Local trial details and assets live under ignored `out/no7-trial/`.
