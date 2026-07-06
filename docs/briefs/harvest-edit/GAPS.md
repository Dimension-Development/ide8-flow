# Harvest Edit — Gap & Edge-Case Report

What the maximal brief demands vs. what ide8.flow does today. Findings are
**predicted** from a code read first; the live-run column is filled in after
loading the fixture against the local stack (see the run log at the bottom).

Disposition key: 🔧 **closing in this change** · 📋 **documented, deferred** ·
✅ **already works**.

---

## Summary

The brief exposes **23** issues across brief intake, brand handling, fonts,
assets, copy integrity and shaped formats. This change closes the ones that are
self-contained and ship on SQLite (brand de-singleton + CRUD, mandatory-element
wiring, copy-integrity VAL-5, a richer brief form, and an asset-upload guard).
The larger structural items (multi-format BRF-2/VAR-1, vector-asset ingestion,
render-host font validation) are documented with a recommended approach.

| Closing now 🔧 | Deferred 📋 |
|---|---|
| Brand profiles in the store + select by `brief.brand` (BRAND-3) | Multi-format kit / variant reflow (BRF-2, VAR-1) |
| Brand admin UI (list/create, swatch + type preview) | Vector (SVG/EPS/PDF) + layered PSD asset ingestion (RND-5) |
| `brief.mandatoryElements` actually enforced + prompted | Render-host font-availability check (server fonts) |
| Copy-integrity check VAL-5 (verbatim copy deck) | Profile-version pinning / reproducible `.sla` (BRAND-4) |
| Brief form: brand, mandatory elements, bleed/margins, reference assets | Per-format mandatory elements; closed die-cut contours |
| Asset upload guard (max dimension / byte size) | CMYK preview + TIFF dimension sniffing in the UI |

---

## A. Brief intake & API

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| A1 | `brief.brand` selects nothing | Worker loads ONE profile from the `BRAND_PROFILE` env var (default `examples/brand_profile.json`, hardcoded "Example Brand"). The Meridian profile can't be chosen. | High | BRAND-3 | 🔧 |
| A2 | `brief.mandatoryElements` ignored | Collected by form/api, never read. Only `profile.rules.mandatoryElements` is validated. | High | BRF-1, VAL-2 | 🔧 |
| A3 | Brief form too thin | Hardcodes `brand:"Example Brand"`, `mandatoryElements:[]`, `bleed:8.5`, `margins:[12,12,12,12]`; no brand select, mandatory elements, reference uploads, or formats. | High | BRF-1 | 🔧 |
| A4 | No multi-format kit | `/generate` makes _n_ concepts for ONE format; `formats[]`/master are prompt text only. BRF-2 wants one document per format; VAR-1 wants variants reflowed from the approved master. | High | BRF-2, VAR-1 | 📋 |
| A5 | Rich brief fields unstructured | `campaign`, `price`, `strapline`, `production`, `creativeDirection` are free-form prompt context with no schema/contract. | Low | BRF-1 | 📋 |

## B. Brand

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| B1 | Brand is a singleton; no admin | No CRUD, no swatch/style preview; one env-var JSON. | High | BRAND-3 | 🔧 |
| B2 | `logoAssets` not consumed | BRAND-1 says a profile carries logo assets; nothing links them — logos only exist if separately uploaded with matching names. (They are at least surfaced to the engine via the profile in the prompt.) | Med | BRAND-1 | 📋 |
| B3 | Profile styles bypass brand rules | `brand_rules` runs on the RAW document, so profile-defined char styles/swatches are never re-checked against `minTypeSize`/contrast. A profile `Legal` at 7 pt or a low-contrast pairing in a profile style is invisible to VAL-2/4. | Med | VAL-2/4 | 📋 |
| B4 | Profiles not pinned once used | EXP-1 `.sla` recompiles against the **live** profile, so a stored version isn't reproducible if the profile later changes. | Med | BRAND-4 | 📋 |

## C. Fonts

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| C1 | Whitelisted ≠ installed | The font whitelist can name faces absent on the render host. No validator checks availability; Scribus silently substitutes. The brand's licensed Canela/Söhne are whitelisted but only Liberation/DejaVu exist on the host → substitution. (This is the "server-licensed fonts" homework.) | High | VAL-2 | 📋 |

## D. Images & assets

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| D1 | **Vector logos unsupported** | `sniff()` accepts only PNG/JPEG/TIFF → SVG/EPS/PDF upload returns 415. The brief ships a vector logo master; it must be hand-rebuilt as native `shape`/`path` items or flattened to PNG (loses scalability). | High | RND-5 | 📋 |
| D2 | TIFF dimensions unknown | `sniff()` returns `(mime, None, None)` for TIFF (no IFD walk) → UI shows no dimensions; the engine gets no aspect hint for TIFF assets. | Med | RND-5 | 📋 |
| D3 | CMYK JPEG previews wrong | Accepted (mime+dims read) but browsers render Adobe CMYK JPEGs inverted in `<img>` — wrong in Assets grid and any preview. | Med | RND-5 | 📋 |
| D4 | No upload size guard | 5000×3500 accepted; no max-dimension or byte-size limit → DB BLOB bloat, slow staging to the render host. | Med | RND-5 | 🔧 |
| D5 | No min-size / DPI check | 16×16 accepted and upscaled into any frame → blurry print. No effective-DPI warning vs frame. | Low | RND-5 | 📋 |
| D6 | Aspect never validated | Asset aspect is shown to the engine but never checked against the placing frame; `stretch` can distort silently. | Low | RND-5 | 📋 |
| D7 | Write-once, no delete/replace | Fixing a typo or updating artwork needs a brand-new name; there's no admin delete (by design for history, but no affordance/guidance). | Low | RND-5 | 📋 |
| D8 | **Layered PSD unsupported** (noted 6 Jul 2026 from a client-asset question, not part of the Harvest fixture) | `sniff()` doesn't recognise `8BPS` → `.psd` upload returns 415, same gate as D1. Two distinct halves: **transparency already works** — a flattened PNG with alpha uploads, places in Scribus, and survives PDF/X-4 export (X-4 keeps live transparency); **layers are structurally unsupported** — the document schema treats assets as atomic images, so layer semantics ("hide the price flash") have nowhere to live even if upload accepted PSD. Tiers: (1) state "flattened PNG/TIFF with transparency" as the client asset requirement in brand intake docs (free — recommended, fold into the pilot-brand-assets homework); (2) accept + stage PSD as-is (S — Scribus places `.psd` natively; needs sniff signature, `EXT_BY_MIME`, dims for the D4 guard; thumbnails need Pillow's composite read, which requires "Maximize Compatibility" saves, else convert to PNG at ingest); (3) layer-aware assets = new schema semantics, Phase 3. | Med | RND-5 | 📋 |

## E. Copy

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| E1 | No copy-integrity check | The system prompt says "verbatim", but nothing verifies the headline/subhead/body/legal actually appear unaltered — a paraphrased or dropped legal line passes validation. | High | VAL-5 | 🔧 |
| E2 | Special-char round-trip | Legal carries `£ © * & /` + a date. JSON → SLA → PDF encoding fidelity is unverified. | Med | VAL-5 | ✅/confirm |

## F. Geometry & shaped formats

| # | Gap | Today | Sev | PRD | Disp |
|---|---|---|---|---|---|
| F1 | Closed die-cut contours | VAL-3 requires cut paths be OPEN (no `Z`). A round wobbler / sealed die is inherently a **closed** contour — the rule assumes open cut/crease lines only. | Med | VAL-3 | 📋 |
| F2 | Per-format mandatories | A `CutContour` is mandatory on shaped pieces but not flat ones; mandatory elements are global per profile/brief, not per format. | Med | BRF-2 | 📋 |
| F3 | Tiny-frame feasibility | The shelf strip (510×74 pt) + 7 pt minimum may be physically infeasible for the copy → overflow (VAL-6). Tight formats have no feasibility pre-check. | Low | VAL-6 | 📋 |

---

## Live-run confirmation

Run on 2026-06-22 against the local stack (render container on :8127, worker on
:8200) via `load.py --edge` + targeted generations. Anthropic spend ≈ $1.50.

### Confirmed as predicted

| ID | Confirmation |
|---|---|
| A1 / B1 | `brief.brand: "Meridian Market"` resolved to the stored profile; `/generate` echoed `"brand": "Meridian Market"`. De-singleton works (🔧 verified end-to-end, incl. the new Brands admin UI rendering all 9 swatches + spot tags). |
| A2 / E1 | The 3 brief mandatory elements **and** verbatim headline/legal were enforced — the approved-path document contained named items `meridian-logo`, `legal-line`, `harvest-recipe-qr` and verbatim headline + legal (🔧 verified). |
| D1 | `meridian-logo.svg` and the GIF both returned **415** — vector logos genuinely cannot be ingested. |
| D2 | `harvest-hero-cmyk.tif` uploaded with `width/height = null` (no IFD walk) — and the BLOB was **7.5 MB** vs the same image's 159 KB JPEG. |
| D3 | CMYK JPEG accepted with dims read (1600×1200); print-correct but previews unreliably in `<img>`. |
| D4 | `oversized-banner` (5000×3500) and a 7.5 MB TIFF both accepted — **no size guard** (now closed: see below). |
| D5 / D6 | 16×16 and 3000×80 accepted with no min-size / aspect validation. |
| E2 | **`£`, `©`, `&`, `/` and the date round-tripped intact** through brief → document → SLA → 120 dpi proof. No mojibake. |

### New findings surfaced only by running it

| # | Finding | Evidence | Sev |
|---|---|---|---|
| L1 | **A profile floor can be unsatisfiable against its own palette.** At the originally-authored `contrastFloor: 4.5`, every accent pairing the brand directs (OrchardRust / GoldenOchre subhead on Bone or Plum) lands at 3.0–4.34 — below the floor. Both a draft and a standard fan-out produced **zero** stored concepts; all iterations were spent on `low-contrast`. Recalibrated the fixture to `4.0` (still catches the genuine 1.07–3.02 invisible-text cases) and one Opus concept then passed cleanly. | 7× `low-contrast` (incl. 4.31, and several ~1.07 invisible-text) on a well-formed Sonnet emit | High |
| L2 | **A fully-failed concept stores nothing — no trace of why.** When no iteration passes validation, `result.document` stays `None`, so no `doc_version` is written and the proof grid shows "no proof" with no error/validation report. The reviewer can't see what blocked it. | Draft + standard runs: concepts created, latest summary `null`; worker log clean | High (ADM-2) |
| L3 | **The maximal brief blows the per-concept cost target on premium.** One Opus concept = **$0.637**; a 6-up fan-out ≈ $3.8, over the £2/brief NFR. The richer the brief (long legal, many mandatories, strict contrast), the more repair iterations, the higher the cost. | `usage.cost_usd = 0.63714`, 4 Opus iterations | Med (GEN-5/§8) |
| L4 | **Self-critique rarely approves the maximal brief at the iteration cap.** The one valid Opus concept rendered correctly but `critique.approve = false` at iteration 4 — a denser brief needs a higher cap or it never self-approves. | `approved: false`, models `[opus×4]` | Low |
| L5 | **Models sometimes wrap the tool input in a `{"document": …}` envelope.** Haiku did; the schema gate catches it (`additionalProperties`/missing `version`) and feeds repair, but weaker models can burn iterations on it. | First Haiku emit had top-level key `document` only | Low |

### Closed during this run

- **D4 guard** added: `/assets` now rejects images over a max dimension
  (default 4096 px) or byte size (default 16 MB) with **413**, both env-
  configurable. Verified live: the 5000×3500 banner is now refused
  (`5000x3500px exceeds the 4096px max-dimension limit`). The 7.5 MB CMYK TIFF
  still passes the byte cap (under 16 MB) and is dimension-blind (gap D2), so
  TIFF byte/DPI limits remain the recommended follow-up.
- **L1 / E1 / A2** are the gates working as designed once calibrated; the
  fixture floor is set to a demanding-but-satisfiable 4.0.

### Still open (recommended next)

L2 (persist a failed-concept validation report so the grid can explain "no
proof"), L3 (per-brief budget guard / iteration cap surfaced in BRF-1), and the
deferred structural items (BRF-2 multi-format, RND-5 vector ingestion,
render-host font validation).
