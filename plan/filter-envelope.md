# Remaining filter-envelope qualification

The bounded implementation was approved on 2026-11-14. Its contract and
ownership are recorded in [the design](../doc/filter-envelope-design.md) and
[conversion documentation](../doc/conversion.md#filter-envelopes).

## Remaining work

1. Resolve the Windows asset-import blocker in reccy under separate scope, then
   rerun Windows qualification. Linux/macOS native qualification passes; detailed
   results and the retained external failures are in the findings.
2. Decide separately whether to replace the pre-existing normalized amplifier
   release mapping with the captured SFZ release law. The filter-envelope audit
   found this compatibility gap, without changing playback. Its isolated results
   and the deliberate filter realization differences are recorded in the findings.
3. Scope richer modifiers, filter-envelope export, captured voice-amplitude
   integration and nested/repeated stage traversal separately. They remain
   diagnosed or rejected rather than approximated by the bounded profile.

## Additional work beyond the prompt

None.
