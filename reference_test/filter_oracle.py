"""Authored filter equations, independent of safaz/uFor/enge DSP helpers."""

from typing import Literal

import numpy as np
from pydantic import BaseModel


class FilterSpec(BaseModel, frozen=True):
    response: Literal['lpf_2p', 'hpf_2p', 'bpf_2p', 'brf_2p']
    cutoff: float = 1500
    resonance: float = 0
    keytrack: int = 0
    keycenter: int = 60
    veltrack: int = 0
    lfo_frequency: float = 0
    lfo_depth: float = 0
    lfo_delay: float = 0
    lfo_fade: float = 0


class FilterProfile(BaseModel, frozen=True):
    filters: list[FilterSpec]
    attack: float = 0


def declarations(profile: FilterProfile) -> str:
    result = []
    for index, spec in enumerate(profile.filters, 1):
        prefix = 'fil' if index == 1 else 'fil2'
        suffix = '' if index == 1 else '2'
        result.extend(
            [
                f'{prefix}_type={spec.response}',
                f'cutoff{suffix}={spec.cutoff:g}',
                f'resonance{suffix}={spec.resonance:g}',
                f'{prefix}_keytrack={spec.keytrack}',
                f'{prefix}_keycenter={spec.keycenter}',
                f'{prefix}_veltrack={spec.veltrack}',
            ]
        )
        if spec.lfo_frequency:
            result.extend(
                [
                    f'fillfo_freq={spec.lfo_frequency:g}',
                    f'fillfo_depth={spec.lfo_depth:g}',
                ]
            )
        if spec.lfo_delay or spec.lfo_fade:
            result.extend(
                [f'fillfo_delay={spec.lfo_delay:g}', f'fillfo_fade={spec.lfo_fade:g}']
            )
    return ' '.join(result)


def cutoffs(
    spec: FilterSpec, key: int, velocity: float, frames: int, rate: int
) -> np.ndarray:
    age = np.arange(frames) / rate
    delayed_age = np.maximum(0, age - np.ceil(spec.lfo_delay * rate) / rate)
    gate = (age >= np.ceil(spec.lfo_delay * rate) / rate).astype(float)
    if spec.lfo_fade:
        gate *= np.minimum(1, delayed_age / spec.lfo_fade)
    triangle = (
        1 - 4 * np.abs((spec.lfo_frequency * delayed_age + 0.25) % 1 - 0.5)
    ) * gate
    cents = (
        spec.keytrack * (key - spec.keycenter)
        + spec.veltrack * velocity
        + spec.lfo_depth * triangle
    )
    return spec.cutoff * 2 ** (cents / 1200)


def render(
    profile: FilterProfile,
    audio: np.ndarray,
    key: int,
    velocity: float,
    rate: int,
    *,
    before_amplitude: bool = False,
) -> np.ndarray:
    """Solve the coupled trapezoidal equations by an explicit 2x2 inverse.

    [1 + g/Q, g; -g, 1] [band, low] = [s1 + g*x, s2].
    Integrator memory becomes 2*[band, low] - [s1, s2]. Static transfer is RBJ;
    time-varying state is deliberately the declared native topology.
    """
    result = audio.copy()
    amplitude = (
        np.minimum(np.arange(len(audio)) / (profile.attack * rate), 1)
        if profile.attack
        else np.ones(len(audio))
    )
    if not before_amplitude:
        result *= amplitude[:, None]
    for spec in profile.filters:
        q = 10 ** (spec.resonance / 20)
        g = np.tan(np.pi * cutoffs(spec, key, velocity, len(audio), rate) / rate)
        d = 1 + g / q + g * g
        s1 = np.zeros(audio.shape[1])
        s2 = np.zeros(audio.shape[1])
        for index in range(len(audio)):
            rhs = s1 + g[index] * result[index]
            band = (rhs - g[index] * s2) / d[index]
            low = (g[index] * rhs + (1 + g[index] / q) * s2) / d[index]
            s1, s2 = 2 * band - s1, 2 * low - s2
            if spec.response == 'lpf_2p':
                result[index] = low
            elif spec.response == 'hpf_2p':
                result[index] -= band / q + low
            elif spec.response == 'bpf_2p':
                result[index] = band / q
            else:
                result[index] -= band / q
    if before_amplitude:
        result *= amplitude[:, None]
    return result


def transfer(
    spec: FilterSpec, cutoff: float, frequencies: np.ndarray, rate: int
) -> np.ndarray:
    """RBJ z-domain transfer, independent of the time-domain matrix oracle."""
    omega = 2 * np.pi * cutoff / rate
    c = np.cos(omega)
    alpha = np.sin(omega) / (2 * 10 ** (spec.resonance / 20))
    if spec.response == 'lpf_2p':
        b = [(1 - c) / 2, 1 - c, (1 - c) / 2]
    elif spec.response == 'hpf_2p':
        b = [(1 + c) / 2, -1 - c, (1 + c) / 2]
    elif spec.response == 'bpf_2p':
        b = [alpha, 0, -alpha]
    else:
        b = [1, -2 * c, 1]
    z = np.exp(-2j * np.pi * frequencies / rate)
    return (b[0] + b[1] * z + b[2] * z**2) / (
        1 + alpha - 2 * c * z + (1 - alpha) * z**2
    )


def response_measurements(
    profile: FilterProfile,
    audio: np.ndarray,
    source: np.ndarray,
    key: int,
    velocity: float,
    gain: float,
    rate: int,
    waveform_budget: float,
) -> dict[str, object]:
    """Fixed steady window; no offset search or fitted gain. LFOs use full audio."""
    frequencies = np.array([500, 1500, 3500, 7500])
    start, end = rate // 4, rate // 2
    phases = np.exp(-2j * np.pi * frequencies[:, None] * np.arange(start, end) / rate)
    source_amplitudes = 2 * np.abs(phases @ source[start:end, 0]) / (end - start)
    actual = 2 * np.abs(phases @ audio[start:end, 0]) / (end - start)
    expected_transfer = np.ones(len(frequencies), dtype=np.complex128)
    for spec in profile.filters:
        cutoff = float(cutoffs(spec, key, velocity, 1, rate)[0])
        expected_transfer *= transfer(spec, cutoff, frequencies, rate)
    expected = source_amplitudes * gain * np.abs(expected_transfer)
    observed_gain = actual / (source_amplitudes * gain)
    nonnull = np.abs(expected_transfer) > 1e-12
    positive = bool(np.all(observed_gain[nonnull] > 0))
    db_error = (
        float(
            np.max(
                np.abs(
                    20
                    * np.log10(
                        observed_gain[nonnull] / np.abs(expected_transfer[nonnull])
                    )
                )
            )
        )
        if positive
        else None
    )
    # |2/N sum(e[n] exp(-jw*n))| <= 2*max|e|. Reuse the existing
    # pointwise PCM/float budget; this is not an empirically fitted dB limit.
    amplitude_limit = 2 * waveform_budget
    return {
        'frequencies_hz': frequencies.tolist(),
        'window_relative_frames': [start, end],
        'expected_gain': np.abs(expected_transfer).tolist(),
        'observed_gain': observed_gain.tolist(),
        'expected_output_amplitude': expected.tolist(),
        'observed_output_amplitude': actual.tolist(),
        'maximum_response_db_error': db_error,
        'maximum_null_gain': float(np.max(observed_gain[~nonnull], initial=0)),
        'native_response_db_limit': 1e-6,
        'native_null_gain_limit': 1e-12,
        'amplitude_error_limit': amplitude_limit,
        'amplitude_passed': bool(np.all(np.abs(actual - expected) <= amplitude_limit)),
    }
