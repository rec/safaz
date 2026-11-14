# Remaining reference qualification

The runner, fixtures, independent oracles, artifacts and three-platform workflow
are implemented. Their contract and historical rollout are in
[reference testing](../doc/reference-testing.md); detailed evidence is in
[findings](../reference_test/findings.md) and the
[reference suite README](../reference_test/README.md).

## Remaining work

1. Complete corrected macOS modulation qualification. Run 41456697605 completed
   on Linux/Windows, but its macOS job was cancelled without comparison evidence.
   Use a current authorized run; do not treat the earlier triangle-based run as
   qualification of the corrected parabolic pitch/amplitude profiles.
2. Investigate retained signed waveform and block-repeatability failures.
   Native/authored agreement and matching failure counts do not establish
   sfizz equivalence or identify which implementation is responsible.
3. Keep the filter triangle/parabolic convention difference explicit. A change
   to the existing filter profile requires a separate playback decision.
4. Wait for the user's human review before reporting the packaged intermittent
   sfizz cutoff upstream. The reproducer is committed under
   `reference_test/reproducers/sfizz-preload-cutoff/`.
5. Extend qualification with subsequently approved features, including filter
   envelopes after implementation. Preserve sfizz and numerical limits unless
   the user explicitly changes that contract.

The latest committed corrected Linux/Windows evidence reports 359 passed,
181 failed, 56 skipped and zero errors per platform. All 112 native case WAVs
agree across those platforms. These are historical qualification results,
not a new test run of today's repository.

## Additional work beyond the prompt

None.
