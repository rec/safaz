"""Authored modulation equations, independent of importer and DSP helpers."""

import numpy as np
from pydantic import BaseModel


class ModulationProfile(BaseModel, frozen=True):
    pitch_depth: float = 0
    frequency: float = 2
    delay: float = 0
    fade: float = 0


def declarations(profile: ModulationProfile) -> str:
    return (
        f'pitchlfo_freq={profile.frequency:g} pitchlfo_depth={profile.pitch_depth:g} '
        f'pitchlfo_delay={profile.delay:g} pitchlfo_fade={profile.fade:g}'
    )


def render(profile: ModulationProfile, source: np.ndarray, rate: int) -> np.ndarray:
    age = np.arange(2 * rate) / rate
    delay = np.ceil(profile.delay * rate) / rate
    active = np.maximum(0, age - delay)
    gate = (age >= delay).astype(float)
    if profile.fade:
        gate *= np.minimum(1, active / profile.fade)
    triangle = (1 - 4 * np.abs((profile.frequency * active + 0.25) % 1 - 0.5)) * gate
    increments = 2 ** (profile.pitch_depth * triangle / 1200)
    positions = np.concatenate(([0], np.cumsum(increments[:-1])))
    return np.column_stack(
        [
            np.interp(positions, np.arange(len(source)), source[:, c], right=0)
            for c in range(source.shape[1])
        ]
    )
