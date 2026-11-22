import json
from fractions import Fraction
from math import log, sin, sinh, tau
from pathlib import Path
from typing import Literal

import pytest
from envelfo import patch
from envelfo.runtime import envelfo_at, initial_envelfo
from pytest_regressions.data_regression import DataRegressionFixture
from ufor import modulation
from ufor.envelfo import Patch
from ufor.samples import processing
from ufor.samples.instrument import SampleInstrumentScore
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, exporter, parser, registry
from safaz.model import SfzCompileResult, SfzLocation
from safaz.modulators import FilterLfoResponse


@pytest.mark.parametrize('rate', [44100, 48000, 96000])
def test_static_equalizer_uses_digital_bandwidth_and_round_trips(rate: int) -> None:
    original = _compile(
        '<global> eq1_gain=-12 eq2_bw=1.5 eq2_gain=6 '
        '<region> sample=audio/glass.wav eq1_bw=0.5 eq2_freq=2500 '
        'eq3_freq=5500 eq3_gain=9',
        eq_response='sfizz_rbj',
        rate=rate,
    )
    assert original.complete and original.instrument is not None
    settings = original.instrument.body.slots[0].processing
    assert settings.filter_order == processing.FilterOrder.after_amplitude
    for band, frequency, gain, width in zip(
        settings.equalizer, [50, 2500, 5500], [-12, 6, 9], [0.5, 1.5, 1], strict=True
    ):
        omega = tau * frequency / rate
        assert band.frequency_hz == frequency
        assert band.gain_db == gain
        assert band.resonance == pytest.approx(
            1 / (2 * sinh(0.5 * log(2) * width * omega / sin(omega)))
        )
    exported = exporter.write(original.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, eq_response='sfizz_rbj', rate=rate)
    assert restored.complete and restored.instrument is not None
    assert restored.instrument.body.slots[0].processing == settings


@pytest.mark.parametrize(
    ('settings', 'response', 'message'),
    [
        ('eq1_gain=4', 'diagnose', 'eq_response'),
        ('eq1_gain=4 eq1_type=lshelf', 'sfizz_rbj', 'peaking-band'),
        ('eq1_gain=4 eq1_bw=0', 'sfizz_rbj', 'bandwidth'),
        ('eq1_freq=1500 eq2_gain=4', 'sfizz_rbj', 'frequency'),
        ('eq4_gain=4', 'sfizz_rbj', 'bands 1 to 3'),
    ],
)
def test_unverified_eq_retains_located_diagnostics(
    settings: str, response: Literal['diagnose', 'sfizz_rbj'], message: str
) -> None:
    result = _compile(
        f'<global> {settings}\n<region> sample=audio/glass.wav',
        eq_response=response,
    )
    assert result.instrument is not None and not result.complete
    assert not result.instrument.body.slots[0].processing.equalizer
    assert all(
        i.location.line == 1 and message in i.reason for i in result.unimplemented
    )


@pytest.mark.parametrize(
    ('filter_type', 'response'),
    [
        ('lpf_2p', processing.FilterResponse.lowpass),
        ('hpf_2p', processing.FilterResponse.highpass),
        ('bpf_2p', processing.FilterResponse.bandpass),
        ('brf_2p', processing.FilterResponse.notch),
    ],
)
@pytest.mark.parametrize(('resonance', 'q'), [(0, 1), (20, 10), (40, 100)])
def test_static_filters_preserve_response_cutoff_and_resonance(
    filter_type: str, response: processing.FilterResponse, resonance: int, q: int
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav fil_type={filter_type} '
        f'cutoff=2000 resonance={resonance}',
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    assert (
        result.instrument.body.slots[0].processing.filter_order
        == processing.FilterOrder.after_amplitude
    )
    assert result.instrument.body.slots[0].processing.filters == [
        processing.ResonantFilter(
            name='sfz-filter-1', response=response, cutoff_hz=2000, q=q
        )
    ]
    exported = exporter.write(result.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    assert (
        restored.instrument.body.slots[0].processing
        == result.instrument.body.slots[0].processing
    )


def test_filter_import_requires_explicit_response_acceptance() -> None:
    result = _compile('<region> sample=audio/glass.wav cutoff=1000')
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert len(result.unimplemented) == 1
    assert result.unimplemented[0].location == SfzLocation(
        header='region', opcode='cutoff', line=1, column=33
    )
    assert 'filter_response="sfizz_rbj"' in result.unimplemented[0].reason


def test_filter_conformance_preserves_inheritance_and_serial_order() -> None:
    result = _compile(
        Path('conformance/filters.sfz').read_text(), filter_response='sfizz_rbj'
    )
    assert result.complete
    assert result.instrument is not None
    assert all(
        s.processing.filter_order == processing.FilterOrder.after_amplitude
        for s in result.instrument.body.slots
    )
    expected = json.loads(Path('conformance/filters.json').read_text())
    assert [
        [f.model_dump(mode='json') for f in s.processing.filters]
        for s in result.instrument.body.slots
    ] == expected
    exported = exporter.write(result.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    assert [s.processing for s in restored.instrument.body.slots] == [
        s.processing for s in result.instrument.body.slots
    ]


def test_export_flattens_shared_filter_after_the_region_filter() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav fil_type=hpf_2p cutoff=200 '
        'fil2_type=brf_2p cutoff2=1000 resonance2=7',
        filter_response='sfizz_rbj',
    )
    assert result.complete and result.instrument is not None
    raw = result.instrument.model_dump(mode='json')
    local = raw['body']['slots'][0]['processing']['filters']
    raw['body']['settings']['processing'].update(
        filters=[local.pop()], filter_order='after_amplitude'
    )
    exported = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    assert (
        restored.instrument.body.slots[0].processing.filters
        == result.instrument.body.slots[0].processing.filters
    )


def test_second_filter_retains_settings_with_implicit_first_filter_diagnosed() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff2=1000', filter_response='sfizz_rbj'
    )
    assert not result.complete
    assert result.instrument is not None
    assert any(
        'filter 1 has no explicit cutoff' in f.reason for f in result.unimplemented
    )
    assert result.instrument.body.slots[0].processing.filters == [
        processing.ResonantFilter(
            name='sfz-filter-2',
            response=processing.FilterResponse.lowpass,
            cutoff_hz=1000,
            q=1,
        )
    ]


def test_declared_filter_without_cutoff_remains_diagnosed() -> None:
    result = _compile('<region> sample=audio/glass.wav fil_type=hpf_2p resonance=20')
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert 'player initialization differs' in result.unimplemented[0].reason


@pytest.mark.parametrize('cutoff', [0, 0.5, 20_001, 24_000])
def test_unverified_cutoff_boundaries_are_diagnosed_without_clamping(
    cutoff: float,
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff={cutoff}',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert len(result.unimplemented) == 1
    assert result.unimplemented[0].location.opcode == 'cutoff'


@pytest.mark.parametrize('cutoff', [1, 20_000])
def test_verified_cutoff_endpoints_import_without_clamping(cutoff: int) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff={cutoff}',
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters[0].cutoff_hz == cutoff


@pytest.mark.parametrize(('cutoff', 'imported'), [(7992, True), (7993, False)])
def test_cutoff_bounds_follow_output_rate_instead_of_asset_rate(
    cutoff: int, imported: bool
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff={cutoff}',
        filter_response='sfizz_rbj',
        rate=16_000,
    )
    assert result.complete == imported
    assert result.instrument is not None
    assert len(result.instrument.body.slots[0].processing.filters) == int(imported)


@pytest.mark.parametrize('filter_type', ['lpf_1p', 'lpf_4p', 'lpf_2p_sv', 'unknown'])
def test_unsupported_filter_type_does_not_replace_a_supported_serial_filter(
    filter_type: str,
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav fil_type={filter_type} cutoff=1000 '
        'fil2_type=hpf_2p cutoff2=250',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert [f.name for f in result.instrument.body.slots[0].processing.filters] == [
        'sfz-filter-2'
    ]
    assert len(result.unimplemented) == 1
    assert any(f.location.opcode == 'fil_type' for f in result.unimplemented)


@pytest.mark.parametrize('opcode', ['cutoff_oncc1', 'fil_random', 'fileg_depth'])
def test_unsupported_modulation_retains_only_the_static_filter(opcode: str) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff=1000 {opcode}=1200',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert len(result.instrument.body.slots[0].processing.filters) == 1
    assert len(result.unimplemented) == 1
    assert any(f.location.opcode == opcode for f in result.unimplemented)


@pytest.mark.parametrize(
    'opcodes',
    [
        'cutoff=-1',
        'cutoff=nan',
        'cutoff=inf',
        'resonance=-1',
        'resonance=41',
        'resonance=nan',
        'resonance2=inf',
        'cutoff2=oops',
    ],
)
def test_malformed_filter_values_fail_explicitly(opcodes: str) -> None:
    with pytest.raises(ValueError, match='cutoff|resonance'):
        _compile(f'<region> sample=audio/glass.wav {opcodes}')


@pytest.mark.parametrize(
    'opcode',
    [
        'fil_type',
        'cutoff',
        'resonance',
        'fil2_type',
        'cutoff2',
        'resonance2',
        'fil_keytrack',
        'fil_keycenter',
        'fil2_keytrack',
        'fil2_keycenter',
    ],
)
def test_static_filter_catalog_requires_explicit_player_semantics(opcode: str) -> None:
    assert registry.opcode_support(opcode)[0] == registry.Support.ambiguous


def test_filter_key_tracking_conformance_preserves_inheritance_and_shared_key(
    data_regression: DataRegressionFixture,
) -> None:
    result = _compile(
        Path('conformance/filter-key-tracking.sfz').read_text(),
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    rows = []
    for slot in result.instrument.body.slots:
        assert [b.name for b in slot.bindings if b.kind == 'key'] == ['key']
        for key in range(slot.mapping.lowest_key, slot.mapping.highest_key + 1):
            evaluated = {
                v.target.name: v.value
                for v in modulation.evaluate(
                    slot.modulation,
                    {
                        s.name: modulation.SourceValue(
                            value=key if s.name == 'key' else 1
                        )
                        for s in slot.modulation.sources
                    },
                )
                if v.target.parameter == 'cutoff_hz'
            }
            rows.append(
                {
                    'slot': slot.name,
                    'key': key,
                    'cutoff_hz': {
                        f.name: evaluated.get(f'filter-{f.name}', f.cutoff_hz)
                        for f in slot.processing.filters
                    },
                }
            )
    data_regression.check(rows)
    exported = exporter.write(result.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    assert [s.modulation for s in restored.instrument.body.slots] == [
        s.modulation for s in result.instrument.body.slots
    ]


@pytest.mark.parametrize('index', [1, 2])
@pytest.mark.parametrize(
    ('tracking', 'ratio'), [(0, 1), (100, 2 ** (1 / 12)), (1200, 2)]
)
def test_filter_key_tracking_uses_default_center_and_exact_note_ratio(
    index: int,
    tracking: int,
    ratio: float,
) -> None:
    prefix = 'fil' if index == 1 else 'fil2'
    result = _compile(
        f'<region> sample=audio/glass.wav key=61 cutoff=1000 cutoff2=1000 '
        f'{prefix}_keytrack={tracking}',
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    parameters = modulation.evaluate(
        slot.modulation,
        {
            s.name: modulation.SourceValue(value=61 if s.name == 'key' else 1)
            for s in slot.modulation.sources
        },
    )
    cutoffs = {
        v.target.name: v.value for v in parameters if v.target.parameter == 'cutoff_hz'
    }
    assert cutoffs.get(f'filter-sfz-filter-{index}', 1000) == 1000 * ratio


@pytest.mark.parametrize(
    ('keys', 'cutoff', 'rate', 'supported'),
    [
        ('key=61', 4000, 48_000, True),
        ('key=61', 4000, 16_000, False),
        ('lokey=59 hikey=61', 10_000, 48_000, True),
        ('lokey=59 hikey=62', 10_000, 48_000, False),
        ('key=60', 1, 48_000, True),
        ('lokey=59 hikey=60', 1, 48_000, False),
    ],
)
def test_tracked_cutoff_checks_only_playable_keys_at_output_rate(
    keys: str,
    cutoff: int,
    rate: int,
    supported: bool,
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav {keys} cutoff={cutoff} fil_keytrack=1200',
        filter_response='sfizz_rbj',
        rate=rate,
    )
    assert result.complete == supported
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.processing.filters[0].cutoff_hz == cutoff
    assert (
        any(r.target.parameter == 'cutoff_hz' for r in slot.modulation.routes)
        == supported
    )
    if not supported:
        issue = result.unimplemented[0]
        assert issue.location.opcode == 'fil_keytrack'
        assert 'playable key' in issue.reason
        assert len(result.unimplemented) == 1


@pytest.mark.parametrize('tracking', [-100, 1201])
def test_unverified_filter_key_tracking_retains_static_filter(tracking: int) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav key=60 cutoff=1000 fil_keytrack={tracking}',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters[0].cutoff_hz == 1000
    assert len(result.unimplemented) == 1
    assert '0-1200' in result.unimplemented[0].reason


@pytest.mark.parametrize(
    'opcodes',
    [
        'fil_keytrack=nan',
        'fil2_keytrack=1.5',
        'fil_keycenter=128',
        'fil2_keycenter=oops',
    ],
)
def test_malformed_filter_key_tracking_fails_explicitly(opcodes: str) -> None:
    with pytest.raises(ValueError, match='fil.*key'):
        _compile(f'<region> sample=audio/glass.wav {opcodes}')


def test_filter_key_tracking_requires_imported_static_response() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=60 cutoff=1000 fil_keytrack=100'
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert not any(
        r.target.parameter == 'cutoff_hz'
        for r in result.instrument.body.slots[0].modulation.routes
    )
    assert 'filter_response' in result.unimplemented[0].reason


def test_unsupported_tracking_keeps_other_filter_and_preprocessed_location() -> None:
    result = _compile(
        '#define $BAD -100\n<global> fil_keytrack=$BAD\n'
        '<region> sample=audio/glass.wav key=61 cutoff=1000 cutoff2=1000 '
        'fil2_keytrack=100',
        filter_response='sfizz_rbj',
    )
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert len(slot.processing.filters) == 2
    assert len(result.unimplemented) == 1
    assert result.unimplemented[0].location == SfzLocation(
        header='global',
        opcode='fil_keytrack',
        line=2,
        column=10,
    )
    assert [
        r.target.name
        for r in slot.modulation.routes
        if r.target.parameter == 'cutoff_hz'
    ] == ['filter-sfz-filter-2']


@pytest.mark.parametrize('prefix', ['fil', 'fil2'])
def test_tracking_without_explicit_cutoff_remains_diagnosed(prefix: str) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav key=60 {prefix}_keytrack=100',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert any('no explicit cutoff' in f.reason for f in result.unimplemented)


def test_controller_filter_tracking_is_diagnosed_without_note_binding() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=-1 loop_mode=one_shot '
        'pitch_keytrack=0 amp_veltrack=0 on_locc1=1 on_hicc1=127 '
        'cutoff=1000 fil_keytrack=100',
        filter_response='sfizz_rbj',
    )
    assert result.instrument is not None
    assert not result.complete
    slot = result.instrument.body.slots[0]
    assert slot.processing.filters[0].cutoff_hz == 1000
    assert not any(b.kind == 'key' for b in slot.bindings)
    assert any(
        f.location.opcode == 'fil_keytrack' and 'note key' in f.reason
        for f in result.unimplemented
    )


@pytest.mark.parametrize('depth', [-9600, -1200, 0, 1200, 9600])
@pytest.mark.parametrize('velocity', [0, 0.137, 0.5, 1])
def test_filter_velocity_tracks_continuously_in_both_directions(
    depth: int, velocity: float
) -> None:
    base = 256 if depth == -9600 else 64
    result = _compile(
        f'<region> sample=audio/glass.wav key=60 cutoff={base} fil_veltrack={depth}',
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    values = {
        s.name: modulation.SourceValue(value=velocity if s.name == 'velocity' else 60)
        for s in slot.modulation.sources
    }
    observed = modulation.evaluate(slot.modulation, values)
    cutoff = next(
        (v.value for v in observed if v.target.parameter == 'cutoff_hz'), base
    )
    assert cutoff == pytest.approx(base * 2 ** (depth * velocity / 1200))
    assert sum(b.kind == 'velocity' for b in slot.bindings) == 1
    tracked = [r for r in slot.modulation.routes if r.target.parameter == 'cutoff_hz']
    assert len(tracked) == (depth != 0)
    if tracked:
        assert tracked[0].interpolation == modulation.Interpolation.exponential


@pytest.mark.parametrize(('first', 'second'), [(-9600, 9600), (713, -487), (0, -1200)])
def test_filter_velocity_export_recreates_both_cutoff_routes(
    first: int, second: int
) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=60 cutoff=320 cutoff2=32 '
        f'fil_veltrack={first} fil2_veltrack={second}',
        filter_response='sfizz_rbj',
        rate=44100,
    )
    assert result.complete and result.instrument is not None
    exported = exporter.write(result.instrument)
    assert exported.complete, exported.unimplemented
    assert 'fil2_veltrack=' + str(second) in exported.contents
    if first:
        assert 'fil_veltrack=' + str(first) in exported.contents
    else:
        assert 'fil_veltrack=' not in exported.contents
    restored = _compile(exported.contents, filter_response='sfizz_rbj', rate=44100)
    assert restored.complete and restored.instrument is not None
    before, after = result.instrument.body.slots[0], restored.instrument.body.slots[0]
    assert after.processing == before.processing
    assert after.modulation == before.modulation
    assert after.bindings == before.bindings


@pytest.mark.parametrize(
    'tracking',
    [
        'key=60 fil_keytrack=100 fil_keycenter=60 fil2_keytrack=77 fil2_keycenter=59',
        'lokey=59 hikey=62 fil_keytrack=713 fil_keycenter=66 fil2_keytrack=1200',
    ],
)
def test_filter_export_round_trips_key_and_velocity_tracking(tracking: str) -> None:
    original = _compile(
        '<region> sample=audio/glass.wav cutoff=800 cutoff2=640 '
        f'fil_veltrack=933 fil2_veltrack=-1200 {tracking}',
        filter_response='sfizz_rbj',
    )
    assert original.complete and original.instrument is not None
    exported = exporter.write(original.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    before, after = original.instrument.body.slots[0], restored.instrument.body.slots[0]
    assert after.processing == before.processing
    assert after.modulation == before.modulation
    assert after.bindings == before.bindings


@pytest.mark.parametrize('rate', [44100, 48000])
def test_filter_lfo_export_round_trips_with_key_and_velocity_tracking(
    rate: int,
) -> None:
    original = _compile(
        '<region> sample=audio/glass.wav lokey=60 hikey=62 cutoff=1000 '
        'fil_keytrack=100 fil_veltrack=-713 fillfo_freq=2.331 '
        'fillfo_depth=-783.4 fillfo_delay=0.00005 fillfo_fade=0.234',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
        rate=rate,
    )
    assert original.complete and original.instrument is not None
    exported = exporter.write(original.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(
        exported.contents,
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
        rate=rate,
    )
    assert restored.complete and restored.instrument is not None
    before, after = original.instrument.body.slots[0], restored.instrument.body.slots[0]
    assert after.processing == before.processing
    assert after.modulation == before.modulation
    assert after.bindings == before.bindings
    assert after.envelfos == before.envelfos


@pytest.mark.parametrize('trigger', ['release', 'release_key'])
def test_release_region_filter_keyboard_tracking_round_trips(trigger: str) -> None:
    original = _compile(
        f'<region> sample=audio/glass.wav lokey=60 hikey=65 trigger={trigger} '
        'cutoff=1000 fil_keytrack=100 fil_keycenter=61',
        filter_response='sfizz_rbj',
    )
    assert original.complete and original.instrument is not None
    exported = exporter.write(original.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(exported.contents, filter_response='sfizz_rbj')
    assert restored.complete and restored.instrument is not None
    assert restored.instrument.body.slots[0] == original.instrument.body.slots[0]


@pytest.mark.parametrize('change', ['fractional', 'linear', 'bounds'])
def test_filter_velocity_export_diagnoses_unrepresentable_routes(change: str) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=60 cutoff=1000 fil_veltrack=1200 '
        'cutoff2=500 fil2_veltrack=-1200',
        filter_response='sfizz_rbj',
    )
    assert result.complete and result.instrument is not None
    raw = result.instrument.model_dump(mode='json')
    routing = raw['body']['slots'][0]['modulation']
    first_route = next(
        r
        for r in routing['routes']
        if r['source'] == 'velocity' and r['target']['name'] == 'filter-sfz-filter-1'
    )
    if change == 'fractional':
        ratio = 2 ** (1200.5 / 1200)
        first_route['points'][1]['amount'] = ratio
        parameter = next(
            p for p in routing['parameters'] if p['target'] == first_route['target']
        )
        parameter['maximum'] = 1000 * ratio
    elif change == 'linear':
        first_route['interpolation'] = 'linear'
    else:
        parameter = next(
            p for p in routing['parameters'] if p['target'] == first_route['target']
        )
        parameter['maximum'] *= 1.1
    exported = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not exported.complete
    assert 'fil_veltrack=' not in exported.contents
    assert 'cutoff=1000' in exported.contents
    assert 'fil2_veltrack=-1200' in exported.contents
    index = routing['routes'].index(first_route)
    assert any(
        i.location.path == f'body.slots[0].modulation.routes[{index}]'
        for i in exported.unimplemented
    )


def test_filter_velocity_conformance_preserves_inheritance_and_combined_cutoffs(
    data_regression: DataRegressionFixture,
) -> None:
    result = _compile(
        Path('conformance/filter-velocity-tracking.sfz').read_text(),
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    observed = []
    for slot in result.instrument.body.slots:
        for key in range(slot.mapping.lowest_key, slot.mapping.highest_key + 1):
            for velocity in (0, 0.5, 1):
                values = {
                    s.name: modulation.SourceValue(
                        value=key if s.name == 'key' else velocity
                    )
                    for s in slot.modulation.sources
                }
                cutoffs = {
                    v.target.name: round(v.value, 8)
                    for v in modulation.evaluate(slot.modulation, values)
                    if v.target.parameter == 'cutoff_hz'
                }
                observed.append(
                    {
                        'slot': slot.name,
                        'key': key,
                        'velocity': velocity,
                        'cutoffs': cutoffs,
                    }
                )
        assert sum(b.kind == 'velocity' for b in slot.bindings) == 1
    data_regression.check(observed)


@pytest.mark.parametrize('cutoff,depth,key', [(6000, 1200, 61), (2, -1200, 59)])
def test_combined_tracking_outside_bounds_diagnoses_both_and_retains_static(
    cutoff: int,
    depth: int,
    key: int,
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav key={key} cutoff={cutoff} '
        f'fil_keytrack=1200 fil_veltrack={depth}',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.processing.filters[0].cutoff_hz == cutoff
    assert not any(r.target.parameter == 'cutoff_hz' for r in slot.modulation.routes)
    assert {f.location.opcode for f in result.unimplemented} == {
        'fil_keytrack',
        'fil_veltrack',
    }
    assert all('Combined' in f.reason for f in result.unimplemented)


@pytest.mark.parametrize(
    'declaration',
    [
        'fil_veltrack=9601',
        'fil_veltrack=-9601',
        'fil_veltrack=1200 trigger=release',
        'fil_veltrack=1200 trigger=release_key',
    ],
)
def test_unverified_velocity_tracking_retains_valid_keyboard_tracking(
    declaration: str,
) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=60 cutoff=1000 fil_keytrack=100 '
        + declaration,
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    tracked = [
        r
        for r in result.instrument.body.slots[0].modulation.routes
        if r.target.parameter == 'cutoff_hz'
    ]
    assert [r.source for r in tracked] == ['key']
    assert any(f.location.opcode == 'fil_veltrack' for f in result.unimplemented)


@pytest.mark.parametrize('prefix', ['fil', 'fil2'])
def test_malformed_filter_velocity_fails_explicitly(prefix: str) -> None:
    with pytest.raises(ValueError, match=f'{prefix}_veltrack must be an integer'):
        _compile(
            f'<region> sample=audio/glass.wav {prefix}_veltrack=1.5',
            filter_response='sfizz_rbj',
        )


def test_controller_filter_velocity_remains_diagnosed() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=-1 loop_mode=one_shot '
        'pitch_keytrack=0 amp_veltrack=0 on_locc1=1 on_hicc1=127 '
        'cutoff=1000 fil_veltrack=1200',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert not any(b.kind == 'velocity' for b in slot.bindings)
    assert any(
        f.location.opcode == 'fil_veltrack' and 'controller-trigger' in f.reason
        for f in result.unimplemented
    )


@pytest.mark.parametrize('rate,cutoff,depth', [(2000, 600, 1200), (48000, 1, -1200)])
def test_velocity_cutoff_bounds_include_output_rate_and_lower_limit(
    rate: int,
    cutoff: int,
    depth: int,
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff={cutoff} fil_veltrack={depth}',
        filter_response='sfizz_rbj',
        rate=rate,
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters[0].cutoff_hz == cutoff
    assert any(
        f.location.opcode == 'fil_veltrack' and 'unclamped' in f.reason
        for f in result.unimplemented
    )


@pytest.mark.parametrize('depth', [-1200, -333.5, 333.5, 1200])
@pytest.mark.parametrize('profile', ['sfizz_triangle', 'sfizz_parabolic'])
def test_filter_lfo_starts_zero_rising_and_maps_signed_depth(
    depth: float, profile: FilterLfoResponse
) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 '
        f'fillfo_freq=2 fillfo_depth={depth}',
        filter_response='sfizz_rbj',
        filter_lfo_response=profile,
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    oscillator = slot.envelfos['sfz-filter-lfo']
    for at, triangle in [
        (Fraction(0), 0),
        (Fraction(1, 16), 0.5),
        (Fraction(1, 8), 1),
        (Fraction(1, 4), 0),
        (Fraction(3, 8), -1),
        (Fraction(1, 2), 0),
    ]:
        if isinstance(oscillator, Patch):
            signal = patch.advance_patch(
                oscillator,
                patch.initial_patch(oscillator, Fraction(0)),
                at,
                next_delivery=at + 1,
            ).values['signal']
            expected = triangle * (2 - abs(triangle))
        else:
            signal = envelfo_at(
                oscillator, initial_envelfo(oscillator, Fraction(0)), at
            ).value
            expected = triangle
        assert signal == pytest.approx(expected)
        values = {
            s.name: modulation.SourceValue(
                value=signal if s.name == 'filter-lfo' else 1,
            )
            for s in slot.modulation.sources
        }
        cutoff = next(
            v.value
            for v in modulation.evaluate(slot.modulation, values)
            if v.target.parameter == 'cutoff_hz'
        )
        assert cutoff == pytest.approx(1000 * 2 ** (depth * expected / 1200))
    exported = exporter.write(result.instrument)
    assert exported.complete, exported.unimplemented
    restored = _compile(
        exported.contents,
        filter_response='sfizz_rbj',
        filter_lfo_response=profile,
    )
    assert restored.complete and restored.instrument is not None
    assert restored.instrument.body.slots[0].modulation == slot.modulation


def test_filter_lfo_export_diagnoses_a_different_oscillator_shape() -> None:
    original = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 fillfo_freq=2 fillfo_depth=1200',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert original.instrument is not None
    raw = original.instrument.model_dump(mode='json')
    raw['body']['slots'][0]['envelfos']['sfz-filter-lfo']['shape'] = 'sine'
    exported = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not exported.complete and 'fillfo_freq=' not in exported.contents
    assert any(
        f.location.path == 'body.slots[0].envelfos.sfz-filter-lfo'
        for f in exported.unimplemented
    )


@pytest.mark.parametrize('delay,fade', [(0.1, 0), (0, 0.2), (0.1, 0.2)])
def test_filter_lfo_delay_and_fade_scale_cents_before_exponentiation(
    delay: float, fade: float
) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 fillfo_freq=2 '
        f'fillfo_depth=1200 fillfo_delay={delay} fillfo_fade={fade}',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    oscillator = slot.envelfos['sfz-filter-lfo']
    for at in [
        Fraction(0),
        Fraction(1, 20),
        Fraction(1, 10),
        Fraction(3, 20),
        Fraction(1, 5),
        Fraction(1, 2),
    ]:
        observed = patch.advance_patch(
            oscillator,
            patch.initial_patch(oscillator, Fraction(0)),
            at,
            next_delivery=at + 1,
        ).values['signal']
        age = max(0, float(at) - delay)
        gate = 0 if float(at) < delay else min(1, age / fade) if fade else 1
        expected = (1 - 4 * abs((2 * age + 0.25) % 1 - 0.5)) * gate
        assert observed == pytest.approx(expected, abs=1e-14)
        values = {
            s.name: modulation.SourceValue(
                value=observed if s.name == 'filter-lfo' else 1
            )
            for s in slot.modulation.sources
        }
        cutoff = next(
            v.value
            for v in modulation.evaluate(slot.modulation, values)
            if v.target.parameter == 'cutoff_hz'
        )
        assert cutoff == pytest.approx(1000 * 2**expected)


def test_filter_lfo_requires_separate_explicit_acceptance() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 fillfo_freq=2 fillfo_depth=1200',
        filter_response='sfizz_rbj',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}
    assert len(result.unimplemented) == 1
    assert result.unimplemented[0].location.opcode == 'fillfo_depth'
    assert 'filter_lfo_response="sfizz_triangle"' in result.unimplemented[0].reason


@pytest.mark.parametrize(
    'declaration',
    [
        'fillfo_delay=-0.1',
        'fillfo_fade=-0.1',
        'trigger=release',
        'trigger=release_key',
        'trigger=legato',
        'fillfo_freq=21',
        'fillfo_depth=1201',
        'fillfo_depth=-1201',
    ],
)
def test_unverified_filter_lfo_retains_valid_tracking(declaration: str) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=60 cutoff=1000 fil_keytrack=100 '
        'fillfo_freq=2 fillfo_depth=1200 ' + declaration,
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert not result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.envelfos == {}
    assert any(
        r.source == 'key' and r.target.parameter == 'cutoff_hz'
        for r in slot.modulation.routes
    )
    assert any(f.location.opcode.startswith('fillfo_') for f in result.unimplemented)


@pytest.mark.parametrize(
    'declaration',
    ['', 'fillfo_freq=0 fillfo_depth=1200', 'fillfo_freq=2 fillfo_depth=0'],
)
def test_inactive_filter_lfo_creates_no_envelfo(declaration: str) -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 ' + declaration,
        filter_response='sfizz_rbj',
    )
    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}


@pytest.mark.parametrize(
    'opcode', ['fillfo_freq', 'fillfo_depth', 'fillfo_delay', 'fillfo_fade']
)
def test_malformed_filter_lfo_fails_explicitly(opcode: str) -> None:
    with pytest.raises(ValueError):
        _compile(f'<region> sample=audio/glass.wav {opcode}=oops')


@pytest.mark.parametrize('cutoff,depth,key', [(3000, 1200, 61), (4, -1200, 59)])
def test_filter_lfo_combination_diagnoses_all_cutoff_routes(
    cutoff: int, depth: int, key: int
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav key={key} cutoff={cutoff} '
        f'fil_keytrack=1200 fil_veltrack={depth} fillfo_freq=2 fillfo_depth=1200 '
        'cutoff2=400 fil2_veltrack=-1200',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert not result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.envelfos == {}
    assert [
        r.target.name
        for r in slot.modulation.routes
        if r.target.parameter == 'cutoff_hz'
    ] == ['filter-sfz-filter-2']
    assert {f.location.opcode for f in result.unimplemented} == {
        'fil_keytrack',
        'fil_veltrack',
        'fillfo_depth',
    }
    assert all('Combined' in f.reason for f in result.unimplemented)


def test_filter_lfo_controller_trigger_remains_diagnosed() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav key=-1 loop_mode=one_shot '
        'pitch_keytrack=0 amp_veltrack=0 on_locc1=1 on_hicc1=127 '
        'cutoff=1000 fillfo_freq=2 fillfo_depth=1200',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].envelfos == {}
    assert any(
        f.location.opcode == 'fillfo_depth' and 'note-on' in f.reason
        for f in result.unimplemented
    )


def test_filter_lfo_conformance_preserves_inheritance_and_first_filter_target(
    data_regression: DataRegressionFixture,
) -> None:
    result = _compile(
        Path('conformance/filter-lfo.sfz').read_text(),
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert result.complete
    assert result.instrument is not None
    observed = []
    for slot in result.instrument.body.slots:
        for at in (Fraction(0), Fraction(1, 8), Fraction(3, 8)):
            oscillator = slot.envelfos['sfz-filter-lfo']
            observation = envelfo_at(
                oscillator, initial_envelfo(oscillator, Fraction(0)), at
            )
            values = {
                s.name: modulation.SourceValue(
                    value=observation.value
                    if s.name == 'filter-lfo'
                    else 61
                    if s.name == 'key'
                    else 0.5
                )
                for s in slot.modulation.sources
            }
            resolved = {
                v.target.name: round(v.value, 8)
                for v in modulation.evaluate(slot.modulation, values)
                if v.target.parameter == 'cutoff_hz'
            }
            observed.append({'slot': slot.name, 'at': str(at), 'cutoffs': resolved})
        assert all(
            r.target.name == 'filter-sfz-filter-1'
            for r in slot.modulation.routes
            if r.source == 'filter-lfo'
        )
    data_regression.check(observed)


@pytest.mark.parametrize('rate,cutoff', [(2000, 600), (48000, 1), (48000, 12000)])
def test_filter_lfo_cutoff_bounds_retain_the_static_filter(
    rate: int, cutoff: int
) -> None:
    result = _compile(
        f'<region> sample=audio/glass.wav cutoff={cutoff} '
        'fillfo_freq=2 fillfo_depth=1200',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
        rate=rate,
    )
    assert not result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.processing.filters[0].cutoff_hz == cutoff
    assert slot.envelfos == {}
    assert any(
        f.location.opcode == 'fillfo_depth' and 'unclamped' in f.reason
        for f in result.unimplemented
    )


def test_filter_lfo_acceptance_does_not_accept_the_static_response() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav cutoff=1000 fillfo_freq=2 fillfo_depth=1200',
        filter_lfo_response='sfizz_triangle',
    )
    assert not result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].processing.filters == []
    assert result.instrument.body.slots[0].envelfos == {}
    assert any('filter_response="sfizz_rbj"' in f.reason for f in result.unimplemented)


def test_filter_lfo_without_explicit_cutoff_remains_diagnosed() -> None:
    result = _compile(
        '<region> sample=audio/glass.wav fillfo_freq=2 fillfo_depth=1200',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    assert not result.complete
    assert any('no explicit cutoff' in f.reason for f in result.unimplemented)


def test_unknown_filter_lfo_response_fails_explicitly() -> None:
    with pytest.raises(ValueError, match='Unknown SFZ filter LFO response'):
        _compile('<region> sample=audio/glass.wav', filter_lfo_response='unknown')


def _compile(
    text: str,
    filter_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
    rate: int = 48_000,
    filter_lfo_response: FilterLfoResponse = 'diagnose',
    eq_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
) -> SfzCompileResult:
    return compiler.compile_instrument(
        parser.parse(text),
        name='glass',
        title='Glass',
        assets={
            'audio/glass.wav': AudioMetadata(
                channels=1,
                frames=48_000,
                sample_rate=48_000,
                encoding='WAV/PCM_16',
                byte_length=96_044,
                sha256='0' * 64,
                embedded_loop_known=True,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=rate)),
        output_channels=['left', 'right'],
        filter_response=filter_response,
        filter_lfo_response=filter_lfo_response,
        eq_response=eq_response,
    )
