# ide8.flow document schema — reference v0.2

**Normative human reference** for document `0.2`. The machine-readable
contract is [`schema/document-0.2.schema.json`](../schema/document-0.2.schema.json).
Everything not changed below retains the `0.1` meaning documented in
[`SCHEMA.md`](./SCHEMA.md).

`0.2` adds the smallest renderer-neutral vocabulary needed by the agency-card
pilot: gradients, item opacity and deterministic image placement. It does not
expose Scribus attributes, general effects or a renderer-specific crop model.

## Version and compatibility

- `version` is the JSON string `"0.2"`.
- A `0.1` document is never silently upgraded.
- `0.2` properties remain invalid under the `0.1` formal schema.
- `pages[].items` remains canonical back-to-front paint order.
- A filled custom motif remains a `shape` with `d`; no motif-specific item
  types are introduced.

## Gradient fills

`fill` accepts either a swatch-name string or a gradient object. Gradient
colours are always named swatches; raw RGB/CMYK values do not appear inside a
fill.

### Linear

```json
{
  "fill": {
    "type": "linear-gradient",
    "start": [0, 0.5],
    "end": [1, 0.5],
    "stops": [
      {"at": 0, "color": "ExamplePink"},
      {"at": 1, "color": "ExampleYellow"}
    ]
  }
}
```

`start` and `end` are `[x, y]` positions normalised to the item frame. They
must be different; the compiler returns `bad-gradient` for a zero-length
vector.

### Radial

```json
{
  "fill": {
    "type": "radial-gradient",
    "center": [0.5, 0.5],
    "focal": [0.4, 0.5],
    "radius": 0.5,
    "stops": [
      {"at": 0, "color": "ExampleYellow"},
      {"at": 1, "color": "ExamplePink"}
    ]
  }
}
```

- `center` and optional `focal` are normalised to the item frame.
- `focal` defaults to `center`.
- `radius` is greater than `0`, at most `2`, and is relative to the frame's
  shorter edge.
- the focal point must lie strictly inside the radial circle. This distance
  rule is checked by the compiler because JSON Schema cannot express it.

### Stops

- 2–16 stops;
- each `at` is `0..1`;
- stop positions are non-decreasing;
- first stop is exactly `0`, last stop exactly `1`;
- repeated positions are allowed for a hard transition;
- every `color` must resolve to a document or merged profile swatch.

Stop ordering/endpoints and swatch resolution are semantic compiler checks.
The formal schema enforces the individual shape and numeric ranges.

Gradients are valid on `shape`, text-frame backgrounds and image-frame
backgrounds. Production `path` items remain stroke-only.

## Item opacity

`opacity` is allowed on `shape` and `image`:

```json
{
  "type": "shape",
  "frame": [10, 10, 60, 60],
  "fill": "ExamplePaper",
  "opacity": 0.5
}
```

- range: `0..1`;
- default: `1`;
- applies to the complete item, including its stroke;
- not valid on `text` or production `path` items in `0.2`.

Text transparency, stop opacity, blend modes, masks and transparency groups
are deliberately outside this version.

## Image placement

An image remains an asset-library reference, never a path:

```json
{
  "type": "image",
  "name": "model-shot",
  "frame": [0, 0, 212.598425, 425.19685],
  "src": "model-cutout",
  "fit": "cover",
  "focus": [0.42, 0.35],
  "zoom": 1.1
}
```

### `fit`

- `contain` (default) — scale proportionally until the complete image fits,
  then centre it in the frame;
- `cover` — scale proportionally until the frame is covered, position the
  focal point at frame centre, then clamp both axes to prevent empty frame
  area;
- `stretch` — scale independently on both axes to fill the frame.

The `0.1` values `frame`, `free` and its separate `stretch` flag do not carry
into `0.2`; versioned documents retain their own semantics.

### `focus` and `zoom`

- valid only when `fit` is explicitly `cover`;
- `focus` is a normalised intrinsic-image point and defaults to `[0.5, 0.5]`;
- `zoom` is `1..8` and defaults to `1`;
- `contain`, `cover` and `stretch` require known source pixel dimensions from
  the asset record;
- missing dimensions fail as `image-dimensions-required` rather than silently
  changing the fit mode.

Source dimensions are transient compile metadata. They are neither authored by
the model nor persisted inside document JSON.

## Stacking

Items are painted in their array order: the first item is furthest back and
the last is on top. This was proven against the pinned Scribus 1.6.1 exporter;
no `zIndex` property is needed.

## Formal-schema versus semantic validation

The formal JSON Schema catches shape, type, range, conditional-property and
unsupported-key failures. The compiler/validation layer must add stable errors
for rules that span values:

| Error | Condition |
|---|---|
| `bad-gradient` | zero-length linear vector, radial focal outside radius, malformed semantic geometry |
| `gradient-stop-order` | stops decrease |
| `gradient-stop-endpoints` | first/last stops are not `0/1` |
| `unknown-swatch` | any solid/stroke/gradient stop references an unknown swatch |
| `bad-opacity` | direct compiler input falls outside `0..1` or uses opacity on an unsupported type |
| `image-dimensions-required` | image placement has no source dimensions |
| `bad-image-dimensions` | dimensions are zero, negative or malformed |
| `bad-image-placement` | fit/focus/zoom cannot produce a finite placement |
| `unsupported-feature` | valid semantic input cannot be represented by the pinned renderer |

## Complete example

[`services/render/examples/example-0.2.json`](../services/render/examples/example-0.2.json)
exercises a gradient background, cover/focal image, 50%-opacity filled vector
motif, text hierarchy and an open spot-colour production path. It is synthetic
construction evidence, not a brand design or a claim of creative quality.

## Still outside schema scope

Linked/chained text frames, text-on-path, master-page content, blend modes,
masks, nested transparency groups, general crop matrices, per-image ICC intent,
tables and arbitrary Affinity/InDesign/Illustrator round-tripping.
