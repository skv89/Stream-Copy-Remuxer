from __future__ import annotations

from pathlib import Path

from stream_copy_remuxer.models import MediaProbe, StreamInfo


def video_stream(
    *,
    codec: str = "ffv1",
    frame_count: int | None = None,
    index: int = 0,
) -> StreamInfo:
    return StreamInfo(
        index=index,
        codec_type="video",
        codec_name=codec,
        width=1920,
        height=1080,
        pixel_format="yuv444p12le" if codec == "ffv1" else "yuv420p",
        frame_rate="25/1",
        duration=10.0,
        frame_count=frame_count,
    )


def audio_stream(*, codec: str = "aac", index: int = 1) -> StreamInfo:
    return StreamInfo(
        index=index,
        codec_type="audio",
        codec_name=codec,
        sample_rate=48000,
        channels=2,
        channel_layout="stereo",
        duration=10.0,
    )


def subtitle_stream(
    *,
    codec: str = "subrip",
    index: int = 2,
    language: str = "chi",
    title: str = "Traditional",
) -> StreamInfo:
    return StreamInfo(
        index=index,
        codec_type="subtitle",
        codec_name=codec,
        language=language,
        title=title,
        duration=10.0,
    )


def make_probe(
    path: Path,
    *,
    streams: tuple[StreamInfo, ...] | None = None,
    size: int | None = None,
    duration: float = 10.0,
    chapters: int = 0,
) -> MediaProbe:
    source_stat = path.stat() if path.exists() else None
    return MediaProbe(
        path=path,
        format_name="matroska,webm" if path.suffix.lower() == ".mkv" else "mov,mp4,m4a,3gp,3g2,mj2",
        format_long_name="Matroska / WebM" if path.suffix.lower() == ".mkv" else "QuickTime / MOV",
        duration=duration,
        size=source_stat.st_size if size is None and source_stat is not None else (size or 4096),
        modified_ns=source_stat.st_mtime_ns if source_stat is not None else 0,
        bit_rate=None,
        streams=streams or (video_stream(), audio_stream()),
        chapter_count=chapters,
    )
