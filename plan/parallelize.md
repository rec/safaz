# Test parallelization and performance

## Current position

As checked on 2026-10-08:

| Project | Configured default | Last slice's full-suite execution |
| --- | --- | --- |
| safaz | Serial pytest; no pytest-xdist dependency | Serial, 243 tests, roughly 1–2 seconds |
| uFor | pytest-xdist, `-n auto --dist=worksteal` | Explicitly overridden with `-n 0`, 1,129 tests |
| enge | pytest-xdist, `-n auto --dist=worksteal` | Four workers; clean implementation run passed 976 tests with 21 skips in about eight minutes |

Several enge verification runs overlapped during that slice. Those timings are
observations, not comparable performance benchmarks. Worker count, CPU
contention, build time, and test selection must be controlled before claiming
a speedup.

The largest opportunity is faster enge verification and better coordination of
the existing parallel suites. Parallelizing safaz alone is unlikely to produce
a significant improvement while its complete suite takes only a few seconds.

## Goal

Aim to halve the elapsed time of the complete verification workflow on a
representative development machine, while preserving every test, assertion,
audio regression, and existing skip condition. Treat this as a measurement
target, not a promised result. Report the measured improvement and remaining
bottlenecks if the target is not reached.

## 1. Measure without competing test runs

Prepare dependencies and enge's native extension once before measuring test
execution. Measure builds separately. Run one full suite at a time, from the
same revision, with the same dependencies, environment, and test selection.

For enge and uFor, compare these commands in each project's directory:

```text
uv run --locked pytest -q -n 0 --durations=25
uv run --locked pytest -q -n 4 --dist=worksteal --durations=25
uv run --locked pytest -q -n 8 --dist=worksteal --durations=25
uv run --locked pytest -q -n auto --dist=worksteal --durations=25
```

Use smaller worker counts on machines with fewer cores. Repeat each useful
configuration three times and compare median elapsed time, including worker
startup and collection. Record test counts, skips, CPU/core information,
memory pressure, and the slowest tests. Do not infer gains from different
suite sizes or simultaneous runs.

Use uFor's existing parallel default for full-suite verification unless these
measurements show a reason to override it. Keep serial execution available for
debugging and small selections where startup dominates.

## 2. Add measured parallel support to safaz

Add pytest-xdist to the development dependency group and update uv.lock in a
separate dependency commit. Compare serial execution with two and four workers
using the same procedure. Adopt `-n auto --dist=worksteal` as the default only
if it improves complete-suite elapsed time. Otherwise retain the serial default
and document explicit parallel execution for larger future suites.

Before enabling a parallel default, verify that generated files remain inside
each test's `tmp_path`, conformance inputs remain read-only, collection order
is deterministic, and regression fixtures do not overwrite shared baselines.
Baseline regeneration should run separately and serially. Address observed
collisions locally rather than introducing a global locking system.

Verify the chosen configuration on Linux, Windows, and macOS. Preserve existing
platform-specific skips, including unavailable symlink support.

## 3. Remove measured enge bottlenecks

Use the duration results to identify the few tests responsible for most elapsed
time. Work stealing distributes test cases; it cannot divide a single long
test. If a long test contains independent scenarios, expose those scenarios
as parametrized cases so workers can distribute them. Keep continuous state,
event-ordering, partition, and snapshot checks together where their sequence
is the behavior under test.

For expensive reference calculations, reuse immutable expected data only when
the measured cost justifies it and the inputs are genuinely identical. Preserve
independent numerical oracles. Do not replace expected results with output from
the implementation being tested. Account for fixture setup repeating in each
worker before choosing a wider fixture scope.

Keep audio regressions at 48,000 samples per second and at least one second
long. Preserve waveform comparisons, tolerances, meaningful parameter coverage,
and NumPy/native checks. Avoid new dependencies or engine changes solely to
make the tests faster.

## 4. Coordinate the verification workflow

Give active test runs a shared CPU budget. Do not launch several full enge
suites against the same machine while tuning worker counts. Prefer one measured
parallel suite over several competing pools. Parallel project execution should
be adopted only if a fixed total worker budget beats sequential project runs.

Run focused tests while editing. Once the final implementation is ready, run
one full verification of that exact candidate. Repeat it only after relevant
changes or unresolved failures. Independently required per-commit verification
still applies, including dependency-only commits. Reuse already built native
artifacts within an unchanged candidate rather than rebuilding between test
commands.

## Acceptance and implementation order

1. Record comparable baseline timings and identify the slowest enge cases.
2. Select measured worker counts and avoid competing full-suite runs.
3. Evaluate safaz's pytest-xdist dependency and retain the fastest default.
4. Split or improve only demonstrated expensive enge tests, in small commits.
5. Repeat the same timing matrix and report end-to-end gains, with unchanged
   test coverage and passing correctness checks on supported platforms.

Follow the repository's required checks before committing Python or data
changes. Commit dependency changes separately and push each requested commit.
This document authorizes no implementation or dependency changes by itself.

## References

- [pytest-xdist worker counts and scheduling](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
- [pytest-xdist worker isolation and fixture execution](https://pytest-xdist.readthedocs.io/en/stable/how-to.html)

## Additional work beyond the prompt

None.
