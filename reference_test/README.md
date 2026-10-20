# Independent SFZ rendering comparisons

This opt-in suite uses **unmodified upstream sfizz_render**, pinned to
`f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, including its submodules.
There is no patched client or replacement driver. The normal `test/` suite
does not import or require enge or sfizz.

The harness currently reports real failures. It is not evidence that SFZ
playback already agrees. See [current findings](findings.md).

## Run locally

Install the optional group with `uv sync --frozen --group reference`.
Building enge and its meedee dependency requires Rust; CI pins its build
toolchain to 1.87.0, meedee's declared minimum.
Linux also requires ALSA development headers and pkg-config; the workflow
installs `libasound2-dev` and `pkg-config` before building the locked dependencies.
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
On Windows with Visual Studio 2022, add `-G "Visual Studio 17 2022" -A x64` to
the configure command. The workflow selects this generator explicitly instead
of relying on NMake or a preinitialized compiler shell.
It uses the `windows-2022` runner, whose image includes Visual Studio 2022;
the observed `windows-2025` image instead contains Visual Studio 2026.
The macOS workflow selects the installed Xcode 16.2 toolchain and SDK through
`DEVELOPER_DIR`, `CC` and `CXX` before configuring sfizz. Newer Clang versions
reject template syntax in sfizz's pinned bundled `atomic_queue` header. No
third-party source is patched and no compiler diagnostic is disabled.
With the optional dependencies installed, omitting the runner options runs the
native/authored checks and skips only external comparisons locally.
`--require-reference` turns missing configuration
into a failure. Configured missing files, build failures, subprocess errors and
renderer exceptions always fail.

The manual [reference workflow](../.github/workflows/reference-test.yml) builds
the same upstream revision on Linux, Windows and macOS. Each job uploads its
inputs, logs and available comparison evidence, including on failure. It runs
serially and independently of the fast unit workflow.
Hidden-file upload is enabled for the explicitly listed evidence paths so
`.reference-artifacts/` reports and WAVs are included alongside build metadata.

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
The native path uses enge's MIDI reader with an explicit `MidiConverter` and
safaz's generated performance binding. Trigger velocity feeds the imported
native EventBinding; the unused horizon controller does not select a voice.
The input MIDI and converted native event list are retained. Wider controller
behavior remains outside these fixtures.

Native region selection is checked against authored note/sample expectations.
Audio uses safaz import, uFor preparation and enge's existing
OfflineSampler with `control_interval=1`, through both NumPy and native backends.
It does not edit the imported envelope to bypass renderer restrictions.

The client fixes master gain at −7.35 dB in `Defaults.h` and exposes no override.
The native output receives that same declared multiplier. Quality 1 selects
linear interpolation in the pinned `Voice.cpp`; capacity is 64 voices. These
baseline fixtures use stereo sources, default equal temperament, one-shot playback,
zero-duration envelope phases, and no authored effects or voice stealing.
The authored oracle uses source positions, dB equations and `(velocity/127)^2`,
independently of either engine. Disagreements with that contract remain failures.
Imported instruments explicitly select `body.pan_law="sfizz"`. For these
centered stereo fixtures the authored oracle includes `10**(6/20)/2`, derived
from the two centered pan stages and their declared +6 dB compensation. This
implements the selected convention without reproducing lookup quantization,
architecture-dependent coefficients or timing defects. Acceptance limits are
unchanged.

Twenty pan cases add mono/stereo sources at SFZ pan -100, -50, 0, 50 and 100
for both declared instrument laws, through both backends. One handwritten SFZ
template supplies the pan value; all source files still contain one second at
48 kHz with a silent second half. Every import must explicitly select the sfizz
law. Generic native-law cases then explicitly select `PanLaw.native` in the
test document; `import.json` retains the original SFZ conversion and
`instrument.json` records the instrument actually rendered. Native-law cases
make no SFZ equivalence claim, so their two external comparison tests are
explicitly inapplicable; no sfizz mismatch is skipped on this account.

The independent oracle uses `p = pan/100`, `a = (p+1)*pi/4`:

| Law | Mono source-to-L/R gains | Stereo L/R gains, retaining original channels |
| --- | --- | --- |
| Native | `cos(a), sin(a)` | `min(1,1-p), min(1,1+p)` |
| sfizz | `10**(3/20) * [cos(a), sin(a)]` | `10**(6/20)/sqrt(2) * [cos(a), sin(a)]` |

Hard-muted endpoints are exactly zero. The oracle does not call uFor/enge's
pan helper. Reports retain its gains and authored/native/reference channel
levels and timing, without estimating or fitting gains from sfizz output.

## Independent checks and reference status

Each case/backend renders natively once before any sfizz invocation. Native
length comes from the authored horizon rounded to the native block size,
independently of reference output. Separate tests assert prepared selection,
native/authored waveform agreement, and exact authored audible coordinates
with silent block padding. Missing or failing sfizz configuration does not
prevent those tests from running.

Two separate external tests then assert native/reference and
authored/reference waveform agreement, sharing one sfizz invocation per case.
Those assertions remain ordinary failures at the unchanged numerical limits;
known sfizz defects are not xfailed, retried, aligned away or filtered out.
Exceptions from reference invocation preserve a stage-labelled `failure.json`
alongside the completed native evidence. Native preparation exceptions are also
stage-labelled. The workflow retains JUnit `results.xml` so authored results
remain individually visible even while the external comparisons fail.

The original eight baseline variants and 40 pan variants provide 144 native
checks. The 28 SFZ-convention variants provide 56 external waveform checks;
40 generic-native-law external checks are explicitly inapplicable. One
reference-repeatability test and six measurement checks complete the suite.
The workflow remains failing while genuine reference comparisons fail; native
correctness and sfizz waveform equivalence are distinct claims.

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

Timing reports search from frame zero for the first note, then partition the
declared horizon at midpoints between expected note starts. These fixtures have
separated audible notes and intervening silence; this search includes early
starts without assigning a previous note's tail to the following note. Each
measurement records `expected_onset_frame` and the half-open
`timing_window_frames` alongside the first and last audible frames. These timing
windows are not an overlap-aware note detector. Channel levels retain their
original expected-onset-to-next-onset windows. Neither measurement changes the
whole-horizon waveform comparisons or their acceptance limits.

Case directories contain input hashes, instrument revisions, platform,
imported document, events, available actions, reports and native/authored WAVs.
External cases add pinned reference revisions, build cache, executable hash,
arguments, process logs, reference WAV and signed residual WAVs. Missing
reference evidence does not erase native results. Preparation failures preserve
their traceback instead of fabricated audio.
Differences retain their original signed scale.

Repeatability checks use two identical 256-frame renders and 64/257-frame
renders over the same declared interval. Five measurement tests deliberately
alter gain, pitch, onset, source eligibility or channel routing to ensure those
errors are caught, plus the existing early/late/silent timing measurement test.

## Additional work beyond the prompt

None. Wider event-binding support and an upstream float-output pull request
remain separate future work. Sample velocity bindings are implemented; the
remaining baseline differences are recorded in the findings.
