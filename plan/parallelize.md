# Test parallelization and performance

## Baseline before implementation

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
Implementation began after the user's explicit request to implement this plan.

## Implementation results (2026-10-08)

The implementation keeps safaz serial and preserves uFor and enge's existing
`-n auto --dist=worksteal` defaults. safaz now has pytest-xdist in its development
dependencies, with explicit parallel execution documented. All three READMEs
describe running one full suite at a time. safaz documents serial baseline
regeneration, and enge documents reusing the native build for unchanged Rust code.

### Measurement method

Measurements used frozen source copies on macOS 14.5, arm64, with 10 available
logical CPUs and 64 GiB RAM. Tests used Python 3.13.12, pytest 9.1.1, and
pytest-xdist 3.8.0. Elapsed times include worker startup and collection. Each
isolated run had a fresh temporary output directory, avoiding cleanup of a
previous suite's audio files inside the timed interval. Suites ran sequentially.

| Project | Frozen revision | Passing tests before scheduling changes |
| --- | --- | --- |
| safaz | `b084358ece7bc8d05c7381fc1305d9a2ac03e62a` plus the approved development dependency update | 243 |
| uFor | `f4799104c93ceb67d4caef867adfe903d89a4d2e` | 1,129 |
| enge | `b0d53aa28713434dee8b5e490482bc593925ecbd` | 976, with 21 existing skips |

Dependency/native preparation happened once, outside these timings: safaz
0.43 seconds, uFor 0.36 seconds, and enge 25.10 seconds. Independent feature
changes made in other work during this task were excluded from the benchmark
copies, while the final current revisions also received correctness checks.

### Worker measurements

The following are elapsed seconds, using medians from three isolated full-suite
runs except where marked as a single screening run:

| Project | Serial | 2 workers | 4 workers | 8 workers | Automatic workers |
| --- | ---: | ---: | ---: | ---: | ---: |
| safaz | 0.99 | 1.03 | 1.01 | Not measured | Not measured |
| uFor | 17.21 | Not measured | 6.38 | 4.42 | 4.44 |
| enge, grouped renderers | Excluded screen | Not measured | 323.42 | 195.65 (one run) | 180.90 |
| enge, split experiment | Not measured | Not measured | 324.08 (one run) | 190.94 (one run) | 189.35 |

safaz's worker startup outweighs its small amount of test work, so its serial
default remains. uFor's automatic setting reduces elapsed time by 74% compared
with the serial override used in the previous slice. Eight workers and automatic
workers are effectively tied on this host, so no host-specific cap was added.
enge's automatic workers beat the eight-worker screen and the repeated
four-worker measurements, so its automatic default also remains. Its serial
screen overlapped other work and is excluded from quantitative comparisons.

### enge scheduling experiment

The duration profiles identified Patch division's bundled renderer scenarios
as expensive cases, with individual bundled calls reaching about 17 seconds
in an isolated automatic-worker baseline. The experiment parametrized NumPy,
native, and persistent renderers independently: 160 bundled cases became 480
independently scheduled cases. The frozen full suite therefore reported 1,296
passes instead of 976, with the same 21 skips. This was a collection change, not
additional or removed behavior coverage. Waveform oracles, tolerances, 48 kHz
one-second WAV output, partition checks, snapshot replay, and the existing
callback checks remain.

A focused selection containing ten original cases, or thirty split cases, ran
three times before and after with eight workers. Its median fell from 21.08 to
17.61 seconds, a 16.5% improvement. However, the full-suite automatic-worker
median rose from 180.90 to 189.35 seconds, a 4.7% regression. Aggregate child CPU
time also increased, with renderer-specific cases repeating setup and reference
calculations. A four-worker screen with the split took 324.08 seconds and did
not show a useful gain. The split was therefore reverted; the final suite keeps
the original grouped renderer scenarios and all their assertions. No caching
or engine-code changes were retained.

### Workflow result

Summing the sequential suite medians for the previous slice's choices gives
341.62 seconds: safaz serial, uFor serial, and enge with four workers. Using
safaz serial and the existing automatic defaults for uFor and enge gives
186.33 seconds, about 45.5% less pytest time. These are sums of independently
measured suite medians, not a timed run including every verification tool.

The 50% complete-verification target was not demonstrated. enge still accounts
for roughly 97% of the selected pytest budget. Its many audio scenarios, including
Patch division and child-stage event checks, remain the main test-time cost.
Native preparation took another 25.10 seconds in the separate preparation
measurement. The retained improvements are measured worker selection, avoiding
competing full suites, and reusing unchanged native artifacts. The rejected split
shows why finer parametrization should be measured rather than assumed faster.

The final current enge tree, including the independent Threshold and Slew work,
passed 995 tests with 21 skips in 205.43 seconds after restoring the grouped
test. Its slowest case was the new Slew/Threshold cue regression at 32.98
seconds. This current-revision check is not part of the frozen-source speedup
calculation. Ruff, formatting, type checking, pyupgrade on changed Python, and
diff checks passed for the changes.

### Platform verification

Manual CI workflows verify the selected configuration on Linux, Windows, and
macOS. safaz additionally tests four-worker isolation on every platform. enge's
existing core and Rubber Band matrix now accepts manual dispatch, follows its
project worker default, and allows 45 minutes after Windows exceeded the
previous 25-minute build-and-test budget.

- [safaz: serial and parallel suites passed on all three platforms](https://github.com/rec/safaz/actions/runs/37824346512).
- [uFor: parallel suites passed on all three platforms](https://github.com/rec/ufor/actions/runs/37825346490).
- [enge: core and Rubber Band suites passed on all three platforms](https://github.com/rec/enge/actions/runs/37831710821). This run exercised the split layout before its performance-based reversion; it preserves the same assertion coverage as the final grouped layout.

The Windows checks exposed uFor's unconditional POSIX locking import, implicit
text encodings, and an exact comparison of calculated ring coordinates. These
were corrected with Windows standard-library locking, explicit UTF-8, and a
1e-15 absolute coordinate tolerance while keeping metadata and names exact.

Initial overlapping measurements and measurements affected by temporary-file
cleanup are excluded from performance claims. Memory-pressure readings remained
comfortable; the largest-child RSS measurement is not the total worker-pool
peak. These results describe this development host, not all supported hardware.
Builds, linters, and type checks are separate from the reported pytest timings.

## References

- [pytest-xdist worker counts and scheduling](https://pytest-xdist.readthedocs.io/en/stable/distribution.html)
- [pytest-xdist worker isolation and fixture execution](https://pytest-xdist.readthedocs.io/en/stable/how-to.html)

## Additional work beyond the prompt

None.
