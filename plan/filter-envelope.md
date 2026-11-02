# Portable filter-envelope proposal

Status: proposed for review, not approved or implemented. The user requested
this design after the 2026-11-02 modulation audit. Existing filter-envelope
diagnostics and playback remain unchanged.

## Problem and evidence

The pinned sfizz envelope is not a fixed-duration interpolation between two
levels. Its decay and release repeatedly multiply the current value, test a
threshold, and then enter a linear transition. Release captures the current
level, so its exponential phase ends at different times when a key is released
during attack, decay or sustain.

Source: sfizz `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`,
[`ADSREnvelope.cpp`](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/ADSREnvelope.cpp)
and [`Config.h`](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Config.h).

- Attack advances by `1 / (sample_rate * attack_seconds)`, independently of
  the starting level. A nonzero start therefore shortens the attack.
- Positive decay/release time yields a multiplier `exp(-9 / (time * rate))`,
  with the source's minimum-time rule. It is not a normalized curve ending
  exactly at the nominal duration.
- Decay approaches zero until it reaches sustain or its sustain threshold,
  then settles to sustain over a 50 ms transition when needed.
- Release approaches zero until `1e-4`, then fades linearly. The fade slope
  uses `max(1e-4, captured_level) / (rate * 0.05)`, so a small starting level
  can finish in less than 50 ms.
- Even zero release time retains the terminal fade. Mapping it to an
  instantaneous generic release would silently change behavior.
- Update-before-output and event-boundary rules affect individual samples.
  Continuous curve agreement alone does not establish matching audio.
- Release starts its terminal fade from the last pre-crossing value, rather
  than the exponentially advanced value that crossed the threshold. Decay's
  sustain-threshold check occurs after its inner output loop, so block-boundary
  observation also needs explicit qualification. These details must not be
  mistaken for a generic fixed-duration decay curve.

For example, with a nominal one-second release and a zero asymptote, the
continuous threshold time is `log(initial / 1e-4) / 9`. It is about 1.023 seconds
from level 1, and 0.768 seconds from level 0.1, before the terminal fade. A
release starting below the threshold skips the exponential part; starting at
`1e-5` gives a roughly 5 ms fade under the 50 ms / `1e-4` speed-floor rule.
These are explanatory continuous values, not sample-exact sfizz predictions.

uFor's current `Segment` is an endpoint/duration curve. EnveLFO already owns
envelope evaluation and event state, and enge consumes that evaluation. Adding
an SFZ envelope implementation directly to safaz or enge would duplicate this
ownership and leave snapshot/event semantics inconsistent.

## Recommended scope

Add one generic exponential-approach stage to the shared envelope model, with
an explicit stopping condition and terminal transition. Keep existing Segment
semantics and defaults unchanged. This primitive is useful for physical decay
and envelopes beyond SFZ; its fields must describe behavior, not opcode names.

The proposed contract needs:

1. A captured initial value and an asymptotic target, with a positive time
   constant. The continuous equation is
   `target + (initial - target) * exp(-elapsed / time_constant)`.
2. A declared crossing level that completes the exponential phase. Completion
   must be deterministic and must not depend on the renderer's block size.
3. A terminal linear transition to a declared final level, with a duration and
   optional minimum transition speed. The speed floor expresses sfizz's
   sub-threshold release without assigning the same duration to every level.
4. Explicit handling of zero time, already-crossed thresholds, interrupted
   phases, and release during onset delay. These are part of the contract,
   not fallback behavior.

Proposed stage fields for review:

| Field | Meaning |
| --- | --- |
| `kind = exponential_approach` | A distinct stage, leaving existing Segment behavior intact. |
| `asymptote` | The level approached by the exponential equation. |
| `time_constant` | Nonnegative seconds; zero skips the exponential phase and enters the terminal transition from the captured value. |
| `threshold` | Level whose crossing ends the exponential phase. Already-crossed starting values skip that phase. |
| `transition_to` | Final level after the terminal transition. |
| `transition_seconds` | Nonnegative nominal transition duration; zero jumps to the final level. |
| `minimum_transition_distance = 0` | A nonnegative distance floor when calculating transition speed. |

Each stage captures its initial value from the current envelope value. It does
not need a second initial-value field. At the terminal transition, capture the
remaining distance to `transition_to`; speed is the larger of that distance and
`minimum_transition_distance`, divided by `transition_seconds`. This gives an
explicitly bounded transition duration without an SFZ-specific release flag.
Level bounds, direction and the threshold's relationship to the asymptote must
be validated; moving away from the threshold is rejected.

The generic stage's crossing time is analytic and independent of block size.
The SFZ adapter must declare how that crossing is observed on the output sample
grid, including advance-before-output. This observation convention is the main
remaining design question to settle before implementation. If the existing
host boundary model cannot express it, revise this proposal rather than silently
changing generic envelope sampling. Do not reinterpret the existing curve
parameter as a time constant.

Recommendation: keep portable stage transitions independent of render block
size. Do not reproduce a reference engine's block-boundary-dependent transition
as a default envelope convention. Qualify the adapter against sfizz and retain
any residual difference explicitly. Approval of this primitive would not by
itself authorize claiming exact sfizz envelope equivalence.

## Ownership and implementation order

1. **uFor:** define and validate the stage and its wire representation. Specify
   captured-level, crossing, interruption and sample-observation rules. Existing
   documents continue to describe exactly their existing behavior.
2. **enveLFO:** implement scalar and native evaluation, exact event ordering and
   snapshot state for the new stage. Share one set of conformance vectors.
3. **enge:** consume the shared stage through the existing generator path.
   Preserve per-voice state, render partitions and snapshot continuation.
4. **safaz:** map the verified first-filter `fileg_*` subset behind an explicit
   response choice. Combine signed envelope depth with keyboard, velocity and
   LFO cents before cutoff conversion; verify combined bounds. Richer envelope
   modifiers and export remain diagnosed until separately supported.

The SFZ adapter must explicitly account for its time rounding and observation
convention. It must not change the default phase/timing of generic envelopes.
Exact floating-point identity with sfizz is not promised; comparisons keep the
existing numerical limits and retain any differences.

## Acceptance evidence

- Independently calculated levels and crossing times, including releases from
  multiple attack/decay/sustain positions and levels on both sides of `1e-4`.
- Zero durations, nonzero starting level, sustain endpoints and signed depth.
- Note-off during delay, simultaneous events, overlapping voices, and restart.
- Partition invariance and JSON snapshot continuation before and after each
  phase transition on both backends.
- One-second-or-longer 48 kHz audio regressions, then the unchanged pinned
  sfizz client on Linux, Windows and macOS with retained WAVs and residuals.
- Combined cutoff-bound diagnostics remain explicit; no clipping, fitted gain,
  timing alignment or tolerance relaxation may hide discrepancies.

## Decision requested

Approve a separate shared-envelope implementation batch along the ownership
order above. Until then, leave filter-envelope import diagnosed. The completed
LFO and pitch-bend work does not depend on this proposal.

## Additional work beyond the prompt

None. This is the requested design proposal; implementing it requires approval.
