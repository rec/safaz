from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption('--sfizz-source', help='Unmodified pinned sfizz checkout')
    parser.addoption('--sfizz-render', help='Upstream sfizz_render executable')
    parser.addoption('--sfizz-build', help='Build directory containing CMakeCache.txt')
    parser.addoption('--reference-output', default='.reference-artifacts')
    parser.addoption('--require-reference', action='store_true')


@pytest.fixture(scope='session')
def reference_paths(request: pytest.FixtureRequest) -> tuple[Path, Path, Path, Path]:
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
    output = Path(request.config.getoption('--reference-output')).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return paths[0], paths[1], paths[2], output
