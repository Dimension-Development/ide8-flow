# A/B: designPrinciples on/off — run 1 (16 Jul 2026)

Same brief (Harvest Edit), same six archetypes, engine `standard`
(sonnet-4-6 fan-out → opus-4-8 escalation), n=6 per arm, sequential runs.
Arm A: "Meridian Market" with `designPrinciples` (DESIGN.md). Arm B:
identical profile, principles stripped. Total spend $6.02.

## Headline numbers

| | A (principles) | B (no principles) |
|---|---|---|
| Concepts with a stored version | 3/6 | 6/6 |
| Validation-clean latest version | 2/6 | 5/6 |
| Dominant failure | `low-contrast` ×4 | `overflow` ×1 |
| Self-critique approved | 0/6 | 0/6 |
| Cost | $2.61 | $3.41 |

## Finding 1 — principles measurably change colour behaviour, into a wall

The principles arm lost 4/6 concepts to `low-contrast` (3 stored nothing
after 4 iterations; 1 stored a failing version). The stripped arm had zero
contrast failures. The DESIGN.md draft steers the model toward the muted
mid-tone Meridian palette hard enough to fight `contrastFloor: 4.0` — the
same tension as the original fixture calibration issue, now induced by
taste text instead of rule numbers. Principles are demonstrably not inert;
this draft is net-negative against the current rules.

**Action:** revise DESIGN.md to encode the constraint as taste ("reserve
mid-tones for accents; headline/subhead pairings stay high-contrast") or
relax the floor. Taste and rules must point the same direction.

## Finding 2 — the 0/12 approval rate was a render bug, not a quality signal

Every multi-line text item in both arms rendered with all lines stacked on
one baseline. Root cause: models emit CSS-style `lineHeight` multipliers
(1.0–1.4); the schema takes absolute points, so 1.2 compiles to 1.2pt
leading. The vision critique correctly refused the garbled proofs — in
both arms — so critique pass rate carried no signal about principles.
Fixed on this branch: `lineheight-not-points` is now a VAL-3 error (the
repair loop corrects it in-flight) and SCHEMA.md states the unit.

**Action:** re-run this A/B after the fix lands; approval rate should be
readable next time.

## Verdict

Inconclusive on the core question (does taste text raise critique pass
rate?) because of finding 2, but productive: one systemic render-quality
bug found and fixed, and clear evidence the principles lever pulls hard
enough to need rule-alignment before the next run.
