# Scribus 1.6.1 feature mapping for document schema `0.2`

| | |
|---|---|
| **Renderer** | Scribus `1.6.1-0ubuntu7` from the pinned `ide8-render` image |
| **Harvested** | 18 August 2026 |
| **Fixtures** | [`services/render/tests/fixtures/scribus-1.6.1-features`](../../../services/render/tests/fixtures/scribus-1.6.1-features/) |
| **Purpose** | Evidence for T03/T04 compiler implementation; no production compiler behaviour changed |

## Result

Scribus 1.6.1 can preserve and export the capabilities needed by the technical
slice: vector linear/radial gradients, fill/stroke and image opacity, PNG alpha,
filled custom vectors, deterministic manual image placement and back-to-front
page-object order. The present limitation is in ide8.flow's `0.1` document
vocabulary/compiler, not an absence of basic transparency in this Scribus
build.

The harvest also found two behaviours that must be absorbed by the compiler:

1. Scripter initially emits legacy gradient codes `1` (linear) and `5`
   (radial); Scribus changes them to stable codes `6` and `7` on reopen/save.
   The compiler must emit `6/7` directly.
2. Scripter accepts *transparency*, while SLA `TransValue` and `TransValueS`
   store *opacity*. A 25% transparency call saves `0.75`. Document `opacity`
   therefore maps directly to those SLA attributes.

## Stable mappings

All geometry below is local to the `PAGEOBJECT` frame. Public document
coordinates remain normalised; the compiler converts them to points.

| Document concept | Round-trip-stable Scribus 1.6.1 representation |
|---|---|
| Linear gradient | `GRTYP="6"`; `GRSTARTX/Y` and `GRENDX/Y` are item-local points; `GRSCALE="1"`; `GRSKEW="0"`; `GRExt="3"` |
| Radial gradient | `GRTYP="7"`; `GRSTARTX/Y` is centre; `GRENDX/Y` is a radius endpoint; `GRFOCALX/Y` is an absolute item-local focal point |
| Gradient stops | Ordered child elements `<CSTOP RAMP="0..1" NAME="Swatch" SHADE="100" TRANS="1"/>` |
| Shape/image opacity | `TransValue="opacity"`; omit only for the default `1` |
| Stroke opacity | `TransValueS="opacity"`; emit alongside `TransValue` when an opaque/translucent stroked object uses item opacity |
| Centred contain | Manual placement: `SCALETYPE="1"`, `RATIO="1"`, equal `LOCALSCX/Y`, source-pixel `LOCALX/Y` offsets |
| Cover/focal crop | Manual placement: `SCALETYPE="1"`, `RATIO="1"`, equal `LOCALSCX/Y`, clamped source-pixel `LOCALX/Y` offsets |
| Stretch | `SCALETYPE="0"`, `RATIO="0"`, independent `LOCALSCX/Y` |
| Source image | `PFILE` is relative to the SLA; PNG alpha is preserved through proof PDF and rasterisation |
| Filled vector | `PTYPE="6"`, `PCOLOR` fill, optional `PCOLOR2` stroke, closed item-local SVG `path` |
| Stacking | `PAGEOBJECT` XML order is back-to-front; the last overlapping object is painted on top |

### Gradient conversion

For an item frame width `w` and height `h`:

```text
linear start = (start.x * w, start.y * h)
linear end   = (end.x * w,   end.y * h)

radial centre = (center.x * w, center.y * h)
radius points = radius * min(w, h)
radial end    = (centre.x + radius points, centre.y)
radial focal  = (focal.x * w, focal.y * h)
```

The focal point must lie strictly inside the radial circle. The 1.6 renderer
source and gradient editor enforce `distance(focal, centre) < radius`; T03 must
return `bad-gradient` if the semantic document violates that constraint.

`CSTOP` elements remain in document order. T03 must separately enforce first
stop `0`, last stop `1` and non-decreasing positions because JSON Schema cannot
express the cross-element rule.

### Image conversion

`LOCALSCX/Y` are points per source pixel. `LOCALX/Y` are offsets in source
pixels, so a desired frame-local point offset is divided by the corresponding
scale before emission.

For source size `(sw, sh)`, frame `(fw, fh)` and focus `(fx, fy)`:

```text
contain scale = min(fw / sw, fh / sh)
contain offset points = ((fw - sw*scale)/2, (fh - sh*scale)/2)

cover scale = max(fw / sw, fh / sh) * zoom
cover wanted offset points = (fw/2 - fx*sw*scale,
                              fh/2 - fy*sh*scale)
cover clamped x = clamp(wanted x, fw - sw*scale, 0)
cover clamped y = clamp(wanted y, fh - sh*scale, 0)

LOCALSCX = scale
LOCALSCY = scale
LOCALX = offset x / scale
LOCALY = offset y / scale
```

The harvested cover sample uses a `400×200 px` source, `140×120 pt` frame,
focus `(0.625, 0.5)` and zoom `1`. It saves:

```text
scale = 0.6 pt/px
point offset = (-80, 0)
LOCALSCX/Y = 0.6
LOCALX = -133.333333333333
LOCALY = 0
```

The centred contain sample saves scale `0.35`, `LOCALX=0` and
`LOCALY=71.4285714285714`, which corresponds to a `25 pt` vertical offset.

## Paint order and alpha evidence

The paint-order PDF was rasterised at 72 dpi. Pixel `(100, 80)` lies inside
all three shapes and resolves to the blue third/last `PAGEOBJECT`, proving the
array/XML order is back-to-front.

The transparent PNG proof was also rasterised at 72 dpi. Two points inside the
image frame were checked: a transparent source pixel reveals the cyan backing,
while an opaque source pixel remains magenta. Source alpha therefore survives
SLA loading, PDF proof export and Poppler rasterisation.

## Reproduce and verify

Build the pinned image and generate the fixtures as described in the fixture
[`README.md`](../../../services/render/tests/fixtures/scribus-1.6.1-features/README.md).
Then create temporary round-trip and proof outputs:

```bash
mkdir -p /tmp/ide8-scribus-roundtrip /tmp/ide8-scribus-proofs

docker run --rm \
  -v "$PWD/services/render/tests/fixtures/scribus-1.6.1-features:/harvest:ro" \
  -v "/tmp/ide8-scribus-roundtrip:/roundtrip" \
  ide8-render timeout 60s xvfb-run -a scribus -g -ns \
  -py /harvest/roundtrip_features.py /harvest /roundtrip

docker run --rm \
  -v "$PWD/services/render/tests/fixtures/scribus-1.6.1-features:/harvest:ro" \
  -v "/tmp/ide8-scribus-proofs:/out" \
  ide8-render timeout 60s xvfb-run -a scribus -g -ns \
  -py /app/service/scribus_scripts/export_pdf.py \
  /harvest/paint-order.sla /out/paint-order.pdf proof

docker run --rm \
  -v "$PWD/services/render/tests/fixtures/scribus-1.6.1-features:/harvest:ro" \
  -v "/tmp/ide8-scribus-proofs:/out" \
  ide8-render timeout 60s xvfb-run -a scribus -g -ns \
  -py /app/service/scribus_scripts/export_pdf.py \
  /harvest/transparent-png.sla /out/transparent-png.pdf proof

pdftoppm -r 72 -f 1 -l 1 -singlefile \
  /tmp/ide8-scribus-proofs/paint-order.pdf \
  /tmp/ide8-scribus-proofs/paint-order
pdftoppm -r 72 -f 1 -l 1 -singlefile \
  /tmp/ide8-scribus-proofs/transparent-png.pdf \
  /tmp/ide8-scribus-proofs/transparent-png

python3 \
  services/render/tests/fixtures/scribus-1.6.1-features/verify_harvest.py \
  services/render/tests/fixtures/scribus-1.6.1-features \
  /tmp/ide8-scribus-roundtrip \
  /tmp/ide8-scribus-proofs/paint-order.ppm \
  /tmp/ide8-scribus-proofs/transparent-png.ppm
```

Expected result:

```text
ok: Scribus 1.6.1 feature harvest verified
```

## Boundaries retained for `0.2`

- Stop-level transparency remains fixed at `TRANS="1"`; it is not exposed.
- `GRSCALE`, `GRSKEW` and extend modes remain fixed compiler details.
- Blend modes, masks and nested transparency groups remain unsupported.
- Image placement requires source pixel dimensions from the worker asset
  record; these values must not be model-authored or persisted in document
  JSON.
- General DPI-aware image semantics are deferred. `0.2` placement deliberately
  uses source pixels plus frame points and emits raw SLA scale/offset values.
