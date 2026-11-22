from pathlib import Path

import harness
import numpy as np
from ufor.interface import ScoreReference

from safaz.model import SfzMidiBindingRequest
from safaz.reader import read


def test_nested_root_relative_includes_match_flattened_sfz(
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    _, executable, _, output = reference_paths
    case = harness.Case(name='unity', notes=[harness.Note(tick=11)], end_tick=6000)
    flat = output / 'includes-flat'
    nested = output / 'includes-nested'
    for folder in (flat, nested):
        harness.create_inputs(case, folder)
    flat_sfz = flat / 'instrument.sfz'
    flat_sfz.write_text(flat_sfz.read_text().replace('sample=a.wav', 'sample=b.wav'))
    root = nested / 'instrument.sfz'
    control, region = flat_sfz.read_text().split('\n', maxsplit=1)
    root.write_text(f'{control}\n#define $LAYER parts/layer.sfzh\n#include "$LAYER"\n')
    (nested / 'parts').mkdir()
    (nested / 'parts/layer.sfzh').write_text('#include "source.sfzh"\n')
    (nested / 'source.sfzh').write_text(
        '#define $SAMPLE b.wav\n' + region.replace('b.wav', '$SAMPLE')
    )

    midi_binding = SfzMidiBindingRequest(
        instrument=ScoreReference(path='instrument.toml'),
        part='main',
        repeated_key_release='oldest',
    )
    flattened = read(flat_sfz, midi_binding=midi_binding)
    included = read(root, resolve_includes=True, midi_binding=midi_binding)
    assert flattened.complete and included == flattened

    # Compare the selected sample in a stable window before note-off.
    window = slice(1024, 8192)
    expected = harness.render_reference(executable, flat, 256)[window]
    actual = harness.render_reference(executable, nested, 256)[window]
    assert np.max(np.abs(expected)) > 100 * harness.PCM_ERROR
    np.testing.assert_array_equal(actual, expected)
