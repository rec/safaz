"""Offline comparisons against the unmodified pinned sfizz client."""

import json
import platform
import subprocess
from hashlib import sha256
from importlib.metadata import distribution
from pathlib import Path
from typing import Literal

import mido
import numpy as np
import soundfile
from enge import midi, sample_instrument
from pydantic import BaseModel
from ufor.assets import RelativeFileLocation
from ufor.events import ControlChange, PerformanceEvent, Trigger
from ufor.instrument_trace import TraceAction
from ufor.interface import ScoreReference
from ufor.samples import trace

from safaz import reader
from safaz.model import SfzMidiBindingRequest

RATE = 48_000
SFIZZ_REVISION = 'f5c6e29f23b8057867c08e88f5f6ac6738baa30b'
MASTER_DB = -7.35  # SynthPrivate.h / Defaults.h, no client override.
MASTER_GAIN = 10 ** (MASTER_DB / 20)
# drwav uses floor((x + 1) * 32767.5) - 32768, bounded by two LSBs.
PCM_ERROR = 2 / 32768
FLOAT_ERROR = 2e-6


class Note(BaseModel, frozen=True):
    tick: int
    key: int = 60
    velocity: int = 127
    sample: str | None = 'a.wav'
    gain_db: float = 0
    step: float = 1


class Case(BaseModel, frozen=True):
    name: str
    notes: list[Note]
    end_tick: int


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def verify_source(source: Path) -> dict[str, str]:
    """Reject tracked edits and substituted submodules, including nested ones."""
    revision = subprocess.check_output(
        ['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True
    ).strip()
    if revision != SFIZZ_REVISION:
        raise ValueError(f'Expected sfizz {SFIZZ_REVISION}, got {revision}')
    status = subprocess.check_output(
        ['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=no'],
        text=True,
    )
    submodules = subprocess.check_output(
        ['git', '-C', str(source), 'submodule', 'status', '--recursive'], text=True
    )
    if status or any(s and s[0] != ' ' for s in submodules.splitlines()):
        raise ValueError('Reference source or submodules differ from the pinned tree')
    return {'revision': revision, 'submodules': submodules}


def package_revision(name: str) -> object:
    metadata = distribution(name)
    direct = metadata.read_text('direct_url.json')
    return json.loads(direct) if direct else {'version': metadata.version}


def create_inputs(case: Case, folder: Path) -> np.ndarray:
    """Use integer-valued PCM sources, distinct periods, and a silent tail."""
    folder.mkdir(parents=True)
    (folder / 'instrument.sfz').write_bytes(
        (Path(__file__).parent / 'fixtures' / f'{case.name}.sfz').read_bytes()
    )
    sources: dict[str, np.ndarray] = {}
    for name, period in [('a.wav', 96), ('b.wav', 64)]:
        audio = np.zeros((RATE, 2))
        phase = np.arange(RATE // 2) % period
        audio[: RATE // 2, 0] = np.where(phase < period // 2, 0.125, -0.125)
        audio[: RATE // 2, 1] = -audio[: RATE // 2, 0] / 2
        soundfile.write(folder / name, audio, RATE, subtype='PCM_16')
        sources[name] = audio
    performance = mido.MidiFile(type=0, ticks_per_beat=960)
    track = mido.MidiTrack()
    performance.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=500_000))
    previous = 0
    for note in case.notes:
        track.append(
            mido.Message(
                'note_on',
                note=note.key,
                velocity=note.velocity,
                time=note.tick - previous,
            )
        )
        track.append(mido.Message('note_off', note=note.key, velocity=0, time=1920))
        previous = note.tick + 1920
    # fmidi ignores delayed EOT metadata. A final unused control sets the horizon.
    track.append(
        mido.Message(
            'control_change', control=1, value=0, time=case.end_tick - previous
        )
    )
    track.append(mido.MetaMessage('end_of_track', time=0))
    performance.save(folder / 'performance.mid')

    # Independent authored oracle; no importer or renderer code computes this.
    expected = np.zeros((case.end_tick * 25, 2))
    for note in case.notes:
        if note.sample is None:
            continue
        source = sources[note.sample]
        positions = np.arange(int(RATE / note.step)) * note.step
        audio = np.column_stack(
            [np.interp(positions, np.arange(RATE), source[:, c]) for c in range(2)]
        )
        gain = MASTER_GAIN * 10 ** (note.gain_db / 20) * (note.velocity / 127) ** 2
        start = note.tick * 25
        expected[start : start + len(audio)] += audio * gain
    soundfile.write(folder / 'expected.wav', expected, RATE, subtype='FLOAT')
    return expected


def render_reference(executable: Path, folder: Path, block: int) -> np.ndarray:
    args = [
        str(executable),
        '--sfz',
        str(folder / 'instrument.sfz'),
        '--midi',
        str(folder / 'performance.mid'),
        '--wav',
        str(folder / 'reference.wav'),
        '--samplerate',
        str(RATE),
        '--blocksize',
        str(block),
        '--quality',
        '1',
        '--polyphony',
        '64',
        '--use-eot',
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    write_json(
        folder / 'reference-process.json',
        {
            'arguments': args,
            'exit_status': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr,
        },
    )
    result.check_returncode()
    info = soundfile.info(folder / 'reference.wav')
    if info.samplerate != RATE or info.channels != 2 or info.subtype != 'PCM_16':
        raise ValueError(f'Unexpected reference output: {info}')
    return soundfile.read(folder / 'reference.wav', always_2d=True)[0]


def compare(actual: np.ndarray, expected: np.ndarray) -> dict[str, object]:
    """No normalization, offset search, trimming, or fitted tolerances."""
    if actual.shape != expected.shape:
        return {
            'passed': False,
            'actual_shape': list(actual.shape),
            'expected_shape': list(expected.shape),
        }
    residual = actual - expected
    maximum = float(np.max(np.abs(residual)))
    rms = float(np.sqrt(np.mean(residual**2)))
    return {
        'passed': maximum <= PCM_ERROR + FLOAT_ERROR,
        'maximum_error': maximum,
        'rms_error': rms,
        'maximum_error_limit': PCM_ERROR + FLOAT_ERROR,
    }


def measure_notes(case: Case, audio: np.ndarray) -> list[dict[str, object]]:
    """Report absolute levels and frame coordinates, without correcting them."""
    measurements = []
    for index, note in enumerate(case.notes):
        start = note.tick * 25
        end = (
            case.notes[index + 1].tick if index + 1 < len(case.notes) else case.end_tick
        ) * 25
        window = audio[start:end]
        audible = np.flatnonzero(np.max(np.abs(window), axis=1) > PCM_ERROR)
        measurements.append(
            {
                'key': note.key,
                'velocity': note.velocity,
                'peak_channels': np.max(np.abs(window), axis=0).tolist(),
                'rms_channels': np.sqrt(np.mean(window**2, axis=0)).tolist(),
                'first_audible_frame': int(start + audible[0])
                if len(audible)
                else None,
                'last_audible_frame': int(start + audible[-1])
                if len(audible)
                else None,
                'audibility_threshold': PCM_ERROR,
                'gain_ratio_measurable': note.velocity != 1,
            }
        )
    return measurements


def run_case(
    case: Case,
    folder: Path,
    executable: Path,
    source: Path,
    build: Path,
    backend: Literal['numpy', 'native'],
    block: int,
) -> dict[str, object]:
    expected = create_inputs(case, folder)
    cache = build / 'CMakeCache.txt'
    (folder / 'CMakeCache.txt').write_bytes(cache.read_bytes())
    write_json(
        folder / 'manifest.json',
        {
            'reference': verify_source(source),
            'platform': platform.platform(),
            'python': platform.python_version(),
            'safaz_revision': subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], text=True
            ).strip(),
            'ufor': package_revision('ufor'),
            'enge': package_revision('enge'),
            'block': block,
            'backend': backend,
            'control_interval': 1,
            'rate': RATE,
            'channels': ['left', 'right'],
            'master_db': MASTER_DB,
            'interpolation': 'linear',
            'reference_executable_sha256': sha256(executable.read_bytes()).hexdigest(),
            'compiler_metadata': {
                p.name: p.read_text(encoding='utf-8')
                for p in (build / 'CMakeFiles').glob('*/CMake*Compiler.cmake')
            },
            'voices': 64,
            'initial_cc': {'7': 127, '10': 'sfizz default 0.5', '11': 127},
            'case': case.model_dump(),
            'input_sha256': {
                p.name: sha256(p.read_bytes()).hexdigest()
                for p in folder.iterdir()
                if p.suffix in {'.wav', '.sfz', '.mid'}
            },
            'unresolved': ['velocity 1 gain ratio below useful PCM16 precision'],
        },
    )
    reference = render_reference(executable, folder, block)
    horizon = len(expected)
    if not horizon <= len(reference) < horizon + block:
        raise ValueError(f'Reference horizon {len(reference)} outside EOT block bounds')
    if np.any(np.abs(reference[horizon:]) > PCM_ERROR):
        raise ValueError('Reference block padding contains sound')
    # Compare the declared EOT interval; raw reference WAV retains its padding.
    report: dict[str, object] = {
        'reference_frames': len(reference),
        'declared_frames': horizon,
        'padding_frames': len(reference) - horizon,
        'reference_vs_authored': compare(reference[:horizon], expected),
        'reference_notes': measure_notes(case, reference[:horizon]),
        'authored_notes': measure_notes(case, expected),
    }
    soundfile.write(
        folder / 'reference-authored-difference.wav',
        reference[:horizon] - expected,
        RATE,
        subtype='FLOAT',
    )
    write_json(folder / 'report.json', report)
    compiled = reader.read(
        folder / 'instrument.sfz',
        midi_binding=SfzMidiBindingRequest(
            instrument=ScoreReference(path='instrument.json'),
            part='channel-0',
            repeated_key_release='oldest',
        ),
    )
    (folder / 'import.json').write_text(
        compiled.model_dump_json(indent=2), encoding='utf-8'
    )
    if not compiled.complete or compiled.instrument is None:
        raise ValueError('Positive fixture did not import completely; see import.json')
    document = compiled.instrument
    (folder / 'instrument.json').write_text(
        document.model_dump_json(indent=2), encoding='utf-8'
    )
    events = midi.read_midi(folder / 'performance.mid').parts[0]
    # enge's MIDI reader initializes oscillator controls. Sample velocity is
    # already carried by Trigger.velocity and consumed by EventBinding.
    # These fixtures have no controller behavior; the final CC only sets EOT.
    controls = document.body.settings.controls.keys()
    bound_events: list[PerformanceEvent] = []
    for event in events:
        if isinstance(event, Trigger):
            bound_events.append(
                event.model_copy(
                    update={
                        'controls': {
                            n: v for n, v in event.controls.items() if n in controls
                        },
                    }
                )
            )
        elif not isinstance(event, ControlChange) or event.control in controls:
            bound_events.append(event)
    write_json(folder / 'events.json', [e.model_dump(mode='json') for e in events])
    write_json(
        folder / 'bound-events.json', [e.model_dump(mode='json') for e in bound_events]
    )
    actions = trace.prepare(document.body, bound_events, seed=0)
    (folder / 'actions.json').write_text(
        actions.model_dump_json(indent=2), encoding='utf-8'
    )
    slices = {s.name: s.asset for s in document.body.slices}
    assets = {a.name: a.location for a in document.assets}
    starts = []
    for action in actions.actions:
        if isinstance(action, trace.VoiceStart):
            location = assets[slices[action.slice]]
            if not isinstance(location, RelativeFileLocation):
                raise ValueError('Fixture requires relative sample locations')
            starts.append([action.tick, location.path, action.velocity])
    expected_starts = [
        [n.tick * 25, n.sample, n.velocity / 127]
        for n in case.notes
        if n.sample is not None
    ]
    report['selection'] = {
        'passed': starts == expected_starts,
        'actual': starts,
        'expected': expected_starts,
    }
    write_json(folder / 'report.json', report)
    if starts != expected_starts:
        raise ValueError('Prepared region selection disagrees with authored notes')
    decoded: dict[str, np.ndarray] = {}
    for asset in document.assets:
        location = asset.location
        if not isinstance(location, RelativeFileLocation):
            raise ValueError('Fixture requires relative sample locations')
        decoded[asset.name] = soundfile.read(folder / location.path, always_2d=True)[0]
    prepared = sample_instrument.prepare(document, decoded)
    sampler = sample_instrument.OfflineSampler(prepared, backend, control_interval=1)
    native = np.zeros(reference.shape)
    for start in range(0, len(native), block):
        end = min(start + block, len(native))
        selected: list[TraceAction] = [
            a for a in actions.actions if start <= a.tick < end
        ]
        native[start:end] = sampler.advance(selected, start, end) * MASTER_GAIN
    soundfile.write(folder / 'native.wav', native, RATE, subtype='FLOAT')
    soundfile.write(
        folder / 'difference.wav', native - reference, RATE, subtype='FLOAT'
    )
    report['native_vs_reference'] = compare(native, reference)
    report['native_vs_authored'] = compare(native[:horizon], expected)
    write_json(folder / 'report.json', report)
    return report


CASES = [
    Case(name='unity', notes=[Note(tick=11)], end_tick=6000),
    Case(
        name='gain',
        notes=[
            Note(tick=11, gain_db=-6),
            Note(tick=5001, key=61, gain_db=6),
            Note(tick=10001, key=62, velocity=64),
            Note(tick=15001, key=62, velocity=1),
            Note(tick=20001, key=62),
        ],
        end_tick=24000,
    ),
    Case(
        name='pitch',
        notes=[
            Note(tick=11, key=48, step=0.5),
            Note(tick=5001),
            Note(tick=10001, key=72, step=2),
        ],
        end_tick=14000,
    ),
    Case(
        name='regions',
        notes=[
            Note(tick=11, key=59, sample=None),
            Note(tick=5001, key=60),
            Note(tick=10001, key=61, sample='b.wav'),
            Note(tick=15001, key=62, velocity=63),
            Note(tick=20001, key=62, velocity=64, sample='b.wav'),
            Note(tick=25001, key=63, sample=None),
        ],
        end_tick=29000,
    ),
]
