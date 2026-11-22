"""Export representable native sample instruments as SFZ text."""

import json
import math
from typing import Literal

from ufor import base, envelfo, envelope, modulation, segments
from ufor.approach import ExponentialApproach
from ufor.assets import RelativeFileLocation
from ufor.control import Clock, Scope
from ufor.performance_binding import MidiPitchBend, PerformanceBindingScore
from ufor.samples import controls, crossfade, enums, playback, processing, selection
from ufor.samples.instrument import (
    SampleInstrumentScore,
    SampleSlot,
    effective_selection,
    effective_settings,
)
from ufor.streams import AudioType

from .filter_envelope import filter_envelope_values
from .filters import FILTER_RESPONSES, cutoff_limit, inverse_value, nearby_values
from .model import (
    InstrumentLocation,
    Opcode,
    SfzExportResult,
    UnimplementedFeature,
    _channel_routes,
)
from .modulators import lfo_values
from .polyphony import oversized_batch
from .spatial import stereo_opcodes


def write(
    instrument: SampleInstrumentScore,
    *,
    midi_binding: PerformanceBindingScore | None = None,
    polyphony_overflow: Literal['diagnose', 'oldest_immediate'] = 'diagnose',
    sequence_counter: Literal['reject', 'all_note_ons'] = 'reject',
    cc_crossfade_response: Literal['diagnose', 'portable_ramp'] = 'diagnose',
    variation_response: Literal['diagnose', 'portable_seeded'] = 'diagnose',
) -> SfzExportResult:
    """Serialize a native instrument without reading or writing sample assets."""
    if polyphony_overflow not in ('diagnose', 'oldest_immediate'):
        raise ValueError(f'Unknown SFZ polyphony overflow rule: {polyphony_overflow}')
    if sequence_counter not in ('reject', 'all_note_ons'):
        raise ValueError(f'Unknown SFZ sequence counter rule: {sequence_counter}')
    if cc_crossfade_response not in ('diagnose', 'portable_ramp'):
        raise ValueError(f'Unknown SFZ CC crossfade response: {cc_crossfade_response}')
    if variation_response not in ('diagnose', 'portable_seeded'):
        raise ValueError(f'Unknown SFZ variation response: {variation_response}')
    issues: list[UnimplementedFeature] = []
    _instrument_issues(instrument, issues)
    controllers, bend_control, control_lines, global_lines = _midi_export(
        instrument, midi_binding, issues
    )
    limits = _polyphony_limits(instrument, polyphony_overflow, issues)
    groups, victims = _choke_groups(instrument, limits, issues)
    articulations = instrument.body.settings.articulations
    switches = _keyswitch_map(articulations)
    emitted_switches: set[int] = set()
    has_switch_condition = False
    regions: list[list[str]] = []
    slot_groups = {g.name: g for g in instrument.body.groups}
    for i, slot in enumerate(instrument.body.slots):
        group = slot_groups.get(slot.group)
        if group is not None:
            slot = SampleSlot.model_validate(
                slot.model_dump()
                | effective_settings(slot, group).model_dump()
                | {'group': None, 'selection': effective_selection(slot, group)}
            )
        opcodes = _region(
            instrument,
            slot,
            i,
            groups,
            victims,
            controllers,
            bend_control,
            sequence_counter,
            variation_response == 'portable_seeded',
            issues,
        )
        written = {o.name for o in opcodes or []}
        for field, opcode in (
            ('delay_seconds', 'delay_random'),
            ('offset_frames', 'offset_random'),
            ('gain_db', 'amp_random'),
            ('pitch_cents', 'pitch_random'),
        ):
            if (value := getattr(slot.variation, field)) and opcode not in written:
                _issue(
                    issues,
                    f'body.slots[{i}].variation.{field}',
                    value,
                    'Pass variation_response=portable_seeded to accept native draws'
                    if variation_response == 'diagnose'
                    else 'Variation falls outside the portable SFZ export profile',
                )
        conditions = _keyswitch_opcodes(slot, articulations, switches, i, issues)
        conditions.extend(_controller_conditions(slot, controllers, i, issues))
        fades = _crossfade_opcodes(
            slot, f'body.slots[{i}]', controllers, cc_crossfade_response, issues
        )
        if opcodes is None:
            continue
        if slot.voice_pool is not None and slot.voice_pool in limits:
            opcodes.append(Opcode(name='polyphony', value=str(limits[slot.voice_pool])))
        emitted_switches.update(int(o.value) for o in conditions if o.name == 'sw_last')
        has_switch_condition |= any(
            o.name in ('sw_last', 'sw_down', 'sw_up') for o in conditions
        )
        opcodes.extend(conditions)
        opcodes.extend(fades)
        metadata = '// recs:slot ' + _json(
            {
                'name': slot.name,
                'title': slot.title,
                'description': slot.description,
                'tags': slot.tags,
            }
        )
        regions.append(
            [metadata, '<region>', *(f'{o.name}={o.value}' for o in opcodes)]
        )
    if not regions:
        _issue(
            issues,
            'body.slots',
            instrument.body.slots,
            'No slot can be represented as an SFZ region',
        )
        return SfzExportResult(contents='// Generated by safaz\n', unimplemented=issues)
    lines = [
        '// Generated by safaz',
        '// recs:instrument '
        + _json(
            {
                'version': 2,
                'title': instrument.title,
                'description': instrument.description,
                'tags': instrument.tags,
            }
        ),
    ]
    if articulations is not None:
        if (
            switches is None
            or not has_switch_condition
            or emitted_switches != set(switches.values())
        ):
            _issue(
                issues,
                'body.settings.articulations',
                articulations,
                'SFZ requires a contiguous consumed switch range '
                'and a region for each sticky switch',
            )
        if switches is not None and has_switch_condition:
            keys = [k.key for k in articulations.keys]
            global_lines.extend([f'sw_lokey={min(keys)}', f'sw_hikey={max(keys)}'])
            if (
                articulations.default is not None
                and (key := switches[articulations.default]) in emitted_switches
            ):
                global_lines.append(f'sw_default={key}')
    if control_lines:
        lines.extend(['', '<control>', *control_lines])
    if global_lines:
        lines.extend(['', '<global>', *global_lines])
    if bend_control is not None and not any(
        line.startswith('bend_up=') for region in regions for line in region
    ):
        _issue(
            issues, 'midi_binding', bend_control, 'No region can export the MIDI bend'
        )
    for region in regions:
        lines.extend(['', *region])
    return SfzExportResult(contents='\n'.join(lines) + '\n', unimplemented=issues)


def _instrument_issues(
    document: SampleInstrumentScore, issues: list[UnimplementedFeature]
) -> None:
    instrument = document.body.settings
    if document.body.pan_law != processing.PanLaw.sfizz:
        _issue(
            issues,
            'body.pan_law',
            document.body.pan_law,
            'SFZ playback uses the sfizz pan convention, not the native pan law',
        )
    if instrument.voice_policy is not None:
        _issue(
            issues,
            'body.settings.voice_policy',
            instrument.voice_policy,
            'Voice policy has no exact SFZ conversion',
        )
    for i, parameter in enumerate(document.parameters):
        _issue(
            issues,
            f'parameters[{i}]',
            parameter,
            'Public parameter exports have no SFZ conversion',
        )
    if instrument.selections:
        for i, value in enumerate(instrument.selections):
            _issue(
                issues,
                f'body.settings.selections[{i}]',
                value,
                'SFZ alternate-selection behavior is not represented',
            )
    canonical_sustain = selection.Sustain(control='sustain')
    if instrument.sustain != canonical_sustain:
        _issue(
            issues,
            'body.settings.sustain',
            instrument.sustain,
            'SFZ only provides its implicit canonical sustain-pedal behavior',
        )
    _sound_issues(instrument, 'body.settings', issues)


def _sound_issues(
    settings: processing.SoundSettings,
    path: str,
    issues: list[UnimplementedFeature],
) -> None:
    for i, value in enumerate(settings.processing.equalizer):
        _issue(
            issues,
            f'{path}.processing.equalizer[{i}]',
            value,
            'Instrument equalizer bands have no implemented SFZ conversion',
        )
    for name, value in settings.envelfos.items():
        _issue(
            issues,
            f'{path}.envelfos.{name}',
            value,
            'Instrument envelfos have no implemented SFZ conversion',
        )
    for i, value in enumerate(settings.modulation.routes):
        _issue(
            issues,
            f'{path}.modulation.routes[{i}]',
            value,
            'Instrument-wide modulation has no exact SFZ region conversion',
        )


def _region(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    index: int,
    groups: dict[str, int],
    victims: dict[str, tuple[int, enums.ChokeMode]],
    controllers: dict[str, int],
    bend_control: str | None,
    sequence_counter: Literal['reject', 'all_note_ons'],
    seeded_variation: bool,
    issues: list[UnimplementedFeature],
) -> list[Opcode] | None:
    path = f'body.slots[{index}]'
    control = _control_trigger_export(document, slot, controllers, path, issues)
    if slot.control_trigger is not None and not control:
        _filter_opcodes(document, slot, path, issues)
        _slot_issues(slot, path, issues)
        return None
    sample_slice = next(s for s in document.body.slices if s.name == slot.slice)
    asset = next(a for a in document.assets if a.name == sample_slice.asset)
    if not isinstance(asset.location, RelativeFileLocation):
        _issue(
            issues,
            f'{path}.sample',
            asset.location,
            'SFZ export requires a relative-file sample location',
        )
        return None
    sample = asset.location.path
    try:
        expected_channels = _channel_routes(
            len(asset.audio.channels),
            next(
                p.stream.channels
                for p in document.outputs
                if isinstance(p.stream, AudioType)
            ),
        )
    except ValueError:
        expected_channels = []
    spatial = None
    if (
        slot.channels != expected_channels
        and len(asset.audio.channels) == 2
        and expected_channels
        and document.body.pan_law == processing.PanLaw.sfizz
        and not (document.body.settings.processing.pan or slot.processing.pan)
    ):
        spatial = stereo_opcodes(slot.channels)
    if slot.channels != expected_channels and spatial is None:
        _issue(
            issues,
            f'{path}.channels',
            slot.channels,
            'Custom channel routing has no SFZ conversion',
        )
    sample_safe = _safe_sample(sample)
    if not sample_safe:
        _issue(
            issues,
            f'{path}.sample',
            sample,
            'Sample reference contains syntax that is unsafe in portable SFZ',
        )
    mapping_eligible = _mapping_eligible(slot.mapping, path, issues)
    if not sample_safe or not mapping_eligible:
        _diagnose_omitted_slot(
            document, slot, path, groups, victims, bend_control, issues
        )
        return None

    opcodes = [Opcode(name='sample', value=sample)]
    if spatial is not None:
        width, pan, position = spatial
        opcodes.append(Opcode(name='width', value=_number_text(100 * width)))
        if pan:
            opcodes.append(Opcode(name='pan', value=_number_text(100 * pan)))
        if position:
            opcodes.append(Opcode(name='position', value=_number_text(100 * position)))
    if slot.title is not None and _safe_value(slot.title):
        opcodes.insert(0, Opcode(name='region_label', value=slot.title))
    opcodes.extend(control or _mapping(slot.mapping))
    if slot.sequence is not None:
        if slot.sequence.length > 100 or slot.trigger != enums.TriggerKind.start:
            _issue(
                issues,
                f'{path}.sequence',
                slot.sequence,
                'SFZ sequence requires a note-on trigger and a length of at most 100',
            )
        else:
            opcodes.extend(
                [
                    Opcode(name='seq_length', value=str(slot.sequence.length)),
                    Opcode(name='seq_position', value=str(slot.sequence.position)),
                ]
            )
            if sequence_counter == 'reject':
                _issue(
                    issues,
                    f'{path}.sequence',
                    slot.sequence,
                    'Pass sequence_counter=all_note_ons to accept the SFZ counter rule',
                )
    opcodes.extend(_random_range_opcodes(slot.random_range))
    if not control:
        opcodes.extend(_trigger_opcodes(slot, path, issues))
    opcodes.extend(_choking(slot, path, groups, victims, issues))
    opcodes.extend(_playback_opcodes(document, slot, path, issues))
    seeded_variation &= slot.trigger == enums.TriggerKind.start
    if seeded_variation:
        opcodes.extend(_playback_variation_opcodes(document, slot, sample_slice))
    opcodes.extend(_processing_opcodes(document, slot, path, issues, seeded_variation))
    envelopes, envelope_routes = _envelope_opcodes(document, slot, path, issues)
    opcodes.extend(envelopes)
    filters, filter_routes, generators = _filter_opcodes(document, slot, path, issues)
    opcodes.extend(filters)
    opcodes.extend(
        _modulation_opcodes(
            document,
            slot,
            path,
            issues,
            filter_routes + envelope_routes,
            generators,
            bend_control,
        )
    )
    _slot_issues(slot, path, issues, generators)
    return opcodes


def _diagnose_omitted_slot(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    groups: dict[str, int],
    victims: dict[str, tuple[int, enums.ChokeMode]],
    bend_control: str | None,
    issues: list[UnimplementedFeature],
) -> None:
    _trigger_opcodes(slot, path, issues)
    _choking(slot, path, groups, victims, issues)
    _playback_opcodes(document, slot, path, issues)
    instrument = document.body.settings.processing
    local = slot.processing
    if not slot.mapping.pitch_tracking and slot.mapping.reference_pitch_hz is not None:
        _issue(
            issues,
            f'{path}.mapping.reference_pitch_hz',
            slot.mapping.reference_pitch_hz,
            'An untracked SFZ region cannot retain a reference pitch as metadata',
        )
    if (instrument.pan + local.pan) and (
        instrument.stereo_balance + local.stereo_balance
    ):
        _issue(
            issues,
            f'{path}.processing',
            local,
            'One SFZ pan opcode cannot distinguish simultaneous pan and balance',
        )
    for i, band in enumerate(local.equalizer):
        _issue(
            issues,
            f'{path}.processing.equalizer[{i}]',
            band,
            'Instrument equalizer bands have no implemented SFZ conversion',
        )
    _, envelope_routes = _envelope_opcodes(document, slot, path, issues)
    _, filter_routes, generators = _filter_opcodes(document, slot, path, issues)
    _modulation_opcodes(
        document,
        slot,
        path,
        issues,
        filter_routes + envelope_routes,
        generators,
        bend_control,
    )
    _slot_issues(slot, path, issues, generators)


def _mapping_eligible(
    mapping: playback.Mapping, path: str, issues: list[UnimplementedFeature]
) -> bool:
    valid = True
    if not 0 <= mapping.lowest_key <= mapping.highest_key <= 127:
        _issue(
            issues,
            f'{path}.mapping',
            mapping,
            'SFZ key bounds must be within 0 through 127',
        )
        valid = False
    for field in ('minimum_velocity', 'maximum_velocity'):
        value = getattr(mapping, field)
        if _velocity_number(value) is None:
            _issue(
                issues,
                f'{path}.mapping.{field}',
                value,
                'SFZ velocity bounds must be exact integer multiples of 1/127',
            )
            valid = False
    if mapping.event_key is not None:
        _issue(
            issues,
            f'{path}.mapping.event_key',
            mapping.event_key,
            'SFZ sustain event-key mappings require an external input binding',
        )
        valid = False
    if mapping.pitch_tracking and _pitch_key(mapping.reference_pitch_hz) is None:
        _issue(
            issues,
            f'{path}.mapping.reference_pitch_hz',
            mapping.reference_pitch_hz,
            'Reference pitch has no in-range SFZ pitch key center',
        )
        valid = False
    return valid


def _mapping(mapping: playback.Mapping) -> list[Opcode]:
    result = [
        Opcode(name='lokey', value=str(mapping.lowest_key)),
        Opcode(name='hikey', value=str(mapping.highest_key)),
        Opcode(name='lovel', value=str(_velocity_number(mapping.minimum_velocity))),
        Opcode(name='hivel', value=str(_velocity_number(mapping.maximum_velocity))),
    ]
    if mapping.pitch_tracking:
        assert mapping.reference_pitch_hz is not None
        assert (key := _pitch_key(mapping.reference_pitch_hz)) is not None
        result.append(Opcode(name='pitch_keycenter', value=str(key)))
    else:
        result.append(Opcode(name='pitch_keytrack', value='0'))
    return result


def _random_range_opcodes(value: selection.RandomRange | None) -> list[Opcode]:
    if value is None:
        return []
    return [
        Opcode(name='lorand', value=str(value.minimum)),
        Opcode(name='hirand', value=str(value.maximum)),
    ]


def _trigger_opcodes(
    slot: SampleSlot, path: str, issues: list[UnimplementedFeature]
) -> list[Opcode]:
    values = {
        enums.TriggerKind.start: None,
        enums.TriggerKind.release: 'release_key',
        enums.TriggerKind.logical_release: 'release',
    }
    if slot.trigger in values:
        value = values[slot.trigger]
        return [Opcode(name='trigger', value=value)] if value else []
    _issue(
        issues,
        f'{path}.trigger',
        slot.trigger,
        'Sustain-transition triggers require an external SFZ input binding',
    )
    return []


def _midi_export(
    document: SampleInstrumentScore,
    binding: PerformanceBindingScore | None,
    issues: list[UnimplementedFeature],
) -> tuple[dict[str, int], str | None, list[str], list[str]]:
    settings = document.body.settings
    if binding is None:
        if settings.controls != {'sustain': controls.ControlDeclaration()}:
            _issue(
                issues,
                'body.settings.controls',
                settings.controls,
                'Named instrument controls require an external SFZ input binding',
            )
        return {}, None, [], []
    midi = binding.body.midi[0]
    channels = sorted(midi.channels)
    if (
        len(binding.body.midi) != 1
        or channels != list(range(channels[0], channels[-1] + 1))
        or midi.tuning is not None
        or len({c.control for c in midi.controllers}) != len(midi.controllers)
        or not any(c.number == 64 for c in midi.controllers)
        or any(
            (c.minimum, c.maximum) != (0, 1)
            or (c.number == 64) != (c.control == 'sustain')
            for c in midi.controllers
        )
    ):
        _issue(
            issues,
            'midi_binding',
            binding,
            'SFZ needs contiguous MIDI channels and unscaled CC bindings',
        )
        return {}, None, [], []
    numbers = {c.control: c.number for c in midi.controllers}
    bend_control = None
    if (bend := midi.pitch_bend) is not None:
        if (
            bend != MidiPitchBend(control=bend.control)
            or settings.controls.get(bend.control)
            != controls.ControlDeclaration(polarity='bipolar')
            or bend.control in numbers
        ):
            _issue(
                issues,
                'midi_binding',
                bend,
                'SFZ bend needs unscaled bipolar MIDI input',
            )
        else:
            bend_control = bend.control
    result: dict[str, int] = {}
    defaults: list[str] = []
    for name, declaration in settings.controls.items():
        if name == bend_control:
            continue
        number = numbers.get(name)
        if name == 'sustain' and declaration == controls.ControlDeclaration():
            if number is not None:
                result[name] = number
            continue
        initial = _velocity_number(declaration.default)
        if (
            number is None
            or initial is None
            or not 0 <= initial <= 127
            or declaration != controls.ControlDeclaration(default=initial / 127)
        ):
            _issue(
                issues,
                f'body.settings.controls.{name}',
                declaration,
                'An SFZ control requires a MIDI CC binding and an exact 7-bit default',
            )
            continue
        result[name] = number
        defaults.append(f'set_cc{number}={initial}')
    for name in numbers.keys() - settings.controls.keys():
        _issue(issues, 'midi_binding', name, 'MIDI CC references an undeclared control')
    global_lines = (
        [f'lochan={channels[0]}', f'hichan={channels[-1]}']
        if (channels[0], channels[-1]) != (1, 16)
        else []
    )
    return result, bend_control, defaults, global_lines


def _controller_conditions(
    slot: SampleSlot,
    controllers: dict[str, int],
    index: int,
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    result: list[Opcode] = []
    for i, condition in enumerate(slot.control_conditions):
        bounds = _controller_range(condition, controllers)
        if (
            bounds is None
            or slot.trigger not in (enums.TriggerKind.start, enums.TriggerKind.control)
            or sum(c.control == condition.control for c in slot.control_conditions) != 1
        ):
            _issue(
                issues,
                f'body.slots[{index}].control_conditions[{i}]',
                condition,
                'SFZ needs one exact 7-bit range per bound CC on note or control start',
            )
            continue
        number, low, high = bounds
        result.extend(
            [
                Opcode(name=f'locc{number}', value=str(low)),
                Opcode(name=f'hicc{number}', value=str(high)),
            ]
        )
    return result


def _controller_range(
    condition: selection.ControlCondition, controllers: dict[str, int]
) -> tuple[int, int, int] | None:
    number = controllers.get(condition.control)
    low, high = map(
        _velocity_number, (condition.minimum_value, condition.maximum_value)
    )
    if (
        number is None
        or low is None
        or high is None
        or not 0 <= low <= high <= 127
        or (low / 127, high / 127) != (condition.minimum_value, condition.maximum_value)
    ):
        return None
    return number, low, high


def _control_trigger_export(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    controllers: dict[str, int],
    path: str,
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    trigger = slot.control_trigger
    if trigger is None:
        return []
    bounds = _controller_range(trigger, controllers)
    key = _pitch_key(trigger.pitch_hz)
    playback_settings = document.body.settings.playback
    if (
        bounds is None
        or key is None
        or trigger.velocity != 1
        or trigger.pitch_hz != 440.0 * 2 ** ((key - 69) / 12)
        or (slot.playback.mode or playback_settings.mode) != enums.PlaybackMode.one_shot
        or slot.playback.start_delay_seconds
        or slot.mapping
        != playback.Mapping(
            lowest_key=0,
            highest_key=127,
            minimum_velocity=1 / 127,
            pitch_tracking=False,
        )
        or slot.sequence is not None
        or slot.random_range is not None
        or slot.articulations
        or slot.key_conditions
        or slot.previous_key is not None
        or slot.crossfades
        or slot.modulation.routes
    ):
        _issue(
            issues,
            f'{path}.control_trigger',
            trigger,
            'SFZ control triggers need a 7-bit CC and independent one-shot playback',
        )
        return []
    number, low, high = bounds
    return [
        Opcode(name='key', value='-1'),
        Opcode(name='pitch_keytrack', value='0'),
        Opcode(name='pitch_keycenter', value=str(key)),
        Opcode(name=f'on_locc{number}', value=str(low)),
        Opcode(name=f'on_hicc{number}', value=str(high)),
    ]


def _keyswitch_map(
    articulations: selection.Articulations | None,
) -> dict[str, int] | None:
    if articulations is None or articulations.controls or not articulations.keys:
        return None
    keys = sorted(k.key for k in articulations.keys)
    if keys != list(range(keys[0], keys[-1] + 1)) or any(
        not k.consume or k.behavior != enums.KeyBehavior.latched
        for k in articulations.keys
    ):
        return None
    switches = {
        k.articulation: k.key for k in articulations.keys if k.articulation is not None
    }
    if switches.keys() != set(articulations.ids) or len(switches) != sum(
        k.articulation is not None for k in articulations.keys
    ):
        return None
    return switches


def _keyswitch_opcodes(
    slot: SampleSlot,
    articulations: selection.Articulations | None,
    switches: dict[str, int] | None,
    index: int,
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    path = f'body.slots[{index}]'
    result: list[Opcode] = []
    if slot.articulations:
        if (
            switches is not None
            and len(slot.articulations) == 1
            and slot.articulations[0] in switches
        ):
            result.append(
                Opcode(name='sw_last', value=str(switches[slot.articulations[0]]))
            )
        else:
            _issue(
                issues,
                f'{path}.articulations',
                slot.articulations,
                'SFZ requires one sticky keyswitch per region',
            )
    if slot.key_conditions:
        keys = (
            {k.key for k in articulations.keys} if articulations is not None else set()
        )
        if (
            slot.trigger == enums.TriggerKind.start
            and switches is not None
            and all(k.key in keys for k in slot.key_conditions)
            and len({k.pressed for k in slot.key_conditions})
            == len(slot.key_conditions)
        ):
            result.extend(
                Opcode(name='sw_down' if k.pressed else 'sw_up', value=str(k.key))
                for k in slot.key_conditions
            )
        else:
            _issue(
                issues,
                f'{path}.key_conditions',
                slot.key_conditions,
                'SFZ needs a shared consumed switch range '
                'and at most one condition of each kind',
            )
    if slot.previous_key is not None:
        if slot.trigger == enums.TriggerKind.start:
            result.append(Opcode(name='sw_previous', value=str(slot.previous_key)))
        else:
            _issue(
                issues,
                f'{path}.previous_key',
                slot.previous_key,
                'SFZ previous-key history is verified only for note-on regions',
            )
    return result


def _polyphony_limits(
    document: SampleInstrumentScore,
    overflow: Literal['diagnose', 'oldest_immediate'],
    issues: list[UnimplementedFeature],
) -> dict[str, int]:
    result: dict[str, int] = {}
    for i, pool in enumerate(document.body.voice_pools):
        members = [s for s in document.body.slots if s.voice_pool == pool.name]
        maximum = pool.policy.maximum_voices
        reason = None
        if (
            pool.policy.overflow != enums.VoiceOverflow.replace_oldest
            or pool.policy.same_key != enums.SameKey.stack
        ):
            reason = 'SFZ group polyphony requires stacked notes and oldest replacement'
        elif not members or len({_choke_signature(s) for s in members}) != 1:
            reason = 'SFZ polyphony requires one shared group per used voice pool'
        elif oversized_batch(members, maximum):
            reason = 'SFZ polyphony limit can reject simultaneous region layers'
        else:
            result[pool.name] = maximum
            if overflow == 'diagnose':
                reason = (
                    'Pass polyphony_overflow=oldest_immediate '
                    'to accept the SFZ group retirement rule'
                )
        if reason is not None:
            _issue(issues, f'body.voice_pools[{i}]', pool, reason)
    return result


def _choke_signature(slot: SampleSlot) -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            (c.group, c.mode.value)
            for c in slot.chokes
            if c.mode != enums.ChokeMode.fade
        )
    )


def _choke_groups(
    document: SampleInstrumentScore,
    limits: dict[str, int],
    issues: list[UnimplementedFeature],
) -> tuple[dict[str, int], dict[str, tuple[int, enums.ChokeMode]]]:
    signatures: dict[tuple[str | None, tuple[tuple[str, str], ...]], int] = {}
    groups: dict[str, int] = {}
    for slot in document.body.slots:
        pool = slot.voice_pool if slot.voice_pool in limits else None
        signature = _choke_signature(slot)
        if pool is not None or signature:
            key = pool, signature
            if key not in signatures:
                signatures[key] = len(signatures) + 1
            groups[slot.name] = signatures[key]
    incoming: dict[str, set[tuple[int, enums.ChokeMode]]] = {}
    for slot in document.body.slots:
        for choke in slot.chokes:
            if choke.mode != enums.ChokeMode.fade:
                incoming.setdefault(choke.group, set()).add(
                    (groups[slot.name], choke.mode)
                )
    victims: dict[str, tuple[int, enums.ChokeMode]] = {}
    for group, rules in incoming.items():
        if len(rules) == 1:
            victims[group] = next(iter(rules))
        else:
            for i, slot in enumerate(document.body.slots):
                if slot.choke_group == group:
                    _issue(
                        issues,
                        f'body.slots[{i}].choke_group',
                        group,
                        'SFZ off_by cannot express multiple triggering groups or modes',
                    )
    return groups, victims


def _choking(
    slot: SampleSlot,
    path: str,
    groups: dict[str, int],
    victims: dict[str, tuple[int, enums.ChokeMode]],
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    result: list[Opcode] = []
    if slot.name in groups:
        result.append(Opcode(name='group', value=str(groups[slot.name])))
    if slot.choke_group in victims:
        off_by, mode = victims[slot.choke_group]
        result.extend(
            [
                Opcode(name='off_by', value=str(off_by)),
                Opcode(
                    name='off_mode',
                    value='fast' if mode == enums.ChokeMode.immediate else 'normal',
                ),
            ]
        )
    for i, choke in enumerate(slot.chokes):
        if choke.mode == enums.ChokeMode.fade:
            _issue(
                issues,
                f'{path}.chokes[{i}]',
                choke,
                'Timed instrument fade choking has no exact SFZ off_mode',
            )
    return result


def _playback_opcodes(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    instrument = document.body.settings.playback
    value = slot.playback
    sample_slice = next(s for s in document.body.slices if s.name == slot.slice)
    direction = value.direction if value.direction is not None else instrument.direction
    direction_path = (
        f'{path}.playback.direction'
        if value.direction is not None
        else 'body.settings.playback.direction'
    )
    mode = value.mode if value.mode is not None else instrument.mode
    result: list[Opcode] = []
    if direction == enums.Direction.backward:
        result.append(Opcode(name='direction', value='reverse'))
    elif direction == enums.Direction.mirror:
        _issue(
            issues,
            direction_path,
            direction,
            'Mirror traversal has no exact SFZ direction',
        )
    if sample_slice.start_frame:
        result.append(Opcode(name='offset', value=str(sample_slice.start_frame)))
    if sample_slice.end_frame is not None:
        result.append(
            Opcode(name='end', value=str(_inclusive_end(sample_slice.end_frame)))
        )
    if sample_slice.loop is not None:
        loop = sample_slice.loop
        result.extend(
            [
                Opcode(
                    name='loop_mode',
                    value=(
                        'loop_continuous'
                        if loop.mode == enums.LoopMode.through_release
                        else 'loop_sustain'
                    ),
                ),
                Opcode(name='loop_start', value=str(loop.start_frame)),
                Opcode(name='loop_end', value=str(_inclusive_end(loop.end_frame))),
            ]
        )
        if loop.repeat_count is not None:
            result.append(Opcode(name='loop_count', value=str(loop.repeat_count)))
        if loop.direction != enums.Direction.forward:
            result.append(
                Opcode(
                    name='loop_type',
                    value=(
                        'backward'
                        if loop.direction == enums.Direction.backward
                        else 'alternate'
                    ),
                )
            )
        if loop.crossfade_frames:
            _issue(
                issues,
                f'{path}.playback.loop.crossfade_frames',
                loop.crossfade_frames,
                'Loop crossfade frames have no exact implemented SFZ conversion',
            )
    else:
        result.append(
            Opcode(
                name='loop_mode',
                value='one_shot' if mode == enums.PlaybackMode.one_shot else 'no_loop',
            )
        )
    if value.play_count is not None:
        if value.play_count > 2**32:
            _issue(
                issues,
                f'{path}.playback.play_count',
                value.play_count,
                'SFZ count exceeds its supported range',
            )
        else:
            result.append(Opcode(name='count', value=str(value.play_count)))
    if value.start_delay_seconds:
        if (
            mode == enums.PlaybackMode.one_shot
            and slot.trigger == enums.TriggerKind.start
        ):
            _issue(
                issues,
                f'{path}.playback.start_delay_seconds',
                value.start_delay_seconds,
                'SFZ one-shot delayed note-off behavior differs between players',
            )
        elif value.start_delay_seconds > 100:
            _issue(
                issues,
                f'{path}.playback.start_delay_seconds',
                value.start_delay_seconds,
                'SFZ delay exceeds 100 seconds',
            )
        else:
            result.append(Opcode(name='delay', value=str(value.start_delay_seconds)))
    if value.end_fade_seconds:
        result.append(
            Opcode(name='sample_fadeout', value=_number_text(value.end_fade_seconds))
        )
    return result


def _playback_variation_opcodes(
    document: SampleInstrumentScore, slot: SampleSlot, sample: playback.Slice
) -> list[Opcode]:
    defaults = document.body.settings.playback
    settings = slot.playback
    result: list[Opcode] = []
    if (
        (delay := slot.variation.delay_seconds)
        and delay + settings.start_delay_seconds <= 100
        and (settings.mode or defaults.mode) != enums.PlaybackMode.one_shot
        and settings.play_count is None
    ):
        result.append(Opcode(name='delay_random', value=_number_text(delay)))
    if (
        0 < (offset := slot.variation.offset_frames) <= 2**31 - 1
        and sample.start_frame + offset < sample.end_frame
        and sample.loop is None
        and (settings.direction or defaults.direction) == enums.Direction.forward
    ):
        result.append(Opcode(name='offset_random', value=str(offset)))
    return result


def _variation_base(
    midpoint: float,
    half_range: float,
    minimum: float,
    maximum: float,
    max_depth: float,
    *,
    integral: bool = False,
) -> tuple[float, float] | None:
    if not 0 < 2 * half_range <= max_depth:
        return None
    # Either orientation of the SFZ interval produces the same native draw.
    for half in (half_range, -half_range):
        for authored in nearby_values(midpoint - half):
            if (
                minimum <= authored <= maximum
                and (not integral or authored == round(authored))
                and authored + half == midpoint
            ):
                return authored, 2 * half
    return None


def _processing_opcodes(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
    seeded_variation: bool,
) -> list[Opcode]:
    instrument = document.body.settings.processing
    local = slot.processing
    volume = instrument.volume_db + local.volume_db
    tuning = instrument.tuning_cents + local.tuning_cents
    if slot.mapping.pitch_tracking:
        assert slot.mapping.reference_pitch_hz is not None
        assert (key := _pitch_key(slot.mapping.reference_pitch_hz)) is not None
        reference = 440.0 * 2 ** ((key - 69) / 12)
        tuning += 1200 * math.log2(slot.mapping.reference_pitch_hz / reference)
    elif slot.mapping.reference_pitch_hz is not None:
        _issue(
            issues,
            f'{path}.mapping.reference_pitch_hz',
            slot.mapping.reference_pitch_hz,
            'An untracked SFZ region cannot retain a reference pitch as metadata',
        )
    result: list[Opcode] = []
    if seeded_variation:
        if (
            gain := _variation_base(volume, slot.variation.gain_db, -144, 6, 24)
        ) is not None:
            volume, depth = gain
            result.append(Opcode(name='amp_random', value=_number_text(depth)))
        if (
            pitch := _variation_base(
                tuning, slot.variation.pitch_cents, -12800, 12800, 12000, integral=True
            )
        ) is not None:
            tuning, depth = pitch
            result.append(Opcode(name='pitch_random', value=_number_text(depth)))
    if not -144 <= volume <= 6:
        _issue(
            issues,
            f'{path}.processing.volume_db',
            volume,
            'Combined volume exceeds the SFZ range [-144, 6] dB',
        )
    elif volume:
        result.append(Opcode(name='volume', value=_number_text(volume)))
    if instrument.invert_polarity != local.invert_polarity:
        result.append(Opcode(name='phase', value='invert'))
    if tuning:
        nearest_cent = round(tuning)
        if tuning != nearest_cent:
            _issue(
                issues,
                f'{path}.processing.tuning_cents',
                tuning,
                'SFZ tuning has integral-cent resolution',
            )
        elif not -12800 <= nearest_cent <= 12800:
            _issue(
                issues,
                f'{path}.processing.tuning_cents',
                tuning,
                'Combined tuning exceeds SFZ transpose and tune ranges',
            )
        else:
            transpose = max(-127, min(127, round(nearest_cent / 100)))
            residual = nearest_cent - 100 * transpose
            if transpose:
                result.append(Opcode(name='transpose', value=str(transpose)))
            if residual:
                result.append(Opcode(name='tune', value=_number_text(residual)))
    pan = instrument.pan + local.pan
    balance = instrument.stereo_balance + local.stereo_balance
    if pan and balance:
        _issue(
            issues,
            f'{path}.processing',
            {'pan': pan, 'stereo_balance': balance},
            'One SFZ pan opcode cannot distinguish simultaneous pan and balance',
        )
    elif pan or balance:
        result.append(
            Opcode(
                name='pan',
                value=_number_text(100 * (pan or balance)),
            )
        )
    for i, band in enumerate(local.equalizer):
        _issue(
            issues,
            f'{path}.processing.equalizer[{i}]',
            band,
            'Instrument equalizer bands have no implemented SFZ conversion',
        )
    return result


def _envelope_opcodes(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
) -> tuple[list[Opcode], list[modulation.Route]]:
    value = slot.envelope or document.body.settings.envelope
    envelope_path = (
        f'{path}.envelope' if slot.envelope is not None else 'body.settings.envelope'
    )
    finite = [s for s in value.segments if isinstance(s, segments.Segment)]
    release = [s for s in value.release if isinstance(s, ExponentialApproach)]
    initial = value.initial
    representable = (
        value.clock == Clock.seconds
        and value.scope == Scope.voice
        and isinstance(initial, float)
        and 0 <= initial <= 1
        and value.start == 'activation'
        and value.playback == envelfo.PlaybackMode.once
        and value.position_driver == envelfo.PositionDriver.elapsed
        and not value.markers
        and value.hold
        and value.retrigger == envelope.Retrigger.current
        and len(finite) == len(value.segments) == 4
        and len(release) == len(value.release) == 1
    )
    if representable:
        representable = (
            [s.to for s in finite[:3]] == [value.initial, 1, 1]
            and [s.curve for s in finite] == [0, 0, 0, -5]
            and release[0].asymptote == 0
            and release[0].threshold == 0.0001
            and release[0].transition_to == 0
            and release[0].transition_seconds == 0.05
            and release[0].minimum_transition_distance == 0.0001
            and release[0].minimum_time_constant == 0.006 / 9
        )
    if not representable:
        _issue(
            issues,
            envelope_path,
            value,
            'SFZ requires a seconds-based delay/attack/hold/decay envelope '
            'with linear attack, curved decay and a captured exponential release',
        )
        return [], []
    assert isinstance(initial, float)
    values = dict(
        zip(
            ('ampeg_delay', 'ampeg_attack', 'ampeg_hold', 'ampeg_decay'),
            (float(s.duration) for s in finite),
            strict=True,
        )
    )
    values['ampeg_sustain'] = finite[-1].to * 100
    if initial:
        values['ampeg_start'] = initial * 100
    constant = release[0].time_constant
    release_seconds = constant * 9
    values['ampeg_release'] = (
        inverse_value(release_seconds, lambda n: n / 9, constant, 0, math.inf)
        or release_seconds
    )
    routes: list[modulation.Route] = []
    for name, parameter in (
        ('delay', 'on-0-duration'),
        ('attack', 'on-1-duration'),
        ('hold', 'on-2-duration'),
        ('decay', 'on-3-duration'),
        ('release', 'release-0-time_constant'),
    ):
        base = constant if name == 'release' else values[f'ampeg_{name}']
        target = modulation.Target(name='envelope', parameter=parameter)
        route = _envelope_velocity_route(slot, target, base)
        if route is None:
            continue
        amount = route.points[1].amount
        if name == 'release':
            amount = inverse_value(amount * 9, lambda n: n / 9, amount, -100, 100)
        if (
            amount is not None
            and -100 <= amount <= 100
            and values[f'ampeg_{name}'] + amount >= 0
        ):
            values[f'ampeg_vel2{name}'] = amount
            routes.append(route)
    return [Opcode(name=n, value=_number_text(v)) for n, v in values.items()], routes


def _envelope_velocity_route(
    slot: SampleSlot, target: modulation.Target, base: float
) -> modulation.Route | None:
    routes = [r for r in slot.modulation.routes if r.target == target]
    if len(routes) != 1:
        return None
    route = routes[0]
    if (
        route.operation != modulation.Operation.add
        or route.unit != modulation.Unit.seconds
        or route.interpolation != modulation.Interpolation.linear
        or [p.input for p in route.points] != [0, 1]
        or route.points[0].amount != 0
        or not _event_source(slot, route, 'velocity', 1)
    ):
        return None
    end = base + route.points[1].amount
    if not math.isfinite(end):
        return None
    parameter = modulation.Parameter(
        target=target,
        unit=modulation.Unit.seconds,
        scope=Scope.voice,
        minimum=min(base, end),
        maximum=max(base, end),
        default=base,
    )
    return route if parameter in slot.modulation.parameters else None


def _filter_opcodes(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
) -> tuple[list[Opcode], list[modulation.Route], set[str]]:
    local = slot.processing
    common = document.body.settings.processing
    filters = [
        *((f, f'{path}.processing.filters[{i}]') for i, f in enumerate(local.filters)),
        *(
            (f, f'body.settings.processing.filters[{i}]')
            for i, f in enumerate(common.filters)
        ),
    ]
    if not filters:
        return [], [], set()
    output_rate = _output_rate(document)
    upper = cutoff_limit(output_rate)
    order = local.filter_order if local.filters else common.filter_order
    values: dict[str, str] = {}
    for index, (filter, location) in enumerate(filters):
        response = next(
            (n for n, r in FILTER_RESPONSES.items() if r == filter.response), None
        )
        resonance = inverse_value(
            20 * math.log10(filter.q), lambda n: 10 ** (n / 20), filter.q, 0, 40
        )
        canonical = processing.ResonantFilter(
            name=filter.name,
            response=filter.response,
            cutoff_hz=filter.cutoff_hz,
            q=filter.q,
        )
        reason = None
        if len(filters) > 2:
            reason = 'SFZ supports at most two ordered filters'
        elif order != processing.FilterOrder.after_amplitude:
            reason = 'SFZ requires filters after the amplitude envelope'
        elif response is None or filter != canonical:
            reason = (
                'Filter does not use a supported single two-pole response and bounds'
            )
        elif not 1 <= filter.cutoff_hz <= upper or resonance is None:
            reason = 'Filter cutoff or resonance is outside the verified SFZ profile'
        if reason is not None:
            _issue(issues, location, filter, reason)
            continue
        assert response is not None and resonance is not None
        suffix = '2' if index else ''
        values[f'fil{suffix}_type'] = response
        values[f'cutoff{suffix}'] = _number_text(filter.cutoff_hz)
        values[f'resonance{suffix}'] = _number_text(resonance)
    if len(values) != 3 * len(filters):
        return [], [], set()
    generators: set[str] = set()
    exported_routes: list[modulation.Route] = []
    if slot.trigger in (
        enums.TriggerKind.start,
        enums.TriggerKind.release,
        enums.TriggerKind.logical_release,
    ):
        for index, (filter, _) in enumerate(filters):
            prefix = 'fil2' if index else 'fil'
            tracking, routes, references = _filter_cutoff_opcodes(
                slot, filter, prefix, output_rate
            )
            values.update(tracking)
            exported_routes.extend(routes)
            generators.update(references)
    return (
        [Opcode(name=n, value=v) for n, v in values.items()],
        exported_routes,
        generators,
    )


def _filter_cutoff_opcodes(
    slot: SampleSlot,
    filter: processing.ResonantFilter,
    prefix: str,
    output_rate: float,
) -> tuple[dict[str, str], list[modulation.Route], set[str]]:
    target = modulation.Target(name=f'filter-{filter.name}', parameter='cutoff_hz')
    routes = [r for r in slot.modulation.routes if r.target == target]
    if not routes:
        return {}, [], set()
    generators: set[str] = set()
    values: dict[str, str] = {}
    bounds: dict[str, tuple[float, float]] = {}
    cutoff = filter.cutoff_hz
    low = high = cutoff
    upper = cutoff_limit(output_rate)
    for route in routes:
        minimum = min(p.amount for p in route.points)
        maximum = max(p.amount for p in route.points)
        if not 1 <= cutoff * minimum <= cutoff * maximum <= upper:
            return {}, [], set()
        if (key := _filter_key_tracking(slot, route)) is not None:
            tracking, center = key
            values[f'{prefix}_keytrack'] = str(tracking)
            values[f'{prefix}_keycenter'] = str(center)
            kind = 'key'
        elif _filter_exponential_route(route):
            if slot.trigger != enums.TriggerKind.start:
                return {}, [], set()
            if (depth := _filter_velocity_depth(slot, route)) is not None:
                values[f'{prefix}_veltrack'] = str(depth)
                kind = 'velocity'
            elif prefix == 'fil':
                envelope, generator = _filter_envelope_export(slot, route, output_rate)
                if generator is None:
                    return {}, [], set()
                values.update(envelope)
                generators.add(generator.reference)
                kind = 'envelope'
            else:
                return {}, [], set()
        elif (
            prefix == 'fil'
            and (lfo := _lfo_export(slot, route, 'fillfo', output_rate)) is not None
        ):
            opcodes, reference, _ = lfo
            values.update(opcodes)
            generators.add(reference)
            kind = 'lfo'
        else:
            return {}, [], set()
        if kind in bounds:
            return {}, [], set()
        bounds[kind] = minimum, maximum
    for kind in ('key', 'velocity', 'envelope', 'lfo'):
        if kind in bounds:
            minimum, maximum = bounds[kind]
            low *= minimum
            high *= maximum
    if not 1 <= low <= high <= upper:
        return {}, [], set()
    parameter = modulation.Parameter(
        target=target,
        unit=modulation.Unit.hz,
        scope=Scope.voice,
        minimum=min(cutoff, low),
        maximum=max(cutoff, high),
        default=cutoff,
    )
    if parameter not in slot.modulation.parameters:
        return {}, [], set()
    return values, routes, generators


def _filter_key_tracking(
    slot: SampleSlot, route: modulation.Route
) -> tuple[int, int] | None:
    keys = range(slot.mapping.lowest_key, slot.mapping.highest_key + 1)
    if (
        route.operation != modulation.Operation.multiply
        or route.unit != modulation.Unit.ratio
        or route.interpolation != modulation.Interpolation.linear
        or [p.input for p in route.points] != list(keys)
        or any(p.amount <= 0 for p in route.points)
        or not any(b.name == route.source and b.kind == 'key' for b in slot.bindings)
        or modulation.Source(name=route.source, scope='voice', minimum=0, maximum=127)
        not in slot.modulation.sources
    ):
        return None
    offset = round(1200 * math.log2(route.points[0].amount))
    if len(keys) == 1:
        if route.points[0].amount == 1:
            return 100, keys.start
        candidates = [
            (offset // (keys.start - c), c)
            for c in sorted(range(128), key=lambda k: abs(k - 60))
            if c != keys.start and offset % (keys.start - c) == 0
        ]
    else:
        tracking = round(
            (1200 * math.log2(route.points[-1].amount) - offset) / (len(keys) - 1)
        )
        if not 1 <= tracking <= 1200 or offset % tracking:
            return None
        candidates = [(tracking, keys.start - offset // tracking)]
    return next(
        (
            (t, c)
            for t, c in candidates
            if 1 <= t <= 1200
            and 0 <= c <= 127
            and all(
                2 ** (t * (k - c) / 1200) == p.amount
                for k, p in zip(keys, route.points, strict=True)
            )
        ),
        None,
    )


def _filter_exponential_route(route: modulation.Route) -> bool:
    return (
        route.operation == modulation.Operation.multiply
        and route.unit == modulation.Unit.ratio
        and route.interpolation == modulation.Interpolation.exponential
        and len(route.points) == 2
        and route.points[0] == modulation.Point(input=0, amount=1)
        and route.points[1].input == 1
        and route.points[1].amount != 1
    )


def _filter_velocity_depth(slot: SampleSlot, route: modulation.Route) -> int | None:
    if (
        not any(b.name == route.source and b.kind == 'velocity' for b in slot.bindings)
        or modulation.Source(name=route.source, scope='voice', minimum=0, maximum=1)
        not in slot.modulation.sources
    ):
        return None
    ratio = route.points[1].amount
    depth = round(1200 * math.log2(ratio))
    if -9600 <= depth <= 9600 and depth and 2 ** (depth / 1200) == ratio:
        return depth
    return None


def _filter_envelope_export(
    slot: SampleSlot,
    route: modulation.Route,
    output_rate: float,
) -> tuple[dict[str, str], processing.GeneratorBinding | None]:
    if (
        slot.event_connections
        or modulation.Source(name=route.source, scope='voice', minimum=0, maximum=1)
        not in slot.modulation.sources
        or sum(r.source == route.source for r in slot.modulation.routes) != 1
    ):
        return {}, None
    binding = next((b for b in slot.bindings if b.name == route.source), None)
    if (
        not isinstance(binding, processing.GeneratorBinding)
        or binding.output is not None
        or binding.release_timing != processing.ReleaseTiming.voice
        or sum(
            isinstance(b, processing.GeneratorBinding)
            and b.reference == binding.reference
            for b in slot.bindings
        )
        != 1
    ):
        return {}, None
    body = slot.envelfos.get(binding.reference)
    if not isinstance(body, envelfo.Envelope):
        return {}, None
    if any(
        p.target.name == f'envelfo-{binding.reference}'
        for p in slot.modulation.parameters
    ):
        return {}, None
    ratio = route.points[1].amount
    depth = inverse_value(
        1200 * math.log2(ratio), lambda n: 2 ** (n / 1200), ratio, -12000, 12000
    )
    if depth is None or (values := filter_envelope_values(body, output_rate)) is None:
        return {}, None
    return values | {'fileg_depth': _number_text(depth)}, binding


def _lfo_export(
    slot: SampleSlot, route: modulation.Route, prefix: str, output_rate: float
) -> tuple[dict[str, str], str, float] | None:
    if (
        slot.trigger != enums.TriggerKind.start
        or slot.control_trigger is not None
        or slot.event_connections
        or sum(r.source == route.source for r in slot.modulation.routes) != 1
        or [p.input for p in route.points] != [-1, 1]
    ):
        return None
    extent = 1 if prefix == 'fillfo' else 2
    if (
        modulation.Source(
            name=route.source, scope='voice', minimum=-extent, maximum=extent
        )
        not in slot.modulation.sources
    ):
        return None
    negative, positive = (p.amount for p in route.points)
    if prefix == 'pitchlfo':
        if (
            route.operation != modulation.Operation.add
            or route.unit != modulation.Unit.cents
            or route.interpolation != modulation.Interpolation.linear
            or negative != -positive
            or not 0 < abs(positive) <= 1200
        ):
            return None
        depth = positive
    else:
        if (
            route.operation != modulation.Operation.multiply
            or route.unit != modulation.Unit.ratio
            or route.interpolation != modulation.Interpolation.exponential
        ):
            return None
        base, scale, limit = (10, 20, 10) if prefix == 'amplfo' else (2, 1200, 1200)
        logarithm = math.log10 if prefix == 'amplfo' else math.log2
        estimate = scale * (logarithm(positive) - logarithm(negative)) / 2
        depth = next(
            (
                d
                for d in nearby_values(estimate)
                if 0 < abs(d) <= limit
                and base ** (d / scale) == positive
                and base ** (-d / scale) == negative
            ),
            None,
        )
        if depth is None:
            return None
    binding = next((b for b in slot.bindings if b.name == route.source), None)
    if (
        not isinstance(binding, processing.GeneratorBinding)
        or binding.release_timing != processing.ReleaseTiming.event
        or sum(
            isinstance(b, processing.GeneratorBinding)
            and b.reference == binding.reference
            for b in slot.bindings
        )
        != 1
        or any(
            p.target.name == f'envelfo-{binding.reference}'
            for p in slot.modulation.parameters
        )
    ):
        return None
    body = slot.envelfos.get(binding.reference)
    if body is None or binding.output != (
        'signal' if isinstance(body, envelfo.Patch) else None
    ):
        return None
    values = lfo_values(body, prefix, output_rate)
    if values is None:
        return None
    return values | {f'{prefix}_depth': _number_text(depth)}, binding.reference, depth


def _processing_lfo_export(
    document: SampleInstrumentScore, slot: SampleSlot, route: modulation.Route
) -> tuple[dict[str, str], str] | None:
    if route.target != modulation.Target(name='processing', parameter='amplitude'):
        return None
    if (lfo := _lfo_export(slot, route, 'amplfo', _output_rate(document))) is None:
        return None
    values, reference, depth = lfo
    others = [
        r for r in slot.modulation.routes if r.target == route.target and r != route
    ]
    if len(others) > 1 or any(not _amplitude_velocity_route(slot, r) for r in others):
        return None
    parameter = modulation.Parameter(
        target=route.target,
        unit=modulation.Unit.ratio,
        scope=Scope.voice,
        minimum=0,
        maximum=10 ** (abs(depth) / 20),
        default=1,
    )
    return (values, reference) if parameter in slot.modulation.parameters else None


def _pitch_modulation_export(
    document: SampleInstrumentScore, slot: SampleSlot, bend_control: str | None
) -> tuple[dict[str, str], list[modulation.Route], str | None]:
    target = modulation.Target(name='processing', parameter='tuning_cents')
    routes = [r for r in slot.modulation.routes if r.target == target]
    if not routes or document.body.settings.processing.tuning_cents:
        return {}, [], None
    center = _pitch_key(slot.mapping.reference_pitch_hz)
    if slot.mapping.pitch_tracking and (
        center is None
        or slot.mapping.reference_pitch_hz != 440.0 * 2 ** ((center - 69) / 12)
    ):
        return {}, [], None
    values: dict[str, str] = {}
    generator = None
    for route in routes:
        if (
            route.operation != modulation.Operation.add
            or route.unit != modulation.Unit.cents
            or route.interpolation != modulation.Interpolation.linear
        ):
            return {}, [], None
        if len(route.points) == 4 and 'bend_up' not in values:
            bend = _pitch_bend_export(slot, route, bend_control)
            if bend is not None:
                values.update(bend)
                continue
        if len(route.points) != 2:
            return {}, [], None
        start, end = route.points
        if (
            (start.input, end.input) == (0, 1)
            and start.amount == 0
            and 0 < abs(end.amount) <= 9600
            and end.amount == round(end.amount)
            and _event_source(slot, route, 'velocity', 1)
            and 'pitch_veltrack' not in values
        ):
            values['pitch_veltrack'] = _number_text(end.amount)
        elif (
            center is not None
            and slot.mapping.pitch_tracking
            and (start.input, end.input) == (0, 127)
            and _event_source(slot, route, 'key', 127)
            and 'pitch_keytrack' not in values
        ):
            if max(abs(start.amount), abs(end.amount)) > 1300 * 127:
                return {}, [], None
            delta = round((end.amount - start.amount) / 127)
            tracking = 100 + delta
            if (
                not -1200 <= tracking <= 1200
                or tracking in (0, 100)
                or start.amount != -center * delta
                or end.amount != (127 - center) * delta
            ):
                return {}, [], None
            values['pitch_keytrack'] = str(tracking)
        elif (
            generator is None
            and (lfo := _lfo_export(slot, route, 'pitchlfo', _output_rate(document)))
            is not None
        ):
            opcodes, generator, _ = lfo
            values.update(opcodes)
        else:
            return {}, [], None
    base = slot.processing.tuning_cents
    parameter = modulation.Parameter(
        target=target,
        unit=modulation.Unit.cents,
        scope=Scope.voice,
        minimum=base + sum(min(0, *(p.amount for p in r.points)) for r in routes),
        maximum=base + sum(max(0, *(p.amount for p in r.points)) for r in routes),
        default=base,
    )
    if parameter not in slot.modulation.parameters:
        return {}, [], None
    return values, routes, generator


def _pitch_bend_export(
    slot: SampleSlot, route: modulation.Route, control: str | None
) -> dict[str, str] | None:
    if (
        control is None
        or slot.trigger != enums.TriggerKind.start
        or processing.ControlBinding(name=route.source, control=control, smoothing=0)
        not in slot.bindings
        or modulation.Source(name=route.source, scope='part', minimum=-1, maximum=1)
        not in slot.modulation.sources
        or [p.input for p in route.points] != [-1, -8191 / 8192, 0, 1]
    ):
        return None
    down, plateau, center, up = (p.amount for p in route.points)
    if down != plateau or center or max(abs(up), abs(down)) > 12000:
        return None
    return {'bend_down': _number_text(down), 'bend_up': _number_text(up)}


def _event_source(
    slot: SampleSlot, route: modulation.Route, kind: str, maximum: int
) -> bool:
    return (
        any(b.name == route.source and b.kind == kind for b in slot.bindings)
        and modulation.Source(
            name=route.source, scope='voice', minimum=0, maximum=maximum
        )
        in slot.modulation.sources
    )


def _amplitude_velocity_route(slot: SampleSlot, route: modulation.Route) -> bool:
    return (
        route.target == modulation.Target(name='processing', parameter='amplitude')
        and any(b.name == route.source and b.kind == 'velocity' for b in slot.bindings)
        and route.operation == modulation.Operation.multiply
        and route.interpolation == modulation.Interpolation.linear
        and all(_velocity_number(p.input) is not None for p in route.points)
        and all(0 <= p.amount <= 1 for p in route.points)
    )


def _key_gain_export(
    document: SampleInstrumentScore, slot: SampleSlot, route: modulation.Route
) -> tuple[Opcode, Opcode] | None:
    if (
        route.target != modulation.Target(name='processing', parameter='volume_db')
        or route.operation != modulation.Operation.add
        or route.unit != modulation.Unit.db
        or route.interpolation != modulation.Interpolation.linear
        or [p.input for p in route.points] != [0, 127]
        or not _event_source(slot, route, 'key', 127)
        or document.body.settings.processing.volume_db
        or sum(r.target == route.target for r in slot.modulation.routes) != 1
    ):
        return None
    left, right = (p.amount for p in route.points)
    if left == right or max(abs(left), abs(right)) > 96 * 127:
        return None
    estimate = (right - left) / 127
    if estimate == 0:
        return None
    pivot = -left / estimate
    if not -0.5 <= pivot <= 127.5:
        return None
    center = round(pivot)
    if center == 128:
        return None
    endpoint = 127 - center if center < 64 else -center
    amount = right if center < 64 else left
    depth = next(
        (
            n
            for n in nearby_values(amount / endpoint)
            if -96 <= n <= 12 and -center * n == left and (127 - center) * n == right
        ),
        None,
    )
    base = slot.processing.volume_db
    parameter = modulation.Parameter(
        target=route.target,
        unit=modulation.Unit.db,
        scope=Scope.voice,
        minimum=base + min(0, left, right),
        maximum=base + max(0, left, right),
        default=base,
    )
    if depth is None or parameter not in slot.modulation.parameters:
        return None
    return (
        Opcode(name='amp_keycenter', value=str(center)),
        Opcode(name='amp_keytrack', value=_number_text(depth)),
    )


def _modulation_opcodes(
    document: SampleInstrumentScore,
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
    exported_routes: list[modulation.Route],
    generators: set[str],
    bend_control: str | None,
) -> list[Opcode]:
    supported: list[modulation.Route] = []
    pitch, pitch_routes, generator = _pitch_modulation_export(
        document, slot, bend_control
    )
    if generator is not None:
        generators.add(generator)
    result = [Opcode(name=n, value=v) for n, v in pitch.items()]
    for i, curve in enumerate(slot.modulation.routes):
        if curve in exported_routes or curve in pitch_routes:
            continue
        if _amplitude_velocity_route(slot, curve):
            supported.append(curve)
            continue
        if (gain := _key_gain_export(document, slot, curve)) is not None:
            result.extend(gain)
            continue
        if (lfo := _processing_lfo_export(document, slot, curve)) is not None:
            values, reference = lfo
            generators.add(reference)
            result.extend(Opcode(name=n, value=v) for n, v in values.items())
        else:
            _issue(
                issues,
                f'{path}.modulation.routes[{i}]',
                curve,
                'Modulation route has no implemented exact SFZ mapping',
            )
    if len(supported) > 1:
        for curve in supported:
            _issue(
                issues,
                f'{path}.modulation',
                curve,
                'Multiple amplitude curves cannot share one SFZ amp_veltrack',
            )
        return [*result, Opcode(name='amp_veltrack', value='0')]
    if not supported:
        return [*result, Opcode(name='amp_veltrack', value='0')]
    result.append(Opcode(name='amp_veltrack', value='100'))
    for point in supported[0].points:
        velocity = _velocity_number(point.input)
        assert velocity is not None
        result.append(
            Opcode(name=f'amp_velcurve_{velocity}', value=_number_text(point.amount))
        )
    return result


def _crossfade_opcodes(
    slot: SampleSlot,
    path: str,
    controllers: dict[str, int],
    response: Literal['diagnose', 'portable_ramp'],
    issues: list[UnimplementedFeature],
) -> list[Opcode]:
    result: list[Opcode] = []
    curves: dict[str, enums.FadeCurve] = {}
    for i, fade in enumerate(slot.crossfades):
        cc_number = ''
        if isinstance(fade, crossfade.ControlCrossfade):
            number = controllers.get(fade.control)
            start, end = map(_velocity_number, (fade.start, fade.end))
            if (
                number is None
                or response != 'portable_ramp'
                or fade.scope != 'part'
                or fade.smoothing_seconds != 0.005
                or fade.curve != enums.FadeCurve.linear
                or start is None
                or end is None
                or not 0 <= start < end <= 127
                or (fade.start, fade.end) != (start / 127, end / 127)
            ):
                _issue(
                    issues,
                    f'{path}.crossfades[{i}]',
                    fade,
                    'SFZ CC crossfade requires a bound 7-bit CC '
                    'and the portable ramp profile',
                )
                continue
            suffix, cc_number = 'cc', str(number)
        elif fade.input == enums.CrossfadeInput.velocity:
            start = _velocity_number(fade.start)
            end = _velocity_number(fade.end)
            if start is None or end is None:
                _issue(
                    issues,
                    f'{path}.crossfades[{i}]',
                    fade,
                    'SFZ velocity crossfades require integer multiples of 1/127',
                )
                continue
            suffix = 'vel'
        else:
            start, end, suffix = fade.start, fade.end, 'key'
        if suffix in curves and curves[suffix] != fade.curve:
            _issue(
                issues,
                f'{path}.crossfades[{i}].curve',
                fade.curve,
                'SFZ permits only one crossfade curve per input in a region',
            )
            continue
        curves[suffix] = fade.curve
        prefix = 'xfin' if fade.direction == enums.FadeDirection.fade_in else 'xfout'
        result.extend(
            [
                Opcode(name=f'{prefix}_lo{suffix}{cc_number}', value=str(start)),
                Opcode(name=f'{prefix}_hi{suffix}{cc_number}', value=str(end)),
            ]
        )
    for suffix, curve in curves.items():
        result.append(
            Opcode(
                name=f'xf_{suffix}curve',
                value='gain' if curve == enums.FadeCurve.linear else 'power',
            )
        )
    return result


def _slot_issues(
    slot: SampleSlot,
    path: str,
    issues: list[UnimplementedFeature],
    exported_generators: set[str] | None = None,
) -> None:
    for name in ('take', 'microphone', 'alignment_frames'):
        if value := getattr(slot, name):
            _issue(
                issues,
                f'{path}.{name}',
                value,
                'Linked microphone takes have no exact SFZ conversion',
            )
    if slot.selection:
        _issue(
            issues,
            f'{path}.selection',
            slot.selection,
            'SFZ alternate-selection behavior is not represented',
        )
    for name, value in slot.envelfos.items():
        if exported_generators is not None and name in exported_generators:
            continue
        _issue(
            issues,
            f'{path}.envelfos.{name}',
            value,
            'Envelfo has no implemented exact SFZ region mapping',
        )


def _pitch_key(value: float | None) -> int | None:
    if value is None:
        return None
    key = round(69 + 12 * math.log2(value / 440))
    return key if 0 <= key <= 127 else None


def _output_rate(document: SampleInstrumentScore) -> float:
    output = next(p.stream for p in document.outputs if isinstance(p.stream, AudioType))
    rate = next(t.rate for t in document.timebases if t.name == output.timebase)
    return rate.numerator / rate.denominator


def _velocity_number(value: object) -> int | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    scaled = value * 127
    rounded = round(scaled)
    return rounded if math.isclose(scaled, rounded, rel_tol=0, abs_tol=1e-12) else None


def _inclusive_end(value: int) -> int:
    return value - 1


def _number_text(value: object) -> str:
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    number = float(value)
    if number == 0:
        return '0'
    if number.is_integer():
        return str(int(number))
    return repr(number)


def _safe_sample(value: str) -> bool:
    return _safe_value(value) and not value.startswith('*')


def _safe_value(value: str) -> bool:
    return not any(token in value for token in ('\n', '\r', '//', '/*', '<', '=', '#'))


def _issue(
    issues: list[UnimplementedFeature], path: str, value: object, reason: str
) -> None:
    issue = UnimplementedFeature(
        location=InstrumentLocation(path=path),
        value=_json_value(value),
        reason=reason,
    )
    if issue not in issues:
        issues.append(issue)


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(',', ':'),
        default=_json_default,
    )


def _json_default(value: object) -> object:
    if isinstance(value, base.Model):
        return value.model_dump(mode='json')
    raise TypeError(f'Cannot serialize {type(value).__name__} as JSON')


def _json_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, base.Model):
        return value.model_dump_json(exclude_none=False)
    return _json(value)
