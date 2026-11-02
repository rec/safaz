"""Authored modulation equations, independent of importer and DSP helpers."""

import numpy as np
from pydantic import BaseModel


class ModulationProfile(BaseModel, frozen=True):
    pitch_depth: float = 0
    amplitude_depth: float = 0
    bend_up: float | None = None
    bend_down: float = -200
    frequency: float = 2
    delay: float = 0
    fade: float = 0


def declarations(profile: ModulationProfile) -> str:
    result = (
        f'pitchlfo_freq={profile.frequency:g} pitchlfo_depth={profile.pitch_depth:g} '
        f'pitchlfo_delay={profile.delay:g} pitchlfo_fade={profile.fade:g} '
        f'amplfo_freq={profile.frequency:g} amplfo_depth={profile.amplitude_depth:g} '
        f'amplfo_delay={profile.delay:g} amplfo_fade={profile.fade:g}'
    )
    if profile.bend_up is not None:
        result += f' bend_up={profile.bend_up:g} bend_down={profile.bend_down:g}'
    return result


def render(profile: ModulationProfile, source: np.ndarray, rate: int) -> np.ndarray:
    age = np.arange(2 * rate) / rate
    delay = np.ceil(profile.delay * rate) / rate
    active = np.maximum(0, age - delay)
    gate = (age >= delay).astype(float)
    if profile.fade:
        gate *= np.minimum(1, active / profile.fade)
    phase = (profile.frequency * active) % 1
    x = 2 * phase - 1
    signal = -4 * x * (1 - np.abs(x)) * gate
    cents = profile.pitch_depth * signal
    if profile.bend_up is not None:
        bend = np.select(
            [
                (age >= 0.1) & (age < 0.2),
                (age >= 0.3) & (age < 0.4),
                (age >= 0.4) & (age < 0.45),
                (age >= 0.45) & (age < 0.5),
            ],
            [
                profile.bend_up,
                profile.bend_down,
                profile.bend_down * 4096 / 8191,
                profile.bend_up * 4096 / 8191,
            ],
            default=0,
        )
        cents = cents + bend
    increments = 2 ** (cents / 1200)
    positions = np.concatenate(([0], np.cumsum(increments[:-1])))
    audio = np.column_stack(
        [
            np.interp(positions, np.arange(len(source)), source[:, c], right=0)
            for c in range(source.shape[1])
        ]
    )
    return audio * 10 ** (profile.amplitude_depth * signal[:, None] / 20)
