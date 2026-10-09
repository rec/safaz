# Independent SFZ rendering comparisons

This opt-in suite uses **unmodified upstream sfizz_render**, pinned to
`f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, including its submodules.
There is no patched client or replacement driver. The normal `test/` suite
does not import or require enge or sfizz.

The harness currently reports real failures. It is not evidence that SFZ
playback already agrees. See [current findings](findings.md).

## Run locally

Install the optional group with `uv sync --frozen --group reference`.
Building enge requires Rust; CI pins its build toolchain to 1.85.0.
Check out sfizz separately at the revision above and initialize its recursive
submodules. Build outside its source tree, without changing upstream files:

```text
uv run --no-project --with cmake==3.31.10 cmake -S SFIZZ_SOURCE -B SFIZZ_BUILD -DCMAKE_BUILD_TYPE=Release -DSFIZZ_JACK=OFF -DSFIZZ_SHARED=OFF -DSFIZZ_TESTS=OFF -DSFIZZ_RENDER=ON -DENABLE_LTO=OFF -DCMAKE_CXX_STANDARD=17
uv run --no-project --with cmake==3.31.10 cmake --build SFIZZ_BUILD --config Release --target sfizz_render --parallel 4
uv run --no-sync pytest -q reference_test --require-reference --sfizz-source SFIZZ_SOURCE --sfizz-build SFIZZ_BUILD --sfizz-render SFIZZ_EXECUTABLE --reference-output RESULTS
```

Substitute paths for the uppercase arguments. The default executable is
`SFIZZ_BUILD/library/bin/sfizz_render`; with Visual Studio it is
`SFIZZ_BUILD/library/bin/Release/sfizz_render.exe`. Use a new output directory
for each run so evidence cannot be overwritten. No audio device is required.
With the optional dependencies installed, omitting the runner options skips
external comparisons locally. `--require-reference` turns missing configuration
into a failure. Configured missing files, build failures, subprocess errors and
renderer exceptions always fail.

The manual [reference workflow](../.github/workflows/reference-test.yml) builds
the same upstream revision on Linux, Windows and macOS. Each job uploads its
inputs, logs and available comparison evidence, including on failure. It runs
serially and independently of the fast unit workflow.

## Fixtures and comparisons

Four handwritten SFZs cover unity playback, gain/velocity, octave transposition,
and inclusive key/velocity region boundaries. Sources are generated from exact
PCM16 values: stereo square waves with different periods, opposite channel
polarity, and a silent second half. Each source is one second at 48 kHz. MIDI
uses 960 PPQN and 500,000 microseconds per quarter note, giving exactly 25
frames per tick. An explicit final CC1 reset establishes the output horizon;
the pinned fmidi client ignores delayed end-of-track metadata.

The fixtures also explicitly initialize CC7 to 127; sfizz otherwise inserts a
volume controller at its default of 100. safaz imports this initialization with
an explicit MIDI binding request using the `channel-0` part and oldest matching
release identity. CC10 retains sfizz's center value 0.5 and CC11 its unity value.
The note-only native path uses enge's existing MIDI reader. Its oscillator
control initializers are projected onto the imported instrument's declared
controls. Trigger velocity remains unchanged and feeds the imported native
EventBinding; the unused horizon controller does not select a voice. Both the
original and bound event lists are retained. Controller behavior is outside
these fixtures; a future controller family needs the full binding contract.

Native region selection is checked against authored note/sample expectations
before rendering. Audio uses safaz import, uFor preparation and enge's existing
OfflineSampler with `control_interval=1`, through both NumPy and native backends.
It does not edit the imported envelope to bypass renderer restrictions.

The client fixes master gain at −7.35 dB in `Defaults.h` and exposes no override.
The native output receives that same declared multiplier. Quality 1 selects
linear interpolation in the pinned `Voice.cpp`; capacity is 64 voices. These
fixtures use stereo sources, default equal temperament, one-shot playback,
zero-duration envelope phases, and no authored effects or voice stealing.
The authored oracle uses source positions, dB equations and `(velocity/127)^2`,
independently of either engine. Disagreements with that contract remain failures.

Reference WAVs retain their original block-rounded duration. Comparisons use
the explicitly authored MIDI horizon and separately check that remaining block
padding falls within the PCM16 silence bound. Nothing searches for an offset,
trims based on audio content, normalizes gain, or fits a threshold to a render.

Maximum waveform error is bounded by `2/32768 + 2e-6`. The two PCM16 steps follow
the pinned dr_wav equation `floor((x + 1) * 32767.5) - 32768`; its asymmetric
conversion maps zero to −1, and its unclipped error is less than two steps.
The additional absolute allowance is a declared float32 arithmetic budget,
not a tolerance for differing algorithms. Reports also include RMS residuals,
absolute channel levels and audible frame coordinates. Velocity 1's gain ratio
is explicitly unresolved at PCM16 precision, although its absolute residual is
still recorded. No passing residual establishes its relative gain accuracy.

Failure directories contain input hashes, pinned revisions, platform, build
cache, executable hash and arguments, process logs, imported document, events,
available actions, reports and WAVs. Native and native/reference difference
WAVs exist only if native rendering succeeds. Preparation failures preserve
their traceback and reference/authored difference instead of fabricated audio.
Differences retain their original signed scale.

Repeatability checks use two identical 256-frame renders and 64/257-frame
renders over the same declared interval. Four measurement tests deliberately
alter gain, pitch, onset or source eligibility to ensure those errors are caught.

## Additional work beyond the prompt

None. Event-binding support, nonzero-duration curved envelope support and an
upstream float-output pull request remain separate future work.
