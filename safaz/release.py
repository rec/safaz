"""SFZ release law shared by amplitude and filter-envelope conversion."""

from ufor.approach import ExponentialApproach


def release_stage(seconds: float) -> ExponentialApproach:
    return ExponentialApproach(
        asymptote=0,
        time_constant=seconds / 9,
        minimum_time_constant=0.006 / 9,
        threshold=0.0001,
        transition_to=0,
        transition_seconds=0.05,
        minimum_transition_distance=0.0001,
    )
