import pytest
from ufor.samples.enums import Direction
from ufor.samples.metadata import AudioMetadata, EmbeddedLoop
from ufor.time import Rate, Timebase

from safaz import compiler, exporter, parser
from safaz.model import SfzCompileResult


@pytest.mark.parametrize(
    ('loop_type', 'direction'),
    [
        ('forward', Direction.forward),
        ('backward', Direction.backward),
        ('alternate', Direction.mirror),
    ],
)
def test_sfz_loop_direction_is_independent_of_sample_direction(
    loop_type: str, direction: Direction
) -> None:
    result = _compile(
        '<region> sample=loop.wav loop_mode=loop_continuous '
        f'loop_start=10 loop_end=99 loop_type={loop_type} direction=reverse'
    )

    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].playback.direction == Direction.backward
    assert result.instrument.body.slices[0].loop is not None
    assert result.instrument.body.slices[0].loop.direction == direction
    exported = exporter.write(result.instrument)
    assert exported.complete
    assert ('loop_type=' in exported.contents) == (loop_type != 'forward')
    imported = _compile(exported.contents).instrument
    assert imported is not None
    assert imported.body.slices[0].loop is not None
    assert imported.body.slices[0].loop.direction == direction


def test_sfz_loop_direction_without_loop_is_diagnosed() -> None:
    result = _compile('<region> sample=loop.wav loop_mode=no_loop loop_type=alternate')

    assert not result.complete
    assert result.unimplemented[0].location.opcode == 'loop_type'
    assert result.unimplemented[0].reason == 'SFZ loop_type requires an active loop'


@pytest.mark.parametrize(
    ('loop_type', 'direction'),
    [(1, Direction.mirror), (2, Direction.backward)],
)
def test_embedded_wav_loop_direction_is_preserved(
    loop_type: int, direction: Direction
) -> None:
    result = _compile(
        '<region> sample=loop.wav',
        embedded_loop=EmbeddedLoop(start_frame=10, end_frame=100, loop_type=loop_type),
    )

    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slices[0].loop is not None
    assert result.instrument.body.slices[0].loop.direction == direction


def test_unknown_embedded_wav_loop_type_is_diagnosed() -> None:
    result = _compile(
        '<region> sample=loop.wav',
        embedded_loop=EmbeddedLoop(start_frame=10, end_frame=100, loop_type=3),
    )

    assert not result.complete
    assert result.unimplemented[0].reason == 'WAV smpl loop type 3 is not implemented'


def test_sfz_default_velocity_excludes_note_off() -> None:
    result = _compile('<region> sample=loop.wav')

    assert result.complete
    assert result.instrument is not None
    assert result.instrument.body.slots[0].mapping.minimum_velocity == 1 / 127


def _compile(text: str, embedded_loop: EmbeddedLoop | None = None) -> SfzCompileResult:
    return compiler.compile_instrument(
        parser.parse(text),
        name='loop',
        title='Loop',
        assets={
            'loop.wav': AudioMetadata(
                channels=1,
                sample_rate=48000,
                encoding='pcm_s16le',
                byte_length=96000,
                sha256='0' * 64,
                frames=48000,
                embedded_loop=embedded_loop,
                embedded_loop_known=True,
            )
        },
        output_timebase=Timebase(name='output', rate=Rate(numerator=48000)),
        output_channels=['mono'],
    )
