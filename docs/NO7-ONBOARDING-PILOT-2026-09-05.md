# No7 onboarding pilot

**Current status:** the standalone pilot's selected assets and reviewed guidance
have since been imported into the real [brand workspace](BRAND-WORKSPACE-2026-09-05.md).
Source upload and model-assisted PDF extraction are also implemented; see the
[follow-on guide](PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md).
The sections below retain the earlier preparation/handoff findings. A general
large-PSD/TIFF asset-preparation importer remains future work.

The local pilot pack is at `out/no7-onboarding/index.html`. All client source material, previews, inventories and extracted guidance remain git-ignored under `out/`; this document records product/implementation findings only.

The user confirmed the May 2026 Believe in Possible BVI and the campaign's three skincare ranges. This pilot prepares an asset catalogue, font audit, source-linked draft rules and a human-review surface. The initial pack was standalone; the subsequent provisional trial handoff is recorded below. The full app importer remains unimplemented.

## Evidence from the pilot

- 54 source artworks (~16.94 GB), 69 font files and 5 PDFs (230 pages).
- No byte-identical artwork duplicates; 42 font duplicate copies, leaving 27 unique font byte streams.
- 53 identification previews. Embedded Photoshop/TIFF thumbnails avoid decoding heavy masters, but some appear inconsistent with matching filename variants or show utility shapes; they cannot be trusted as production composites.
- A nearly 30,000 × 32,000 JPEG demonstrates the need for pixel-count limits and reduced-resolution decoding, separate from byte-size limits.
- Two TIFF variants require metadata fallback and studio conversion; the legacy Illustrator/PostScript master requires a supported vector export.
- 52 evidence-linked draft rules and 15 colour records; three source RGB/HEX inconsistencies were retained for review. All 115 governing pages are text-indexed, with 50 page images and explicit coverage status.
- The rule set separates shared, masterbrand and range guidance, restrictions, format references and conditional permissions. No examples or draft rules were automatically promoted to approved claims or enforceable checks.

## Product changes this evidence supports

1. A source registry with immutable hashes, versions, brand/campaign/range eligibility and approval status. Logical filenames are insufficient identity or authority.
2. A bounded ingestion worker: inspect before decode, stream large files, retain masters, produce previews, and quarantine unsupported or ambiguous conversions for studio preparation.
3. Distinct preview, production derivative and utility/mask roles. Preserve operation history, colour profiles, alpha/clipping details and source identity. Verify placed resolution against the actual crop rather than a universal downsampling rule.
4. A font registry that resolves true family/style names, deduplicates exact bytes, pins the chosen build and checks actual renderer availability. A whitelist alone does not install fonts or guarantee role-specific typography.
5. PDF extraction using page text plus rendered evidence, with source coverage, visual-text discrepancies, exact numeric transcription, applicable scope and unresolved values. Document examples must remain distinct from live approved copy.
6. Reviewable draft rules and an immutable published brand pack. Capture reviewer edits, exceptions and authority. Do not silently change historical projects when a guide changes.
7. An explicit enforcement mapping: deterministic checks where implemented, visual review for interpretive direction, and visible unsupported checks. Approval of a rule does not automatically implement its validator.

These requirements overlap the asset-lineage/raster pipeline and studio-workspace work already identified in the product delivery review. A full Photoshop-compatible compositor is not required for the first onboarding release; a clear studio preparation queue is.

## Verification and next gate

The local pack is intended for Luke's asset and guidance review. Review choices save a browser copy and timestamped local file backups and can be exported/imported; they do not automatically write to ide8's database or count as client approval. The explicit merged-review handoff below applies the current choices. No live Fable extraction/generation call was made. Human review time, correction rate and missed-rule rate are still unmeasured.

After the review, use the accepted Prime Forever/A4 subset to update the trial pack, check the missing subline font and relevant layout checks, then run the first real model-generated concept through the app.

Verified all 128 source hashes remained unchanged, 53 previews decoded, all 52 excerpts matched the indexed source and all referenced page images existed. Browser checks covered shortlist/search, note persistence across reload, readable source-page zoom, saving a real review file and re-importing a test decision. Test choices were cleared. The local export endpoint rejects unknown item IDs, decision values and fields.

## Provisional trial handoff into the app

Luke authorised best-guess decisions for internal testing. The selected review export is recorded by hash in a new immutable trial brand version (v2), with the existing No7 campaign explicitly repinned to it. The previous profile and technical control remain intact. All ten decision notes and a backup of the prior live records are saved in the ignored trial folder. Relevant assumptions are included in interpretive design guidance; source conflicts are not converted into invented brand facts or new validators. No client approval was recorded.

The app already held the prepared campaign photograph, white-logo proof derivative and four-font profile, but the UI exposed no way to load the saved campaign into the brief form. BRF-1 now offers saved campaigns, restores mandatory wording and image selections, shows the pinned brand version, and saves edits through the existing project API. Generation from a loaded campaign uses the project endpoint, retaining its brand pin and overrides. The image library and brief now show visible previews, including white artwork against a darker background. Additional source assets, full PDF review and font ingestion remain outside this handoff.

Validation: UI typecheck and production build; 20 project/override tests; browser loading and saving the No7 brief; API equality check of the saved brief including required endline and review metadata; served asset hashes match both prepared files. Model routing/credentials are unchanged and live model calls remain zero.

## Image selections recovered and merged

Luke's subsequent browser export recovered eight selected images (A001, A002, A005, A009, A027, A029, A034, A041) and all 52 accepted rule interpretations. His export contained no decision notes. It was merged with the ten earlier assistant-authored provisional decisions, taking only the decision field from that earlier export. Luke's asset and rule choices are preserved exactly. D01 and D10 were revised to resolve the conflict between his A005 selection and the assistant's earlier exclusion; the source notes and both versions are retained in merge provenance. The browser imported and re-exported the merged review with exact asset/rule/decision equality. The cause of the earlier missing browser state remains unconfirmed.

The local review tool now appends automatic file backups, handles both input and change events, captures visible edits before leaving a section/exporting, displays the selected-image count, and backs up the current review before importing a replacement. Four isolated persistence tests passed. Preserve all review snapshots; do not replace the recovered user choices with older test exports.

Seven new internal-proof derivatives were prepared from six Photoshop masters and one TIFF. The Photoshop derivatives use full saved merged image data, not embedded identification thumbnails or a re-rendered layer stack. Colour conversion, downsampling, transparency handling, source hashes and limitations are recorded per asset. Untagged sources retain a provisional colour assumption; 16-bit and CMYK sources are converted to 8-bit sRGB proof copies. Two large CMYK composites were reduced before ICC conversion to stay within the bounded preparation allocation. Every prepared image was visually compared with its identification preview. A005's full saved image confirms the eye-patch artwork despite its Serum/SPF filename. No original file was changed. These are internal proof copies, not production-certified derivatives; the small A001 source still requires a placed-resolution check.

All eight selected images are now available in the app, with the existing campaign JPEG reused and the assistant's provisional white-logo derivative retained separately: nine library assets in total. The Assets screen includes a Refresh library action for external imports. Brand version 3 records the merged review and source provenance; the existing campaign is explicitly repinned while earlier brand versions and the technical control remain intact. All 52 accepted interpretations remain recorded, with the 46 shared/Prime Forever interpretations applied conditionally to this trial. Three source-CMYK Prime Forever swatches were added without inventing CMYK values for a digital-only swatch. Accepted interpretations do not automatically add validators.

The saved A4 brief still starts with the campaign photograph and provisional white logo. Library availability and the images required in one composition are distinct. No client approval or live model generation was recorded. The full reusable onboarding importer remains product work; this was an explicit local pilot import with backups and verification.

Verification: exact merged-review browser round-trip; all eight original source hashes unchanged; served bytes match all eight selected asset records; nine images visible in the app library; UI typecheck and production build pass. A separate image-placement diagnostic rendered all nine assets with labels in 6.67 seconds and no text overflow. Its contact sheet was visually checked, including transparent cutouts against grey. It created no campaign concept and made no model request. This verifies placement, not print colour accuracy or client approval.

## First live app run and repair follow-up

After the import, Luke submitted a six-concept brief through the app. The persisted run records Claude Opus 4.8, correcting the earlier assumption that the local app could not yet make model calls. The user's desired provider migration has not been implemented. This was an ad hoc brief with new supplied copy and four reference images, not the saved project's original two-image brief; no automatic reassociation or copy changes were made during diagnosis.

Five concepts failed deterministic validation. Two omitted the top-level document version throughout four attempts. The previous diagnostic records do not retain their emitted payloads or stop reasons, so nesting versus omission versus incomplete output cannot be established retrospectively. Other attempts repeatedly failed the contrast estimate and/or exceeded the app's exact page bounds. One concept rendered, but its visual self-critique rejected the plain gradient background being used as a product hero and other craft issues. The technical control shown alongside these results is a separate earlier document.

The repair follow-up corrects legacy image-fit advice leaking into 0.2 prompts, provides the model with computed page/bleed frames, puts asset descriptions beside their names, and supplies brand-only solid-fill pairings from the same contrast estimate used by validation. Contrast failure messages now suggest passing brand text colours conditionally; the contrast floor and brand palette remain unchanged. Version errors explicitly state the required top-level structure and participate in escalation. Truncated responses have a separate error. Attempt records now retain emitted candidates, stop reasons and model identity; those diagnostics are not accepted document versions. Compile and overflow failures also follow configured escalation.

The UI names Anthropic and the current preset model versions explicitly. Ten added regression tests plus the existing suite pass: 188 worker tests total, UI typecheck/build, browser provider-label check and local worker health. The app's declared Pillow dependency was missing from its virtual environment and was installed to complete image tests. The idle local worker was restarted after a database backup. All seven concepts, two versions, nine assets, three brand versions, one project and one job remain unchanged. No additional paid model request was made during this repair; a fresh live run is still needed to measure the improved generation success rate.

## Six-brief benchmark preparation

Luke authorised a multi-agent testing push with Computer Use. Six isolated benchmark projects were prepared under ignored `out/no7-trial/benchmark/`, each pinned to the copied immutable brand v3 with nine prepared assets. Cases cover an A4 product poster, custom 150×100mm shelf card, typography, multiple products, landscape and copy density. Only the previously accepted two phrases are used; the density case repeats wording and is explicitly an integrity diagnostic rather than approved long-copy advertising.

Independent baseline review exposed product-identity risk: the previous serum brief selected cleanser, eye-patch and gradient imagery. A generic suggestion to add any packshot would still be wrong. Its self-critique also suggested colour repairs requiring further brand/contrast checking. The benchmark rubric separates technical validity, brief fidelity, visual craft, brand direction, legibility and asset fitness; no assistant score is client approval.

Computer Use verified loading, saving and reopening all six briefs with exact stored equality. Custom size editing was added in mm/points, preserves loaded point values, derives orientation and blocks nonpositive dimensions. An explicit Generate action against the preparation-only benchmark returned the expected pre-job 503: no concept or paid request was created. The isolated app at localhost:8132 carries a visible preparation banner; localhost:5174 remains the original working app.

Failed-generation usage now survives later SDK/renderer exceptions and contributes to scoped usage totals without double counting document versions or inventing missing historical events. The original app now reports $1.8325 of recorded aggregate spend, including its five historical failures; this is reconstructed application metering, not a new charge or provider invoice verification. A provider-neutral shared reservation/cancellation wrapper is implemented with atomic audit snapshots. Live runners must still supply verified provider pricing and conservative estimates, disable hidden SDK retries, and share one ledger; this does not impose a global limit on the original app.

Validation: 206 worker tests pass, UI typecheck/build pass, both local workers healthy, original record counts preserved after backup/reload, benchmark zero concepts/versions/spend. At that preparation checkpoint, provider choice and the proposed US$10 cap were pending; no twelve-artwork benchmark had run. The subsequent authorisation and completed run are recorded below.


## Completed Opus 4.8 benchmark

Luke explicitly authorised Opus 4.8 for every generation, self-critique and revision call with no spend ceiling. The isolated benchmark now enforces `claude-opus-4-8`, disables SDK retries and logs every dispatch/return/error. It ran twelve initial concepts across the six briefs plus two targeted revisions through the browser. The original campaign database still has seven concepts, two versions, nine assets, three brand versions, one project and one job.

All twelve initial outputs and both revisions produced valid editable documents. Independent checks confirmed exact page geometry, eligible named assets and copy. Both density outputs retained all six paragraphs of ten repeated phrases each, plus the headline and single endline. All fourteen exact-version craft bundles rerendered byte-for-byte and pixel-for-pixel identically to their saved proofs. Packaged PDFs passed page geometry and embedded-font inspection. This verifies export integrity, not certified print colour or client approval.

All 52 model calls reconcile: recorded spend $3.080574; token-repriced ledger $3.08057475 (per-version rounding only). No failed concepts, pending jobs or unmatched calls remain. Ten initial concepts self-approved, but visual review found repeated false acceptance of product overlap, weak photographic contrast and campaign-specific colour violations. Initial versions retain seven safe-zone and sixteen image-contrast-review warnings; these warnings are separate from technical validity. Both targeted browser revisions worked in one iteration while retaining copy/assets.

The proof grid now labels each card by brief and uses a neutral heading when briefs are mixed, with matching accessible controls. UI typecheck/build and browser verification passed. Generation prompts and validation gates were held fixed during this benchmark.

Next implementation priorities are source-image previews for initial composition, campaign/channel-specific palette and layout permissions, and independent visual acceptance of product clearance, photographic contrast and unresolved brand warnings. Keep the JSON contract and provider routing independent of the selected model. The complete local report and evidence live under ignored `out/no7-trial/benchmark/REPORT.md`, with separate technical, visual and export reviews. This is a single-brand diagnostic rather than a comparative model ranking.

Independent creative assessment: only two of ten initial creative concepts were useful drafts, rising to four of ten after the two repairs. Only the revised B02 shelf card passed all five visual criteria. B06 is excluded from that rate: both versions preserved copy density, but both failed artwork requirements. These are assistant reviews, with no human approval.
