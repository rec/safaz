from pathlib import Path
from typing import Literal

import harness
import numpy as np
import soundfile
from enge.performance import MidiConverter
from enge.sample_instrument import OfflineSampler, SamplerSnapshot, prepare
from meedee.messages import NoteOn, PitchBend
from modulation_oracle import ModulationProfile
from ufor.interface import ScoreReference
from ufor.samples import trace

from safaz.model import SfzMidiBindingRequest
from safaz.reader import read


def test_held_pitch_bends_are_part_local_and_survive_restore(
    backend: Literal['numpy', 'native'], reference_output: Path
) -> None:
    case = harness.Case(
        name='bend-parts',
        notes=[harness.Note(tick=11)],
        end_tick=6000,
        source_channels=1,
        modulation_profile=ModulationProfile(bend_up=1200, bend_down=-300),
    )
    folder = reference_output / f'bend-parts-{backend}'
    harness.create_inputs(case, folder)
    compiled = read(
        folder / 'instrument.sfz',
        pitch_bend_response='sfizz_symmetric',
        midi_binding=SfzMidiBindingRequest(
            instrument=ScoreReference(path='instrument.toml'),
            part='first',
            repeated_key_release='oldest',
        ),
    )
    assert (
        compiled.complete
        and compiled.instrument is not None
        and compiled.binding is not None
    )
    document = compiled.instrument
    entry = compiled.binding.body.midi[0]
    binding = compiled.binding.model_copy(
        update={
            'body': compiled.binding.body.model_copy(
                update={
                    'midi': [
                        entry.model_copy(update={'channels': [1], 'part': 'first'}),
                        entry.model_copy(update={'channels': [2], 'part': 'second'}),
                    ]
                }
            )
        }
    )
    converter = MidiConverter(source='keys', binding=binding, instrument=document)
    events = []
    for ordinal, (tick, message) in enumerate(
        [
            (0, PitchBend(channel=1, value=8191)),
            (1, NoteOn(channel=1, note=60, velocity=127)),
            (1, NoteOn(channel=2, note=60, velocity=64)),
            (4800, PitchBend(channel=1, value=0)),
            (9600, PitchBend(channel=2, value=-8192)),
        ]
    ):
        events.extend(converter.feed(message, tick=tick, ordinal=ordinal))
    actions = trace.prepare(document.body, events, seed=0).actions
    source = soundfile.read(folder / 'a.wav', always_2d=True)[0]
    prepared = prepare(document, {'asset-1': source})
    renderer = OfflineSampler(prepared, backend=backend)
    chunks = []
    for start, end in [(0, 4800), (4800, 9600), (9600, 24000), (24000, 96000)]:
        chunks.append(
            renderer.advance([a for a in actions if start <= a.tick < end], start, end)
        )
        snapshot = SamplerSnapshot.model_validate_json(
            renderer.snapshot().model_dump_json()
        )
        renderer = OfflineSampler(prepared, backend=backend)
        renderer.restore(snapshot)
    expected = np.zeros((96000, 2))
    frames = np.arange(1, 96000)
    for cents, velocity in [
        (np.where(frames < 4800, 1200, 0), 127),
        (np.where(frames < 9600, 0, -300), 64),
    ]:
        positions = np.concatenate(([0], np.cumsum(2 ** (cents[:-1] / 1200))))
        audio = np.interp(positions, np.arange(len(source)), source[:, 0], right=0)
        expected[1:] += (
            audio[:, None]
            * harness.MASTER_GAIN
            * (velocity / 127) ** 2
            * np.array(harness.authored_pan_gains(case))
        )
    actual = np.concatenate(chunks) * harness.MASTER_GAIN
    soundfile.write(folder / 'parts-native.wav', actual, harness.RATE, subtype='FLOAT')
    soundfile.write(
        folder / 'parts-expected.wav', expected, harness.RATE, subtype='FLOAT'
    )
    measurement = harness.compare(actual, expected)
    harness.write_json(folder / 'parts-report.json', measurement)
    assert measurement['passed'], measurement
