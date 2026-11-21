from fractions import Fraction
from typing import Literal

import pytest
from envelfo.runtime import envelfo_at, envelfo_event, initial_envelfo
from ufor.approach import ExponentialApproach
from ufor.envelfo import EnvelfoEvent, Envelope
from ufor.samples.instrument import SampleInstrumentScore
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, exporter, parser
from safaz.model import SfzCompileResult


@pytest.mark.parametrize('depth', [-1200, 1200])
def test_filter_envelope_preserves_signed_cutoff_and_combined_bounds(
    depth: int,
) -> None:
    result = compile_filter(f'fileg_depth={depth} fileg_attack=0.5')
    assert result.complete and result.instrument is not None
    slot = result.instrument.body.slots[0]
    route = next(r for r in slot.modulation.routes if r.source == 'filter-envelope')
    assert route.points[0].amount == 1
    assert route.points[1].amount == 2 ** (depth / 1200)
    parameter = next(
        p for p in slot.modulation.parameters if p.target.parameter == 'cutoff_hz'
    )
    assert parameter.minimum == 1000 * min(1, 2 ** (depth / 1200))
    assert parameter.maximum == 1000 * max(1, 2 ** (depth / 1200))
    assert isinstance(slot.envelfos['sfz-filter-envelope'], Envelope)


def test_delay_start_attack_and_zero_release_follow_explicit_convention() -> None:
    result = compile_filter(
        'fileg_depth=1200 fileg_delay=0.1 fileg_start=20 fileg_attack=0.5 '
        'fileg_hold=0.1 fileg_decay=0.3 fileg_sustain=50 fileg_release=0'
    )
    assert result.complete and result.instrument is not None
    body = result.instrument.body.slots[0].envelfos['sfz-filter-envelope']
    assert isinstance(body, Envelope)
    state = envelfo_event(
        body,
        initial_envelfo(body, Fraction(0)),
        EnvelfoEvent(at=Fraction(0), ordinal=0, action='note_on'),
    )
    for at, expected in [
        (Fraction(1, 20), 0.2),
        (Fraction(1, 4), 0.5),
        (Fraction(1, 2), 1.0),
        (Fraction(7, 10), 0.5),
    ]:
        assert envelfo_at(body, state, at).value == pytest.approx(expected)
    released = envelfo_event(
        body, state, EnvelfoEvent(at=Fraction(1, 4), ordinal=1, action='note_off')
    )
    assert envelfo_at(body, released, Fraction(11, 40)).value == pytest.approx(0.25)
    assert envelfo_at(body, released, Fraction(3, 10)).value == 0
    assert isinstance(body.release[0], ExponentialApproach)
    assert body.release[0].time_constant == 0


def test_positive_times_use_minimum_rate_and_zero_sustain_runs_freely() -> None:
    result = compile_filter(
        'fileg_depth=1200 fileg_decay=0.001 fileg_release=0.001 fileg_sustain=0'
    )
    assert result.complete and result.instrument is not None
    body = result.instrument.body.slots[0].envelfos['sfz-filter-envelope']
    assert isinstance(body, Envelope) and not body.hold
    assert body.segments[3].time_constant == pytest.approx(0.006 / 9)
    state = envelfo_event(
        body,
        initial_envelfo(body, Fraction(0)),
        EnvelfoEvent(at=Fraction(0), ordinal=0, action='note_on'),
    )
    observed = envelfo_at(body, state, Fraction(1))
    assert observed.status == 'complete' and observed.value == 0


def test_combined_modulation_diagnoses_every_route_and_keeps_static_filter() -> None:
    result = compile_filter(
        'cutoff=2000 key=61 fil_keytrack=1200 fil_veltrack=1200 '
        'fillfo_freq=2 fillfo_depth=1200 fileg_depth=1200'
    )
    assert not result.complete and result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.processing.filters[0].cutoff_hz == 2000
    assert not any(r.target.parameter == 'cutoff_hz' for r in slot.modulation.routes)
    assert slot.envelfos == {}
    assert {f.location.opcode for f in result.unimplemented} == {
        'fil_keytrack',
        'fil_veltrack',
        'fillfo_depth',
        'fileg_depth',
    }


@pytest.mark.parametrize(
    'extra',
    ['fileg_attack=-1', 'fileg_sustain=101', 'fileg_depth=12001', 'trigger=release'],
)
def test_unverified_filter_envelope_is_diagnosed(extra: str) -> None:
    result = compile_filter('fileg_depth=1200 ' + extra)
    assert not result.complete and result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}


def test_filter_envelope_requires_explicit_choice_and_imported_filter() -> None:
    result = compile_filter('fileg_depth=1200', response='diagnose')
    assert not result.complete
    assert 'filter_envelope_response' in result.unimplemented[0].reason
    missing = compile_filter('cutoff=0 fileg_depth=1200')
    assert not missing.complete and missing.instrument is not None
    assert missing.instrument.body.slots[0].envelfos == {}


@pytest.mark.parametrize(
    ('rate', 'opcodes'),
    [
        (
            44100,
            'fileg_depth=-821.3 fileg_delay=0.000025 fileg_hold=0.00005 '
            'fileg_start=33.3333 fileg_attack=0.4 fileg_decay=0.3 '
            'fileg_sustain=31.37 fileg_release=0 cutoff2=1234 resonance=6.17',
        ),
        (
            48000,
            'fileg_depth=1200 fileg_decay=0.001 fileg_release=0.001 fileg_sustain=0.32',
        ),
        (
            48000,
            'fileg_depth=-1200 fileg_start=100 fileg_attack=1 '
            'fileg_decay=0 fileg_sustain=0',
        ),
        (96000, 'fileg_depth=1200 fileg_sustain=100 fileg_decay=0.3'),
    ],
)
def test_filter_envelope_exports_and_reimports_the_same_shape(
    rate: int, opcodes: str
) -> None:
    original = compile_filter(opcodes, rate=rate)
    assert original.complete and original.instrument is not None
    exported = exporter.write(original.instrument)
    assert exported.complete, exported.unimplemented
    restored = compile_filter(exported.contents, rate=rate, document=True)
    assert restored.complete and restored.instrument is not None
    before, after = original.instrument.body.slots[0], restored.instrument.body.slots[0]
    assert after.processing == before.processing
    assert after.envelfos == before.envelfos
    assert after.modulation == before.modulation
    assert after.bindings == before.bindings


@pytest.mark.parametrize('change', ['cutoff', 'stages', 'envelope', 'combined'])
def test_filter_export_diagnoses_unsupported_shapes(change: str) -> None:
    extra = ' fil_keytrack=100 fil_keycenter=61' if change == 'combined' else ''
    result = compile_filter('fileg_depth=1200 fileg_release=0.1' + extra)
    assert result.complete and result.instrument is not None
    raw = result.instrument.model_dump(mode='json')
    slot = raw['body']['slots'][0]
    if change == 'cutoff':
        slot['processing']['filters'][0]['cutoff_hz'] = 21000
        slot.update(modulation={}, bindings=[], envelfos={})
    elif change == 'stages':
        slot['processing']['filters'][0]['stages'] = 2
    elif change == 'envelope':
        slot['envelfos']['sfz-filter-envelope']['release'][0]['transition_seconds'] = (
            0.1
        )
    exported = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not exported.complete
    assert 'fileg_depth=' not in exported.contents
    if change in ('cutoff', 'stages'):
        assert 'cutoff=' not in exported.contents
        assert any(
            i.location.path == 'body.slots[0].processing.filters[0]'
            for i in exported.unimplemented
        )
    else:
        assert 'cutoff=1000' in exported.contents
        assert any(
            i.location.path == 'body.slots[0].envelfos.sfz-filter-envelope'
            for i in exported.unimplemented
        )


def compile_filter(
    text: str,
    response: Literal['diagnose', 'portable_exponential'] = 'portable_exponential',
    *,
    rate: int = 48000,
    document: bool = False,
) -> SfzCompileResult:
    return compiler.compile_instrument(
        parser.parse(
            text
            if document
            else '<region> sample=a.wav loop_mode=no_loop key=60 cutoff=1000 ' + text
        ),
        name='test',
        title='Test',
        assets={
            'a.wav': AudioMetadata(
                channels=1,
                sample_rate=48000,
                frames=96000,
                encoding='WAV/PCM_16',
                byte_length=192044,
                sha256='0' * 64,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=rate)),
        output_channels=['left', 'right'],
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
        filter_envelope_response=response,
    )
