"""Explicit continuous envelope convention for the bounded SFZ filter subset."""

from decimal import Decimal, localcontext
from fractions import Fraction
from math import floor, isfinite
from typing import Literal

from ufor import envelfo, segments
from ufor.approach import ExponentialApproach

from .filters import inverse_value, nearby_values
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
    return _build_envelope(values, settings, output_rate)


def filter_envelope_values(
    body: envelfo.Envelope, output_rate: float
) -> dict[str, str] | None:
    """Recover SFZ values only when the importer can recreate this envelope."""
    if not isinstance(body.initial, float) or len(body.segments) < 4:
        return None
    delay, attack, hold, decay = body.segments[:4]
    if not (
        isinstance(delay, segments.Segment)
        and isinstance(attack, segments.Segment)
        and isinstance(hold, segments.Segment)
    ):
        return None
    if len(body.release) != 1 or not isinstance(
        release := body.release[0], ExponentialApproach
    ):
        return None
    release_time = inverse_value(
        release.time_constant * 9, lambda n: n / 9, release.time_constant, 0, 100
    )
    if isinstance(decay, ExponentialApproach):
        decay_time = inverse_value(
            max(0.006, decay.time_constant * 9),
            lambda n: max(0.006, n) / 9,
            decay.time_constant,
            0.006,
            100,
        )
        sustain = decay.transition_to if body.hold else decay.threshold - 0.001
    elif isinstance(decay, segments.Segment):
        decay_time = 0.0
        sustain = decay.to
    else:
        return None
    if decay_time is None or release_time is None:
        return None
    rate = Fraction(output_rate)
    delay_text, hold_text = (_frame_time(s.duration, rate) for s in (delay, hold))
    if delay_text is None or hold_text is None:
        return None
    for start in nearby_values(body.initial * 100):
        if not 0 <= start <= 100 or start / 100 != body.initial:
            continue
        scale = 1 - Fraction(str(start)) / 100
        if scale == 0 and attack.duration != 0:
            continue
        duration = attack.duration / scale if scale else Fraction(0)
        if (
            not 0 <= duration <= 100
            or (attack_text := _exact_decimal(duration)) is None
        ):
            continue
        for percent in nearby_values(sustain * 100):
            if not 0 <= percent <= 100:
                continue
            values = {
                'fileg_delay': delay_text,
                'fileg_attack': attack_text,
                'fileg_hold': hold_text,
                'fileg_decay': str(decay_time),
                'fileg_release': str(release_time),
                'fileg_start': str(start),
                'fileg_sustain': str(percent),
            }
            settings = {n.removeprefix('fileg_'): float(v) for n, v in values.items()}
            if _build_envelope(values, settings, output_rate) == body:
                return values
    return None


def _frame_time(seconds: Fraction, rate: Fraction) -> str | None:
    frames = seconds * rate
    if frames.denominator != 1 or not 0 <= seconds <= 100:
        return None
    for candidate in nearby_values(float(seconds)):
        text = str(candidate)
        if 0 <= candidate <= 100 and floor(Fraction(text) * rate) == frames:
            return text
    return None


def _exact_decimal(value: Fraction) -> str | None:
    with localcontext() as context:
        context.prec = len(str(abs(value.numerator))) + value.denominator.bit_length()
        text = str(Decimal(value.numerator) / Decimal(value.denominator))
    return text if Fraction(text) == value else None


def _build_envelope(
    values: dict[str, str], settings: dict[str, float], output_rate: float
) -> envelfo.Envelope:
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
