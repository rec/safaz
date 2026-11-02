import json
from pathlib import Path

import harness
import numpy as np
import pytest
from modulation_oracle import ModulationProfile


@pytest.fixture(
    scope='module',
    params=[
        ModulationProfile(pitch_depth=d, delay=t, fade=f)
        for d, t, f in [(100, 0, 0), (-100, 0, 0), (600, 0.1, 0.2)]
    ]
    + [
        ModulationProfile(amplitude_depth=d, delay=t, fade=f)
        for d, t, f in [(6, 0, 0), (-6, 0, 0), (10, 0.1, 0.2)]
    ]
    + [ModulationProfile(pitch_depth=100, amplitude_depth=6, delay=0.1, fade=0.2)]
    + [
        ModulationProfile(bend_up=200),
        ModulationProfile(bend_up=1200, bend_down=-300),
        ModulationProfile(bend_up=200, pitch_depth=100, amplitude_depth=6),
    ],
    ids=[
        'pitch-positive',
        'pitch-negative',
        'pitch-delay-fade',
        'amplitude-positive',
        'amplitude-negative',
        'amplitude-delay-fade',
        'combined',
        'bend-symmetric',
        'bend-asymmetric',
        'bend-and-lfos',
    ],
)
def case(request: pytest.FixtureRequest) -> harness.Case:
    profile = request.param
    return harness.Case(
        name=f'modulation-{profile.pitch_depth}-{profile.amplitude_depth}-{profile.delay}-{profile.fade}-{profile.bend_up}',
        notes=[harness.Note(tick=11), harness.Note(tick=5001)],
        end_tick=10000,
        source_channels=1,
        modulation_profile=profile,
    )


def test_native_modulation_matches_authored(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['native_vs_authored']['passed'], report['native_vs_authored']


def test_native_modulation_selection_and_padding(
    native_render: tuple[Path, np.ndarray, np.ndarray],
) -> None:
    folder, _, _ = native_render
    report = json.loads((folder / 'report.json').read_text())
    assert report['selection']['passed']
    assert report['native_padding_silent']


def test_reference_modulation_matches_authored(
    reference_report: dict[str, object],
) -> None:
    measurement = reference_report['reference_vs_authored']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement


def test_reference_modulation_matches_native(
    reference_report: dict[str, object],
) -> None:
    measurement = reference_report['native_vs_reference']
    assert isinstance(measurement, dict)
    assert measurement['passed'], measurement
