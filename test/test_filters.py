import json
from pathlib import Path
from typing import Literal

import pytest
from pytest_regressions.data_regression import DataRegressionFixture
from ufor import modulation
from ufor.samples import processing
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, exporter, parser, registry
from safaz.model import SfzCompileResult, SfzLocation


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
    assert not exported.complete
    assert any('Resonant filters' in f.reason for f in exported.unimplemented)


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


@pytest.mark.parametrize('opcode', ['cutoff_oncc1', 'fil_veltrack', 'fileg_depth'])
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
    assert not exporter.write(result.instrument).complete


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


def _compile(
    text: str,
    filter_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
    rate: int = 48_000,
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
    )
