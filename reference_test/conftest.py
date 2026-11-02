import json
import subprocess
import traceback
from pathlib import Path
from typing import Literal

import harness
import numpy as np
import pytest
from ufor.samples.processing import PanLaw


@pytest.fixture(scope='module', params=['numpy', 'native'])
def backend(request: pytest.FixtureRequest) -> Literal['numpy', 'native']:
    return request.param


@pytest.fixture(scope='module')
def rendered_case(
    case: harness.Case,
    backend: Literal['numpy', 'native'],
    reference_output: Path,
) -> tuple[Path, np.ndarray | None, np.ndarray]:
    folder = reference_output / f'{case.name}-{backend}-256'
    assert not folder.exists(), f'Choose a new --reference-output: {folder}'
    expected = harness.create_inputs(case, folder)
    native = None
    try:
        native = harness.run_native_case(case, folder, backend, 256, expected)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        harness.write_json(
            folder / 'native-failure.json',
            {
                'stage': 'native',
                'error': str(error),
                'traceback': traceback.format_exc(),
                'status': 'native rendering incomplete',
            },
        )
    return folder, native, expected


@pytest.fixture(scope='module')
def native_render(
    rendered_case: tuple[Path, np.ndarray | None, np.ndarray],
) -> tuple[Path, np.ndarray, np.ndarray]:
    folder, native, expected = rendered_case
    if native is None:
        failure = json.loads((folder / 'native-failure.json').read_text())
        raise RuntimeError(f'Native rendering failed: {failure["error"]}; {folder}')
    return folder, native, expected


@pytest.fixture(scope='module')
def reference_report(
    case: harness.Case,
    rendered_case: tuple[Path, np.ndarray | None, np.ndarray],
    reference_paths: tuple[Path, Path, Path, Path],
) -> dict[str, object]:
    if case.pan_law == PanLaw.native:
        pytest.skip('Generic native law has no SFZ equivalence claim')
    folder, native, expected = rendered_case
    source, executable, build, _ = reference_paths
    try:
        return harness.run_reference_case(
            case, folder, executable, source, build, native, expected, 256
        )
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        harness.write_json(
            folder / 'reference-failure.json',
            {
                'stage': 'reference',
                'error': str(error),
                'traceback': traceback.format_exc(),
                'status': 'reference incomplete; native checks are independent',
            },
        )
        raise


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption('--sfizz-source', help='Unmodified pinned sfizz checkout')
    parser.addoption('--sfizz-render', help='Upstream sfizz_render executable')
    parser.addoption('--sfizz-build', help='Build directory containing CMakeCache.txt')
    parser.addoption('--reference-output', default='.reference-artifacts')
    parser.addoption('--require-reference', action='store_true')


@pytest.fixture(scope='session')
def reference_output(request: pytest.FixtureRequest) -> Path:
    output = Path(request.config.getoption('--reference-output')).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return output


@pytest.fixture(scope='session')
def reference_paths(
    request: pytest.FixtureRequest, reference_output: Path
) -> tuple[Path, Path, Path, Path]:
    options = [
        request.config.getoption(n)
        for n in (
            '--sfizz-source',
            '--sfizz-render',
            '--sfizz-build',
        )
    ]
    if not all(options):
        if request.config.getoption('--require-reference'):
            pytest.fail('Dedicated reference run requires source, executable and build')
        pytest.skip('External reference not enabled; see reference_test/README.md')
    paths = [Path(p).resolve() for p in options]
    if not paths[0].is_dir() or not paths[1].is_file() or not paths[2].is_dir():
        pytest.fail('Configured reference paths are missing')
    return paths[0], paths[1], paths[2], reference_output
