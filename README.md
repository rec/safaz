# safaz

safaz reads and writes SFZ instruments using [uFor](https://github.com/rec/ufor)
as the native instrument format. It preserves supported musical behavior and
reports unsupported features with precise source locations or native model
paths.

```python
from pathlib import Path

from safaz.exporter import write
from safaz.reader import read
from ufor.codec import score_toml

result = read(Path('Glass.sfz'))
if result.complete and result.instrument is not None:
    Path('instrument.toml').write_text(score_toml(result.instrument), encoding='utf-8')
    exported = write(result.instrument)
```

Check `complete` and inspect `unimplemented` before accepting an import or
export. Import seals existing audio assets; it does not rewrite them. The file
reader defaults to 48 kHz stereo output, with explicit rate/layout options.

For conversion without file I/O, use `safaz.parser.parse`,
`safaz.parser.sample_paths`, and `safaz.compiler.compile_instrument` with
caller-supplied `ufor.samples.metadata.AudioMetadata` facts.
`safaz.exporter.write` returns text without writing files.

Static two-pole filter responses can be imported with
`read(Path('Glass.sfz'), filter_response='sfizz_rbj')`. The default diagnoses
them without importing a filter. Accepted responses use native filtering after
amplitude, matching the sfizz voice pipeline; see the
[filter conversion rules](doc/conversion.md#static-filter-responses).

uFor owns generic instrument definitions, controller bindings, and preparation.
safaz owns SFZ rules, compatibility diagnostics, sample-file inspection, tests,
and documentation. Rendering and live device access belong to consuming
applications.

safaz supports Linux, Windows, and macOS with Python 3.13 or newer. SFZ files
are read as UTF-8, with an optional BOM; save exported text with
`Path('output.sfz').write_text(exported.contents, encoding='utf-8')`.
Both slash and backslash sample separators are accepted and stored as portable
relative paths using slashes. Match filename case exactly so instruments also
work on case-sensitive filesystems.

SoundFile wheels bundle libsndfile for the supported Linux, Windows, and macOS
platforms. Source installations need a system libsndfile installation; see
the [SoundFile installation instructions](https://python-soundfile.readthedocs.io/en/latest/#installation).
The symlink containment test requires Windows Developer Mode or symlink
privileges and skips only when Windows reports that privilege is unavailable.

- [Conversion contract](doc/conversion.md)
- [Opcode support](doc/sfz-support.md)
- [Remaining work](plan/sfz.md)

Development uses `uv sync`, `uv run pytest`, `uv run ruff check safaz test`, and
`uv run ty check safaz`. Tests default to serial execution because worker startup
costs more than it saves for this suite. Use
`uv run --locked pytest -n 4 --dist=worksteal` to check parallel isolation.
Regenerate regression baselines separately with `-n 0`. Run one full suite at a
time when also verifying uFor or enge; their workers share the same CPU budget.
The manual [cross-platform workflow](.github/workflows/test.yml) checks both
serial execution and four workers on Linux, Windows, and macOS.
See [test performance](plan/parallelize.md) for measurements and worker choices.

The optional [reference suite](reference_test/README.md) compares imported
playback against a pinned, unmodified sfizz client. Its separate manual workflow
preserves mismatches as failure evidence; it does not imply playback equivalence.

The implementation and tests were extracted from uFor
and recs; this project retains their MIT license and copyright notices.
