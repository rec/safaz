# Remaining SFZ work

Implemented behavior is recorded in [import status](../doc/import-status.md),
the [conversion contract](../doc/conversion.md) and the generated
[opcode support catalog](../doc/sfz-support.md). This plan lists unfinished work
only. A standard opcode classification is not a claim of complete support.

## Current qualification

The bounded filter-envelope implementation was approved on 2026-11-14 and now
spans uFor, enveLFO, enge and safaz. See [the design](../doc/filter-envelope-design.md),
[remaining envelope work](filter-envelope.md) and the reference findings.

## Remaining feature priorities

1. Scope richer filter-envelope modifiers.
2. Richer expressive controls: aftertouch, stepped/smoothed bend, controller
   curves, additional LFO shapes and controller modulation.
3. Remaining articulation rules: release-region controller/keyswitch history,
   richer controller-trigger combinations, repeated-note masking and release-tail
   termination. Specify portable rules before importing them.
4. Export coverage for sparse stereo width and position matrices. Static import
   and verified matrix export are covered in the conversion contract.
5. Qualify runtime snapshot continuation for the imported seeded-variation
   profile and design export behavior for native seeded variation.
6. EQ, after bandwidth and resonance transfer functions are specified and tested.
7. Export gaps for supported import-only features, as listed in the catalog.

Each feature needs precise defaults, bounds, inheritance, source-located
diagnostics and focused regressions. A portable concept must be useful outside
SFZ. Unsupported behavior must stay visible rather than be approximated.

## Qualification still open

See [reference qualification](reference-test.md). Native/authored agreement is
established for the tested profiles; full sfizz waveform equivalence and
repeatability are not. The existing triangle filter-LFO convention differs from
sfizz's default parabolic waveform; changing it is a separate playback decision.

## Larger deferred designs

Beat-synchronized SFZ controls need a declared transport mapping. Buses, sends
and effects need routing semantics. Generated waveforms and waveguides need a
synthesis-source model. Vendor extensions, including `#include`, remain outside
the compatibility promise. Player-dependent sample-unit interpretations and
other disputed conventions need explicit profiles rather than guesses.

## Additional work beyond the prompt

None.
