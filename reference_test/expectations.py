"""Expected mismatches from the frozen sfizz qualification evidence."""

from math import isfinite

import harness
import pytest


def check_waveform(
    case: harness.Case, report: dict[str, object], comparison: str
) -> None:
    measurement = report[comparison]
    assert isinstance(measurement, dict)
    if measurement['passed']:
        return
    # Shape mismatches and unavailable comparisons must still fail.
    maximum = measurement.get('maximum_error')
    assert isinstance(maximum, float) and isfinite(maximum), measurement
    authored = report['authored_notes']
    reference = report['reference_notes']
    assert isinstance(authored, list) and isinstance(reference, list)
    pairs = list(zip(authored, reference, strict=True))
    # A missing note supplies no evidence of where its playback stopped.
    assert all(
        a['first_audible_frame'] is None or r['first_audible_frame'] is not None
        for a, r in pairs
    ), report['reference_notes']
    if any(preload_cutoff(a, r) for a, r in pairs):
        pytest.xfail(f'Frozen sfizz: 8192-frame preload cutoff; {measurement}')
    if case.name in WAVEFORM_MISMATCHES:
        pytest.xfail(f'Frozen sfizz: documented {case.name} mismatch; {measurement}')
    pytest.fail(str(measurement))


def preload_cutoff(authored: dict[str, object], reference: dict[str, object]) -> bool:
    """Recognize an audible note ending at the preload boundary plus filter tail."""
    onset = authored['expected_onset_frame']
    first = reference['first_audible_frame']
    last = reference['last_audible_frame']
    expected_last = authored['last_audible_frame']
    if not (
        isinstance(onset, int)
        and isinstance(first, int)
        and isinstance(last, int)
        and isinstance(expected_last, int)
    ):
        return False
    # The ordinary MIDI onset can be one frame early. The 256-frame window
    # allows the measured filter tail, while the authored note must outlast it.
    return (
        abs(onset - first) <= 1
        and first + 8191 <= last < first + 8192 + 256 < expected_last
    )


# Both backends showed these waveform mismatches on Linux and Windows in
# run 44923385625. Explicit case names keep subsequent fixtures strict.
WAVEFORM_MISMATCHES = {
    'unity',
    'gain',
    'pitch',
    'regions',
    *(f'pan-sfizz-{c}-{p}' for c in (1, 2) for p in (-100, -50, 0, 50, 100)),
    *(
        f'filter-static-{s}-{q}'
        for s in ('lpf_2p', 'hpf_2p', 'bpf_2p', 'brf_2p')
        for q in (0, 6)
    ),
    'filter-cascade',
    'filter-tracking-key',
    'filter-tracking-velocity-up',
    'filter-tracking-velocity-down',
    'filter-tracking-combined',
    'filter-tracking-second',
    'filter-lfo-2-1200',
    'filter-lfo-2--1200',
    'filter-lfo-5-600',
    'filter-lfo-combined',
    'filter-lfo-parabolic',
    'filter-lfo-timing-0.1-0',
    'filter-lfo-timing-0-0.2',
    'filter-lfo-timing-0.1-0.2',
    'filter-envelope-delay-release',
    'filter-envelope-attack-release',
    'filter-envelope-decay-release',
    'filter-envelope-sustain-release',
    'filter-envelope-negative-depth',
    'filter-envelope-zero-release',
    'filter-envelope-free-running',
    'filter-envelope-combined',
    'modulation--100.0-0-0.0-0.0-None',
    'modulation-0--6.0-0.0-0.0-None',
    'modulation-0-0-0-0-1200.0',
    'modulation-0-0-0-0-200.0',
    'modulation-0-10.0-0.1-0.2-None',
    'modulation-0-6.0-0.0-0.0-None',
    'modulation-100.0-0-0.0-0.0-None',
    'modulation-100.0-6.0-0-0-200.0',
    'modulation-100.0-6.0-0.1-0.2-None',
    'modulation-600.0-0-0.1-0.2-None',
}
