from fractions import Fraction
from math import log, sqrt

import pytest
from envelfo.runtime import envelfo_at, envelfo_event, initial_envelfo
from test_modulators import compile_modulation
from ufor.approach import ExponentialApproach
from ufor.envelfo import EnvelfoEvent

from safaz.compiler import amplitude_envelope


@pytest.mark.parametrize('seconds', [0, 0.001, 0.1])
@pytest.mark.parametrize('initial', [0, 0.00001, 0.2, 1])
def test_release_captures_the_level_and_preserves_the_terminal_fade(
    seconds: float,
    initial: float,
) -> None:
    body = amplitude_envelope(
        {
            'ampeg_start': str(initial * 100),
            'ampeg_delay': '0.1',
            'ampeg_release': str(seconds),
        }
    )
    assert isinstance(body.release[0], ExponentialApproach)
    state = envelfo_event(
        body,
        initial_envelfo(body, Fraction(0)),
        EnvelfoEvent(at=Fraction(0), ordinal=0, action='note_on'),
    )
    gate = Fraction(1, 20)
    released = envelfo_event(
        body, state, EnvelfoEvent(at=gate, ordinal=1, action='note_off')
    )
    duration = (
        Fraction(round(max(seconds, 0.006) / 9 * log(initial / 0.0001) * 1e9), 10**9)
        if seconds and initial > 0.0001
        else Fraction(0)
    )
    terminal = 0.0001 if duration else initial
    fade = Fraction(round(0.05 * min(1, terminal / 0.0001) * 1e9), 10**9)
    if duration:
        assert envelfo_at(body, released, gate + duration / 2).value == pytest.approx(
            sqrt(initial * 0.0001)
        )
    if fade:
        assert envelfo_at(
            body, released, gate + duration + fade / 2
        ).value == pytest.approx(terminal / 2)
    complete = envelfo_at(body, released, gate + duration + fade)
    assert complete.value == 0 and complete.status == 'complete'


@pytest.mark.parametrize('base,amount', [(0, 0.1), (0.001, 0.1), (0.1, -0.1)])
def test_velocity_release_modulates_time_constant_before_the_positive_floor(
    base: float,
    amount: float,
) -> None:
    result = compile_modulation(f'ampeg_release={base} ampeg_vel2release={amount}')
    assert result.complete and result.instrument is not None
    slot = result.instrument.body.slots[0]
    parameter = next(
        p for p in slot.modulation.parameters if p.target.name == 'envelope'
    )
    route = next(r for r in slot.modulation.routes if r.target == parameter.target)
    assert parameter.target.parameter == 'release-0-time_constant'
    assert slot.parameter_definition(parameter.target)[1] == base / 9
    assert parameter.default == base / 9
    assert route.points[-1].amount == amount / 9
    stage = slot.envelope.release[0]
    assert isinstance(stage, ExponentialApproach)
    assert stage.minimum_time_constant == 0.006 / 9
