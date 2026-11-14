# Remaining filter-envelope qualification

The bounded implementation was approved on 2026-11-14. Its contract and
ownership are recorded in [the design](../doc/filter-envelope-design.md) and
[conversion documentation](../doc/conversion.md#filter-envelopes).

## Remaining work

1. Finish the expanded reference run and inspect the retained reports and WAVs
   across Linux, Windows and macOS. Keep sfizz and numerical limits unchanged.
2. Classify sample/block-boundary residuals explicitly. Portable continuous
   crossings do not promise sfizz's advance-before-output or block observation.
3. Scope richer modifiers, filter-envelope export, captured voice-amplitude
   integration and nested/repeated stage traversal separately. They remain
   diagnosed or rejected rather than approximated by the bounded profile.

## Additional work beyond the prompt

None.
