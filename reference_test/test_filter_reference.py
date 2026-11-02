import json
from pathlib import Path

import filter_cases
import filter_oracle
import harness
import numpy as np
import pytest
from pytest_regressions.data_regression import DataRegressionFixture

from safaz import reader
from safaz.model import SfzLocation


@pytest.fixture(
    scope='module',
    params=filter_cases.STATIC_CASES
    + filter_cases.TRACKING_CASES
    + filter_cases.LFO_CASES,
    ids=lambda c: c.name,
)
def case(request: pytest.FixtureRequest) -> harness.Case:
    return request.param


def test_native_filter_waveform(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['native_vs_authored']['passed'], report['native_vs_authored']


def test_native_filter_selection_and_timing(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['selection']['passed'], report['selection']
    assert report['native_padding_silent']
    for actual, expected in zip(
        report['native_notes'], report['authored_notes'], strict=True
    ):
        assert actual['first_audible_frame'] == expected['first_audible_frame']
        assert actual['last_audible_frame'] == expected['last_audible_frame']


def test_native_filter_response_and_processing_contract(
    case: harness.Case,
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    document = json.loads((folder / 'instrument.json').read_text())
    profile = case.filter_profile
    assert profile is not None
    processing = document['body']['slots'][0]['processing']
    assert processing['filter_order'] == 'after_amplitude'
    assert [f['name'] for f in processing['filters']] == [
        f'sfz-filter-{i}' for i in range(1, len(profile.filters) + 1)
    ]
    responses = {
        'lpf_2p': 'lowpass',
        'hpf_2p': 'highpass',
        'bpf_2p': 'bandpass',
        'brf_2p': 'notch',
    }
    for actual, expected in zip(processing['filters'], profile.filters, strict=True):
        assert actual['response'] == responses[expected.response]
        assert actual['cutoff_hz'] == expected.cutoff
        assert actual['q'] == 10 ** (expected.resonance / 20)
    for measurement in report['filter_contract']['steady_responses']:
        assert measurement['maximum_response_db_error'] is not None
        assert (
            measurement['maximum_response_db_error']
            <= measurement['native_response_db_limit']
        ), measurement
        assert (
            measurement['maximum_null_gain'] <= measurement['native_null_gain_limit']
        ), measurement
        assert measurement['amplitude_passed'], measurement
    if 'restart_waveform' in report['filter_contract']:
        assert report['filter_contract']['restart_waveform']['passed']
    if profile.attack:
        import soundfile

        source = soundfile.read(folder / 'a.wav', always_2d=True)[0]
        expected = filter_oracle.render(profile, source, 60, 1, harness.RATE)
        wrong = filter_oracle.render(
            profile, source, 60, 1, harness.RATE, before_amplitude=True
        )
        assert (
            np.max(np.abs(expected - wrong)) * harness.MASTER_GAIN
            > harness.PCM_ERROR + harness.FLOAT_ERROR
        )


def test_reference_filter_waveform(reference_report: dict[str, object]) -> None:
    measurement = reference_report['native_vs_reference']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement


def test_reference_filter_matches_authored(reference_report: dict[str, object]) -> None:
    measurement = reference_report['reference_vs_authored']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement


def test_reference_filter_response(reference_report: dict[str, object]) -> None:
    contract = reference_report['reference_filter_contract']
    assert isinstance(contract, dict)
    measurements = contract['steady_responses']
    if not measurements:
        pytest.skip(
            'Dynamic/order profiles use full-waveform assertions, not a static response'
        )
    for measurement in measurements:
        assert measurement['amplitude_passed'], measurement


@pytest.mark.parametrize(
    ('opcodes', 'diagnosed'),
    [
        (
            'cutoff=2 fil_keytrack=1200 fil_veltrack=-1200',
            ['fil_keytrack', 'fil_veltrack'],
        ),
        (
            'cutoff=6000 fil_keytrack=1200 fil_veltrack=1200',
            ['fil_keytrack', 'fil_veltrack'],
        ),
        ('cutoff=12000 fillfo_freq=2 fillfo_depth=1200', ['fillfo_depth']),
    ],
    ids=['combined-low', 'combined-high', 'lfo-high'],
)
def test_unsupported_cutoff_ranges_retain_diagnostics(
    opcodes: str,
    diagnosed: list[str],
    tmp_path: Path,
    data_regression: DataRegressionFixture,
) -> None:
    folder = tmp_path / 'bounds'
    harness.create_inputs(harness.CASES[0], folder)
    (folder / 'instrument.sfz').write_text(
        '<region> sample=a.wav lokey=59 hikey=61 pitch_keytrack=0 ' + opcodes
    )
    compiled = reader.read(
        folder / 'instrument.sfz',
        filter_response='sfizz_rbj',
        filter_lfo_response='sfizz_triangle',
    )
    harness.write_json(folder / 'diagnostics.json', compiled.model_dump(mode='json'))
    assert not compiled.complete and compiled.instrument is not None
    locations = []
    for feature in compiled.unimplemented:
        assert isinstance(feature.location, SfzLocation)
        assert feature.location.opcode is not None
        locations.append(feature.location.opcode)
    assert sorted(locations) == diagnosed
    slot = compiled.instrument.body.slots[0]
    assert not [r for r in slot.modulation.routes if r.target.parameter == 'cutoff_hz']
    data_regression.check(
        {
            'diagnostics': [f.model_dump(mode='json') for f in compiled.unimplemented],
            'retained_filters': [
                f.model_dump(mode='json') for f in slot.processing.filters
            ],
        }
    )
