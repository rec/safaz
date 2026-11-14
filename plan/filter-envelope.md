# Remaining filter-envelope qualification

The bounded implementation was approved on 2026-11-14. Its contract and
ownership are recorded in [the design](../doc/filter-envelope-design.md) and
[conversion documentation](../doc/conversion.md#filter-envelopes).

## Remaining work

1. Resolve the Windows asset-import blocker in reccy under separate scope, then
   rerun Windows qualification. Linux/macOS native qualification passes; detailed
   results and the retained external failures are in the findings.
2. Isolate remaining external envelope differences from existing sample traversal,
   amplifier and event timing. Portable continuous crossings do not promise
   sfizz's advance-before-output or block observation. Keep numerical limits.
3. Scope richer modifiers, filter-envelope export, captured voice-amplitude
   integration and nested/repeated stage traversal separately. They remain
   diagnosed or rejected rather than approximated by the bounded profile.

## Additional work beyond the prompt

None.
