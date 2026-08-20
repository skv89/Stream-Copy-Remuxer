from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MP4_MOV_COPY_SAFE_SUBTITLE_CODECS = frozenset({"mov_text"})


@dataclass(frozen=True)
class Toolchain:
    ffmpeg: Path | None
    ffprobe: Path | None
    source: str
    ffmpeg_version: str = "Not found"
    ffprobe_version: str = "Not found"

    @property
    def ready(self) -> bool:
        return bool(self.ffmpeg and self.ffprobe)


@dataclass(frozen=True)
class StreamInfo:
    index: int
    codec_type: str
    codec_name: str
    codec_long_name: str = ""
    codec_tag_string: str = ""
    width: int | None = None
    height: int | None = None
    pixel_format: str = ""
    frame_rate: str = ""
    sample_rate: int | None = None
    channels: int | None = None
    channel_layout: str = ""
    duration: float | None = None
    frame_count: int | None = None
    language: str = ""
    title: str = ""
    disposition: dict[str, int] = field(default_factory=dict)

    def preservation_signature(self) -> tuple[Any, ...]:
        if self.codec_type == "video":
            details: tuple[Any, ...] = (self.width, self.height, self.pixel_format)
        elif self.codec_type == "audio":
            details = (self.sample_rate, self.channels, self.channel_layout)
        else:
            details = ()
        return (self.codec_type, self.codec_name, *details)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "codec_type": self.codec_type,
            "codec_name": self.codec_name,
            "codec_long_name": self.codec_long_name,
            "codec_tag_string": self.codec_tag_string,
            "width": self.width,
            "height": self.height,
            "pixel_format": self.pixel_format,
            "frame_rate": self.frame_rate,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "channel_layout": self.channel_layout,
            "duration_seconds": self.duration,
            "frame_count": self.frame_count,
            "language": self.language,
            "title": self.title,
            "disposition": self.disposition,
        }


@dataclass(frozen=True)
class MediaProbe:
    path: Path
    format_name: str
    format_long_name: str
    duration: float | None
    size: int
    modified_ns: int
    bit_rate: int | None
    streams: tuple[StreamInfo, ...]
    chapter_count: int
    format_tags: dict[str, str] = field(default_factory=dict)

    @property
    def video_streams(self) -> tuple[StreamInfo, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "video")

    @property
    def audio_streams(self) -> tuple[StreamInfo, ...]:
        return tuple(stream for stream in self.streams if stream.codec_type == "audio")

    def selected_streams(
        self,
        stream_mode: str,
        container_key: str | None = None,
    ) -> tuple[StreamInfo, ...]:
        if stream_mode == "video":
            return self.video_streams
        if stream_mode == "av":
            return tuple(stream for stream in self.streams if stream.codec_type in {"video", "audio"})
        if stream_mode == "compatible":
            if container_key not in CONTAINER_PROFILES:
                raise ValueError("Compatible stream mode requires a supported destination container.")
            if container_key == "mkv":
                return self.streams
            return tuple(
                stream
                for stream in self.streams
                if stream.codec_type in {"video", "audio"}
                or (
                    stream.codec_type == "subtitle"
                    and stream.codec_name.lower() in MP4_MOV_COPY_SAFE_SUBTITLE_CODECS
                )
            )
        if stream_mode == "all":
            return self.streams
        raise ValueError(f"Unknown stream mode: {stream_mode}")

    def omitted_streams(
        self,
        stream_mode: str,
        container_key: str | None = None,
    ) -> tuple[StreamInfo, ...]:
        selected_indexes = {
            stream.index for stream in self.selected_streams(stream_mode, container_key)
        }
        return tuple(stream for stream in self.streams if stream.index not in selected_indexes)

    def to_dict(self, *, path: Path | None = None) -> dict[str, Any]:
        return {
            "path": str(path or self.path),
            "format_name": self.format_name,
            "format_long_name": self.format_long_name,
            "duration_seconds": self.duration,
            "size_bytes": self.size,
            "modified_ns": self.modified_ns,
            "bit_rate": self.bit_rate,
            "chapter_count": self.chapter_count,
            "format_tags": self.format_tags,
            "streams": [stream.to_dict() for stream in self.streams],
        }


@dataclass(frozen=True)
class ContainerProfile:
    key: str
    label: str
    extension: str
    muxer: str


CONTAINER_PROFILES: dict[str, ContainerProfile] = {
    "mp4": ContainerProfile("mp4", "MP4", ".mp4", "mp4"),
    "mov": ContainerProfile("mov", "MOV", ".mov", "mov"),
    "mkv": ContainerProfile("mkv", "MKV", ".mkv", "matroska"),
}


@dataclass(frozen=True)
class RemuxPlan:
    source_probe: MediaProbe
    output: Path
    partial_output: Path
    preflight_output: Path
    report_output: Path
    profile: ContainerProfile
    stream_mode: str
    compatibility_notes: tuple[str, ...]
    available_bytes: int
    required_bytes: int

    @property
    def selected_source_streams(self) -> tuple[StreamInfo, ...]:
        return self.source_probe.selected_streams(self.stream_mode, self.profile.key)

    @property
    def omitted_source_streams(self) -> tuple[StreamInfo, ...]:
        return self.source_probe.omitted_streams(self.stream_mode, self.profile.key)


@dataclass(frozen=True)
class ProgressUpdate:
    phase: str
    elapsed_seconds: float
    media_seconds: float | None = None
    percent: float | None = None
    bytes_written: int | None = None
    speed: str = ""


@dataclass(frozen=True)
class VerificationCheck:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    checks: tuple[VerificationCheck, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class RemuxResult:
    output: Path
    report: Path
    output_probe: MediaProbe
    verification: VerificationResult
    elapsed_seconds: float
    command: tuple[str, ...]
