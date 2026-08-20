from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from typing import Any

from .models import MediaProbe, StreamInfo
from .tools import CREATE_NO_WINDOW


INPUT_ANALYZE_DURATION_MICROSECONDS = 10_000_000


class ProbeError(RuntimeError):
    pass


def _optional_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0 or parsed > 315_576_000:
        return None
    return parsed


def _optional_int(value: Any, *, positive: bool = False) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    if positive and parsed <= 0:
        return None
    return parsed


def _duration_tag(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    pieces = value.strip().split(":")
    if len(pieces) != 3:
        return None
    try:
        duration = int(pieces[0]) * 3600 + int(pieces[1]) * 60 + float(pieces[2])
    except ValueError:
        return None
    return _optional_float(duration)


def _tags(payload: Any) -> dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def _stream_from_payload(payload: dict[str, Any]) -> StreamInfo:
    tags = _tags(payload.get("tags"))
    duration = _optional_float(payload.get("duration"))
    if duration is None:
        duration = _duration_tag(tags.get("DURATION") or tags.get("duration"))
    disposition_payload = payload.get("disposition")
    disposition = (
        {
            str(key): int(value)
            for key, value in disposition_payload.items()
            if isinstance(value, (int, bool))
        }
        if isinstance(disposition_payload, dict)
        else {}
    )
    return StreamInfo(
        index=_optional_int(payload.get("index")) or 0,
        codec_type=str(payload.get("codec_type") or "unknown"),
        codec_name=str(payload.get("codec_name") or "unknown"),
        codec_long_name=str(payload.get("codec_long_name") or ""),
        codec_tag_string=str(payload.get("codec_tag_string") or ""),
        width=_optional_int(payload.get("width"), positive=True),
        height=_optional_int(payload.get("height"), positive=True),
        pixel_format=str(payload.get("pix_fmt") or ""),
        frame_rate=str(payload.get("avg_frame_rate") or payload.get("r_frame_rate") or ""),
        sample_rate=_optional_int(payload.get("sample_rate"), positive=True),
        channels=_optional_int(payload.get("channels"), positive=True),
        channel_layout=str(payload.get("channel_layout") or ""),
        duration=duration,
        frame_count=_optional_int(payload.get("nb_frames"), positive=True),
        language=tags.get("language", tags.get("LANGUAGE", "")),
        title=tags.get("title", tags.get("TITLE", "")),
        disposition=disposition,
    )


def probe_media(ffprobe: Path, source: Path, *, timeout: float = 120.0) -> MediaProbe:
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ProbeError(f"Source file does not exist: {source}")
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-analyzeduration",
        str(INPUT_ANALYZE_DURATION_MICROSECONDS),
        "-show_format",
        "-show_streams",
        "-show_chapters",
        "-print_format",
        "json",
        str(source),
    ]
    try:
        result = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError(f"FFprobe did not finish within {timeout:.0f} seconds: {source}") from exc
    except OSError as exc:
        raise ProbeError(f"Could not start FFprobe: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise ProbeError(f"FFprobe could not inspect the source: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("FFprobe returned invalid JSON.") from exc
    streams_payload = payload.get("streams")
    if not isinstance(streams_payload, list) or not streams_payload:
        raise ProbeError("No media streams were found in the selected file.")
    streams = tuple(
        _stream_from_payload(item) for item in streams_payload if isinstance(item, dict)
    )
    format_payload = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    format_duration = _optional_float(format_payload.get("duration"))
    if format_duration is None:
        stream_durations = [stream.duration for stream in streams if stream.duration is not None]
        format_duration = max(stream_durations) if stream_durations else None
    try:
        source_stat = source.stat()
    except OSError as exc:
        raise ProbeError(f"Could not read the source file size: {exc}") from exc
    chapters = payload.get("chapters")
    return MediaProbe(
        path=source,
        format_name=str(format_payload.get("format_name") or "unknown"),
        format_long_name=str(format_payload.get("format_long_name") or "Unknown container"),
        duration=format_duration,
        size=source_stat.st_size,
        modified_ns=source_stat.st_mtime_ns,
        bit_rate=_optional_int(format_payload.get("bit_rate"), positive=True),
        streams=streams,
        chapter_count=len(chapters) if isinstance(chapters, list) else 0,
        format_tags=_tags(format_payload.get("tags")),
    )
