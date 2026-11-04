"""Read SFZ files and seal their local sample assets."""

from pathlib import Path
from typing import Literal

from reccy.runtime.asset_sets import (
    AssetPreparationError,
    PackageManifest,
    export_package,
    prepare_assets,
    stream_identity,
)
from ufor.time import Rate, Timebase

from .assets import inspect_audio, open_sample
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
    filter_lfo_response: Literal['diagnose', 'sfizz_triangle'] = 'diagnose',
    pitch_lfo_response: Literal['diagnose', 'sfizz_parabolic'] = 'diagnose',
    amplitude_lfo_response: Literal['diagnose', 'sfizz_parabolic'] = 'diagnose',
    pitch_bend_response: Literal['diagnose', 'sfizz_symmetric'] = 'diagnose',
    midi_binding: SfzMidiBindingRequest | None = None,
) -> SfzCompileResult:
    """Seal local assets and import with explicit stereo/48 kHz output defaults."""
    source = parse(path.read_text(encoding='utf-8-sig'))
    root = path.parent.resolve()
    requests = {}
    for reference in sample_paths(source):
        sample = root.joinpath(reference).resolve()
        if not sample.is_relative_to(root):
            raise ValueError(
                f'SFZ sample escapes the instrument directory: {reference}'
            )
        requests[reference] = open_sample(sample)
    try:
        with prepare_assets(requests) as prepared:
            assets = {n: inspect_audio(s, n) for n, s in prepared.streams.items()}
    except AssetPreparationError as error:
        raise ValueError(f'Cannot read SFZ sample: {error}') from error
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
        filter_lfo_response=filter_lfo_response,
        pitch_lfo_response=pitch_lfo_response,
        amplitude_lfo_response=amplitude_lfo_response,
        pitch_bend_response=pitch_bend_response,
        midi_binding=midi_binding,
    )


def package(path: Path, destination: Path) -> PackageManifest:
    """Publish a verified local SFZ and its samples without changing their bytes."""
    with open_sample(path) as document:
        source = parse(document.read().decode('utf-8-sig'))
        references = sample_paths(source)
        if path.name in references:
            raise ValueError('SFZ document conflicts with a sample path')
        root = path.parent.resolve()
        requests = {}
        for reference in references:
            sample = root.joinpath(reference).resolve()
            if not sample.is_relative_to(root):
                raise ValueError(
                    f'SFZ sample escapes the instrument directory: {reference}'
                )
            requests[reference] = open_sample(sample)
        with prepare_assets(requests) as prepared:
            for name, stream in prepared.streams.items():
                inspect_audio(stream, name)
            manifest = PackageManifest(
                files={
                    path.name: stream_identity(document),
                    **prepared.identities,
                }
            )
            export_package(
                destination, {path.name: document, **prepared.streams}, manifest
            )
            return manifest
