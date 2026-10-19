# Initial reference findings

The harness is implemented, but baseline audio equivalence is **not established**.
The envelope and sample-velocity binding blockers are fixed in enge. Both
backends now complete every baseline render and match the authored oracle;
comparisons with sfizz still fail. Earlier pinned runs below are retained for
comparison. Upstream sfizz and SFZ import behavior remain unchanged.

Current CI evidence is recorded under "Windows unit-decoding fix and rerun,
2026-10-19" below; the subsequent "Gain and off-center pan equation audit"
separates conventions, numerical differences and implementation defects.
Earlier access failures and pending-build statements describe
their original sessions and are superseded by the follow-ups.

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

## macOS compiler follow-up, 2026-10-19

The supplied macOS log identifies four fatal errors in the pinned bundled
`external/atomic_queue/include/atomic_queue/atomic_queue.h`, at lines 403, 409,
532 and 538: `template` precedes a function name without a template argument
list. The same header is included by multiple translation units, repeating
these errors. The unused-variable and NaN warnings did not stop the build.
[Clang 19's release notes](https://releases.llvm.org/19.1.0/tools/clang/docs/ReleaseNotes.html#resolutions-to-c-defect-reports)
document the stricter template syntax check.

The workflow now selects the installed Xcode 16.2 developer directory before
sfizz configuration. `xcrun --find clang` and `xcrun --find clang++` set `CC` and
`CXX`, while `DEVELOPER_DIR` keeps SDK discovery on that Xcode installation.
The compiler version is printed in the job log. This selection happens after
installing the locked Python dependencies; it applies to the reference build
without changing its source or disabling the diagnostic. Xcode 16.2 is listed
in the
[macOS 15 ARM64 runner inventory](https://github.com/actions/runner-images/blob/main/images/macos/macos-15-arm64-Readme.md#xcode).

Local verification compiles the unchanged atomic_queue header in syntax-only
C++17 mode: Apple Clang 15 accepts it, while Homebrew Clang 23.1.3 reproduces
the same four errors. The existing complete local sfizz build also uses Apple
Clang 15. Xcode 16.2 is unavailable locally, so its complete hosted build remains
pending a fresh workflow run. YAML parsing, shell syntax and `git diff --check`
pass; no Python or fixture data changed, so pytest was not rerun. sfizz and
submodules, dependency pins, DSP build options, fixtures and comparison
tolerances remain unchanged.

## Evidence collection and matrix rerun, 2026-10-19

GitHub CLI access works with the existing macOS Keychain credentials when run
outside the execution sandbox. Logs and all three artifacts from
[run 39264689528](https://github.com/rec/safaz/actions/runs/39264689528) were
retrieved. Linux and macOS both built sfizz and reported **9 failed, 5 passed**.
Windows failed during configuration: its actual image was
`windows-2025-vs2026`, version `20261007.264.1`, and the requested Visual Studio
2022 installation was absent. This corrects the earlier inventory assumption.

The old artifacts contain only CMake cache/compiler metadata, with no reports
or WAVs. The macOS ZIP passed integrity verification. Job logs show
`include-hidden-files: false`; the pinned
[upload-artifact action](https://github.com/actions/upload-artifact/tree/ea165f8d65b6e75b540449e92b4886f43607fa02#inputs)
excludes hidden files by default, omitting `.reference-artifacts/` even though
the upload succeeds.

Revision `e8fd52bab0a66cbe1e304ded2359ccca35436bae` enables hidden-file upload
only for the existing explicit evidence paths, selects `windows-2022` with
the existing Visual Studio 2022 generator, and chooses the Windows executable
path by `runner.os`. The observed Windows 2025
[image inventory](https://github.com/actions/runner-images/blob/win25-vs2026/20261007.264/images/windows/Windows2025-VS2026-Readme.md)
lists Visual Studio 2026; the
[Windows 2022 inventory](https://github.com/actions/runner-images/blob/main/images/windows/Windows2022-Readme.md#visual-studio-enterprise-2022)
lists Visual Studio 2022. CMake remains pinned to 3.31.10. No sfizz source,
submodule, dependency pin, DSP option, fixture, authored equation or tolerance
changed.

The corrected workflow was dispatched as
[run 39267848388](https://github.com/rec/safaz/actions/runs/39267848388).
All three platforms now configure and compile sfizz successfully, upload
comparison evidence, and report **9 failed, 5 passed**. The failure counts have
different causes: Linux/macOS fail eight waveform comparisons and repeatability;
Windows fails eight native preparations and repeatability.
Downloaded Linux and macOS artifacts now each contain eight comparison reports,
75 readable 48 kHz WAVs, repeatability results, manifests and compiler metadata.
Every decoded WAV contains finite samples. Both backends pass authored region
selection and native/authored comparisons in all four fixture families; all
eight native/sfizz comparisons fail the unchanged `2/32768 + 2e-6` limit.
Windows has eight partial reports, eight failure tracebacks and 59 readable
48 kHz WAVs, including all reference renders and reference/authored differences.
It has no native renders or native/reference differences. All five passing
tests are the timing-report test and four injected measurement-fault tests.

Windows fails in `ufor.samples.trace.prepare` when
`SampleInstrument.model_validate(instrument.model_dump())` validates quantities
such as `0 s`. The underlying message is `Invalid quantity: 'charmap' codec
can't decode byte 0x81 in position 1794: character maps to <undefined>`.
This occurs before authored selection or native rendering, so Windows native
agreement is unverified. The retained traceback identifies the preparation
boundary but does not identify which underlying file is decoded incorrectly.
No dependency or encoding workaround was introduced to bypass this failure.

### Unity evidence

Linux uses x86_64 and GCC 13.3.0; macOS uses arm64 and AppleClang
16.0.0.16000026 from Xcode 16.2. Both use the clean pinned sfizz revision
`f5c6e29f23b8057867c08e88f5f6ac6738baa30b` and matching recursive submodules.
Windows uses x86_64 MSVC 19.44.35229.0 with the same clean source and submodules.

| Measurement | Linux | macOS |
| --- | --- | --- |
| Native vs authored maximum error | 0 | 0 |
| Native vs sfizz maximum error | 0.10715810568611067 | 0.10712758810798567 |
| Native vs sfizz RMS error | 0.00045359593259165423 | 0.00045428488903197543 |
| Reference first / last audible frame | 274 / 24274 | 274 / 24274 |
| Reference absolute left / right peaks | 0.05352783203125 / 0.02679443359375 | 0.053497314453125 / 0.02679443359375 |
| Reference PCM16 at frame 280, left / right | 1752 / -878 | 1751 / -878 |
| Repeated 256-frame maximum error | 0 | 0 |
| 64 vs 256 maximum error | 0.10699462890625 | 0.10693359375 |
| 257 vs 256 maximum error | 0 | 0.000030517578125 |

Windows reference/authored unity maximum error is `0.10715810568611067`, with
RMS error `0.00045362001423154233`. Its 256-frame unity reference PCM matches
Linux exactly, including padding. Its reference onset, final audible frame,
channel levels and repeatability errors also match Linux. No Windows
native/authored or native/reference measurement is available.

The authored onset is 275 and last audible frame is 24274. All platforms have
unity residuals greater than 0.001 only at frames 274, 322, 370, 418 and 466.
Raw repeatability lengths are 150016/150016/150016/150088 frames for the
150000-frame declared horizon. The reference WAVs from both backend-parameterized
cases agree exactly within each platform, including Windows cases whose native
preparation later failed. Linux and macOS unity reference PCM
differ by at most one PCM16 step; they are not identical. The odd-block macOS
residual and channel-level difference are consistent with the previously
diagnosed architecture-specific panning path, rather than evidence for a
universal timing or gain correction.

All platforms have identical source WAV and MIDI hashes. The checked-out
Windows SFZ has a different byte hash due to line endings; decoded authored
unity WAV samples agree exactly across all three platforms despite differing
WAV file hashes. No conclusion rests on matching test counts alone.

Artifacts are retained for 14 days by the workflow. Downloaded evidence is at
`/private/tmp/safaz-ci-39267848388/{linux,macos,windows}`; these local paths are
temporary conveniences. Executable hashes and all input hashes are in each case
manifest.
YAML parsing and `git diff --check` pass. Only workflow and documentation files
changed, so the Python unit suite was not rerun.

## Windows unit-decoding fix and rerun, 2026-10-19

The Windows preparation failure originates in
`reccy.configuration.units._registry`, which reads Pint's `default_en.txt` and
`constants_en.txt` resources without specifying an encoding. Those files are
UTF-8; decoding them with Windows' default `cp1252` can fail before any quantity
is parsed. The unit parser wraps that decoding failure as `Invalid quantity`,
which becomes a Pydantic validation error when uFor revalidates an instrument.
This is not an SFZ sample-path or sfizz decoding problem.

A local diagnostic made unspecified `Path.read_text` calls use `cp1252` and
reproduced the exact CI error for `0 s`: byte `0x81` at position `1794`.
reccy commit `dd24bf880bca44a83903c58ac3780f3939751ecc` changes only those two
resource reads to `read_text(encoding='utf-8')`. The same diagnostic then parses
`0 s`, `1 μs` and `1 µs`, preserving exact rational magnitudes. It also passes
against safaz's installed updated dependency, without a local source override.
No process-wide encoding setting or parser fallback is added.

reccy's focused unit suite passes 90 tests; its full suite passes 503 tests
with one skip. Ruff, formatting, `ty check reccy`, changed-file pyupgrade and
`git diff --check` pass. safaz's separate lockfile commit
`e43862d` advances only reccy's locked revision to that fix, plus uv's generated
resolution cutoff timestamp. safaz's 340 unit tests, Ruff, formatting and
`ty check safaz` pass. No other package version, sfizz source/submodule, build
option, fixture, oracle equation or comparison tolerance changes.

The updated lockfile was pushed and the unchanged three-platform reference
workflow was dispatched as
[run 39269720084](https://github.com/rec/safaz/actions/runs/39269720084).
All three jobs completed and uploaded their evidence. Each reports **9 failed,
5 passed**, now with the same causes: eight native/sfizz waveform comparisons
and the across-block repeatability assertion. The Windows quantity-decoding
error is gone. All eight Windows native preparations and renders complete,
both backends pass authored selection and native/authored comparisons, and no
`failure.json` is present on any platform.

Every platform's artifact contains eight complete reports and 75 readable,
finite 48 kHz WAVs, including native renders and signed native/reference
differences. Across all three platforms and both backends, native/authored
maximum errors are 0 for unity and pitch, `6.979551485375435e-19` for
gain/velocity, and `1.734723475976807e-18` for regions.

| Unity measurement | Linux | Windows | macOS |
| --- | --- | --- | --- |
| Native vs authored maximum error | 0 | 0 | 0 |
| Native vs sfizz maximum error | 0.10715810568611067 | 0.10715810568611067 | 0.10712758810798567 |
| Native vs sfizz RMS error | 0.00045359593259165423 | 0.00045359593259165423 | 0.00045428488903197543 |
| 64 vs 256 reference maximum error | 0.10699462890625 | 0.10699462890625 | 0.10693359375 |
| 257 vs 256 reference maximum error | 0 | 0 | 0.000030517578125 |

Repeated 256-frame renders agree exactly on each platform. Reference onset and
last audible frame remain 274 and 24274, versus authored onset 275. Raw lengths
remain 150016/150016/150016/150088 for the 150000-frame horizon. Unity reference
PCM is unchanged from the prior run on each platform. Linux and Windows agree
exactly; macOS differs from them by at most one PCM16 step. Source WAV, MIDI
and SFZ hashes are unchanged from each platform's previous run, decoded
authored unity WAV samples are unchanged, and manifests confirm identical sfizz
revision and submodule state.

Downloaded evidence is at
`/private/tmp/safaz-ci-39269720084/{linux,macos,windows}`. Artifacts retain the
workflow's 14-day expiry. This establishes that the Windows encoding blocker
is fixed and native rendering matches the authored baseline on all three
platforms. Baseline sfizz equivalence remains unestablished; neither the
waveform limit nor repeatability checks were relaxed to accept these results.

## Gain and off-center pan equation audit, 2026-10-19

This audit compares the current safaz importer and the pinned uFor/enge used
by the reference suite with unchanged sfizz
`f5c6e29f23b8057867c08e88f5f6ac6738baa30b`. It changes no renderer, fixture,
comparison equation or tolerance. The earlier suggestion that we already had
two implemented off-center pan laws to compare was incorrect: the pinned
native sample renderer rejects nonzero pan and stereo balance.

### Gain equations

For authored volume `d` in dB, native preparation uses `10 ** (d / 20)`.
sfizz's `MathHelpers.h::db2mag` uses `pow(10, d * 0.05)`. These are the same
amplitude convention, with different floating-point evaluation. This is not
a power/amplitude exponent disagreement. The harness separately applies the
declared -7.35 dB master gain to native output, matching sfizz's client setting.

For normalized velocity `v` and `t = amp_veltrack / 100`, both implementations
use the following real-valued default curve:

```text
q(v) = v * v
gain(v, t) = 1 - t * (1 - q(v))     when t >= 0
gain(v, t) = abs(t) * (1 - q(v))    when t < 0
```

The importer constructs 128 route points at `v = MIDI_velocity / 127` in
`safaz/compiler.py::_velocity_modulation`; sfizz computes the default square
directly in `RegionStateful.cpp::velocityCurve`. At MIDI velocity knots these
have the same intended exponent. Diagnostic equation checks covered every
velocity 0 through 127 at tracking -100, -50, 0, 50 and 100. At tracking zero
the importer omits the multiplicative route, giving unity, as does sfizz.
Explicit `amp_velcurve_N` values produce linear interpolation between authored
knots in both implementations (`_interpolated_velocity_curve` versus
`Curve::buildFromVelcurvePoints` and `Curve::evalNormalized`).

There are numerical and representation qualifications:

- sfizz evaluates velocity gain in float32. At tracking 100 its expression
  reduces through `1 - (1 - v*v)`, losing some precision near zero. At MIDI
  velocity 1 the source-equation result is `0.00006198883056640625`, versus
  authored `0.00006200012400024799`, a relative difference of approximately
  -0.0182%. This is cancellation/rounding, not a different velocity exponent.
  The existing PCM16 fixture still cannot establish velocity 1's relative gain.
- Between MIDI knots, our default route linearly interpolates the sampled
  square, whereas sfizz's default equation squares the continuous input. For
  tracking 100 the largest mathematical gap is `1 / (4 * 127**2)`, approximately
  `0.000015500031` in gain. Standard 7-bit MIDI note velocities are at the knots;
  do not generalize their agreement to arbitrary fractional event velocities.
- Other gain factors, controller mappings and custom curves need their own
  declared settings. This audit does not establish agreement for arbitrary
  SFZ modulation or explain every gain-fixture waveform residual.

### Which native pan behavior actually exists

`safaz/compiler.py::_processing` maps SFZ `pan / 100` to `processing.pan` for
mono sources and `processing.stereo_balance` for stereo sources. uFor validates
the corresponding channel layouts. Neither model field specifies an executed
off-center curve in the pinned enge sample renderer.

`enge/sample_instrument.py::_validate_settings` accepts only volume, tuning
and filters in sample processing. Nonzero `pan` or `stereo_balance` raises
`Only sample volume, tuning, and filter processing are implemented` before
either rendering backend runs. Centered mono instead uses the static channel
routes from `safaz/model.py::_channel_routes`: each output receives
`source / sqrt(2)`. Centered stereo uses identity routes with gain 1 per channel.
The reference harness's authored waveform contains no variable-pan equation;
all existing baseline sources are stereo and all fixtures specify `pan=0`.

`enge/presets.py::Patch.prepare_score` separately uses unboosted cosine/sine
routes for its generated mono presets. That is an existing equation elsewhere
in enge, not the implementation of imported SFZ sample pan. It must not be used
to claim imported off-center playback agreement.

### sfizz's off-center equations

Let `p = SFZ_pan / 100`, `a = (p + 1) * pi / 4`, `C3 = 10**(3/20)` and
`C6 = 10**(6/20)`. Ignoring lookup quantization and floating-point rounding,
`Panning.cpp` and `Voice.cpp::panStageMono/panStageStereo` give:

```text
mono: L_out = mono * C3 * cos(a)
      R_out = mono * C3 * sin(a)

stereo, width=100 and position=0:
      L_out = L_in * C6 / sqrt(2) * cos(a)
      R_out = R_in * C6 / sqrt(2) * sin(a)
```

The stereo equations preserve channels at full width; pan attenuates/boosts
each original channel rather than moving the removed channel into the other.
They include both the variable pan stage and the centered position stage.
Nondefault stereo width or position introduces additional operations outside
this diagnostic. The table lists ideal source-to-output coefficients before
volume, velocity, master gain and PCM conversion:

| SFZ pan | sfizz mono L / R | sfizz stereo L / R | Imported native sample |
| --- | --- | --- | --- |
| -100 | 1.412538 / 0 | 1.410864 / 0 | Rejected |
| -50 | 1.305015 / 0.540555 | 1.303468 / 0.539914 | Rejected |
| 0 | 0.998815 / 0.998815 | 0.997631 / 0.997631 | Mono 0.707107 / 0.707107; stereo 1 / 1 |
| 50 | 0.540555 / 1.305015 | 0.539914 / 1.303468 | Rejected |
| 100 | 0 / 1.412538 | 0 / 1.410864 | Rejected |

The core sine/cosine law is equal-power, with a fixed compensation multiplier;
there is no evidence here for an alternate adjustable pan exponent. A square-
root interpolation law can share its center and endpoints while differing
off-center, so centered fixtures alone cannot determine that shape.

### Conventions, implementation defects and limits

The +3 dB mono and +6 dB stereo compensation is explicit in sfizz's source,
including comments describing its intent. That is a convention difference
from unboosted equal-power mono routing and unity stereo routing, not evidence
of a wrong gain exponent. Exact unity compensation would use factors
`sqrt(2)` and `2`, approximately +3.0103 and +6.0206 dB. sfizz's rounded dB
choices leave centered mono at -0.0103 dB relative to a unity-per-output
convention, and stereo at -0.0206 dB. This deliberate normalization must be
distinguished from an implementation defect; no SFZ-spec compliance verdict
is established by this audit.

There is a separate implementation inconsistency in the lookup paths.
The table contains `cos(i*pi/(2*4094))`. Scalar pan rounds each channel's
normalized coordinate using 4094; ARM NEON uses 4095 when calculating its
index, then uses `4094 - left_index` for the other channel. For example:

| SFZ pan | Scalar L / R coefficients for one stage | NEON L / R coefficients for one stage |
| --- | --- | --- |
| -50 | 0.923806 / 0.382506 | 0.923806 / 0.382861 |
| 0 | 0.707107 / 0.707107 | 0.706835 / 0.707378 |
| 50 | 0.382506 / 0.923806 | 0.382506 / 0.923953 |

This is not a deliberately different pan law: two execution paths implement
the same operation with inconsistent lookup coordinates. It is the source
of the diagnosed center imbalance and scalar/vector tail differences. Scalar
lookup quantization and ordinary float32 rounding are separate numerical
approximations; neither alone implies a semantic bug. The native renderer's
rejection of off-center pan is an implementation gap, not a competing curve.

Local macOS arm64 diagnostics rendered unchanged sfizz at pan -100, -75, -50,
-25, 0, 25, 50, 75 and 100 for both mono and stereo one-second 48 kHz sources.
All 18 imported documents were complete; native preparation accepted only the
two centered cases and rejected all 16 off-center cases. For every reference
render, the decoded plateau at frame 280 matched a prediction from sfizz's
scalar or NEON lookup equations, declared compensation/master gain and PCM16
conversion. Centered mono matched the scalar prediction at that frame; stereo
center matched NEON. This checks a plateau, not a reconstruction of every
sample or instrumentation proving which branch executed. Off-center renders
were local only; the scalar off-center table is source-derived, not a new
Linux/Windows CI result.

Inputs, MIDI, process arguments/logs, reference WAVs and `analysis.json` are
retained under `/private/tmp/safaz-pan-equations-20261019`; the diagnostic script
is `/private/tmp/safaz-pan-audit.py`. These are temporary evidence paths.
Only this findings document changed in the repository. No accepted baseline,
sfizz source/build, native playback, dependency pin or tolerance was changed;
the Python suites were not rerun for this documentation-only update.

## Next slice

The Windows preparation blocker is resolved. Decide the reference comparison
contract using the complete three-platform baseline evidence: the NEON pan
factors are architecture-specific, and the pinned client/core timing behavior
should not be copied into enge. Keep the failing comparisons visible and defer
new feature families. Any change to accepted playback semantics needs a
separate decision based on that evidence.
Before proposing off-center playback equivalence, specify the intended mono
normalization and stereo balance law; the pinned native sample renderer does
not yet implement those controls. Treat sfizz's compensation convention
separately from its inconsistent scalar/NEON lookup coordinates.

## Additional work beyond the prompt

None.
