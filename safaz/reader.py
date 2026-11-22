"""Read SFZ files and seal their local sample assets."""

from contextlib import ExitStack
from functools import cache
from pathlib import Path
from typing import BinaryIO, Literal

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
from .modulators import FilterLfoResponse
from .parser import parse, sample_paths


def read(
    path: Path,
    output_rate: int = 48_000,
    output_channels: list[str] | None = None,
    *,
    resolve_includes: bool = False,
    sequence_counter: Literal['reject', 'all_note_ons'] = 'reject',
    polyphony_overflow: Literal['diagnose', 'oldest_immediate'] = 'diagnose',
    filter_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
    eq_response: Literal['diagnose', 'sfizz_rbj'] = 'diagnose',
    filter_lfo_response: FilterLfoResponse = 'diagnose',
    filter_envelope_response: Literal['diagnose', 'portable_exponential'] = 'diagnose',
    pitch_lfo_response: Literal['diagnose', 'sfizz_parabolic'] = 'diagnose',
    amplitude_lfo_response: Literal['diagnose', 'sfizz_parabolic'] = 'diagnose',
    pitch_bend_response: Literal['diagnose', 'sfizz_symmetric'] = 'diagnose',
    variation_response: Literal['diagnose', 'portable_seeded'] = 'diagnose',
    cc_crossfade_response: Literal['diagnose', 'portable_ramp'] = 'diagnose',
    midi_binding: SfzMidiBindingRequest | None = None,
) -> SfzCompileResult:
    """Seal local assets and import with explicit stereo/48 kHz output defaults."""
    root = path.parent.resolve()

    @cache
    def load(reference: str) -> str:
        return _included_file(root, reference).read_text(encoding='utf-8-sig')

    source = parse(
        path.read_text(encoding='utf-8-sig'),
        source_name=path.name,
        include_loader=load if resolve_includes else None,
    )
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
        eq_response=eq_response,
        filter_lfo_response=filter_lfo_response,
        filter_envelope_response=filter_envelope_response,
        pitch_lfo_response=pitch_lfo_response,
        amplitude_lfo_response=amplitude_lfo_response,
        pitch_bend_response=pitch_bend_response,
        variation_response=variation_response,
        cc_crossfade_response=cc_crossfade_response,
        midi_binding=midi_binding,
    )


def package(
    path: Path, destination: Path, *, resolve_includes: bool = False
) -> PackageManifest:
    """Publish a verified local SFZ and its samples without changing their bytes."""
    with ExitStack() as stack:
        document = stack.enter_context(open_sample(path))
        includes: dict[str, BinaryIO] = {}
        root = path.parent.resolve()

        @cache
        def load(reference: str) -> str:
            stream = stack.enter_context(open_sample(_included_file(root, reference)))
            includes[reference] = stream
            return stream.read().decode('utf-8-sig')

        source = parse(
            document.read().decode('utf-8-sig'),
            source_name=path.name,
            include_loader=load if resolve_includes else None,
        )
        references = sample_paths(source)
        if {path.name, *includes} & set(references):
            raise ValueError('SFZ source conflicts with a sample path')
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
                    **{n: stream_identity(s) for n, s in includes.items()},
                    **prepared.identities,
                }
            )
            export_package(
                destination,
                {path.name: document, **includes, **prepared.streams},
                manifest,
            )
            return manifest


def _included_file(root: Path, reference: str) -> Path:
    path = root.joinpath(reference).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError(f'SFZ include escapes the instrument directory: {reference}')
    return path
