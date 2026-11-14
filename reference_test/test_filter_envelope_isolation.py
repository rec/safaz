"""Factor envelope and dynamic filter conventions without the offline player."""

import subprocess
from fractions import Fraction
from hashlib import sha256
from pathlib import Path

import filter_cases
import filter_envelope_oracle
import filter_oracle
import harness
import numpy as np
import pytest
import soundfile
from envelfo.runtime import envelfo_at, envelfo_event, initial_envelfo
from ufor.envelfo import EnvelfoEvent, Envelope
from ufor.samples.metadata import AudioMetadata
from ufor.time import Rate, Timebase

from safaz import compiler, parser
from safaz.model import SfzCompileResult


@pytest.mark.parametrize('name,profile', filter_cases.ENVELOPE_ISOLATION_PROFILES)
def test_imported_envelopes_match_declared_equations(
    name: str, profile: filter_envelope_oracle.EnvelopeProfile
) -> None:
    assert max(check_native_control(profile).values()) < 1e-10


@pytest.mark.parametrize('name,profile', filter_cases.ENVELOPE_ISOLATION_PROFILES)
@pytest.mark.parametrize('block', [64, 256, 257])
def test_filter_envelope_isolation(
    name: str,
    profile: filter_envelope_oracle.EnvelopeProfile,
    block: int,
    request: pytest.FixtureRequest,
    reference_output: Path,
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    executable = request.config.getoption('--sfizz-envelope-probe')
    if not executable:
        pytest.skip('Direct envelope/filter probe not configured')
    provenance = harness.verify_source(reference_paths[0])
    folder = reference_output / f'isolation-{name}-{block}'
    folder.mkdir()
    rate, frames = harness.RATE, 2 * harness.RATE
    age = np.arange(frames) / rate
    portable = filter_envelope_oracle.levels(profile, age, rate)
    source = np.where(np.arange(frames) % 96 < 48, 0.125, -0.125)
    source *= harness.MASTER_GAIN * harness.authored_pan_gains(harness.CASES[0])[0]
    trace = run_probe(
        Path(executable),
        folder,
        profile,
        block,
        source,
        portable,
        round(profile.release_at * rate),
        0,
    )
    actual = trace[:, 0]
    spec = filter_oracle.FilterSpec(response='lpf_2p', cutoff=1000)
    native = filter_oracle.apply_filters(
        source[:, None], [spec], [1000 * 2 ** (profile.depth * portable / 1200)], rate
    )[:, 0]
    native_actual = filter_oracle.apply_filters(
        source[:, None], [spec], [1000 * 2 ** (profile.depth * actual / 1200)], rate
    )[:, 0]
    # These four corners separate envelope values from filter realization.
    portable_amplitude = filter_envelope_oracle.release(
        1, age - profile.release_at, profile.amplitude_release
    )
    # ADSREnvelope advances before emitting a release sample. This is a
    # source-defined prediction, not an alignment search or acceptance offset.
    sfizz_amplitude_prediction = filter_envelope_oracle.release(
        1, age - profile.release_at + 1 / rate, profile.amplitude_release
    )
    trajectory = 1000 * 2 ** (profile.depth * portable / 1200)
    amplifier_audio = [
        filter_oracle.apply_filters((source * a)[:, None], [spec], [trajectory], rate)[
            :, 0
        ]
        for a in [portable_amplitude, trace[:, 3], sfizz_amplitude_prediction]
    ]
    soundfile.write(
        folder / 'amplifier.wav',
        np.column_stack(amplifier_audio),
        rate,
        subtype='FLOAT',
    )
    channels = np.column_stack(
        [portable, actual, native, native_actual, trace[:, 1:], portable_amplitude]
    )
    soundfile.write(folder / 'isolated.wav', channels, rate, subtype='FLOAT')
    regions = {
        'whole': np.ones(frames, dtype=bool),
        'before_release': age < profile.release_at,
        'release': age >= profile.release_at,
    }
    report = {
        'reference': provenance,
        'probe_sha256': sha256(Path(executable).read_bytes()).hexdigest(),
        'profile': profile.model_dump(mode='json'),
        'block': block,
        'source_gain': harness.MASTER_GAIN
        * harness.authored_pan_gains(harness.CASES[0])[0],
        'maximum_level_error_frame': int(np.argmax(np.abs(actual - portable))),
        'maximum_amplifier_error_frame': int(
            np.argmax(np.abs(trace[:, 3] - portable_amplitude))
        ),
        'channels': [
            'portable_level',
            'sfizz_level',
            'tpt_portable',
            'tpt_sfizz',
            'sfizz_portable',
            'sfizz_sfizz',
            'sfizz_amplitude',
            'sfizz_full',
            'portable_amplitude',
        ],
        'measurements': {
            n: {
                'envelope_maximum_error': float(
                    np.max(np.abs(actual[m] - portable[m]))
                ),
                'amplifier_maximum_error': float(
                    np.max(np.abs(trace[m, 3] - portable_amplitude[m]))
                ),
                'envelope_only_tpt': harness.compare(native_actual[m], native[m]),
                'amplifier_only_tpt': harness.compare(
                    amplifier_audio[1][m], amplifier_audio[0][m]
                ),
                'amplifier_advance_prediction': harness.compare(
                    amplifier_audio[1][m], amplifier_audio[2][m]
                ),
                'filter_only_portable': harness.compare(trace[m, 1], native[m]),
                'filter_only_sfizz': harness.compare(trace[m, 2], native_actual[m]),
                'combined': harness.compare(trace[m, 2], native[m]),
            }
            for n, m in regions.items()
            if np.any(m)
        },
        'native_control': check_native_control(profile),
    }
    harness.write_json(folder / 'report.json', report)
    assert np.all(np.isfinite(channels))
    assert max(report['native_control'].values()) < 1e-10
    assert harness.compare(amplifier_audio[1], amplifier_audio[2])['passed']
    if name == 'constant':
        assert np.max(np.abs(trace[:, 2] - native)) <= (
            harness.PCM_ERROR + harness.FLOAT_ERROR
        )


@pytest.mark.parametrize(
    'case',
    [c for c in filter_cases.ENVELOPE_CASES if c.name != 'filter-envelope-combined'],
    ids=lambda c: c.name,
)
def test_filter_envelope_player_resynthesis(
    case: harness.Case,
    request: pytest.FixtureRequest,
    reference_output: Path,
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    executable = request.config.getoption('--sfizz-envelope-probe')
    if not executable:
        pytest.skip('Direct envelope/filter probe not configured')
    source_root, renderer, build, _ = reference_paths
    folder = reference_output / f'resynthesis-{case.name}'
    expected = harness.create_inputs(case, folder)
    native = harness.run_native_case(case, folder, 'native', 256, expected)
    original = harness.run_reference_case(
        case, folder, renderer, source_root, build, native, expected, 256
    )
    profile = case.filter_profile
    assert profile is not None and profile.envelope is not None
    prediction = np.zeros(expected.shape)
    # sfizz_render advances fmidi's double clock before dispatch, strictly >.
    clock = np.cumsum(np.full(len(expected), 1 / harness.RATE))
    events = []
    for index, note in enumerate(case.notes):
        gate_ticks = round(profile.envelope.release_at * harness.RATE / 25)
        on, off = (
            int(np.searchsorted(clock, t * 0.5 / 960, side='right'))
            for t in [note.tick, note.tick + gate_ticks]
        )
        block_start = on // 256 * 256
        trigger_delay = on - block_start
        frames = harness.RATE + 256
        absolute = block_start + np.arange(frames)
        age = absolute - on
        # Voice::renderBlock resets age to zero after its first call;
        # fillWithData repeats the previous source sample at the next block.
        positions = age - (absolute >= block_start + 256)
        samples = np.where(positions % 96 < 48, 0.125, -0.125)
        samples[(age < 0) | (positions >= harness.RATE)] = 0
        samples *= harness.MASTER_GAIN * harness.authored_pan_gains(case)[0]
        note_folder = folder / f'probe-{index}'
        note_folder.mkdir()
        trace = run_probe(
            Path(executable),
            note_folder,
            profile.envelope,
            256,
            samples,
            np.zeros(frames),
            off - block_start,
            trigger_delay,
        )
        prediction[block_start : block_start + frames] += trace[:, 4, None]
        events.append(
            {
                'on_frame': on,
                'off_frame': off,
                'repeated_source_frame': block_start + 256,
            }
        )
    reference = soundfile.read(folder / 'reference.wav', always_2d=True)[0][
        : len(expected)
    ]
    measurement = harness.compare(prediction, reference)
    soundfile.write(
        folder / 'resynthesis.wav', prediction, harness.RATE, subtype='FLOAT'
    )
    soundfile.write(
        folder / 'resynthesis-difference.wav',
        prediction - reference,
        harness.RATE,
        subtype='FLOAT',
    )
    harness.write_json(
        folder / 'resynthesis.json',
        {
            'events': events,
            'source_model': (
                'audited client clock and single repeated source sample; '
                'no fit or alignment'
            ),
            'prediction_vs_reference': measurement,
            'native_vs_reference': original['native_vs_reference'],
        },
    )
    assert measurement['passed'], measurement


def run_probe(
    executable: Path,
    folder: Path,
    profile: filter_envelope_oracle.EnvelopeProfile,
    block: int,
    source: np.ndarray,
    portable: np.ndarray,
    gate: int,
    trigger_delay: int,
) -> np.ndarray:
    header = [
        harness.RATE,
        block,
        len(source),
        gate,
        trigger_delay,
        profile.delay,
        profile.attack,
        profile.hold,
        profile.decay,
        profile.release,
        profile.start,
        profile.sustain,
        1000,
        profile.depth,
        profile.amplitude_release,
    ]
    with (folder / 'request.txt').open('w') as stream:
        stream.write(' '.join(str(v) for v in header) + '\n')
        np.savetxt(stream, np.column_stack([source, portable]), fmt='%.17g')
    process = subprocess.run(
        [
            str(executable.resolve()),
            str(folder / 'request.txt'),
            str(folder / 'trace.txt'),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    harness.write_json(
        folder / 'process.json',
        {
            'arguments': process.args,
            'exit_status': process.returncode,
            'stderr': process.stderr,
        },
    )
    process.check_returncode()
    return np.loadtxt(folder / 'trace.txt')


def check_native_control(
    profile: filter_envelope_oracle.EnvelopeProfile,
) -> dict[str, float]:
    """Observe the imported shared runtime at phase edges and interior points."""
    result: SfzCompileResult = compiler.compile_instrument(
        parser.parse(
            '<region> sample=a.wav loop_mode=no_loop key=60 cutoff=1000 '
            f'ampeg_release={profile.amplitude_release:g} '
            + filter_envelope_oracle.declarations(profile)
        ),
        name='isolation',
        title='Isolation',
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
        filter_response='sfizz_rbj',
        filter_envelope_response='portable_exponential',
        output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
        output_channels=['left', 'right'],
    )
    assert result.complete and result.instrument is not None
    slot = result.instrument.body.slots[0]
    gate = Fraction(str(profile.release_at))
    times = sorted(set([Fraction(i, 1000) for i in range(2000)] + [gate]))
    age = np.asarray([float(t) for t in times])
    expected = filter_envelope_oracle.levels(profile, age, harness.RATE)
    amplifier = filter_envelope_oracle.release(
        1, age - profile.release_at, profile.amplitude_release
    )
    errors = {}
    for name, body, values in [
        ('maximum_error', slot.envelfos['sfz-filter-envelope'], expected),
        ('amplifier_maximum_error', slot.envelope, amplifier),
    ]:
        assert isinstance(body, Envelope)
        state = envelfo_event(
            body,
            initial_envelfo(body, Fraction(0)),
            EnvelfoEvent(at=Fraction(0), ordinal=0, action='note_on'),
        )
        released = envelfo_event(
            body, state, EnvelfoEvent(at=gate, ordinal=1, action='note_off')
        )
        actual = np.asarray(
            [envelfo_at(body, state if t < gate else released, t).value for t in times]
        )
        errors[name] = float(np.max(np.abs(actual - values)))
    return errors
