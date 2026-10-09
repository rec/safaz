# Reference Rendering Tests

## Purpose

Test the complete SFZ import and playback chain against a pinned sfizz build:
original SFZ through sfizz versus safaz import, uFor preparation, and enge
rendering. Start now with a small deterministic baseline, then add feature
families as their behavior is established.

sfizz is a reference for our explicitly accepted profiles, not an authority
for every SFZ player's behavior. A disagreement must be investigated before
changing an importer rule, native model, renderer, or acceptance threshold.
Uncertain cases retain diagnostics.

## Ownership and Scope

Keep the fixtures and comparison harness in safaz's reference-test suite.
safaz owns conversion and diagnostics; uFor owns portable semantics; enge owns
native playback. Test-only use of enge must not introduce a production
dependency or reverse these ownership boundaries.

This plan implements reference testing, not missing SFZ features or automatic
repairs to rendering differences. Report discovered defects with reproducible
fixtures; propose behavior or architecture changes before implementing them.
Do not start with commercial instruments, hardware, plugins, or a DAW.

## 1. Establish the Reference Runner

Use sfizz revision `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, already used by
the filter profiles. Pin its submodules and record the compiler, build options,
platform, sfizz revision, and safaz/uFor/enge revisions with each run.

Start with the bundled `sfizz_render` offline client. Audit its behavior at
the pinned revision before selecting command-line arguments. In particular,
verify MIDI event ordering, frame placement, sample loading completion,
master gain, output sample format, voice limits, and render termination.
Use a library-only/offline build without audio-device or plugin dependencies.
Verify build flags against that revision rather than copying current defaults.

The runner must support identical settings and a declared render horizon.
If the bundled client cannot provide the required control or output precision,
stop and propose replacing it with one small offline driver using sfizz's C
API. Do not maintain two reference paths or silently weaken the comparisons.
The API requires block events to be submitted before rendering that block.

References: [official build documentation](https://www.sfz.tools/sfizz/development/build/),
[C API](https://sfz.tools/sfizz/api/sfizz.h/), and
[pinned source](https://github.com/sfztools/sfizz/tree/f5c6e29f23b8057867c08e88f5f6ac6738baa30b).
Current documentation is guidance; the pinned source defines the tested runner.

## 2. Match the Two Rendering Paths

Use the same source WAVs and MIDI file for both paths. Decode native assets
without rescaling them. Feed imported instruments through existing uFor
performance bindings and enge preparation/rendering APIs, rather than adding
another MIDI interpreter or sampler.

Declare and record:

- Output rate of 48,000 Hz and explicit stereo channel order.
- A fixed output horizon of at least one second, including the required tail.
- Initial block size of 256 frames and native `control_interval=1`.
- Explicit master gain, tuning, interpolation/quality settings, and adequate
  voice capacity; disable optional effects and avoid voice stealing initially.
- MIDI tempo, event times, same-time ordering, controller initialization, and
  note identity/release rules.
- Explicit import choices required by the fixture, including filter profiles.

For the initial MIDI fixtures, use a fixed tempo of 500,000 microseconds per
quarter note and 960 ticks per quarter note: each tick is exactly 25 frames at
48 kHz. This removes event-rounding ambiguity. Events must also exercise block
boundaries. Fractional-frame timing belongs in a later, separately specified
test family.

Require a complete conversion for positive comparison fixtures. Cases expected
to be diagnosed must assert their diagnostics separately and must not pass as
audio-equivalent imports.

Audit the settings with a unity-gain, untransposed sample before testing more
features. Do not compensate for unexplained gain or latency by fitting a scale
or offset to the reference output.

## 3. Implement the First Small Fixture Set

Use compact, handwritten SFZs and deterministic WAV assets at 48 kHz, each at
least 48,000 frames long. Keep assets comfortably below clipping. Use distinct
tones or timed markers to make source selection observable in the reference
audio; do not assume sfizz exposes a portable internal voice-selection trace.

Initial cases:

1. One untransposed, unfiltered sample at explicit unity gain, with simple
   supported playback/envelope settings. Check onset, channels, and completion.
2. Positive and negative authored gain changes and note velocities 1, 64, and
   127. Check absolute gain and the declared velocity-response formula.
3. Reference-key playback and transposition above/below it. Check pitch and
   traversal duration without hiding interpolation differences.
4. Two key regions and two velocity regions with distinct sample signatures.
   Exercise both sides of inclusive boundaries and intentional silence.

Keep each case focused. Resolve baseline discrepancies before using the
baseline to validate more complex instruments. Begin with enge's NumPy
reference backend, then apply the same fixtures to its native backend.

## 4. Define Meaningful Comparisons

Separate independently specified behavior from numerical DSP similarity:

| Behavior | Comparison |
| --- | --- |
| Region eligibility | Authored expectations, native prepared actions, and distinguishable reference sample signatures |
| Timing and termination | Expected frame coordinates and known marker positions; no automatic alignment or silence trimming |
| Gain and velocity response | Absolute level and expected ratios on declared windows; no peak or loudness normalization |
| Pitch and sample traversal | Frequency, marker spacing, and duration with declared measurement precision |
| Equivalent waveform paths | Maximum absolute error and RMS residual over the entire declared horizon |
| Filters and different DSP algorithms | Independently specified response measurements and feature-specific error limits, plus residual audio |

Set thresholds before accepting each fixture. Derive them from signal
precision, independent equations, and the documented equivalence contract.
Calibrate measurement precision with known signals, not by increasing limits
until the implementation passes. If reference output is quantized, account for
its declared quantization explicitly or choose a higher-precision runner.

There is no single universal waveform tolerance. A good spectrum does not
excuse wrong timing, region selection, or gain. A renderer using a different
algorithm may meet a response contract without cancelling sample for sample;
label that distinction explicitly rather than calling it an exact match.

For diagnosis, compare enge's NumPy and native outputs, inspect the converted
document and prepared actions, and reduce the SFZ to the failing behavior.
These checks help locate a discrepancy but do not automatically establish
which implementation is correct.

## 5. Preserve Useful Failure Artifacts

On failure, retain the fixture inputs, imported native document, ordered
events/prepared actions, diagnostics, settings/version manifest, reference WAV,
native WAV, signed difference WAV, and a compact report of failed measurements.
Difference audio must preserve the original scale; any amplified listening
copy must be clearly labelled and excluded from acceptance calculations.

Use isolated temporary directories per case. Run sfizz in a separate process
so native crashes become reported test failures. Preserve exit status and
stderr; do not turn build failures, missing samples, or renderer errors into
passing/skipped comparisons.

Avoid large checked-in render outputs. Keep small deterministic source assets
and expected measurements in the repository; publish failure renders as CI
artifacts. Reference renders may be cached only with keys covering the pinned
build, settings, and all fixture inputs.

## 6. Keep CI Portable and the Fast Suite Fast

Create a separate opt-in reference test job for Linux, Windows, and macOS.
Build the same pinned sfizz revision and install pinned test-only dependencies.
Use portable paths and process APIs; do not require Bash, Unix signals, an
audio device, or locally installed plugins in the harness.

Normal unit tests must remain usable without sfizz or enge installed. Reference
tests may report an explicit local skip when not enabled, but the dedicated CI
job must fail if its reference runner or required dependency is unavailable.
Keep environment installation separate from test execution and review any
dependency changes in separate commits.

Run the initial fixtures serially. Introduce bounded parallelism only after
repeatability is verified, avoiding nested worker pools and shared output paths.
Repeat a representative render and compare it across block sizes, including
an irregular size, before declaring the runner stable. Check cross-platform
measurement consistency without assuming identical floating-point WAV bytes.

## 7. Expand After the Baseline Passes

Add static filters, keyboard/velocity tracking, and the accepted triangle LFO
profiles next. Then extend to loops, envelopes, chokes, keyswitches, controller
conditions, and round-robin behavior where the native and reference rules agree.
Each new family needs its own expectations and comparison rationale.

Differences in player-dependent cases are evidence for diagnostics or an
explicit profile decision, not a reason to silently adopt sfizz behavior.
Keep unsupported features and richer SFZ 2 modulation outside the first slice.

## Completion Criteria

- Both rendering paths use recorded, reproducible settings and identical inputs.
- The four initial fixture families pass their independently defined criteria
  through both native rendering backends on Linux, Windows, and macOS.
- Deliberately changed gain, pitch, event timing, and region boundaries are
  detected, demonstrating that the comparisons can catch meaningful defects.
- Repeat renders and block-size checks establish the supported repeatability.
- Failures produce enough evidence to distinguish conversion, preparation,
  playback, reference-runner, and measurement problems.
- The existing unit suite stays independent of the external reference build.
- No tolerance change, gain fitting, time alignment, or unexpected diagnostic
  can silently turn a mismatch into a pass.

## Additional work beyond the prompt

None.
