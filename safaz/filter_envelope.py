"""Explicit continuous envelope convention for the bounded SFZ filter subset."""

from fractions import Fraction
from math import floor, isfinite
from typing import Literal

from ufor import envelfo, segments
from ufor.approach import ExponentialApproach

from .model import ParsedOpcode, UnimplementedFeature
from .parser import _add_unimplemented
from .release import release_stage


def filter_envelope(
    values: dict[str, str],
    declarations: dict[str, ParsedOpcode],
    output_rate: float,
    response: Literal['diagnose', 'portable_exponential'],
    control_triggered: bool,
    has_filter: bool,
    unimplemented: list[UnimplementedFeature],
) -> envelfo.Envelope | None:
    defaults = {
        'delay': 0,
        'attack': 0,
        'hold': 0,
        'decay': 0,
        'release': 0.001,
        'start': 0,
        'sustain': 100,
        'depth': 0,
    }
    settings = {n: float(values.get(f'fileg_{n}', str(v))) for n, v in defaults.items()}
    invalid = False
    for name, value in settings.items():
        if not isfinite(value):
            raise ValueError(f'fileg_{name} must be finite')
        low, high = (-12000, 12000) if name == 'depth' else (0, 100)
        if not low <= value <= high:
            _add_unimplemented(
                unimplemented,
                declarations[f'fileg_{name}'],
                f'fileg_{name} is outside the verified {low}-{high} range',
            )
            invalid = True
    if invalid or settings['depth'] == 0:
        return None
    reason = None
    if control_triggered or values.get('trigger', 'attack') != 'attack':
        reason = 'Filter envelopes support only ordinary note-on triggers'
    elif not has_filter:
        reason = 'Filter envelope requires an explicit imported first filter'
    elif response == 'diagnose':
        reason = (
            'Filter envelope requires filter_envelope_response="portable_exponential" '
            'to accept continuous threshold crossings and terminal transitions'
        )
    if reason is not None:
        _add_unimplemented(unimplemented, declarations['fileg_depth'], reason)
        return None
    start, sustain = settings['start'] / 100, settings['sustain'] / 100
    release = release_stage(settings['release'])
    rate = Fraction(output_rate)
    parts: list[segments.Segment | segments.IndefiniteSegment | ExponentialApproach] = [
        segments.Segment(
            duration=Fraction(floor(Fraction(values.get('fileg_delay', '0')) * rate))
            / rate,
            to=start,
        ),
        segments.Segment(
            duration=Fraction(values.get('fileg_attack', '0'))
            * (1 - Fraction(values.get('fileg_start', '0')) / 100),
            to=1.0,
        ),
        segments.Segment(
            duration=Fraction(floor(Fraction(values.get('fileg_hold', '0')) * rate))
            / rate,
            to=1.0,
        ),
    ]
    free_running = sustain <= 0.0032
    threshold = min(1.0, sustain + 0.001)
    if settings['decay']:
        parts.append(
            ExponentialApproach(
                asymptote=0.0,
                time_constant=max(0.006, settings['decay']) / 9,
                threshold=threshold,
                transition_to=threshold if free_running else sustain,
                transition_seconds=0.0 if free_running else 0.05,
            )
        )
    else:
        parts.append(segments.Segment(duration=0, to=sustain))
    if free_running:
        parts.append(release)
    return envelfo.Envelope(
        initial=start, segments=parts, release=[release], hold=not free_running
    )
