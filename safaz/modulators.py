"""SFZ modulation signals expressed using portable generator composition."""

from fractions import Fraction
from math import ceil, isfinite
from typing import Literal

from ufor import envelfo, segments

from .model import ParsedOpcode, UnimplementedFeature
from .parser import _add_unimplemented


def accepted_lfo(
    values: dict[str, str],
    declarations: dict[str, ParsedOpcode],
    prefix: str,
    response: Literal['diagnose', 'sfizz_triangle'],
    depth_limit: float,
    control_triggered: bool,
    unimplemented: list[UnimplementedFeature],
) -> bool:
    invalid = False
    for suffix, low, high in [
        ('freq', 0, 20),
        ('depth', -depth_limit, depth_limit),
        ('delay', 0, 100),
        ('fade', 0, 100),
    ]:
        name = f'{prefix}_{suffix}'
        value = float(values.get(name, '0'))
        if not isfinite(value):
            raise ValueError(f'{name} must be finite')
        if not low <= value <= high:
            _add_unimplemented(
                unimplemented,
                declarations[name],
                f'{name} is outside the verified {low}-{high} range',
            )
            invalid = True
    if (
        invalid
        or not float(values.get(f'{prefix}_depth', '0'))
        or not float(values.get(f'{prefix}_freq', '0'))
    ):
        return False
    reason = None
    if control_triggered or values.get('trigger', 'attack') != 'attack':
        reason = 'SFZ LFO supports only ordinary note-on triggers in this profile'
    elif response == 'diagnose':
        choice = (
            'pitch_lfo_response' if prefix == 'pitchlfo' else 'amplitude_lfo_response'
        )
        reason = (
            f'SFZ LFO requires {choice}="sfizz_triangle" '
            'to accept waveform, phase and depth conventions'
        )
    if reason is not None:
        _add_unimplemented(unimplemented, declarations[f'{prefix}_depth'], reason)
        return False
    return True


def triangle_lfo(
    values: dict[str, str], prefix: str, output_rate: float
) -> envelfo.LFO | envelfo.Patch:
    rate = Fraction(values[f'{prefix}_freq'])
    delay = Fraction(
        ceil(Fraction(values.get(f'{prefix}_delay', '0')) * output_rate)
    ) / Fraction(output_rate)
    fade = Fraction(values.get(f'{prefix}_fade', '0'))
    oscillator = envelfo.LFO(
        shape='triangle', rate=rate, phase=(Fraction(1, 4) - rate * delay) % 1
    )
    if not delay and not fade:
        return oscillator
    # Gate the signal before the nonlinear route, not its mapped contribution.
    # The phase offset makes the first audible cycle start after the delay.
    return envelfo.Patch(
        envelfos={
            'oscillator': oscillator,
            'activation': envelfo.Envelope(
                initial=0,
                segments=[
                    segments.Segment(duration=delay, to=0),
                    segments.Segment(duration=fade, to=1),
                ],
            ),
            'signal': envelfo.Product(inputs=['oscillator', 'activation']),
        },
        outputs={'signal': 'signal'},
    )
