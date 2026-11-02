from fractions import Fraction
from typing import Literal

import pytest
from envelfo import patch
from envelfo.runtime import envelfo_at, initial_envelfo
from ufor import envelfo, modulation
from ufor.interface import ScoreReference
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, parser
from safaz.model import SfzCompileResult, SfzMidiBindingRequest


def compile_modulation(
    text: str,
    pitch: Literal['diagnose', 'sfizz_parabolic'] = 'sfizz_parabolic',
    amplitude: Literal['diagnose', 'sfizz_parabolic'] = 'sfizz_parabolic',
    midi: bool = False,
    bend: Literal['diagnose', 'sfizz_symmetric'] = 'sfizz_symmetric',
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
        amplitude_lfo_response=amplitude,
        pitch_bend_response=bend,
        midi_binding=SfzMidiBindingRequest(
            instrument=ScoreReference(path='instrument.toml'),
            part='main',
            repeated_key_release='oldest',
        )
        if midi
        else None,
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
        x = 2 * ((2 * age) % 1) - 1
        signal = -4 * x * (1 - abs(x)) * gate
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
        ) == pytest.approx(17 + 50 + depth * signal)


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


@pytest.mark.parametrize('depth', [-10, -6, 6, 10])
def test_amplitude_lfo_fades_decibels_before_gain_conversion(depth: float) -> None:
    result = compile_modulation(f'amplfo_freq=2 amplfo_depth={depth} amplfo_fade=0.5')
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    oscillator = slot.envelfos['sfz-amplitude-lfo']
    at = Fraction(1, 16)
    signal = patch.advance_patch(
        oscillator,
        patch.initial_patch(oscillator, Fraction(0)),
        at,
        next_delivery=at + 1,
    ).values['signal']
    assert signal == 0.75 / 8
    observed = modulation.evaluate(
        slot.modulation,
        {
            s.name: modulation.SourceValue(
                value=signal if s.name == 'amplitude-lfo' else 0.5
            )
            for s in slot.modulation.sources
        },
    )
    velocity = modulation.map_value(
        next(r for r in slot.modulation.routes if r.source == 'velocity'), 0.5
    )
    assert next(
        v.value for v in observed if v.target.parameter == 'amplitude'
    ) == pytest.approx(velocity * 10 ** (depth * 0.75 / 8 / 20))


@pytest.mark.parametrize(
    'extra', ['amplfo_depth=11', 'amplfo_delay=-1', 'amplfo_freq=21', 'trigger=release']
)
def test_unverified_amplitude_lfo_remains_diagnosed(extra: str) -> None:
    result = compile_modulation('amplfo_freq=2 amplfo_depth=6 ' + extra)
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}


def test_amplitude_lfo_requires_its_own_convention() -> None:
    result = compile_modulation('amplfo_freq=2 amplfo_depth=6', amplitude='diagnose')
    assert not result.complete
    assert 'amplitude_lfo_response' in result.unimplemented[0].reason


@pytest.mark.parametrize('up,down', [(200, -200), (1200, -300), (-100, 500), (0, 0)])
def test_pitch_bend_preserves_asymmetric_endpoints_and_center(
    up: int, down: int
) -> None:
    result = compile_modulation(
        f'bend_up={up} bend_down={down} tune=17 pitch_veltrack=100', midi=True
    )
    assert result.complete
    assert result.instrument is not None and result.binding is not None
    assert result.binding.body.midi[0].pitch_bend.control == 'pitch-bend'
    slot = result.instrument.body.slots[0]
    assert next(b for b in slot.bindings if b.name == 'pitch-bend').smoothing == 0
    for bend in [-1, -0.5, 0, 0.5, 1]:
        observed = modulation.evaluate(
            slot.modulation,
            {
                s.name: modulation.SourceValue(
                    value=bend if s.name == 'pitch-bend' else 0.5
                )
                for s in slot.modulation.sources
            },
        )
        assert next(
            v.value for v in observed if v.target.parameter == 'tuning_cents'
        ) == pytest.approx(
            67 + (bend * up if bend >= 0 else min(1, -bend * 8192 / 8191) * down)
        )


@pytest.mark.parametrize(
    'declaration,midi',
    [
        ('bend_up=201', False),
        ('bend_up=12001', True),
        ('bend_smooth=10', True),
        ('bend_step=100', True),
        ('bend_down=-200 trigger=release', True),
    ],
)
def test_unverified_pitch_bend_has_located_diagnostics_and_no_route(
    declaration: str, midi: bool
) -> None:
    result = compile_modulation(declaration, midi=midi)
    assert not result.complete
    assert result.instrument is not None
    assert not any(
        b.name == 'pitch-bend' for b in result.instrument.body.slots[0].bindings
    )
    assert any(f.location.opcode.startswith('bend_') for f in result.unimplemented)


def test_pitch_bend_rejects_mixed_channel_ranges() -> None:
    result = compile_modulation(
        'lochan=1 hichan=1 bend_up=200 <region> sample=a.wav key=60 '
        'loop_mode=one_shot lochan=2 hichan=2 bend_up=200',
        midi=True,
    )
    assert not result.complete
    assert result.binding is None
    assert result.instrument is not None
    assert all(
        not any(b.name == 'pitch-bend' for b in s.bindings)
        for s in result.instrument.body.slots
    )


def test_pitch_bend_convention_is_explicit_even_with_midi_binding() -> None:
    result = compile_modulation('bend_up=200', midi=True, bend='diagnose')
    assert not result.complete
    assert 'sfizz_symmetric' in result.unimplemented[0].reason
