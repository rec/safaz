from fractions import Fraction
from typing import Literal

import pytest
from envelfo import patch
from envelfo.runtime import envelfo_at, initial_envelfo
from ufor import envelfo, modulation
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, parser
from safaz.model import SfzCompileResult


def compile_modulation(
    text: str, pitch: Literal['diagnose', 'sfizz_triangle'] = 'sfizz_triangle'
) -> SfzCompileResult:
    return compiler.compile_instrument(
        parser.parse('<region> sample=a.wav key=60 loop_mode=one_shot ' + text),
        name='test',
        title='Test',
        assets={
            'a.wav': AudioMetadata(
                channels=1,
                sample_rate=48000,
                frames=48000,
                encoding='WAV/PCM_16',
                byte_length=96044,
                sha256='0' * 64,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
        output_channels=['left', 'right'],
        pitch_lfo_response=pitch,
    )


@pytest.mark.parametrize('depth', [-1200, 333.5, 1200])
@pytest.mark.parametrize('delay,fade', [(0, 0), (0.1, 0.2)])
def test_pitch_lfo_uses_signed_cents_and_delayed_voice_phase(
    depth: float, delay: float, fade: float
) -> None:
    result = compile_modulation(
        f'pitchlfo_freq=2 pitchlfo_depth={depth} pitchlfo_delay={delay} '
        f'pitchlfo_fade={fade} tune=17 pitch_veltrack=100'
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    oscillator = slot.envelfos['sfz-pitch-lfo']
    for at in [
        Fraction(0),
        Fraction(1, 20),
        Fraction(1, 5),
        Fraction(3, 8),
        Fraction(1),
    ]:
        if isinstance(oscillator, envelfo.Patch):
            value = patch.advance_patch(
                oscillator,
                patch.initial_patch(oscillator, Fraction(0)),
                at,
                next_delivery=at + 1,
            ).values['signal']
        else:
            value = envelfo_at(
                oscillator, initial_envelfo(oscillator, Fraction(0)), at
            ).value
        age = max(0, float(at) - delay)
        gate = 0 if float(at) < delay else min(1, age / fade) if fade else 1
        triangle = (1 - 4 * abs((2 * age + 0.25) % 1 - 0.5)) * gate
        observed = modulation.evaluate(
            slot.modulation,
            {
                s.name: modulation.SourceValue(
                    value=value if s.name == 'pitch-lfo' else 0.5
                )
                for s in slot.modulation.sources
            },
        )
        assert next(
            v.value for v in observed if v.target.parameter == 'tuning_cents'
        ) == pytest.approx(17 + 50 + depth * triangle)


@pytest.mark.parametrize(
    'extra',
    [
        'pitchlfo_delay=-1',
        'pitchlfo_fade=101',
        'pitchlfo_freq=21',
        'pitchlfo_depth=1201',
        'trigger=release',
    ],
)
def test_unverified_pitch_lfo_is_diagnosed_without_generator(extra: str) -> None:
    result = compile_modulation('pitchlfo_freq=2 pitchlfo_depth=100 ' + extra)
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}
    assert any(f.location.opcode.startswith('pitchlfo_') for f in result.unimplemented)


def test_pitch_lfo_requires_explicit_convention() -> None:
    result = compile_modulation('pitchlfo_freq=2 pitchlfo_depth=100', pitch='diagnose')
    assert not result.complete
    assert 'pitch_lfo_response' in result.unimplemented[0].reason
