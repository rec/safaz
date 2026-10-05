import json
from fractions import Fraction
from pathlib import Path

import pytest
from ufor import modulation
from ufor.codec import parse_score, score_toml
from ufor.interface import ScoreReference
from ufor.samples import crossfade, enums, playback, selection
from ufor.samples.instrument import (
    SampleInstrumentScore,
)
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, exporter, parser, registry
from safaz.model import SfzCompileResult, SfzMidiBindingRequest


def test_sfz_conformance_requires_only_text_and_supplied_asset_facts() -> None:
    source = parser.parse(Path('conformance/instrument.sfz').read_text())
    assert parser.sample_paths(source) == ['audio/glass.wav']
    result = compiler.compile_instrument(
        source,
        name='glass',
        title='Glass',
        assets={
            'audio/glass.wav': AudioMetadata(
                channels=1,
                frames=44100,
                sample_rate=44100,
                encoding='WAV/PCM_16',
                byte_length=88244,
                sha256='0' * 64,
                embedded_loop_known=True,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
        output_channels=['left', 'right'],
    )
    assert result.complete
    expected = SampleInstrumentScore.model_validate(fixture())
    assert result.instrument.model_dump(
        mode='json', exclude_none=True
    ) == expected.model_dump(mode='json', exclude_none=True)
    assert exporter.write(result.instrument).complete


def test_sfz_reports_missing_sample_metadata() -> None:
    source = parser.parse('<region> sample=audio/missing.wav')
    with pytest.raises(ValueError, match='audio/missing.wav'):
        compiler.compile_instrument(
            source,
            name='missing',
            title='Missing',
            assets={},
            output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
            output_channels=['left'],
        )


def test_sfz_key_amplitude_tracking_combines_with_velocity() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav lokey=60 hikey=67 '
        'pitch_keycenter=60 volume=-3 '
        'amp_keycenter=60 amp_keytrack=-1.5 amp_veltrack=100'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )

    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    values = modulation.evaluate(
        slot.modulation,
        {
            'key': modulation.SourceValue(value=64),
            'velocity': modulation.SourceValue(value=1),
        },
    )
    assert {v.target.parameter: v.value for v in values} == {
        'amplitude': 1,
        'volume_db': -9,
    }


def test_sfz_partial_pitch_tracking_uses_key_modulation() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav lokey=60 hikey=64 '
        'pitch_keycenter=60 pitch_keytrack=50 tune=10'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )

    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.mapping.pitch_tracking
    values = modulation.evaluate(
        slot.modulation,
        {
            'key': modulation.SourceValue(value=64),
            'velocity': modulation.SourceValue(value=1),
        },
    )
    tuning = next(v.value for v in values if v.target.parameter == 'tuning_cents')
    assert tuning == -190
    assert playback.pitch_ratio(slot.mapping, 440 * 2 ** ((64 - 69) / 12), tuning) == (
        pytest.approx(2 ** (210 / 1200))
    )


def test_sfz_pitch_velocity_combines_with_key_tracking() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav key=60 hikey=61 '
        'pitch_keytrack=50 pitch_veltrack=1200 amp_veltrack=0 tune=10'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )

    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    values = modulation.evaluate(
        slot.modulation,
        {
            'key': modulation.SourceValue(value=61),
            'velocity': modulation.SourceValue(value=64 / 127),
        },
    )
    tuning = next(v.value for v in values if v.target.parameter == 'tuning_cents')
    assert tuning == pytest.approx(10 - 50 + 1200 * 64 / 127)


def test_sfz_velocity_changes_envelope_attack_duration() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav ampeg_attack=0.5 '
        'ampeg_vel2attack=-0.4 amp_veltrack=0'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )

    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.envelope.segments[1].duration == Fraction(1, 2)
    at_zero = modulation.evaluate(
        slot.modulation, {'velocity': modulation.SourceValue(value=0)}
    )
    at_max = modulation.evaluate(
        slot.modulation, {'velocity': modulation.SourceValue(value=1)}
    )
    assert at_zero[0].value == pytest.approx(0.5)
    assert at_max[0].value == pytest.approx(0.1)


def test_sfz_define_expands_opcode_values_and_preserves_locations() -> None:
    source = parser.parse(
        '#define $SAMPLE audio/glass.wav\n'
        '#define $KEY 60\n'
        '<region> sample=$SAMPLE key=$KEY\n'
    )

    assert parser.sample_paths(source) == ['audio/glass.wav']
    assert source.unimplemented == []
    locations = [
        (o.opcode, o.value, o.line, o.column) for o in source.regions[0].opcodes
    ]
    assert locations == [
        ('sample', 'audio/glass.wav', 3, 10),
        ('key', '60', 3, 25),
    ]


def test_sfz_define_uses_the_value_at_each_region() -> None:
    source = parser.parse(
        '#define $KEY 60\n'
        '<region> sample=a.wav key=$KEY\n'
        '#define $KEY 61\n'
        '<region> sample=b.wav key=$KEY\n'
    )

    assert [r.opcodes[-1].value for r in source.regions] == ['60', '61']


@pytest.mark.parametrize(
    ('definition', 'error'),
    [
        ('', 'Undefined SFZ variable \\$KEY on line 1'),
        ('#define $KEY $KEY\n', 'Recursive SFZ variable \\$KEY on line 2'),
        ('#define $KEY $MISSING\n', 'Undefined SFZ variable \\$MISSING on line 2'),
    ],
)
def test_sfz_define_rejects_undefined_and_recursive_variables(
    definition: str, error: str
) -> None:
    with pytest.raises(ValueError, match=error):
        parser.parse(f'{definition}<region> sample=a.wav key=$KEY')


@pytest.mark.parametrize(
    ('header', 'reason'),
    [
        ('curve', 'curve-table support'),
        ('effect', 'effect routing support'),
        ('sample', 'sample-definition support'),
    ],
)
def test_sfz_reports_unsupported_header_and_its_opcodes(
    header: str, reason: str
) -> None:
    source = parser.parse(f'<{header}> unsupported=1\n<region> sample=a.wav')

    assert len(source.unimplemented) == 2
    assert source.unimplemented[0].location.header == header
    assert reason in source.unimplemented[0].reason
    assert source.unimplemented[1].location.opcode == 'unsupported'
    assert source.unimplemented[1].value == '1'


@pytest.mark.parametrize(
    ('opcode', 'classification', 'reason'),
    [
        ('cutoff', registry.Support.new_model, 'filter model'),
        ('start_locc7', registry.Support.controller_binding, 'controller binding'),
        ('sync_beats', registry.Support.new_model, 'transport and tempo model'),
        ('md5', registry.Support.asset_metadata, 'asset metadata'),
        ('vendor_setting', registry.Support.vendor_extension, 'Vendor'),
    ],
)
def test_sfz_registry_drives_unsupported_diagnostics(
    opcode: str, classification: registry.Support, reason: str
) -> None:
    source = parser.parse(f'<region> sample=a.wav {opcode}=1')

    assert registry.opcode_support(opcode)[0] == classification
    assert len(source.unimplemented) == 1
    feature = source.unimplemented[0]
    assert feature.location.opcode == opcode
    assert feature.value == '1'
    assert reason in feature.reason


def test_sfz_registry_covers_the_pinned_standard_and_generates_its_table() -> None:
    assert len(registry.STANDARD_OPCODES) == 453
    assert all(
        registry.opcode_support(n)[1] is not None for n in registry.STANDARD_OPCODES
    )
    assert registry.opcode_support('amp_velcurve_64')[0] == registry.Support.supported
    assert registry.opcode_support('ampeg_attack_oncc7')[0] == (
        registry.Support.controller_binding
    )
    assert Path('doc/sfz-support.md').read_text() == registry.support_table()


def test_sfz_random_range_round_trips_without_selection() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav key=60 lorand=0.25 hirand=0.5'
    )
    result = compiler.compile_instrument(
        source,
        name='glass',
        title='Glass',
        assets={
            'audio/glass.wav': AudioMetadata(
                channels=1,
                frames=44100,
                sample_rate=44100,
                encoding='WAV/PCM_16',
                byte_length=88244,
                sha256='0' * 64,
                embedded_loop_known=True,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
        output_channels=['left', 'right'],
    )
    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].random_range == selection.RandomRange(
        minimum=0.25, maximum=0.5
    )
    rendered = exporter.write(result.instrument)
    assert rendered.complete
    assert 'lorand=0.25' in rendered.contents
    assert 'hirand=0.5' in rendered.contents


def test_sfz_crossfades_do_not_narrow_layer_eligibility() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav lokey=40 hikey=80 '
        'xfin_lokey=50 xfin_hikey=60 xf_keycurve=power '
        'xfin_lovel=32 xfin_hivel=64 xf_velcurve=gain'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert (slot.mapping.lowest_key, slot.mapping.highest_key) == (40, 80)
    assert slot.crossfades == [
        crossfade.KeyCrossfade(
            input=enums.CrossfadeInput.key,
            direction=enums.FadeDirection.fade_in,
            start=50,
            end=60,
            curve=enums.FadeCurve.equal_power,
        ),
        crossfade.KeyCrossfade(
            input=enums.CrossfadeInput.velocity,
            direction=enums.FadeDirection.fade_in,
            start=32 / 127,
            end=64 / 127,
        ),
    ]
    rendered = exporter.write(result.instrument)
    assert rendered.complete
    assert 'xfin_lokey=50' in rendered.contents
    assert 'xfin_hivel=64' in rendered.contents


def test_sfz_loop_count_round_trips_as_finite_repeats() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav loop_mode=loop_sustain '
        'loop_start=100 loop_end=999 loop_count=3'
    )
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )
    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slices[0].loop == playback.Loop(
        start_frame=100, end_frame=1000, repeat_count=3
    )
    rendered = exporter.write(result.instrument)
    assert rendered.complete
    assert 'loop_count=3' in rendered.contents


def test_sfz_loop_count_without_loop_is_reported_at_opcode() -> None:
    source = parser.parse('<region> sample=audio/glass.wav loop_count=2')
    result = compiler.compile_instrument(
        source,
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
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )
    assert not result.complete
    assert [(i.location.opcode, i.reason) for i in result.unimplemented] == [
        ('loop_count', 'SFZ loop_count requires an active loop')
    ]


def test_sfz_count_overrides_loop_mode_without_retriggering_the_envelope() -> None:
    metadata = AudioMetadata(
        channels=1,
        frames=48_000,
        sample_rate=48_000,
        encoding='WAV/PCM_16',
        byte_length=96_044,
        sha256='0' * 64,
        embedded_loop_known=True,
    )
    source = parser.parse(
        '<region> sample=audio/glass.wav count=3 loop_mode=loop_continuous '
        'loop_start=100 loop_end=999'
    )
    result = compiler.compile_instrument(
        source,
        name='glass',
        title='Glass',
        assets={'audio/glass.wav': metadata},
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.playback == playback.SlotPlayback(
        mode=enums.PlaybackMode.one_shot, play_count=3
    )
    assert result.instrument.body.slices[0].loop is None
    rendered = exporter.write(result.instrument)
    assert rendered.complete
    assert 'count=3' in rendered.contents

    source = parser.parse('<region> sample=audio/glass.wav count=0')
    ambiguous = compiler.compile_instrument(
        source,
        name='glass',
        title='Glass',
        assets={'audio/glass.wav': metadata},
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )
    assert [(i.location.opcode, i.reason) for i in ambiguous.unimplemented] == [
        ('count', 'SFZ count=0 differs between players')
    ]


def test_sfz_delay_postpones_voice_start_and_reports_one_shot_ambiguity() -> None:
    metadata = AudioMetadata(
        channels=1,
        frames=48_000,
        sample_rate=48_000,
        encoding='WAV/PCM_16',
        byte_length=96_044,
        sha256='0' * 64,
        embedded_loop_known=True,
    )

    def compile_region(text: str) -> SfzCompileResult:
        return compiler.compile_instrument(
            parser.parse(f'<region> sample=audio/glass.wav {text}'),
            name='glass',
            title='Glass',
            assets={'audio/glass.wav': metadata},
            output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
            output_channels=['left', 'right'],
        )

    result = compile_region('delay=0.25')
    assert result.complete
    assert result.instrument is not None
    slot = result.instrument.body.slots[0]
    assert slot.playback.start_delay_seconds == 0.25
    assert slot.envelope is not None
    assert slot.envelope.segments[0].duration == 0
    rendered = exporter.write(result.instrument)
    assert rendered.complete
    assert 'delay=0.25' in rendered.contents

    ambiguous = compile_region('delay=0.25 loop_mode=one_shot')
    assert [(i.location.opcode, i.reason) for i in ambiguous.unimplemented] == [
        ('delay', 'SFZ one-shot delayed note-off behavior differs between players')
    ]
    release = compile_region('delay=0.25 trigger=release')
    assert release.complete
    assert release.instrument is not None
    assert release.instrument.body.slots[0].playback.start_delay_seconds == 0.25


def test_sfz_uniform_midi_channels_return_separate_binding() -> None:
    metadata = AudioMetadata(
        channels=1,
        frames=48_000,
        sample_rate=48_000,
        encoding='WAV/PCM_16',
        byte_length=96_044,
        sha256='0' * 64,
        embedded_loop_known=True,
    )
    request = SfzMidiBindingRequest(
        instrument=ScoreReference(path='glass.toml'),
        part='main',
        repeated_key_release='newest',
    )

    def compile_regions(
        text: str, binding: SfzMidiBindingRequest | None
    ) -> SfzCompileResult:
        return compiler.compile_instrument(
            parser.parse(text),
            name='glass',
            title='Glass',
            assets={'audio/glass.wav': metadata},
            output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
            output_channels=['left', 'right'],
            midi_binding=binding,
        )

    text = (
        '<region> sample=audio/glass.wav key=60 lochan=2 hichan=3\n'
        '<region> sample=audio/glass.wav key=61 lochan=2 hichan=3'
    )
    result = compile_regions(text, request)
    assert result.complete
    assert result.binding is not None
    assert result.binding.body.instrument == ScoreReference(path='glass.toml')
    assert result.binding.body.midi[0].channels == [2, 3]
    assert result.binding.body.midi[0].part == 'main'
    assert result.binding.body.midi[0].repeated_key_release == 'newest'
    assert result.binding.body.midi[0].controllers[0].number == 64
    assert parse_score(score_toml(result.binding)) == result.binding

    missing = compile_regions(text, None)
    assert missing.binding is None
    assert {i.location.opcode for i in missing.unimplemented} == {
        'lochan',
        'hichan',
    }
    assert len(missing.unimplemented) == 4

    mixed = compile_regions(
        '<region> sample=audio/glass.wav key=60 lochan=2 hichan=3\n'
        '<region> sample=audio/glass.wav key=61 lochan=4 hichan=5',
        request,
    )
    assert mixed.binding is None
    assert len(mixed.unimplemented) == 4
    assert all('native channel eligibility' in i.reason for i in mixed.unimplemented)


def test_sfz_sequence_requires_explicit_counter_rule() -> None:
    source = parser.parse(
        '<region> sample=audio/glass.wav key=60 seq_length=2 seq_position=1'
    )
    metadata = AudioMetadata(
        channels=1,
        frames=48_000,
        sample_rate=48_000,
        encoding='WAV/PCM_16',
        byte_length=96_044,
        sha256='0' * 64,
        embedded_loop_known=True,
    )
    kwargs = dict(
        name='glass',
        title='Glass',
        assets={'audio/glass.wav': metadata},
        output_timebase=Timebase(name='output', rate=Rate(numerator=48_000)),
        output_channels=['left', 'right'],
    )

    default = compiler.compile_instrument(source, **kwargs)
    opted_in = compiler.compile_instrument(
        source, sequence_counter='all_note_ons', **kwargs
    )

    assert [i.location.opcode for i in default.unimplemented] == [
        'seq_length',
        'seq_position',
    ]
    assert opted_in.complete
    assert opted_in.instrument is not None
    assert opted_in.instrument.body.slots[0].sequence == selection.SequencePosition(
        length=2, position=1
    )
    exported = exporter.write(opted_in.instrument)
    assert not exported.complete
    assert exported.unimplemented[0].location.path == 'body.slots[0].sequence'
    assert 'seq_length=2' in exported.contents
    assert 'seq_position=1' in exported.contents


def test_voice_pool_round_trips_and_is_reported_by_sfz_export() -> None:
    raw = fixture()
    raw['body']['voice_pools'] = [{'name': 'drums', 'policy': {'maximum_voices': 2}}]
    raw['body']['slots'][0]['voice_pool'] = 'drums'
    document = SampleInstrumentScore.model_validate(raw)

    assert parse_score(score_toml(document)) == document
    exported = exporter.write(document)
    assert not exported.complete
    assert any(
        f.location.path == 'body.voice_pools[0]'
        for f in exported.unimplemented
        if f.location.kind == 'instrument'
    )


def test_sfz_reports_general_envelopes_and_custom_channel_maps_as_unsupported() -> None:
    raw = fixture()
    raw['body']['slots'][0]['envelope']['segments'][1]['curve'] = 2
    raw['body']['slots'][0]['channels'][0]['gain'] = 0.125
    raw['body']['slots'][0]['processing']['pan'] = 0
    result = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not result.complete
    assert [x.location.path for x in result.unimplemented] == [
        'body.slots[0].channels',
        'body.slots[0].envelope',
    ]


def test_sfz_rejects_velocity_gain_outside_its_representable_domain() -> None:
    raw = fixture()
    settings = raw['body']['slots'][0]
    settings['modulation']['parameters'][0]['maximum'] = 2
    settings['modulation']['routes'][0]['points'][-1]['amount'] = 2
    result = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not result.complete
    assert result.unimplemented[0].location.path == 'body.slots[0].modulation.routes[0]'
    assert 'amp_velcurve_127=2' not in result.contents


def test_sfz_generator_diagnostics_use_dictionary_paths() -> None:
    raw = fixture()
    raw['body']['slots'][0]['motions'] = {
        'vibrato': {'body': {'kind': 'cycle', 'rate': 5}}
    }
    result = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not result.complete
    assert result.unimplemented[0].location.path == 'body.slots[0].motions.vibrato'


def test_sfz_export_resolves_group_processing() -> None:
    raw = fixture()
    settings = raw['body']['slots'][0].pop('processing')
    settings['volume_db'] = -6
    raw['body']['groups'] = [{'name': 'quiet', 'processing': settings}]
    raw['body']['slots'][0]['group'] = 'quiet'
    result = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert result.complete
    assert 'volume=-6' in result.contents


@pytest.mark.parametrize(
    'field,value,path',
    [
        ('variation', {'pitch_cents': 5}, 'body.slots[0].variation.pitch_cents'),
        (
            'filters',
            [{'name': 'tone', 'response': 'lowpass', 'cutoff_hz': 1000}],
            'body.slots[0].processing.filters[0]',
        ),
        ('voice_policy', {'maximum_voices': 4}, 'body.settings.voice_policy'),
    ],
)
def test_sfz_reports_unrepresentable_native_features(
    field: str, value: object, path: str
) -> None:
    raw = fixture()
    if field == 'voice_policy':
        raw['body']['settings'][field] = value
    elif field == 'filters':
        raw['body']['slots'][0]['processing'][field] = value
    else:
        raw['body']['slots'][0][field] = value
    result = exporter.write(SampleInstrumentScore.model_validate(raw))
    assert not result.complete
    assert path in [i.location.path for i in result.unimplemented]


@pytest.mark.parametrize('sample', ['../outside.wav', '/outside.wav', 'C:/outside.wav'])
def test_sfz_paths_are_validated_before_requesting_asset_facts(sample: str) -> None:
    source = parser.parse(f'<region> sample={sample}')
    with pytest.raises(ValueError, match='declared root'):
        parser.sample_paths(source)


def fixture() -> dict[str, object]:
    return json.loads(Path('conformance/instrument.json').read_text())
