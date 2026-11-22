"""Shared bounds and response names for the supported SFZ filter profile."""

from collections.abc import Callable, Iterator
from math import asinh, inf, log, nextafter, sin, sinh, tau

from ufor.samples.processing import FilterResponse


def cutoff_limit(output_rate: float) -> float:
    return min(20_000, 0.999 * output_rate / 2)


def eq_resonance(frequency: float, bandwidth: float, rate: float) -> float:
    """Translate octave bandwidth to the pinned player's digital peaking Q."""
    omega = tau * frequency / rate
    scale = log(2) * omega / (2 * sin(omega))
    try:
        return 1 / (2 * sinh(scale * bandwidth))
    except OverflowError:
        return 0


def eq_bandwidth(frequency: float, resonance: float, rate: float) -> float | None:
    omega = tau * frequency / rate
    scale = log(2) * omega / (2 * sin(omega))
    return inverse_value(
        asinh(0.5 / resonance) / scale,
        lambda value: eq_resonance(frequency, value, rate),
        resonance,
        0.001,
        4,
    )


def nearby_values(value: float) -> Iterator[float]:
    """Try adjacent floats when inverting a rounded SFZ lookup."""
    yield value
    yield nextafter(value, -inf)
    yield nextafter(value, inf)


def inverse_value(
    estimate: float,
    forward: Callable[[float], float],
    value: float,
    minimum: float,
    maximum: float,
) -> float | None:
    return next(
        (
            n
            for n in nearby_values(estimate)
            if minimum <= n <= maximum and forward(n) == value
        ),
        None,
    )


FILTER_RESPONSES = {
    'lpf_2p': FilterResponse.lowpass,
    'hpf_2p': FilterResponse.highpass,
    'bpf_2p': FilterResponse.bandpass,
    'brf_2p': FilterResponse.notch,
}
