"""Read and seal existing audio assets for Ufor sample instruments."""

import struct
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import BinaryIO

import soundfile
from reccy.runtime.asset_sets import stream_identity
from reccy.runtime.assets import AssetStore, SourceKind, source_fingerprint
from ufor.samples.metadata import AudioMetadata, EmbeddedLoop


def read_audio_metadata(path: Path) -> AudioMetadata:
    """Read decoded layout plus embedded loop metadata when supported."""
    with open_sample(path) as stream:
        return inspect_audio(stream, str(path))


@contextmanager
def open_sample(path: Path) -> Iterator[BinaryIO]:
    """Snapshot a local sample once, bounded by its observed file length."""
    with TemporaryDirectory(prefix='safaz-sample-') as directory:
        store = AssetStore(Path(directory), credential_scope='local')
        entry = store.import_file(
            path.parent,
            path.name,
            maximum_bytes=max(1, path.stat().st_size),
            source_key=source_fingerprint({'path': str(path)}, {}, None, {}),
            source_kind=SourceKind.local_file,
        )
        with store.open_entry(entry.id) as stream:
            yield stream


def inspect_audio(stream: BinaryIO, label: str) -> AudioMetadata:
    """Inspect decoded facts and loop metadata from the same verified snapshot."""
    identity = stream_identity(stream)
    try:
        info = soundfile.info(stream)
    except soundfile.LibsndfileError as e:
        raise ValueError(f'Cannot read SFZ sample {label}: {e}') from e

    wav = info.format in ('WAV', 'WAVEX')
    stream.seek(0)
    return AudioMetadata(
        sample_rate=info.samplerate,
        encoding=f'{info.format}/{info.subtype}',
        byte_length=identity.length,
        sha256=identity.sha256,
        channels=info.channels,
        frames=info.frames,
        embedded_loop=_wav_loop(stream, label) if wav else None,
        embedded_loop_known=wav,
    )


def _wav_loop(fp: BinaryIO, label: str) -> EmbeddedLoop | None:
    if fp.read(4) not in (b'RIFF', b'RF64'):
        return None
    fp.seek(4, 1)
    if fp.read(4) != b'WAVE':
        return None
    while header := fp.read(8):
        if len(header) != 8:
            raise ValueError(f'Truncated WAV chunk header in {label}')
        name, size = struct.unpack('<4sI', header)
        if name == b'smpl':
            return _read_smpl_chunk(label, fp.read(size))
        if name == b'data' and size == 0xFFFFFFFF:
            return None
        fp.seek(size + size % 2, 1)
    return None


def _read_smpl_chunk(path: str, data: bytes) -> EmbeddedLoop | None:
    if len(data) < 36:
        raise ValueError(f'Truncated WAV smpl chunk in {path}')
    loop_count = struct.unpack_from('<I', data, 28)[0]
    if not loop_count:
        return None
    if len(data) < 60:
        raise ValueError(f'Truncated WAV smpl loop in {path}')
    loop_type = struct.unpack_from('<I', data, 40)[0]
    start, inclusive_end = struct.unpack_from('<II', data, 44)
    return EmbeddedLoop(
        start_frame=start, end_frame=inclusive_end + 1, loop_type=loop_type
    )
