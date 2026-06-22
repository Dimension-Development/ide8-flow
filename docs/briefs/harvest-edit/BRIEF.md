# Creative Brief — The Harvest Edit (Autumn Seasonal POS Kit)

| | |
|---|---|
| **Client** | Meridian Market (premium neighbourhood grocer, 240 stores) |
| **Campaign code** | MM-AUT26-HARVEST |
| **Brief type** | In-store POS kit — seasonal range launch |
| **Brand profile** | `Meridian Market` (`brand_profile.json`) |
| **Prepared** | 2026-06-22 · for ide8.flow generation |
| **In market** | 15 Sep – 31 Oct 2026 |
| **Master format** | Gondola-end header (SRA3 landscape) |

> **Why this brief exists.** It is a deliberately *maximal* brief. It carries
> every input a real 2D graphic-design brief would — brand guidelines, a full
> type system, colour incl. spot separations, logo lockups (raster **and**
> vector), photography, icons, a structured copy deck with legal, a multi-piece
> format kit, die-cut shapes, and production specs — specifically to push every
> part of ide8.flow and surface gaps. The companion [`GAPS.md`](GAPS.md) records
> what the platform does and doesn't yet handle.

---

## 1. Background

Autumn is Meridian's second-biggest seasonal moment after Christmas. "The
Harvest Edit" is a curated range of British seasonal produce and ambient lines
(squash, plums, cobnuts, slow-ripened tomatoes, chutneys, baking). It launches
mid-September and must feel like the considered, editorial counterpart to the
discounters' autumn shout. The retail goal is twofold: drive trial of the
seasonal range, and convert shoppers to the **Meridian+** membership via a
shelf-level member price and a recipe QR.

## 2. Objective

Make the Harvest range unmissable in store and make the member price the reason
to scan and sign up.

**KPIs:** +12% seasonal-range units vs last year · 8,000 new Meridian+ sign-ups
· QR scan-through ≥ 4%.

## 3. Audience

Existing weekly shoppers, 28–55, quality-led and time-poor; skews toward current
and lapsed Meridian+ members. They respond to provenance, craft and a genuine
saving — not to urgency gimmicks.

## 4. Single-minded proposition

**"Seasonal flavour, picked at its peak — at a member price."**

## 5. Deliverables — the format kit (BRF-2)

One campaign, six pieces. **Generate the master now**; the rest are the intended
variant set that should reflow from the approved master.

| # | Format | Size | Orientation | Special | Role |
|---|---|---|---|---|---|
| 1 | Gondola-end header | SRA3 | landscape | spot CopperSpot | **master** |
| 2 | Entrance / window poster | A1 | portrait | spot CopperSpot | variant |
| 3 | Shelf-edge strip | 180 × 26 mm (custom) | landscape | extreme aspect; price-led | variant |
| 4 | Aisle fin | 106 × 212 mm (custom) | portrait | **die-cut** arrow (CutContour) | variant |
| 5 | Wobbler | A5 | portrait | **die-cut** circle (CutContour) | variant |
| 6 | Dump-bin wrap | 423 × 141 mm (custom) | landscape | wraps corners | variant |

Each format is its own document — formats are never mixed in one document.

## 6. Copy deck (use verbatim — VAL-5)

- **Headline:** THE HARVEST EDIT
- **Subhead:** Seasonal flavour, picked at its peak
- **Body 1:** Our growers' best of the season — squash, plums, cobnuts and slow-ripened tomatoes, in store now.
- **Body 2:** Member price unlocked at the shelf. Scan to add this week's Harvest recipes to your basket.
- **Price flash:** £2.50 each · *was £3.50* · Meridian+ only
- **Strapline:** Tastes like the turn of the season.
- **QR caption:** Scan for Harvest recipes
- **Legal (verbatim, do not re-wrap or alter):**
  > *Member price requires a free Meridian+ account. £3.50 saving vs.
  > non-member price on selected lines until 31/10/26, while stocks last.
  > Origin & allergen information at meridianmarket.co.uk/harvest. ©2026
  > Meridian Market Ltd. T&Cs apply.

The legal line intentionally carries `£ © * & /` and a date — it exercises
verbatim-copy and character-encoding handling end to end.

## 7. Brand guidelines (summary — full machine profile in `brand_profile.json`)

**Colour.** Ground in `HarvestPlum`; energy from `OrchardRust` and
`GoldenOchre`; `SageMist` sparingly. `CopperSpot` is a **spot** separation
reserved for the logo lockup and the price flash on premium pieces. `CutContour`
is a **spot** used only as the die-cut guide. `DigitalBerry` is an RGB/screen-
only colour for the QR lockup. Two spot separations must survive to PDF.

**Type.**

| Style | Typeface (intended) | On-host substitute | Use |
|---|---|---|---|
| Display | Canela Deck Medium | Liberation Sans Bold | Headline, price |
| Sans | Söhne Buch / Kräftig | Liberation Sans Regular/Bold | Subhead, body |
| — | — | Liberation Serif | editorial accents |

Minimum type size **7 pt**. The intended licensed faces (Canela, Söhne) are the
brand's; the render host only has the Liberation/DejaVu substitutes — see
[`GAPS.md`](GAPS.md) §Fonts.

**Logo.** `meridian-logo` on light grounds; `meridian-logo-reversed` on plum /
photography; `meridian-mark` where the wordmark won't fit. Clear space ≥ 18 pt;
never below 84 pt wide. The authoritative master is **vector** (`meridian-logo.svg`).

## 8. Mandatory elements (must appear in every piece)

1. `meridian-logo` (correct version for the ground)
2. `legal-line` (the legal copy above, verbatim)
3. `harvest-recipe-qr` (the recipe/sign-up QR)

Plus, on shaped pieces only: a `CutContour` cut path matching the die.

## 9. Tone & art direction

Warm, premium, confident — an editorial grocer. Think a good Saturday market
stall art-directed by a magazine: generous colour blocking, one confident food
hero per piece, strong type hierarchy, calm negative space. Never shouty.

**Hierarchy:** headline → food hero → price / member hook → recipe QR → legal.
**Do:** lean on deep plum grounds and copper accents; let the food breathe.
**Avoid:** cluttered starbursts, rainbow gradients, stock "autumn leaves"
clip-art, drop shadows on type.

## 10. Accessibility & production

- Body & legal must clear a **4.0** contrast ratio; all copy inside the safe zone.
  (Authored at 4.5 first — see [`GAPS.md`](GAPS.md) §L1 for why that floor was
  unsatisfiable against the accent palette and recalibrated to 4.0.)
- Litho + spot CopperSpot (header/poster); digital for short-run fins/wobblers.
- FSC 350 gsm board, matt laminate. Die-cut pieces kiss-cut on the `CutContour` guide.
- Output intent: **PDF/X-4, FOGRA51 (PSO Coated v3)**.

## 11. Reference assets

Provided in [`../../../services/worker/examples/harvest-edit/assets/`](../../../services/worker/examples/harvest-edit/assets/)
and listed in `manifest.json`. Usable set: `harvest-hero`, `harvest-lifestyle`,
`kraft-texture`, `meridian-logo`, `meridian-logo-reversed`, `meridian-mark`,
`harvest-recipe-qr`, `leaf-icon`, `allergen-icons`, `meridian-plus-badge`. An
edge-case set (CMYK, oversized, tiny, extreme-aspect, SVG, GIF) lives in
`assets/edge-cases/` to probe the upload pipeline.

## 12. Timeline & success criteria

Concepts → internal review (Alex's team) → 1 master approved → variant kit →
preflight (PitStop) → release (Phoenix). Success = a master a design director
would put in front of the client first round, that passes preflight with both
spot separations and a named `CutContour` on shaped pieces.

---

### Appendix — how to run this brief through ide8.flow

See [`../../../services/worker/examples/harvest-edit/README.md`](../../../services/worker/examples/harvest-edit/README.md)
for the one-command loader (`load.py`) that creates the brand profile, uploads
the assets, and fires a fan-out against the local worker.
