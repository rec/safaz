"""Offline comparisons against the unmodified pinned sfizz client."""

import json
import platform
import subprocess
from hashlib import sha256
from importlib.metadata import distribution
from math import cos, pi, sin, sqrt
from pathlib import Path
from typing import Literal

import mido
import numpy as np
import soundfile
from enge import midi, sample_instrument
from enge.performance import MidiConverter
from pydantic import BaseModel
from ufor.assets import RelativeFileLocation
from ufor.instrument_trace import TraceAction
from ufor.interface import ScoreReference
from ufor.samples import trace
from ufor.samples.processing import PanLaw

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
    source_channels: Literal[1, 2] = 2
    pan: int | None = None
    pan_law: PanLaw = PanLaw.sfizz


def authored_pan_gains(case: Case) -> list[float]:
    """Independent equations, never the renderer's pan_gains implementation."""
    position = (case.pan or 0) / 100
    if case.pan_law == PanLaw.native and case.source_channels == 2:
        return [min(1.0, 1 - position), min(1.0, 1 + position)]
    angle = (position + 1) * pi / 4
    compensation = 1.0
    if case.pan_law == PanLaw.sfizz:
        compensation = (
            10 ** (3 / 20) if case.source_channels == 1 else 10 ** (6 / 20) / sqrt(2)
        )
    return [
        0.0 if position == 1 else compensation * cos(angle),
        0.0 if position == -1 else compensation * sin(angle),
    ]


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
    fixture = 'pan' if case.pan is not None else case.name
    sfz = (Path(__file__).parent / 'fixtures' / f'{fixture}.sfz').read_text()
    if case.pan is not None:
        sfz = sfz.format(pan=case.pan)
    (folder / 'instrument.sfz').write_text(sfz)
    sources: dict[str, np.ndarray] = {}
    for name, period in [('a.wav', 96), ('b.wav', 64)]:
        audio = np.zeros((RATE, case.source_channels))
        phase = np.arange(RATE // 2) % period
        audio[: RATE // 2, 0] = np.where(phase < period // 2, 0.125, -0.125)
        if case.source_channels == 2:
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
            [
                np.interp(positions, np.arange(RATE), source[:, c])
                for c in range(case.source_channels)
            ]
        )
        gain = MASTER_GAIN * 10 ** (note.gain_db / 20) * (note.velocity / 127) ** 2
        start = note.tick * 25
        expected[start : start + len(audio)] += audio * gain * authored_pan_gains(case)
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
    """Measure separated fixtures, including audio before expected note starts."""
    measurements = []
    for index, note in enumerate(case.notes):
        start = note.tick * 25
        end = (
            case.notes[index + 1].tick if index + 1 < len(case.notes) else case.end_tick
        ) * 25
        window = audio[start:end]
        timing_start = (case.notes[index - 1].tick * 25 + start) // 2 if index else 0
        timing_end = (
            (start + end) // 2 if index + 1 < len(case.notes) else case.end_tick * 25
        )
        timing_window = audio[timing_start:timing_end]
        audible = np.flatnonzero(np.max(np.abs(timing_window), axis=1) > PCM_ERROR)
        measurements.append(
            {
                'key': note.key,
                'velocity': note.velocity,
                'peak_channels': np.max(np.abs(window), axis=0).tolist(),
                'rms_channels': np.sqrt(np.mean(window**2, axis=0)).tolist(),
                'expected_onset_frame': start,
                'timing_window_frames': [timing_start, timing_end],
                'first_audible_frame': int(timing_start + audible[0])
                if len(audible)
                else None,
                'last_audible_frame': int(timing_start + audible[-1])
                if len(audible)
                else None,
                'audibility_threshold': PCM_ERROR,
                'gain_ratio_measurable': note.velocity != 1,
            }
        )
    return measurements


def run_native_case(
    case: Case,
    folder: Path,
    backend: Literal['numpy', 'native'],
    block: int,
) -> tuple[np.ndarray, np.ndarray]:
    expected = create_inputs(case, folder)
    write_json(
        folder / 'manifest.json',
        {
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
            'voices': 64,
            'initial_cc': {'7': 127, '10': 'sfizz default 0.5', '11': 127},
            'case': case.model_dump(mode='json'),
            'input_sha256': {
                p.name: sha256(p.read_bytes()).hexdigest()
                for p in folder.iterdir()
                if p.suffix in {'.wav', '.sfz', '.mid'}
            },
            'unresolved': ['velocity 1 gain ratio below useful PCM16 precision'],
        },
    )
    horizon = len(expected)
    report: dict[str, object] = {
        'declared_frames': horizon,
        'authored_notes': measure_notes(case, expected),
        'authored_pan_gains': authored_pan_gains(case),
        'reference_comparison': 'pending'
        if case.pan_law == PanLaw.sfizz
        else 'not applicable: generic native law, no SFZ equivalence claim',
    }
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
    if document.body.pan_law != PanLaw.sfizz:
        raise ValueError('SFZ import must explicitly select the sfizz pan law')
    if case.pan_law == PanLaw.native:
        document = document.model_copy(
            update={'body': document.body.model_copy(update={'pan_law': PanLaw.native})}
        )
    (folder / 'instrument.json').write_text(
        document.model_dump_json(indent=2), encoding='utf-8'
    )
    assert compiled.binding is not None
    converter = MidiConverter(
        source='reference-test', binding=compiled.binding, instrument=document
    )
    events = midi.read_midi(folder / 'performance.mid', converters=[converter]).parts[
        'channel-0'
    ]
    write_json(folder / 'events.json', [e.model_dump(mode='json') for e in events])
    actions = trace.prepare(document.body, events, seed=0)
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
    decoded: dict[str, np.ndarray] = {}
    for asset in document.assets:
        location = asset.location
        if not isinstance(location, RelativeFileLocation):
            raise ValueError('Fixture requires relative sample locations')
        decoded[asset.name] = soundfile.read(folder / location.path, always_2d=True)[0]
    prepared = sample_instrument.prepare(document, decoded)
    sampler = sample_instrument.OfflineSampler(prepared, backend, control_interval=1)
    native = np.zeros((((horizon + block - 1) // block) * block, 2))
    for start in range(0, len(native), block):
        end = min(start + block, len(native))
        selected: list[TraceAction] = [
            a for a in actions.actions if start <= a.tick < end
        ]
        native[start:end] = sampler.advance(selected, start, end) * MASTER_GAIN
    soundfile.write(folder / 'native.wav', native, RATE, subtype='FLOAT')
    report['native_frames'] = len(native)
    report['native_padding_silent'] = bool(
        np.all(np.abs(native[horizon:]) <= PCM_ERROR)
    )
    report['native_vs_authored'] = compare(native[:horizon], expected)
    report['native_notes'] = measure_notes(case, native[:horizon])
    write_json(folder / 'report.json', report)
    return native, expected


def run_reference_case(
    case: Case,
    folder: Path,
    executable: Path,
    source: Path,
    build: Path,
    native: np.ndarray,
    expected: np.ndarray,
    block: int,
) -> dict[str, object]:
    """Add reference evidence after native rendering, without gating its checks."""
    manifest = json.loads((folder / 'manifest.json').read_text())
    manifest.update(
        reference=verify_source(source),
        reference_executable_sha256=sha256(executable.read_bytes()).hexdigest(),
        compiler_metadata={
            p.name: p.read_text()
            for p in (build / 'CMakeFiles').glob('*/CMake*Compiler.cmake')
        },
    )
    write_json(folder / 'manifest.json', manifest)
    (folder / 'CMakeCache.txt').write_bytes((build / 'CMakeCache.txt').read_bytes())
    reference = render_reference(executable, folder, block)
    horizon = len(expected)
    if not horizon <= len(reference) < horizon + block:
        raise ValueError(f'Reference horizon {len(reference)} outside EOT block bounds')
    if np.any(np.abs(reference[horizon:]) > PCM_ERROR):
        raise ValueError('Reference block padding contains sound')
    report = json.loads((folder / 'report.json').read_text())
    report.update(
        reference_frames=len(reference),
        padding_frames=len(reference) - horizon,
        reference_comparison='measured; failures remain failures',
        reference_vs_authored=compare(reference[:horizon], expected),
        reference_notes=measure_notes(case, reference[:horizon]),
        native_vs_reference=compare(native, reference),
    )
    soundfile.write(
        folder / 'reference-authored-difference.wav',
        reference[:horizon] - expected,
        RATE,
        subtype='FLOAT',
    )
    soundfile.write(
        folder / 'difference.wav', native - reference, RATE, subtype='FLOAT'
    )
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

PAN_CASES = [
    Case(
        name=f'pan-{s.value}-{c}-{p}',
        notes=[Note(tick=11)],
        end_tick=6000,
        source_channels=c,
        pan=p,
        pan_law=s,
    )
    for s in PanLaw
    for c in (1, 2)
    for p in (-100, -50, 0, 50, 100)
]
