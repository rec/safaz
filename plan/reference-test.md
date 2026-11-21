# Remaining reference qualification

The runner, fixtures, independent oracles, artifacts and three-platform workflow
are implemented. Their contract and historical rollout are in
[reference testing](../doc/reference-testing.md); detailed evidence is in
[findings](../reference_test/findings.md) and the
[reference suite README](../reference_test/README.md).

## Remaining work

1. Investigate retained signed waveform and block-repeatability failures.
   Native/authored agreement and matching failure counts do not establish
   sfizz equivalence or identify which implementation is responsible.
2. Keep the filter triangle/parabolic convention difference explicit. A change
   to the existing filter profile requires a separate playback decision.
3. Wait for the user's human review before reporting the packaged intermittent
   sfizz cutoff upstream. The reproducer is committed under
   `reference_test/reproducers/sfizz-preload-cutoff/`.
4. Extend qualification with subsequently approved features. Preserve sfizz and
   numerical limits unless the user explicitly changes that contract.

## Additional work beyond the prompt

None.
