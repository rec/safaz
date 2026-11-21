import expectations
import harness
import pytest


@pytest.mark.parametrize(
    ('case_name', 'first', 'last', 'maximum', 'outcome'),
    [
        ('unity', 274, 24274, 0.1, pytest.xfail.Exception),
        ('new-case', 274, 24274, 0.1, pytest.fail.Exception),
        ('new-case', 274, 8561, 0.1, pytest.xfail.Exception),
        ('new-case', 274, 4000, 0.1, pytest.fail.Exception),
        ('unity', None, None, 0.1, AssertionError),
        ('unity', 274, 24274, None, AssertionError),
    ],
)
def test_only_measured_documented_differences_are_expected(
    case_name: str,
    first: int | None,
    last: int | None,
    maximum: float | None,
    outcome: type[BaseException],
) -> None:
    case = harness.Case(name=case_name, notes=[harness.Note(tick=11)], end_tick=6000)
    report = {
        'native_vs_reference': {'passed': False, 'maximum_error': maximum},
        'authored_notes': [
            {
                'expected_onset_frame': 275,
                'first_audible_frame': 275,
                'last_audible_frame': 24401,
            }
        ],
        'reference_notes': [{'first_audible_frame': first, 'last_audible_frame': last}],
    }
    with pytest.raises(outcome):
        expectations.check_waveform(case, report, 'native_vs_reference')
