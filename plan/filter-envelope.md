# Filter-envelope implementation

Status: awaiting implementation approval. The completed
[design and enge integration review](../doc/filter-envelope-design.md) describe
the equations, captured-level semantics and proposed one-shot restrictions.
The user deferred implementation after that review.

## Remaining work

1. Settle the shared stage representation and conversion of logarithmic
   crossing times to rational boundaries. Preserve existing Segment semantics.
2. Implement captured entry-state resolution in uFor/enveLFO and its Python/Rust
   evaluators. Resolve an approach to an existing curved segment followed by a
   linear transition; preserve authored and resolved stage identities.
3. Verify zero/already-crossed cases, interruption, event ordering, partition
   invariance and snapshot continuation against independent conformance values.
4. Update enge's NumPy, native and persistent adapters to consume shared resolved
   state. Recheck current enge code before implementing against the old review.
5. Import the bounded first-filter `fileg_*` subset behind an explicit choice.
   Validate combined keyboard/velocity/LFO/envelope cutoff bounds. Keep richer
   modifiers and export diagnosed until implemented.
6. Add 48 kHz audio regressions of at least one second, then qualify against
   pinned sfizz across Linux, Windows and macOS. Retain convention differences
   and residuals without fitting gain, shifting time or relaxing limits.

## Additional work beyond the prompt

None.
