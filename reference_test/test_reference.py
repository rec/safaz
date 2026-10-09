import subprocess
import traceback
from pathlib import Path
from typing import Literal

import harness
import numpy as np
import pytest
import soundfile


@pytest.mark.parametrize('case', harness.CASES, ids=[c.name for c in harness.CASES])
@pytest.mark.parametrize('backend', ['numpy', 'native'])
def test_imported_playback_matches_reference(
    case: harness.Case,
    backend: Literal['numpy', 'native'],
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    source, executable, build, output = reference_paths
    folder = output / f'{case.name}-{backend}-256'
    # Each invocation gets its own artifacts; an existing run is not overwritten.
    assert not folder.exists(), f'Choose a new --reference-output: {folder}'
    try:
        report = harness.run_case(case, folder, executable, source, build, backend, 256)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        harness.write_json(
            folder / 'failure.json',
            {
                'error': str(error),
                'traceback': traceback.format_exc(),
                'status': 'comparison incomplete; not audio-equivalent',
            },
        )
        raise
    for name in ('native_vs_reference', 'native_vs_authored', 'reference_vs_authored'):
        measurement = report[name]
        assert isinstance(measurement, dict)
        assert measurement['passed'], f'{name}: {measurement}; artifacts: {folder}'


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


@pytest.mark.parametrize('mutation', ['gain', 'pitch', 'timing', 'region'])
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
    else:
        changed = np.zeros(signal.shape)
    soundfile.write(tmp_path / 'expected.wav', signal, 48_000, subtype='FLOAT')
    soundfile.write(tmp_path / 'changed.wav', changed, 48_000, subtype='FLOAT')
    assert not harness.compare(changed, signal)['passed']
