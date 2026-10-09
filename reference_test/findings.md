# Initial reference findings

The harness is implemented, but baseline audio equivalence is **not established**.
The zero-duration envelope blocker has been fixed in a separate enge slice;
the reference run now stops at unsupported event bindings. The original pinned
run below is retained for comparison. Upstream sfizz and SFZ import behavior
remain unchanged.

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
are now `Only control and motion bindings are implemented`. Imported velocity
uses an EventBinding, which enge does not yet consume. Complete import and
authored region selection continue to pass; native audio remains unavailable.

The reference-only repeatability failure also remains: identical 256-frame
renders agree in this invocation, the 64-frame render differs by a maximum of
0.10693359375, and the 257-frame comparison differs by one PCM16 step. Reference
source, fixtures, settings, oracle equations and acceptance thresholds were not
changed for this rerun. Cross-platform execution remains unverified.

## Next slice

Establish the narrow native EventBinding profile needed for imported note
velocity, then rerun these same fixtures. Keep unresolved binding kinds and
nonzero-duration envelope curves rejected. Reference waveform/block differences
still need investigation before claiming equivalence; no upstream patch is
authorized by these findings.

## Additional work beyond the prompt

None.
