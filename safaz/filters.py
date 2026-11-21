"""Shared bounds and response names for the supported SFZ filter profile."""

from collections.abc import Callable, Iterator
from math import inf, nextafter

from ufor.samples.processing import FilterResponse


def cutoff_limit(output_rate: float) -> float:
    return min(20_000, 0.999 * output_rate / 2)


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
