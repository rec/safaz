from pathlib import Path

import harness
import numpy as np
import pytest
import soundfile
from enge.sample_instrument import OfflineSampler, prepare, prepare_trace
from ufor.events import Trigger
from ufor.interface import ScoreReference

from safaz.model import SfzMidiBindingRequest
from safaz.reader import read


@pytest.mark.parametrize('gain_db', [-12, 0, 9])
def test_static_eq_matches_pinned_reference_at_center_and_both_sides(
    gain_db: int, reference_paths: tuple[Path, Path, Path, Path]
) -> None:
    _, executable, _, output = reference_paths
    rate = harness.RATE
    case = harness.Case(name='unity', notes=[harness.Note(tick=11)], end_tick=6000)
    folder = output / f'eq-{gain_db}'
    harness.create_inputs(case, folder)
    sfz = folder / 'instrument.sfz'
    sfz.write_text(sfz.read_text() + f'\neq1_freq=2500 eq1_bw=1.5 eq1_gain={gain_db}\n')
    center = 2 * np.pi * 2500 / rate
    half_inverse_q = np.sinh(np.log(2) * 1.5 * center / (2 * np.sin(center)))
    edge_ratio = np.hypot(1, half_inverse_q) + half_inverse_q
    phases = 2 * np.arctan(
        np.tan(center / 2) * np.array([1 / edge_ratio, 1, edge_ratio])
    )
    frequencies = phases * rate / (2 * np.pi)
    inputs = 0.04 * np.sin(np.arange(rate)[:, None] * phases).sum(axis=1)
    sample = folder / 'a.wav'
    soundfile.write(
        sample, np.column_stack([inputs, np.zeros(rate)]), rate, subtype='PCM_16'
    )
    decoded, _ = soundfile.read(sample, always_2d=True)
    compiled = read(
        sfz,
        eq_response='sfizz_rbj',
        midi_binding=SfzMidiBindingRequest(
            instrument=ScoreReference(path='instrument.toml'),
            part='main',
            repeated_key_release='oldest',
        ),
    )
    assert compiled.complete and compiled.instrument is not None
    document = compiled.instrument
    prepared = prepare(document, {'asset-1': decoded})
    onset = 11 * 25
    events = [
        Trigger(
            tick=onset,
            ordinal=0,
            part='main',
            trigger_id='note',
            key=60,
            pitch_hz=440 * 2 ** ((60 - 69) / 12),
        )
    ]
    actions = prepare_trace(document.body, events, seed=0).actions
    response_window = slice(4096, 7936)
    window_phases = np.arange(3840)[:, None] * phases
    basis = np.column_stack(
        [np.sin(window_phases), np.cos(window_phases), np.ones(len(window_phases))]
    )

    def amplitudes(audio: np.ndarray) -> np.ndarray:
        weights = np.linalg.lstsq(basis, audio, rcond=None)[0]
        return np.hypot(weights[:3], weights[3:6])

    response = 10 ** (gain_db / np.array([40, 20, 40]))
    expected = (
        amplitudes(decoded[response_window, 0])
        * response
        * harness.MASTER_GAIN
        * harness.authored_pan_gains(case)[0]
    )
    window = slice(onset + 4096, onset + 7936)
    for backend in ('native', 'numpy'):
        rendered = OfflineSampler(prepared, backend).advance(actions, 0, rate)
        soundfile.write(folder / f'{backend}.wav', rendered, rate, subtype='FLOAT')
        np.testing.assert_allclose(
            amplitudes(rendered[window, 0] * harness.MASTER_GAIN),
            expected,
            rtol=0,
            atol=harness.FLOAT_ERROR,
        )
    reference = harness.render_reference(executable, folder, 256)
    reference_amplitudes = amplitudes(reference[window, 0])
    harness.write_json(
        folder / 'eq-response.json',
        {
            'frequencies': frequencies.tolist(),
            'expected': expected.tolist(),
            'reference': reference_amplitudes.tolist(),
        },
    )
    np.testing.assert_allclose(
        reference_amplitudes, expected, rtol=0, atol=2 * harness.PCM_ERROR
    )
