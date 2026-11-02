"""SFZ modulation signals expressed using portable generator composition."""

from fractions import Fraction
from math import ceil

from ufor import envelfo, segments


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
