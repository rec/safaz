"""SFZ modulation signals expressed using portable generator composition."""

from fractions import Fraction
from math import ceil, isfinite
from typing import Literal

from ufor import envelfo, segments

from .model import ParsedOpcode, UnimplementedFeature
from .parser import _add_unimplemented

FilterLfoResponse = Literal['diagnose', 'sfizz_triangle', 'sfizz_parabolic']


def accepted_lfo(
    values: dict[str, str],
    declarations: dict[str, ParsedOpcode],
    prefix: str,
    response: Literal['diagnose', 'sfizz_parabolic'],
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
            f'SFZ LFO requires {choice}="sfizz_parabolic" '
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


def parabolic_lfo(
    values: dict[str, str], prefix: str, output_rate: float
) -> envelfo.Patch:
    """Compose sfizz's v1 sine approximation, u * (2 - abs(u))."""
    rate = Fraction(values[f'{prefix}_freq'])
    delay = Fraction(
        ceil(Fraction(values.get(f'{prefix}_delay', '0')) * output_rate)
    ) / Fraction(output_rate)
    triangle = triangle_lfo(values, prefix, output_rate)
    bodies = (
        triangle.model_dump()['envelfos']
        if isinstance(triangle, envelfo.Patch)
        else {'oscillator': triangle}
    )
    triangle_output = 'signal' if isinstance(triangle, envelfo.Patch) else 'oscillator'
    return envelfo.Patch(
        envelfos=bodies
        | {
            'double': envelfo.LFO(
                shape='triangle', rate=2 * rate, phase=(-2 * rate * delay) % 1
            ),
            'factor': envelfo.Affine(input='double', scale=-0.5, offset=1.5),
            'parabolic': envelfo.Product(inputs=[triangle_output, 'factor']),
        },
        outputs={'signal': 'parabolic'},
    )


def lfo_values(
    body: envelfo.EnveLFO, prefix: str, output_rate: float, *, parabolic: bool
) -> dict[str, str] | None:
    oscillator = (
        body.envelfos.get('oscillator') if isinstance(body, envelfo.Patch) else body
    )
    if not isinstance(oscillator, envelfo.LFO) or not isinstance(
        oscillator.rate, Fraction
    ):
        return None
    rate = oscillator.rate
    if not 0 < rate <= 21 or not 0 < float(rate) <= 20:
        return None
    frequency = _decimal(rate)
    if frequency is None:
        return None
    values = {f'{prefix}_freq': frequency}
    if isinstance(body, envelfo.Patch) and 'activation' in body.envelfos:
        activation = body.envelfos['activation']
        if (
            not isinstance(activation, envelfo.Envelope)
            or len(activation.segments) != 2
        ):
            return None
        first, second = activation.segments
        if not isinstance(first, segments.Segment) or not isinstance(
            second, segments.Segment
        ):
            return None
        delay, fade = first.duration, second.duration
        if (
            not 0 <= delay <= 100 + 1 / output_rate
            or not 0 <= fade <= 101
            or not 0 <= float(fade) <= 100
        ):
            return None
        fade_text = _decimal(fade)
        if fade_text is None:
            return None
        # Any duration rounding up to the same frame rebuilds the same patch.
        delay_value = min(100.0, float(delay) - 0.5 / output_rate) if delay else 0.0
        if not 0 <= delay_value <= 100:
            return None
        values[f'{prefix}_delay'] = repr(delay_value)
        values[f'{prefix}_fade'] = fade_text
    build = parabolic_lfo if parabolic else triangle_lfo
    return values if build(values, prefix, output_rate) == body else None


def _decimal(value: Fraction) -> str | None:
    denominator = value.denominator
    twos = fives = 0
    while denominator % 2 == 0:
        denominator //= 2
        twos += 1
    while denominator % 5 == 0:
        denominator //= 5
        fives += 1
    if denominator != 1:
        return None
    digits = max(twos, fives)
    scaled = value.numerator * 2 ** (digits - twos) * 5 ** (digits - fives)
    return f'{scaled}e-{digits}' if digits else str(scaled)
