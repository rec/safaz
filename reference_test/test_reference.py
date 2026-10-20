import json
import subprocess
import traceback
from pathlib import Path
from typing import Literal

import harness
import numpy as np
import pytest
import soundfile
from ufor.samples.processing import PanLaw


@pytest.fixture(
    scope='module', params=harness.CASES + harness.PAN_CASES, ids=lambda c: c.name
)
def case(request: pytest.FixtureRequest) -> harness.Case:
    return request.param


@pytest.fixture(scope='module', params=['numpy', 'native'])
def backend(request: pytest.FixtureRequest) -> Literal['numpy', 'native']:
    return request.param


@pytest.fixture(scope='module')
def native_render(
    case: harness.Case,
    backend: Literal['numpy', 'native'],
    reference_output: Path,
) -> tuple[Path, np.ndarray, np.ndarray]:
    folder = reference_output / f'{case.name}-{backend}-256'
    assert not folder.exists(), f'Choose a new --reference-output: {folder}'
    try:
        native, expected = harness.run_native_case(case, folder, backend, 256)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        harness.write_json(
            folder / 'failure.json',
            {
                'stage': 'native',
                'error': str(error),
                'traceback': traceback.format_exc(),
                'status': 'native rendering incomplete',
            },
        )
        raise
    return folder, native, expected


@pytest.fixture(scope='module')
def reference_report(
    case: harness.Case,
    native_render: tuple[Path, np.ndarray, np.ndarray],
    reference_paths: tuple[Path, Path, Path, Path],
) -> dict[str, object]:
    if case.pan_law == PanLaw.native:
        pytest.skip('Generic native law has no SFZ equivalence claim')
    folder, native, expected = native_render
    source, executable, build, _ = reference_paths
    try:
        return harness.run_reference_case(
            case, folder, executable, source, build, native, expected, 256
        )
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        harness.write_json(
            folder / 'failure.json',
            {
                'stage': 'reference',
                'error': str(error),
                'traceback': traceback.format_exc(),
                'status': 'reference incomplete; native checks are independent',
            },
        )
        raise


def test_note_timing_reports_early_late_and_silent_notes(tmp_path: Path) -> None:
    case = harness.Case(
        name='timing',
        notes=[harness.Note(tick=t) for t in [11, 2000, 4000]],
        end_tick=6000,
    )
    audio = np.full((150_000, 2), -1 / 32768)
    audio[274:1000, 0] = 0.125
    audio[50_003:51_000, 1] = -0.125
    soundfile.write(tmp_path / 'timing.wav', audio, 48_000, subtype='FLOAT')

    measurements = harness.measure_notes(case, audio)

    assert [m['first_audible_frame'] for m in measurements] == [274, 50_003, None]
    assert [m['last_audible_frame'] for m in measurements] == [999, 50_999, None]
    assert [m['expected_onset_frame'] for m in measurements] == [275, 50_000, 100_000]
    assert measurements[0]['timing_window_frames'] == [0, 25_137]
    assert measurements[1]['timing_window_frames'] == [25_137, 75_000]
    assert measurements[2]['timing_window_frames'] == [75_000, 150_000]
    # Timing inspection must not change the existing level measurement window.
    assert (
        measurements[0]['rms_channels']
        == np.sqrt(np.mean(audio[275:50_000] ** 2, axis=0)).tolist()
    )


def test_native_selects_authored_regions(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['selection']['passed'], report['selection']


def test_native_matches_authored_waveform(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['native_vs_authored']['passed'], report['native_vs_authored']


def test_native_matches_authored_timing_and_silent_padding(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['native_padding_silent']
    for actual, expected in zip(
        report['native_notes'], report['authored_notes'], strict=True
    ):
        assert actual['first_audible_frame'] == expected['first_audible_frame']
        assert actual['last_audible_frame'] == expected['last_audible_frame']


def test_reference_matches_native_waveform(reference_report: dict[str, object]) -> None:
    measurement = reference_report['native_vs_reference']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement


def test_reference_matches_authored_waveform(
    reference_report: dict[str, object],
) -> None:
    measurement = reference_report['reference_vs_authored']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement


def test_reference_repeatability_across_blocks(
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    source, executable, _, output = reference_paths
    harness.verify_source(source)
    renders: list[np.ndarray] = []
    frames = harness.CASES[0].end_tick * 25
    lengths: list[int] = []
    for index, block in enumerate([256, 256, 64, 257]):
        folder = output / f'repeat-{index}-{block}'
        harness.create_inputs(harness.CASES[0], folder)
        audio = harness.render_reference(executable, folder, block)
        assert frames <= len(audio) < frames + block
        assert np.all(np.abs(audio[frames:]) <= 1 / 32768)
        if renders:
            soundfile.write(
                folder / 'repeat-difference.wav',
                audio[:frames] - renders[0],
                48_000,
                subtype='FLOAT',
            )
        renders.append(audio[:frames])
        lengths.append(len(audio))
    measurements = [harness.compare(a, renders[0]) for a in renders[1:]]
    harness.write_json(
        output / 'repeatability.json',
        {
            'raw_frames': lengths,
            'declared_frames': frames,
            'measurements': measurements,
        },
    )
    assert np.array_equal(renders[0], renders[1]), 'Repeated PCM16 output changed'
    assert all(m['passed'] for m in measurements)


@pytest.mark.parametrize('mutation', ['gain', 'pitch', 'timing', 'region', 'pan'])
def test_comparison_detects_meaningful_changes(mutation: str, tmp_path: Path) -> None:
    signal = np.zeros((48_000, 2))
    signal[1000:2000, 0] = np.sin(np.arange(1000) * 2 * np.pi / 96) / 8
    assert harness.compare(signal, signal)['passed']
    if mutation == 'gain':
        changed = signal * 0.5
    elif mutation == 'pitch':
        changed = signal.copy()
        changed[1000:2000, 0] = np.sin(np.arange(1000) * 2 * np.pi / 64) / 8
    elif mutation == 'timing':
        changed = np.roll(signal, 1, axis=0)
    elif mutation == 'pan':
        changed = signal[:, ::-1].copy()
    else:
        changed = np.zeros(signal.shape)
    soundfile.write(tmp_path / 'expected.wav', signal, 48_000, subtype='FLOAT')
    soundfile.write(tmp_path / 'changed.wav', changed, 48_000, subtype='FLOAT')
    assert not harness.compare(changed, signal)['passed']
