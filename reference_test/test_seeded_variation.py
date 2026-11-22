from math import ceil
from pathlib import Path
from typing import Literal

import numpy as np
import pytest
import soundfile
from enge.sample_instrument import (
    OfflineSampler,
    SamplerSnapshot,
    prepare,
    prepare_trace,
)
from ufor.events import Trigger
from ufor.samples import trace
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz.compiler import compile_instrument
from safaz.parser import parse


@pytest.mark.parametrize('backend', ['numpy', 'native'])
def test_seeded_sfz_variation_survives_pending_and_active_snapshots(
    backend: Literal['numpy', 'native'], tmp_path: Path
) -> None:
    rate = 48000
    result = compile_instrument(
        parse(
            '<region> sample=a.wav key=60 loop_mode=no_loop amp_veltrack=0 '
            'offset=100 offset_random=100 delay=0.01 delay_random=0.025 '
            'volume=-10 amp_random=-8 tune=20 pitch_random=35.5'
        ),
        name='variation',
        title='Variation',
        assets={
            'a.wav': AudioMetadata(
                channels=1,
                frames=rate,
                sample_rate=rate,
                encoding='WAV/PCM_16',
                byte_length=96044,
                sha256='0' * 64,
                embedded_loop_known=True,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=rate)),
        output_channels=['mono'],
        variation_response='portable_seeded',
    )
    assert result.complete and result.instrument is not None
    document = result.instrument
    event = Trigger(
        tick=37,
        ordinal=0,
        part='main',
        trigger_id='note',
        key=60,
        pitch_hz=440 * 2 ** ((60 - 69) / 12),
    )
    actions = prepare_trace(document.body, [event], seed=17).actions
    draw = next(a.variation for a in actions if isinstance(a, trace.VoiceStart))
    python_actions = trace.prepare(document.body, [event], seed=17).actions
    assert draw == next(
        a.variation for a in python_actions if isinstance(a, trace.VoiceStart)
    )
    source = np.linspace(0.1, 0.3, rate)
    prepared = prepare(document, {'asset-1': source[:, None]})
    expected = OfflineSampler(prepared, backend).advance(actions, 0, rate)
    renderer = OfflineSampler(prepared, backend)
    chunks = [renderer.advance(actions, 0, 100)]
    for before, after in ((100, 8000), (8000, rate)):
        saved = SamplerSnapshot.model_validate_json(
            renderer.snapshot().model_dump_json()
        )
        renderer = OfflineSampler(prepared, backend)
        renderer.restore(saved)
        chunks.append(renderer.advance([], before, after))
    actual = np.concatenate(chunks)
    soundfile.write(
        tmp_path / f'restored-{backend}.wav', actual, rate, subtype='DOUBLE'
    )
    np.testing.assert_array_equal(actual, expected)

    onset = event.tick + ceil((0.01 + draw.delay_seconds) * rate)
    first_frame = 100 + draw.offset_frames
    ratio = 2 ** ((37.75 + draw.pitch_cents) / 1200)
    gain = 10 ** ((-14 + draw.gain_db) / 20)
    first_samples = np.interp(
        first_frame + np.arange(32) * ratio, np.arange(rate), source
    )
    assert not np.any(actual[:onset])
    np.testing.assert_allclose(actual[onset : onset + 32, 0], first_samples * gain)
