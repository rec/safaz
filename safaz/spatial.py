"""Static SFZ stereo routing under the mathematical sfizz pan law."""

from math import atan2, cos, isclose, pi, sin, sqrt

from ufor.samples.processing import ChannelRoute


def stereo_routes(width: float, pan: float, position: float = 0) -> list[ChannelRoute]:
    """Apply input pan, the symmetric width matrix, and output position."""
    angle = (width + 1) * pi / 4
    cross = 0.0 if width == 1 else cos(angle)
    direct = 0.0 if width == -1 else sin(angle)
    left, right = _stage_gains(pan)
    output_left, output_right = _stage_gains(position)
    routes = [
        ChannelRoute(input=i, output=o, gain=g)
        for i, o, g in (
            ('left', 'left', left * direct * output_left),
            ('left', 'right', left * cross * output_right),
            ('right', 'left', right * cross * output_left),
            ('right', 'right', right * direct * output_right),
        )
        if g != 0
    ]
    return routes or [ChannelRoute(input='left', output='left', gain=0)]


def stereo_opcodes(routes: list[ChannelRoute]) -> tuple[float, float, float] | None:
    gains = {(r.input, r.output): r.gain for r in routes}
    pairs = [('left', 'left'), ('left', 'right'), ('right', 'left'), ('right', 'right')]
    if len(gains) != len(routes) or gains.keys() - set(pairs):
        return None
    ll, lr, rl, rr = (gains.get(p, 0.0) for p in pairs)
    if min(ll, lr, rl, rr) < 0 or max(ll, lr, rl, rr) > 2.000000000000001:
        return None
    direct, cross = ll + rr, lr + rl
    left, right = ll + lr, rl + rr
    if not direct and not cross:
        return 1, -1, 1
    candidates = [(_position(atan2(direct, cross)), _position(atan2(right, left)), 0.0)]
    if min(ll, lr, rl, rr) > 0:
        # Products of opposite entries cancel the two independent pan stages.
        candidates.append(
            (
                _position(atan2(sqrt(ll) * sqrt(rr), sqrt(lr) * sqrt(rl))),
                _position(atan2(sqrt(rl) * sqrt(rr), sqrt(ll) * sqrt(lr))),
                _position(atan2(sqrt(lr) * sqrt(rr), sqrt(ll) * sqrt(rl))),
            )
        )
    for candidate in candidates:
        reconstructed = {(r.input, r.output): r.gain for r in stereo_routes(*candidate)}
        if all(
            isclose(gains.get(p, 0.0), reconstructed.get(p, 0.0), rel_tol=1e-14)
            for p in pairs
        ):
            return candidate
    return None


def _stage_gains(position: float) -> tuple[float, float]:
    if position == 0:
        return 1, 1
    angle = (position + 1) * pi / 4
    return (
        0.0 if position == 1 else sqrt(2) * cos(angle),
        0.0 if position == -1 else sqrt(2) * sin(angle),
    )


def _position(angle: float) -> float:
    position = 4 * angle / pi - 1
    # Keep common decimal spellings when the trigonometric inverse adds noise.
    rounded = round(position, 14)
    return rounded if isclose(position, rounded, rel_tol=1e-14) else position
