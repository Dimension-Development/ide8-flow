# Brand workspace milestone — 5 September 2026

This note records the workspace checkpoint before the subsequent artwork trial
and PDF/client-review milestone. Current status: PDF extraction and client review
are now implemented locally; see [the follow-on guide](PDF-EXTRACTION-AND-CLIENT-REVIEW-2026-09-05.md).
The benchmark later published identity v4 for a fresh four-concept A4 project;
older projects kept their v3 pins. The original trial database remains at v3.

The studio now has a real brand → campaign → project workflow, with a visual identity board backed by saved data. This replaces the need to use the separate No7 onboarding prototype for day-to-day guidance review.

## Delivered

- Studio overview with brand creation, actual project/concept counts and recent projects.
- Brand workspace: visual identity, editable working colour/font definitions, campaigns/projects, assigned assets, source PDFs/fonts and downloadable DESIGN.md.
- Guidance cards carry scope, review status, conditions and source evidence. Editing guidance returns it to draft. Provisional studio interpretations remain distinct from client approval.
- Saved identity drafts are separate from immutable published versions. Publication checks revision conflicts and does not repin existing projects.
- DESIGN.md and model guidance derive from the same structured identity. Draft/rejected cards and source-only colour transcriptions are excluded from generation guidance; working swatches remain explicit renderer definitions.
- Campaigns carry product ranges. Projects belong to a brand and optionally a campaign; duplicate project names are allowed across those boundaries.
- Project workspace shows that project's artwork, saved brief and brand version. Brief loading preserves selected assets and custom dimensions.
- Brand asset membership constrains generation and mutation. New brands start with no assigned assets.
- Brand-owned PDF/font attachments are persisted and served by content hash. PDF cards link to their cited pages; uploaded fonts can supply browser specimens.

## No7 handoff

Both the original trial and isolated benchmark received the same saved identity draft: 86 cards (60 reviewed, 26 provisional), nine assigned assets, the governing BVI PDF, the white-logo PDF and four prepared fonts. Believe in Possible is a campaign with Prime Forever, Future Renew and Pro Age ranges. Existing projects were linked to this campaign.

No7's draft was not published. All existing projects remain pinned to brand version 3. Exact comparisons against pre-migration backups confirmed unchanged concept, document-version, asset, published-brand and job rows; project data is unchanged apart from campaign assignment and update timestamps. Foreign-key checks returned no errors.

Local handoff and evidence: `out/no7-trial/workspace-import/`. The original trial has seven concepts/two document versions; the benchmark has twelve concepts/fourteen document versions. No paid generation calls were made for this milestone.

## Validation

- Full worker unittest suite: 246 tests passed, including migration preservation, brand isolation, stale draft protection, identity projection and attachment routes.
- TypeScript typecheck and Vite production build passed.
- Browser QA in a separate fixture database: create brand; author provisional guidance; save/publish; create campaign and project; load and save brief; reject invalid CMYK values; apply/save/publish valid definitions; reload and verify matching board/DESIGN.md. The earlier project remained pinned to version 2 after the brand advanced to version 3.
- Browser QA on No7: board previews and source page links; campaign with six benchmark projects; B02 workspace with exactly two concepts; preserved 150 × 100 mm brief and three selected assets from the nine assigned assets; navigation back to studio.

## Deliberate remaining work

Source upload does not yet automatically extract new PDFs with a model. No7's existing reviewed extraction was imported. Campaign/range/channel scope is currently descriptive guidance, rather than a complete automatic rule compiler or separately versioned campaign identity package. Font upload supplies browser specimens; renderer font installation remains separate. Client authentication, sharing and approval workflows remain future work.

The workspace does not by itself resolve artwork quality. The next useful trial is to review the No7 board, publish an intentional identity version, create a fresh project pinned to it and repeat a known brief against the previous benchmark.
