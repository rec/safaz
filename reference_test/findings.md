# Initial reference findings

The harness is implemented, but baseline audio equivalence is **not established**.
The envelope and sample-velocity binding blockers are fixed in enge. Both
backends now complete every baseline render and match the authored oracle;
comparisons with sfizz still fail. Earlier pinned runs below are retained for
comparison. Upstream sfizz and SFZ import behavior remain unchanged.

## Local run, 2026-10-09

Environment: macOS 14.5 arm64, Python 3.13.12, AppleClang 15, CMake 3.31.10.
sfizz revision: `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, clean tracked tree
and matching recursive submodules. enge revision:
`0292931487bcee6a7bae32f16e1f6b7712739b43`. uFor revision:
`e24e9aea1323c998c17f855f8ba5c776d8506da0`.

The external suite reports **4 passed, 9 failed**:

- Four injected measurement faults are correctly rejected.
- All eight conversion fixtures import completely and produce the authored
  native region-selection actions. Both backend variants then fail preparation
  with `Only held linear envelopes are implemented`. SFZ decay/release segments
  have curve −5 even at zero duration; enge rejects those shapes. No native audio
  or native/reference difference is available until preparation succeeds.
- The reference repeatability test fails its block-size comparison. Identical
  256-frame renders agree in this invocation, but 64-frame output differs by
  a maximum of 0.10693359375 over the declared interval. The 257-frame comparison
  passes this invocation at one PCM16 step. Earlier invocations also showed a
  larger 257-frame difference. Stability remains unverified.

The unity reference and authored oracle both begin at frame 275 and last exceed
the audibility threshold at frame 24274. Reference left peak is
0.053497314453125; authored left peak is 0.05363027365486068. Their full waveform
maximum difference is 0.10712758810798567, exceeding the predeclared limit
`2/32768 + 2e-6`. Correct onset alone does not establish matching playback.
No gain fitting, time shifting or threshold relaxation was used to accept it.
Investigate the remaining source traversal, gain/pan and block differences before
asserting which implementation is wrong.

## Audited client constraints

- Output is stereo PCM16. The bundled dr_wav conversion maps zero to −1;
  its equation bounds unclipped error by two PCM16 steps.
- Master volume defaults to −7.35 dB and has no client override. Native output
  uses that declared multiplier, not a scale inferred from a reference render.
- sfizz automatically connects default CC7/CC10/CC11 when unused. Default CC7
  is 100, causing extra attenuation. Fixtures explicitly set CC7=127 through
  supported SFZ syntax and request a native MIDI binding. CC10 retains its
  default 0.5 and CC11 its default 1.0.
- Linear interpolation is quality 1. The client enables freewheeling and
  loads the SFZ before starting its MIDI player.
- fmidi terminates at the final channel event, ignoring a delayed EOT marker.
  A final unused CC1 reset establishes the authored horizon without inventing
  a note. Output still rounds to a whole block; raw lengths are recorded.
- Velocity 1's relative gain cannot be meaningfully verified at PCM16 precision.
  Its absolute residual can be recorded, but its gain ratio remains unresolved.

The dedicated Linux/Windows/macOS workflow is manual and retains failing
comparison artifacts. Its matrix has not yet been executed. Cross-platform
audio consistency and the native rendering stage remain outstanding.

## Zero-duration envelope follow-up, 2026-10-09

enge revision: `1bcb76566b813a1566afe0bdf1ed3092e40ed278`. uFor revision:
`5cea0275f1e3cac05540a1d6c8561063a2c94ab1`, matching enge's existing dependency
lock. The compatible uFor pin is required by the current enge Latch imports.

enge now accepts curve metadata on amplitude-envelope phases whose duration is
exactly zero. Those phases already jump immediately to their endpoints in both
renderers; the fix changes only their validation. Held voice/seconds envelopes
and linear nonzero-duration phases remain the accepted profile. Positive-duration
curved attack or release phases still raise an error.

Six focused cases pass, covering zero-duration jumps between linear phases,
linear and instant releases on NumPy/native backends, and positive-duration curve
rejection. WAV regressions contain one second of 48 kHz audio. The full enge run
reported 1,067 passes, 21 optional Rubber Band skips, and one outdated rejection
fixture. That fixture now uses a nonzero duration; its corrected case passes
on rerun. Ruff, formatting, type checking and pyupgrade checks pass.

safaz's 334 unit tests pass with the new pins. The unchanged reference fixtures
still report **4 passed, 9 failed**, but the eight native preparation failures
are now `Only control and envelfo bindings are implemented`. Imported velocity
uses an EventBinding, which enge does not yet consume. Complete import and
authored region selection continue to pass; native audio remains unavailable.

The reference-only repeatability failure also remains: identical 256-frame
renders agree in this invocation, the 64-frame render differs by a maximum of
0.10693359375, and the 257-frame comparison differs by one PCM16 step. Reference
source, fixtures, settings, oracle equations and acceptance thresholds were not
changed for this rerun. Cross-platform execution remains unverified.

## Sample velocity binding follow-up, 2026-10-15

enge revision: `06cdefe51cd5743cf8829eeff869a0c84e2442b9`. Its tested Python
dependency revisions are now pinned in safaz: Ufor
`9b3b0cd6cd65f3af1015ae5b333e1c2e0ee681d6` and enveLFO
`a9213ce9d99602866022339975ae5469e7784985`.

Offline sample instruments now accept voice-scoped velocity EventBindings.
Each declared source captures the prepared VoiceStart's velocity as an
unsmoothed constant. Existing routes determine its effect; no automatic gain
is added. Voice identity and the value survive snapshot/restore, later notes
and controller changes. Key EventBindings and bindings in other offline engines
or native live registration retain their validation restrictions.

Five focused cases cover instrument/slot declarations on both backends,
overlapping voices, controller-name collisions, velocities 0/1/64/127 in MIDI
units, releases, snapshot round trips and rejected key bindings. Audio
regressions write two-second 48 kHz WAVs. The full enge suite passes 1,146 tests,
with 21 optional Rubber Band skips. Changed production files pass type checking;
the whole-package check still reports two pre-existing return-type errors in
unchanged `enge/native.py`. Ruff, formatting and pyupgrade checks pass.

safaz's 340 unit tests pass with these pins. The unchanged reference suite still
reports **4 passed, 9 failed**, now entirely at comparison assertions:

- All eight imports, authored selections and native renders complete. Reference,
  native and signed difference WAVs are retained for every case.
- All eight native-versus-authored comparisons pass. Maximum errors below apply
  to both NumPy and native backends, before WAV output quantization.
- All eight native-versus-sfizz waveform comparisons fail the unchanged
  `2/32768 + 2e-6` limit. The four injected measurement faults remain detected.

| Fixture | Native vs authored maximum error | Native vs sfizz maximum error |
| --- | --- | --- |
| Unity | 0 | 0.10712758810798567 |
| Gain/velocity | 6.98e-19 | 0.21375695224626184 |
| Pitch | 0 | 0.10712758810798567 |
| Regions | 1.73e-18 | 0.10712758810798567 |

Reference repeatability also still fails: the repeated 256-frame render agrees
exactly, the 64-frame comparison has maximum error 0.10693359375, and the
257-frame comparison differs by one PCM16 step. Raw output lengths remain
150016/150016/150016/150088 frames for the declared 150000-frame interval.

sfizz was rebuilt from the same clean pinned tree and recursive submodules,
using the original build settings. No fixture, reference setting, authored
equation, alignment rule or tolerance changed. These results establish native
agreement with the authored baseline, not SFZ playback equivalence. Velocity 1's
relative gain and cross-platform reference consistency remain unresolved.

## Unity investigation, 2026-10-16

The unity disagreement is explained locally by the pinned reference's MIDI
dispatch, voice-age bookkeeping and stereo panning. A diagnostic calculation
from those source equations reproduces **every decoded PCM16 sample**, including
padding, in all four retained and four freshly rendered repeatability WAVs.
This calculation is evidence about sfizz, not a replacement acceptance oracle.
The authored equations, native rendering, fixtures and tolerances are unchanged;
the reference comparisons still fail.

The platform, compiler, sfizz revision and build remain those recorded above.
The executable SHA-256 is
`9cfe47514f8e968aa1660a3f06e8d4c8b446b42a6b421afc8b210818be2a59d0`.
Tracked sfizz source and recursive submodules were checked again and are clean.

### Event placement and the first block

The authored onset is frame 275. The actual reference onset is **274**.
`sfizz_render.cpp:210-211` advances fmidi by one sample before dispatching events
with the current zero-based output-frame delay. In
`external/fmidi/sources/fmidi/fmidi_mini.cpp:55-78`, the player first increments
its time, then dispatches while that time is strictly greater than the event's
timestamp. At this fixture's onset, 275 repeated double-precision additions of
`1/48000` give `0.005729166666666685`, exceeding `11 * 0.5 / 960`,
`0.005729166666666666`. The callback therefore dispatches at output frame 274.
This result is specific to the tested timestamp and arithmetic; a universal
one-frame correction is not justified.

The earlier reported onset of 275 was misleading: `harness.measure_notes`
only searches from the authored onset. Its window excludes frame 274.
The existing whole-horizon waveform comparison does include that frame and
correctly fails. The reporting gap does not invalidate its residual measurement.

There is a second timing effect in
[Voice.cpp](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Voice.cpp#L819).
The first render increments `age_` by the full block length, then assigns
`min(age_ - triggerDelay_, 0)`. For this note that sets the age back to zero.
`fillWithData` at lines 1106-1112 consequently clears the first source-position
jump again on the next block. Since the previous block saved its final source
position, that sample is repeated once. At block size 256 this happens at output
frame 512, cancelling the initial one-frame lead for subsequent source edges.

| Block size | Reference onset | Repeated-source frame | Reference edges near onset |
| --- | --- | --- | --- |
| 64 | 274 | 320 | 274, 323, 371, 419, 467, 515 |
| 256 | 274 | 512 | 274, 322, 370, 418, 466, 515 |
| 257 | 274 | 514 | 274, 322, 370, 418, 466, 515 |
| Authored | 275 | None | 275, 323, 371, 419, 467, 515 |

At 256 frames, the only native/reference residuals exceeding 0.001 occur at
frames **274, 322, 370, 418 and 466**. At 64 versus 256 frames, they occur at
322, 370, 418 and 466. Linear interpolation at this fixture's integer source
positions introduces no fractional-position error. A global time shift would
make the already aligned later edges incorrect.

### Stereo level and the odd block size

[Voice.cpp:989-1030](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Voice.cpp#L989)
applies both pan and position stages to stereo data, then multiplies by
`1.9952623149688797` (+6 dB). Even ideal center coefficients of `sqrt(0.5)`
would leave a multiplier of `0.9976311574844399`, rather than unity.

The ARM path adds a small channel imbalance.
[Panning.cpp:18-98](https://github.com/sfztools/sfizz/blob/f5c6e29f23b8057867c08e88f5f6ac6738baa30b/src/sfizz/Panning.cpp#L18)
builds its table using `cos(i * pi / (2 * 4094))`. At center, the scalar path
indexes 2047 for both channels. The NEON vector path instead indexes 2048 for
left and 2046 for right, using 4095 in its index calculation. Rounded to
float32, these coefficients are `0.7068354487419128` and
`0.7073780298233032`. Applying each twice and the fixed +6 dB multiplier gives
approximately `0.9968656301498413` left and `0.9983966946601868` right.
The default full stereo width preserves the channels here.

Apply those source-derived stages, the existing -7.35 dB master gain and the
audited dr_wav conversion in float32. The resulting plateau integers match
the reference exactly:

| Source left/right | Reference PCM16 left/right |
| --- | --- |
| +0.125 / -0.0625 | 1751 / -878 |
| -0.125 / +0.0625 | -1753 / 876 |
| 0 / 0 | -1 / -1 |

For 257-frame blocks, each block's final frame takes the scalar pan path while
its first 256 frames take the vector path. Those tail samples explain the
one-PCM16-step difference from 256-frame output in these runs. No measured gain
ratio was fitted. These are implementation-specific stereo factors, not an
SFZ import rule or justification for changing enge's generic gain semantics.

### Reproduction and remaining limits

Run the existing repeatability test with a fresh output directory:

```sh
uv run --no-sync pytest -q \
  reference_test/test_reference.py::test_reference_repeatability_across_blocks \
  --require-reference \
  --sfizz-source /private/tmp/safaz-reference-velocity/sfizz \
  --sfizz-build /private/tmp/safaz-reference-velocity/build \
  --sfizz-render /private/tmp/safaz-reference-velocity/build/library/bin/sfizz_render \
  --reference-output /private/tmp/safaz-unity-investigation --tb=short
```

The fresh test fails the unchanged across-block assertion, with the same raw
lengths and errors as October 15. Repeated 256-frame PCM is identical; 64 versus
256 has maximum error `0.10693359375`; 257 versus 256 has maximum error
`3.0517578125e-05`. Local diagnostic script/output are retained alongside these
WAVs as `analysis.py` and `analysis.txt`; the original manifests and WAVs remain
under `/private/tmp/safaz-reference-velocity/results`.

The diagnostic reconstruction uses source index `frame - 274` until the first
block boundary after onset, then `frame - 275`; indices outside `[0, 24000)`
produce silence. Use the original 96-frame square period and channel ratio,
apply the two per-channel pan coefficients, compensation and master gain with
float32 multiplication, then the audited PCM16 conversion. For odd blocks use
the scalar center coefficient on the final `block_size % 4` frames. This
predicts all samples in the eight inspected WAVs with zero decoded mismatch.
It does not alter any harness comparison or acceptance status.

This establishes causes for the inspected local unity renders. It does not
explain every other fixture, qualify Linux/Windows, or resolve the previously
observed larger 257-frame differences from older invocations. Those remain
unverified. No upstream patch or importer/renderer behavior change was made.

## Onset reporting follow-up, 2026-10-19

The reporting fix in safaz revision `92b5848` searches timing windows separated
by midpoints between authored note starts, beginning at frame zero and ending
at the declared horizon. Reports include each expected onset and the half-open
timing window. These fixtures have separated audible notes; the method does
not claim to attribute overlapping voices. Existing channel-level windows,
audibility threshold and whole-horizon acceptance limits are unchanged.

The new focused case covers an early first note, a later note, PCM16 silence,
window boundaries and unchanged RMS measurement. It writes a 150000-frame,
48 kHz WAV. That case and the four injected measurement-fault cases pass.
All 340 normal unit tests, Ruff, formatting, type checking, pyupgrade and
`git diff --check` pass.

A fresh local run, retaining the same sfizz build, reports **5 passed, 9 failed**.
The unity report now correctly records reference onset **274**, authored onset
**275**, and final audible frame 24274 for both. Its native/reference maximum
error remains `0.10712758810798567` and RMS error `0.00045428488903197543`.
All eight native/authored comparisons still pass; the eight reference waveform
comparisons and across-block repeatability still fail. Reports and WAVs are
retained under `/private/tmp/safaz-onset-reporting-20261019`.

The fix was pushed before attempting the existing Linux/Windows/macOS workflow
on `main`. GitHub rejected `gh workflow run reference-test.yml --ref main` with
HTTP 401, `Requires authentication`. No matrix run was created, and the workflow
run list remains empty. Restoring Actions dispatch access, or manually running
[SFZ reference comparisons](https://github.com/rec/safaz/actions/workflows/reference-test.yml)
on this revision, is required to collect that evidence. No cross-platform
qualification is claimed. sfizz, fixtures, dependency pins and tolerances
remain unchanged.

## First matrix run, 2026-10-19

The user manually started
[run 39245504713](https://github.com/rec/safaz/actions/runs/39245504713)
at safaz revision `b89d091736f2f3bc535d23247fa7dad51a38c5fc`, which includes
the onset-reporting fix. All three jobs completed with failure:

| Platform | Last successful stage | Failed stage |
| --- | --- | --- |
| [Linux](https://github.com/rec/safaz/actions/runs/39245504713/job/118036328922) | Build upstream offline client | Compare and preserve findings, exit 1 |
| [Windows](https://github.com/rec/safaz/actions/runs/39245504713/job/118036329148) | Install locked reference dependencies | Configure unmodified sfizz, exit 1 |
| [macOS](https://github.com/rec/safaz/actions/runs/39245504713/job/118036329289) | Configure unmodified sfizz | Build upstream offline client, exit 2 |

Every job successfully uploaded its evidence artifact. However, this session
can read run/job metadata and annotations but cannot retrieve the evidence:
artifact downloads return HTTP 401, `Requires authentication`, and job-log
requests return HTTP 403, `Must have admin rights to Repository`. Check-run
annotations contain generic exit codes without the underlying errors.

Windows and macOS did not reach audio comparisons. Linux reached the comparison
step, but without its output or artifacts, no test counts, render completion,
onset coordinates or waveform measurements can be established. Its failed step
alone does not establish that the known local waveform assertions were the
cause. No cross-platform audio agreement or disagreement is inferred from
these job conclusions.

Run, job and artifact metadata are retained locally as
`/private/tmp/safaz-reference-ci-39245504713-{run,jobs,artifacts}.json`.
Failed-step output and access to the uploaded reports are needed before fixing
the setup failures or comparing platform results. sfizz, the workflow, fixtures
and tolerances remain unchanged.

## Windows generator follow-up, 2026-10-19

The user supplied the Windows configuration failure from run 39245504713.
CMake selected `NMake Makefiles`, but `nmake -?` failed because the executable
was unavailable; CMake then reported unset C and C++ compilers. This failure
occurred before sfizz compilation or audio comparisons.

The workflow now explicitly passes `-G "Visual Studio 17 2022" -A x64` on
Windows, using the installed Visual Studio build system and the existing
`--config Release` build command and `Release/sfizz_render.exe` path. Linux
and macOS retain their existing generator selection. The installed generator
is listed in the
[Windows 2025 image inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md#visual-studio-enterprise-2022),
and its platform flag is documented by
[CMake 3.31](https://cmake.org/cmake/help/v3.31/generator/Visual%20Studio%2017%202022.html).

YAML parsing and `git diff --check` pass. Windows execution remains pending a
new workflow run; these local checks do not establish that sfizz builds or
renders successfully on that platform. No sfizz source, dependency pin,
comparison fixture or tolerance changed.

## Next slice

Rerun the Windows configuration fix, retrieve the Linux comparison output,
resolve the macOS build failure, and collect the unchanged unity case on all
three platforms
before deciding the reference comparison contract: the NEON pan factors
are architecture-specific, and the pinned client/core timing behavior should
not be copied into enge. Keep the failing comparisons visible and defer new
feature families. Any change to accepted playback semantics needs a separate
decision based on that evidence.

## Additional work beyond the prompt

None.
