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
2. Richer expressive controls: aftertouch, stepped/smoothed bend, custom
   controller curves, additional LFO shapes, and continuous CC modulation
   beyond the live layer crossfade profile. CC crossfade power, omitted or
   degenerate endpoints, and player-specific gain smoothing need their own
   verified mapping.
3. Remaining articulation rules: release-region controller/keyswitch history,
   richer controller-trigger combinations, repeated-note masking and release-tail
   termination. Specify portable rules before importing them.
4. EQ, after bandwidth and resonance transfer functions are specified and tested.

Each feature needs precise defaults, bounds, inheritance, source-located
diagnostics and focused regressions. A portable concept must be useful outside
SFZ. Unsupported behavior must stay visible rather than be approximated.

## Qualification still open

See [reference qualification](reference-test.md). Native/authored agreement is
established for the tested profiles; full sfizz waveform equivalence and
repeatability are not. The parabolic filter-LFO profile matches the pinned
player's waveform equation. Its remaining rendered residual is tracked
alongside the existing triangle profile's different waveform.

## Designs that need a separate contract

These features remain diagnostic with the pinned dependencies. Each design
lists the contract needed before a converter or compatibility profile can
claim support.

| Area | Ownership and acceptance boundary |
| --- | --- |
| Beat-synchronized controls | uFor and consumers need a sampler transport contract that identifies the beat clock available to a voice. Define phase origin, behavior across tempo changes, and whether retriggers reset phase. Verify the same event sequence across block partitions and snapshot restore. safaz supplies opcode defaults and reports absent transport configuration. |
| Buses, sends and effects | Map SFZ output numbers and named buses to explicit audio destinations. Define where dry and wet signals branch relative to voice gain, filtering and pan. The sample score and consumer must agree on per-voice versus shared effect state and tail lifetime. Verify multi-output routing, dry/wet gain and tails independently before mapping particular effects. |
| Generated sources and waveguides | uFor needs a source model for generated voices with pitch, channel and lifetime semantics independently of a file asset. Consumers must implement generation and preserve oscillator or waveguide state on restore. safaz maps each supported source family and diagnoses waveform or physical-model options without a matching source. |
| Preprocessor includes and vendor opcodes | An include profile must define path and macro scope, asset-relative paths, include order and export expectations. A pure parser can consume a caller-supplied source inventory. The file adapter and package reader must resolve the same contained files, report missing files and cycles, and retain filenames in diagnostics. Vendor opcodes also require a named compatibility profile with tests for conflicts with the standard spellings. |
| Player-dependent sample units | Establish the player, version, units and rounding for each affected opcode. Test endpoint inclusivity, reverse and loop behavior, source versus output rates, and embedded loop metadata. Use a profile when conventions differ. |

### Remaining playback and conversion contracts

- **Filter envelopes and expressive controls.** Specify whether each modifier is
  sampled at voice start or evaluated while a voice sounds. uFor and the
  consumer must agree on parameter targets, interpolation, release capture
  and snapshot state. The pinned enge MIDI adapter ignores channel and
  polyphonic key pressure. Aftertouch needs an input contract that maps their
  distinct scopes. Controller curves and LFO shapes need verified endpoints,
  defaults and precedence across inherited sections. The shared CC crossfade
  runtime does not specify those rules for other modulation targets.
- **Articulation history and retirement.** Release-region conditions need
  per-trigger records of the note-on conditions and an explicit choice of
  when to read any live controls. Repeated notes and release tails need
  deterministic ordering with pedal changes, choke and voice-limit events.
  The new Rust release planner ports the existing key and sustain decisions.
  Release-region history and controller-trigger combinations still need a
  portable contract with overlapping notes and identical-velocity triggers.
- **Equalizer.** uFor can describe frequency, gain and bandwidth, but the
  pinned enge sampler has no EQ processing. Implement that stage and compare
  its transfer function against SFZ before selecting a profile. Verify zero
  gain, both signed gains, center gain and both bandwidth edges at several
  rates. Include filter and amplifier ordering in the comparison.

## Additional work beyond the prompt

None.
