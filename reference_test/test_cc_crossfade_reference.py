from math import sqrt
from pathlib import Path

import harness
import numpy as np
import pytest


@pytest.mark.parametrize(
    ('declarations', 'value', 'gain'),
    [
        pytest.param('xfin_hicc22=90', 22, sqrt(22 / 90), id='default-power'),
        pytest.param('xf_cccurve=gain xfin_hicc22=127', 63, 0.5, id='top-endpoint'),
        pytest.param('xf_cccurve=gain xfout_locc22=0', 63, 0.5, id='default-upper'),
        pytest.param('xf_cccurve=gain xfin_locc22=64', 63, 0, id='step-below'),
        pytest.param('xf_cccurve=gain xfin_locc22=64', 64, 1, id='step-at'),
        pytest.param('xf_cccurve=gain xfout_hicc22=64', 127, 1, id='unity-out'),
        pytest.param(
            'xfout_locc22=20 xfout_hicc22=100', 70, sqrt(30 / 80), id='power-out'
        ),
    ],
)
def test_pinned_cc_crossfade_steady_gain(
    declarations: str,
    value: int,
    gain: float,
    request: pytest.FixtureRequest,
    reference_paths: tuple[Path, Path, Path, Path],
) -> None:
    _, executable, _, output = reference_paths
    case = harness.Case(name='unity', notes=[harness.Note(tick=11)], end_tick=6000)
    folder = output / f'cc-crossfade-{request.node.callspec.id}'
    authored = harness.create_inputs(case, folder)
    sfz = folder / 'instrument.sfz'
    control, region = sfz.read_text().split('\n', maxsplit=1)
    sfz.write_text(f'{control} set_cc22={value}\n{region}\n{declarations}\n')

    window = slice(1024, 8192)
    reference = harness.render_reference(executable, folder, 256)
    expected_peak = np.max(np.abs(authored[window]), axis=0) * gain
    actual_peak = np.max(np.abs(reference[window]), axis=0)
    np.testing.assert_allclose(actual_peak, expected_peak, atol=2 * harness.PCM_ERROR)
