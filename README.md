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
    Path('instrument.toml').write_text(score_toml(result.instrument))
    exported = write(result.instrument)
```

Check `complete` and inspect `unimplemented` before accepting an import or
export. Import seals existing audio assets; it does not rewrite them. The file
reader defaults to 48 kHz stereo output, with explicit rate/layout options.

For conversion without file I/O, use `safaz.parser.parse`,
`safaz.parser.sample_paths`, and `safaz.compiler.compile_instrument` with
caller-supplied `ufor.samples.metadata.AudioMetadata` facts.
`safaz.exporter.write` returns text without writing files.

uFor owns generic instrument definitions, controller bindings, and preparation.
safaz owns SFZ rules, compatibility diagnostics, sample-file inspection, tests,
and documentation. Rendering and live device access belong to consuming
applications.

- [Conversion contract](doc/conversion.md)
- [Opcode support](doc/sfz-support.md)
- [Remaining work](plan/sfz.md)

Development uses `uv sync`, `uv run pytest`, `uv run ruff check safaz test`, and
`uv run ty check safaz`. The implementation and tests were extracted from uFor
and recs; this project retains their MIT license and copyright notices.
