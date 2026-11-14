# Frozen sfizz envelope isolation

This diagnostic client links to the unmodified pinned sfizz envelope and filter
classes. It does not patch sfizz or change safaz, uFor, enveLFO or enge playback.
The normal reference assertions and `2/32768 + 2e-6` waveform limit remain intact.

Build the ordinary upstream renderer using the parent reference README, then
configure this separate client. `SFIZZ_SOURCE` must be an absolute path to the
clean checkout at `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, including submodules:

```sh
uv run --no-project --with cmake==3.31.10 cmake -S reference_test/envelope_probe -B .reference/probe-build -DSFIZZ_SOURCE=/ABSOLUTE/PATH/TO/sfizz -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_STANDARD=17
uv run --no-project --with cmake==3.31.10 cmake --build .reference/probe-build --target envelope_probe --config Release --parallel 4
uv run --no-sync pytest -q reference_test/test_filter_envelope_isolation.py --require-reference --sfizz-source .reference/sfizz --sfizz-build .reference/build --sfizz-render .reference/build/library/bin/sfizz_render --sfizz-envelope-probe .reference/probe-build/envelope_probe --reference-output RESULTS
```

Use a fresh results directory. Windows executable locations can differ by
generator/configuration, as described in the parent README. The probe bypasses
asset acquisition, but the full player-resynthesis cases also use the installed
safaz/enge import path and are subject to its platform limitations.

The suite contains twelve import/runtime equation checks, 36 direct class probes
(twelve profiles at blocks 64/256/257), and seven full player-resynthesis cases.
The direct probes use a common, held 500 Hz square-wave source for two seconds at
48 kHz. Its gain is the declared client master gain and SFZ mono center law,
never a value fitted to recorded output. They exclude source loading, MIDI,
amplifier attenuation and LFOs from the filter comparisons. The `combined`
profile probes its 600-cent envelope component at the common base cutoff;
tracking and the known triangle/parabolic LFO convention are separate effects.

`isolated.wav` contains nine float channels, in this order:

1. Portable envelope level.
2. Frozen sfizz envelope level.
3. Independent TPT filter with portable levels.
4. Independent TPT filter with sfizz levels.
5. Frozen sfizz filter with portable levels.
6. Frozen sfizz filter with sfizz levels.
7. Frozen sfizz amplifier envelope level.
8. Frozen sfizz filter with sfizz levels and amplifier applied.
9. Portable amplifier envelope level.

These are diagnostic signals, including DC control values. `amplifier.wav`
separately contains the portable and sfizz amplifier laws applied before the
same TPT filter and portable cutoff trajectory. Reports measure each factor
independently; their maximum errors are not additive. Constant-cutoff controls
check that the filter difference disappears when modulation is removed.
The imported filter and amplifier envelopes are also observed at 2,000 evenly
spaced rational times, plus the gate if not already included, and compared with
their independent declared equations.

Full player resynthesis uses the source-audited clock increment and strict event
comparison in `sfizz_render.cpp` / `fmidi_mini.cpp`, plus the single repeated
source sample in `Voice::renderBlock` / `fillWithData`. It feeds that declared
source timeline into the actual frozen sfizz envelope/filter classes. No event
offset, gain or curve is searched for or fitted to the WAV. `resynthesis.json`
retains both this explanatory prediction's comparison and the original failing
native/reference measurement. A truncated reference remains a failed prediction;
it is not retried, xfailed or silently replaced.

For comparison with retained normal evidence, first verify `instrument.sfz`,
`a.wav` and `performance.mid` byte-for-byte with `cmp`. A decoded diagnostic
difference can be inspected without converting it to integer samples:

```sh
ffmpeg -i PREDICTION.wav -i RETAINED_REFERENCE.wav -filter_complex '[0:a]aformat=sample_fmts=dblp[a];[1:a]aformat=sample_fmts=dblp[b];[a][b]amerge=inputs=2,pan=stereo|c0=c0-c2|c1=c1-c3,aformat=sample_fmts=dbl,astats=metadata=0:reset=0' -f null -
```

The merge ends at the prediction's authored horizon, matching the existing
comparison interval. This diagnostic does not replace any acceptance assertion.
Requests, class traces, process status, source provenance, probe hash, WAVs and
reports are generated evidence. All code and build instructions live here.
