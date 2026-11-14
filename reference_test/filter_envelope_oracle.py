"""Independent continuous equations for the declared portable filter profile."""

from math import log

import numpy as np
from pydantic import BaseModel


class EnvelopeProfile(BaseModel, frozen=True):
    depth: float = 1200
    start: float = 0.2
    delay: float = 0.1
    attack: float = 0.5
    hold: float = 0.1
    decay: float = 0.5
    sustain: float = 0.3
    release: float = 0.1
    release_at: float = 0.25
    amplitude_release: float = 0.1


def declarations(profile: EnvelopeProfile) -> str:
    return ' '.join(
        f'fileg_{n}={v:g}'
        for n, v in [
            ('depth', profile.depth),
            ('start', profile.start * 100),
            ('delay', profile.delay),
            ('attack', profile.attack),
            ('hold', profile.hold),
            ('decay', profile.decay),
            ('sustain', profile.sustain * 100),
            ('release', profile.release),
        ]
    )


def levels(profile: EnvelopeProfile, age: np.ndarray, rate: int) -> np.ndarray:
    captured = float(onset(profile, np.asarray([profile.release_at]), rate)[0])
    return np.where(
        age < profile.release_at,
        onset(profile, age, rate),
        release(captured, age - profile.release_at, profile.release),
    )


def onset(profile: EnvelopeProfile, age: np.ndarray, rate: int) -> np.ndarray:
    delay = np.floor(profile.delay * rate) / rate
    attack = profile.attack * (1 - profile.start)
    decay_start = delay + attack + np.floor(profile.hold * rate) / rate
    peak = (
        np.where(
            age < delay,
            profile.start,
            profile.start
            + (1 - profile.start) * np.minimum(np.maximum(0, age - delay) / attack, 1),
        )
        if attack
        else np.where(age < delay, profile.start, 1)
    )
    free = profile.sustain <= 0.0032
    threshold = min(1, profile.sustain + 0.001)
    if profile.decay:
        duration = round(-max(profile.decay, 0.006) / 9 * log(threshold) * 1e9) / 1e9
        decaying = (
            np.exp(log(threshold) * np.clip((age - decay_start) / duration, 0, 1))
            if duration
            else np.full(age.shape, threshold)
        )
        settled = (
            release(threshold, age - decay_start - duration, profile.release)
            if free
            else threshold
            + (profile.sustain - threshold)
            * np.clip((age - decay_start - duration) / 0.05, 0, 1)
        )
        onset = np.where(
            age < decay_start,
            peak,
            np.where(age < decay_start + duration, decaying, settled),
        )
    else:
        settled = (
            release(profile.sustain, age - decay_start, profile.release)
            if free
            else np.full(age.shape, profile.sustain)
        )
        onset = np.where(age < decay_start, peak, settled)
    return onset


def release(initial: float, elapsed: np.ndarray, seconds: float) -> np.ndarray:
    duration = (
        round(max(seconds, 0.006) / 9 * log(initial / 0.0001) * 1e9) / 1e9
        if seconds and initial > 0.0001
        else 0
    )
    terminal = 0.0001 if duration else initial
    fade = round(0.05 * min(1, terminal / 0.0001) * 1e9) / 1e9
    decay = (
        initial * np.exp(log(0.0001 / initial) * np.clip(elapsed / duration, 0, 1))
        if duration
        else np.full(elapsed.shape, initial)
    )
    fading = (
        terminal * np.clip(1 - (elapsed - duration) / fade, 0, 1)
        if fade
        else np.zeros(elapsed.shape)
    )
    return np.where(elapsed < duration, decay, fading)
