# Intermittent 8,192-frame cutoff in unmodified sfizz_render

An occasional offline render stops the first note at the default sample
preload boundary. The attached normal and truncated WAVs were produced by the
same executable, options and byte-identical inputs. Both invocations exited
successfully with empty stdout/stderr. No safaz or enge code participates in
rendering this reproducer.

## Inputs

`instrument.sfz` is the entire instrument:

```sfz
<region> sample=a.wav key=60 loop_mode=one_shot
```

- `a.wav`: one second, 48,000 Hz, mono PCM16, a 500 Hz square wave at
  amplitude 0.125. It contains exactly 48,000 frames and no silent tail,
  loop metadata or embedded instrument settings. It is a generated test
  signal, not a third-party recording.
- `note.mid`: a 35-byte format-0 MIDI file, 480 PPQN, with note-on for C4
  (MIDI 60), channel 1, velocity 127 at tick 0, note-off at tick 960, then
  end-of-track. The implicit standard tempo is 500,000 microseconds/quarter,
  so note-off/end-of-track is at one second. There are no controllers,
  program changes or tempo changes.

The fixture needs no Python packages, project installation or audio device.

## Exact render command

From this directory, with the unmodified executable on PATH:

```sh
sfizz_render --sfz instrument.sfz --midi note.mid --wav output.wav --samplerate 48000 --blocksize 256 --quality 1 --polyphony 64 --use-eot
```

Only the executable path and output filename need substituting. Repeated
invocations can overwrite `output.wav`; preserve each result with a distinct
filename to compare them. For example, this POSIX-shell loop retains 200 runs
and stops on a renderer error:

```sh
for i in $(seq 1 200); do
    sfizz_render --sfz instrument.sfz --midi note.mid --wav "output-$i.wav" --samplerate 48000 --blocksize 256 --quality 1 --polyphony 64 --use-eot || break
done
```

Failure is intermittent. A successful batch does not establish that the issue
is absent, and 200 invocations do not guarantee reproduction. Run serially;
the recorded failure did not require concurrent renderers or deliberate load.
The upstream client already enables freewheeling internally.

## Expected and observed

Expected: approximately one second of steady 500 Hz tone. Listen to
`normal.wav` for the usual output and `truncated.wav` for the observed fault.
These are complete, unmodified sfizz outputs, not normalized or aligned clips.

In the initial 200 serial renders, 199 matched `normal.wav` byte-for-byte.
Invocation 81 (zero-based) produced `truncated.wav`. Both output files have
48,128 stereo PCM16 frames at 48 kHz; the file length itself is not truncated.

The two outputs match exactly through frame 8,191. From frame 8,192 through
48,127, the faulty output is constant `-1/32768` in both channels, the pinned
client's PCM16 encoding of digital silence. The normal output remains audible
through frame 48,127, including its end-of-sample release within the final
block. The maximum absolute difference is `0.033203125`. The faulty tone lasts
`8192 / 48000 = 0.1706667` seconds, despite the one-second source and MIDI gate.
`verification.json` records the hashes, measurements and reduction results.

The packaged inputs were rechecked for another 200 renders from the packaged
directory, all matching the usual output. A direct shell invocation of the
command above (substituting the executable and output paths) also matched.
The recorded bad output is from the initial verified batch, not this recheck.

## Reduction and scope

This is the smallest form that reproduced in this experiment. It reduces the
original three-region, stereo gain/velocity case to one region, one mono sample
and one note, with no gain, pan, controller or envelope overrides.

The still smaller forms below produced only the same usual output:

| Complete SFZ | Serial runs | Observed cutoff |
| --- | ---: | ---: |
| `<region> sample=a.wav` | 1,000 | 0 |
| `<region> sample=a.wav loop_mode=one_shot` | 300 | 0 |
| `<region> sample=a.wav key=60` | 300 | 0 |

Those negative batches do not prove that the removed opcodes are necessary.
All forms use the same sample, MIDI and renderer options. This is a verified
small reproducer, not a claim of a mathematically minimal triggering input.

## Tested build

- sfizz commit `f5c6e29f23b8057867c08e88f5f6ac6738baa30b`, with its recorded
  recursive submodule revisions; unmodified upstream `sfizz_render`.
- macOS 14.5 arm64, AppleClang `15.0.0.15000309`.
- CMake 3.31.10, Release, `SFIZZ_JACK=OFF`, `SFIZZ_SHARED=OFF`,
  `SFIZZ_TESTS=OFF`, `SFIZZ_RENDER=ON`, `ENABLE_LTO=OFF`,
  `CMAKE_CXX_STANDARD=17`.
- Executable SHA-256:
  `9cfe47514f8e968aa1660a3f06e8d4c8b446b42a6b421afc8b210818be2a59d0`.

The retained executable hash was checked against its existing build manifest.
This package does not include or modify sfizz. Other versions and platforms
have not been qualified with this reduced input.

## Suspected mechanism

The 8,192-frame boundary matches `config::preloadSize` in the tested revision.
`FilePool::waitForBackgroundLoading()` waits for dispatched loading futures
but does not wait for requests still in `filesToLoad`. `Voice::Impl::fillWithData`
bounds the sample end by the currently available source length, then can stop
the one-shot voice at that boundary. This is a source-supported explanation,
not an instrumented proof of the failing thread interleaving.

The reproduced early cutoff is separate from pan compensation, ordinary PCM16
rounding and previously observed cross-block MIDI timing differences.
