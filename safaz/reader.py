"""Read SFZ files and seal their local sample assets."""

from pathlib import Path
from typing import Literal

from ufor.time import Rate, Timebase

from .assets import read_audio_metadata
from .compiler import compile_instrument
from .model import SfzCompileResult, SfzMidiBindingRequest
from .parser import parse, sample_paths


def read(
    path: Path,
    output_rate: int = 48_000,
    output_channels: list[str] | None = None,
    *,
    sequence_counter: Literal['reject', 'all_note_ons'] = 'reject',
    polyphony_overflow: Literal['diagnose', 'oldest_immediate'] = 'diagnose',
    filter_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
    midi_binding: SfzMidiBindingRequest | None = None,
) -> SfzCompileResult:
    """Seal local assets and import with explicit stereo/48 kHz output defaults."""
    source = parse(path.read_text(encoding='utf-8-sig'))
    root = path.parent.resolve()
    assets = {}
    for reference in sample_paths(source):
        sample = root.joinpath(reference).resolve()
        if not sample.is_relative_to(root):
            raise ValueError(
                f'SFZ sample escapes the instrument directory: {reference}'
            )
        assets[reference] = read_audio_metadata(sample)
    return compile_instrument(
        source,
        name=path.stem,
        title=path.stem,
        assets=assets,
        output_timebase=Timebase(name='output', rate=Rate(numerator=output_rate)),
        output_channels=output_channels
        if output_channels is not None
        else ['left', 'right'],
        sequence_counter=sequence_counter,
        polyphony_overflow=polyphony_overflow,
        filter_response=filter_response,
        midi_binding=midi_binding,
    )
