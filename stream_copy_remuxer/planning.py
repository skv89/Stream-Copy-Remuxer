from __future__ import annotations

import os
import shutil
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Iterable

from .encoding import (
    AV1_NVENC_PROFILE_KEY,
    AV1_SOFTWARE_PROFILE_KEY,
    COPY_PROFILE_KEY,
    DNXHR_PROFILE_KEY,
    H264_NVENC_PROFILE_KEY,
    H264_SOFTWARE_PROFILE_KEY,
    HEVC_NVENC_PROFILE_KEY,
    HEVC_SOFTWARE_PROFILE_KEY,
    PRORES_PROFILE_KEY,
    EncodingError,
    effective_container_key,
    output_name_suffix,
    profile_for,
    report_suffix,
    resolve_quality,
    resolve_video_encoding,
)
from .models import (
    CONTAINER_PROFILES,
    LIMITED_EXTRA_STREAM_CONTAINER_KEYS,
    MediaProbe,
    RemuxPlan,
    ResolvedVideoEncoding,
    StreamInfo,
)


class PlanError(RuntimeError):
    pass


def describe_stream(stream: StreamInfo) -> str:
    codec_type = stream.codec_type or "unknown"
    codec_name = stream.codec_name or "unknown"
    description = f"#{stream.index} {codec_type}/{codec_name}"
    qualifiers: list[str] = []
    if stream.title:
        qualifiers.append(f'"{stream.title}"')
    if stream.language:
        qualifiers.append(f"language {stream.language}")
    if qualifiers:
        description += " (" + ", ".join(qualifiers) + ")"
    return description


def describe_streams(streams: Iterable[StreamInfo]) -> str:
    return ", ".join(describe_stream(stream) for stream in streams)


def paths_equivalent(first: Path, second: Path) -> bool:
    try:
        first_text = os.path.normcase(str(first.resolve(strict=False)))
        second_text = os.path.normcase(str(second.resolve(strict=False)))
    except OSError:
        first_text = os.path.normcase(os.path.abspath(str(first)))
        second_text = os.path.normcase(os.path.abspath(str(second)))
    return first_text == second_text


def suggest_output(
    source: Path,
    container_key: str,
    *,
    video_encoding_key: str = COPY_PROFILE_KEY,
    output_directory: Path | None = None,
    reserved_paths: Iterable[Path] = (),
) -> Path:
    effective_container = effective_container_key(video_encoding_key, container_key)
    profile = CONTAINER_PROFILES[effective_container]
    directory = Path(output_directory) if output_directory is not None else source.parent
    reserved = {
        os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))
        for path in reserved_paths
    }
    suffix = output_name_suffix(video_encoding_key)
    audit_suffix = report_suffix(video_encoding_key)
    candidate = directory / f"{source.stem}_{suffix}{profile.extension}"
    counter = 2
    while (
        candidate.exists()
        or candidate.with_suffix(candidate.suffix + audit_suffix).exists()
        or os.path.normcase(str(candidate.expanduser().resolve(strict=False))) in reserved
    ):
        candidate = directory / f"{source.stem}_{suffix}_{counter}{profile.extension}"
        counter += 1
    return candidate


def compatibility_notes(
    probe: MediaProbe,
    container_key: str,
    stream_mode: str,
    video_encoding_key: str = COPY_PROFILE_KEY,
    quality: int | str | None = None,
) -> tuple[str, ...]:
    notes: list[str] = []
    selected = probe.selected_streams(stream_mode, container_key)
    codecs = {stream.codec_name.lower() for stream in selected}
    omitted = probe.omitted_streams(stream_mode, container_key)
    copy_notice = " No stream will be re-encoded." if video_encoding_key == COPY_PROFILE_KEY else ""
    if stream_mode == "video" and omitted:
        notes.append(
            "Video only mode will intentionally omit every non-video source stream: "
            + describe_streams(omitted)
            + "."
            + copy_notice
        )
    if stream_mode == "av" and omitted:
        notes.append(
            "Video + audio mode will intentionally omit source stream(s): "
            + describe_streams(omitted)
            + "."
            + copy_notice
        )
    if stream_mode == "compatible" and omitted:
        notes.append(
            f"All compatible streams mode will omit stream(s) that {container_key.upper()} cannot safely copy "
            "without conversion: "
            + describe_streams(omitted)
            + "."
            + copy_notice
        )
    if container_key in LIMITED_EXTRA_STREAM_CONTAINER_KEYS and stream_mode == "all":
        incompatible = probe.omitted_streams("compatible", container_key)
        if incompatible:
            notes.append(
                "Strict all-source mode cannot copy every stream into "
                f"{container_key.upper()} without conversion: {describe_streams(incompatible)}. "
                "Choose All compatible streams, Video + audio, Video only, or MKV."
            )
    if video_encoding_key == COPY_PROFILE_KEY and "ffv1" in codecs and container_key == "mp4":
        notes.append(
            "FFV1 remains lossless in MP4 and the finalized MP4 index should expose a frame count to Topaz; "
            "support in other players and editors can vary."
        )
    if video_encoding_key == COPY_PROFILE_KEY and "ffv1" in codecs and container_key == "mov":
        notes.append(
            "FFV1/MOV is unusual and some FFmpeg builds warn that it may be unplayable; FFV1/MP4 is preferred for Topaz."
        )
    if video_encoding_key == COPY_PROFILE_KEY and "prores" in codecs and container_key == "mp4":
        notes.append("ProRes is normally carried in MOV; choose MOV for broader ProRes compatibility.")
    if container_key == "mkv":
        notes.append("MKV is the broadest-preservation container, but FFV1 frame count may remain unavailable to Topaz.")
    if video_encoding_key == COPY_PROFILE_KEY and container_key == "avi":
        notes.append(
            "AVI is a legacy compatibility container with limited support for modern codecs and extra streams; "
            "the preflight will test whether the selected streams can be copied without conversion."
        )
    if video_encoding_key != COPY_PROFILE_KEY:
        selected_quality = resolve_quality(video_encoding_key, quality)
        resolved = tuple(
            resolve_video_encoding(stream, video_encoding_key, selected_quality, output_video_index=index)
            for index, stream in enumerate(stream for stream in selected if stream.codec_type == "video")
        )
        variants = ", ".join(
            f"source #{item.source_stream_index}: {item.label} / {item.expected_pixel_format}"
            for item in resolved
        )
        notes.append(
            "Video will be decoded and re-encoded using high-quality lossy settings"
            + (f" ({variants})" if variants else "")
            + "; selected non-video streams remain stream-copied."
        )
        precision_notices = tuple(dict.fromkeys(item.precision_notice for item in resolved if item.precision_notice))
        notes.extend(precision_notices)
    return tuple(notes)


def _frame_rate(stream: StreamInfo) -> float:
    try:
        value = float(Fraction(stream.frame_rate))
    except (ValueError, ZeroDivisionError):
        return 25.0
    return value if 0.1 <= value <= 1000 else 25.0


def _estimated_transcode_bytes(
    probe: MediaProbe,
    resolved_video_encodings: tuple[ResolvedVideoEncoding, ...],
    video_encoding_key: str,
) -> int:
    duration = probe.duration
    if duration is None or duration <= 0:
        return max(probe.size * 2, probe.size)
    bpp_by_profile = {
        H264_SOFTWARE_PROFILE_KEY: 1.20,
        H264_NVENC_PROFILE_KEY: 1.20,
        HEVC_SOFTWARE_PROFILE_KEY: 0.85,
        HEVC_NVENC_PROFILE_KEY: 0.85,
        AV1_SOFTWARE_PROFILE_KEY: 0.70,
        AV1_NVENC_PROFILE_KEY: 0.70,
    }
    estimated_video = 0.0
    for resolved in resolved_video_encodings:
        stream = next(
            item for item in probe.video_streams if item.index == resolved.source_stream_index
        )
        if video_encoding_key == PRORES_PROFILE_KEY:
            bits_per_pixel_frame = 8.0 if "4444 XQ" in resolved.label else 3.5
        elif video_encoding_key == DNXHR_PROFILE_KEY:
            bits_per_pixel_frame = 5.0 if "444" in resolved.label else (3.6 if "HQX" in resolved.label else 2.4)
        else:
            bits_per_pixel_frame = bpp_by_profile[video_encoding_key]
        pixels = max(1, (stream.width or 1920) * (stream.height or 1080))
        estimated_video += pixels * _frame_rate(stream) * duration * bits_per_pixel_frame / 8.0
    copied_stream_allowance = max(16 * 1024 * 1024, probe.size // 10)
    estimate = int(estimated_video * 1.35) + copied_stream_allowance
    return max(probe.size, estimate)


def build_remux_plan(
    source_probe: MediaProbe,
    output: Path,
    container_key: str,
    stream_mode: str,
    *,
    video_encoding_key: str = COPY_PROFILE_KEY,
    quality: int | str | None = None,
    enforce_space: bool = True,
) -> RemuxPlan:
    try:
        encoding_profile = profile_for(video_encoding_key)
        selected_quality = resolve_quality(video_encoding_key, quality)
        expected_container = effective_container_key(video_encoding_key, container_key)
    except EncodingError as exc:
        raise PlanError(str(exc)) from exc
    if container_key not in CONTAINER_PROFILES:
        raise PlanError(f"Unsupported destination container: {container_key}")
    if expected_container != container_key:
        fixed = CONTAINER_PROFILES[expected_container].label
        raise PlanError(f"{encoding_profile.label} requires {fixed} output.")
    if stream_mode not in {"video", "av", "compatible", "all"}:
        raise PlanError(f"Unsupported stream mode: {stream_mode}")
    if not source_probe.path.is_file():
        raise PlanError(f"The source file is no longer available: {source_probe.path}")
    profile = CONTAINER_PROFILES[container_key]
    output = Path(output).expanduser().resolve(strict=False)
    if output.suffix.lower() != profile.extension:
        raise PlanError(f"{profile.label} output must use the {profile.extension} extension.")
    if paths_equivalent(source_probe.path, output):
        raise PlanError("The destination cannot be the source file.")
    if not output.parent.is_dir():
        raise PlanError(f"The destination folder does not exist: {output.parent}")
    report = output.with_suffix(output.suffix + report_suffix(video_encoding_key))
    if output.exists() or report.exists():
        raise PlanError("The destination or its audit report already exists; nothing will be overwritten.")
    selected = source_probe.selected_streams(stream_mode, container_key)
    if not selected:
        raise PlanError("The selected stream mode does not include any source streams.")
    selected_video = tuple(stream for stream in selected if stream.codec_type == "video")
    if video_encoding_key != COPY_PROFILE_KEY and not selected_video:
        raise PlanError("The selected video output mode requires at least one source video stream.")
    try:
        resolved_video_encodings = tuple(
            resolve_video_encoding(
                stream,
                video_encoding_key,
                selected_quality,
                output_video_index=index,
            )
            for index, stream in enumerate(selected_video)
        ) if video_encoding_key != COPY_PROFILE_KEY else ()
    except EncodingError as exc:
        raise PlanError(str(exc)) from exc
    if stream_mode == "all" and container_key in LIMITED_EXTRA_STREAM_CONTAINER_KEYS:
        incompatible = source_probe.omitted_streams("compatible", container_key)
        if incompatible:
            raise PlanError(
                f"{profile.label} cannot stream-copy every source stream without re-encoding. "
                f"Incompatible source stream(s): {describe_streams(incompatible)}. "
                "Choose All compatible streams to omit only those disclosed tracks, choose Video + audio "
                "to omit all subtitle/attachment/data streams, choose Video only to omit audio and every "
                "non-video stream, or choose MKV to retain every source stream."
            )
    token = uuid.uuid4().hex[:10]
    partial = output.with_name(f".{output.stem}.{token}.partial{profile.extension}")
    preflight = output.with_name(f".{output.stem}.{token}.preflight{profile.extension}")
    free = shutil.disk_usage(output.parent).free
    estimated_output = (
        source_probe.size
        if video_encoding_key == COPY_PROFILE_KEY
        else _estimated_transcode_bytes(source_probe, resolved_video_encodings, video_encoding_key)
    )
    reserve = max(256 * 1024 * 1024, estimated_output // 100)
    required = estimated_output + reserve
    if enforce_space and free < required:
        raise PlanError(
            "The destination does not have enough free space for this safe media operation. "
            f"Required approximately {required:,} bytes; available {free:,} bytes."
        )
    return RemuxPlan(
        source_probe=source_probe,
        output=output,
        partial_output=partial,
        preflight_output=preflight,
        report_output=report,
        profile=profile,
        stream_mode=stream_mode,
        compatibility_notes=compatibility_notes(
            source_probe,
            container_key,
            stream_mode,
            video_encoding_key,
            selected_quality,
        ),
        available_bytes=free,
        required_bytes=required,
        video_encoding_key=video_encoding_key,
        quality_value=selected_quality,
        resolved_video_encodings=resolved_video_encodings,
        estimated_output_bytes=estimated_output,
    )
