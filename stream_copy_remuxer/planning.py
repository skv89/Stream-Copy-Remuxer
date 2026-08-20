from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Iterable

from .models import CONTAINER_PROFILES, MediaProbe, RemuxPlan, StreamInfo


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
    output_directory: Path | None = None,
    reserved_paths: Iterable[Path] = (),
) -> Path:
    profile = CONTAINER_PROFILES[container_key]
    directory = Path(output_directory) if output_directory is not None else source.parent
    reserved = {
        os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))
        for path in reserved_paths
    }
    candidate = directory / f"{source.stem}_remux{profile.extension}"
    counter = 2
    while (
        candidate.exists()
        or candidate.with_suffix(candidate.suffix + ".remux.json").exists()
        or os.path.normcase(str(candidate.expanduser().resolve(strict=False))) in reserved
    ):
        candidate = directory / f"{source.stem}_remux_{counter}{profile.extension}"
        counter += 1
    return candidate


def compatibility_notes(probe: MediaProbe, container_key: str, stream_mode: str) -> tuple[str, ...]:
    notes: list[str] = []
    selected = probe.selected_streams(stream_mode, container_key)
    codecs = {stream.codec_name.lower() for stream in selected}
    omitted = probe.omitted_streams(stream_mode, container_key)
    if stream_mode == "video" and omitted:
        notes.append(
            "Video only mode will intentionally omit every non-video source stream: "
            + describe_streams(omitted)
            + ". No stream will be re-encoded."
        )
    if stream_mode == "av" and omitted:
        notes.append(
            "Video + audio mode will intentionally omit source stream(s): "
            + describe_streams(omitted)
            + "."
        )
    if stream_mode == "compatible" and omitted:
        notes.append(
            f"All compatible streams mode will omit stream(s) that {container_key.upper()} cannot safely copy "
            "without conversion: "
            + describe_streams(omitted)
            + ". No stream will be re-encoded."
        )
    if container_key in {"mp4", "mov"} and stream_mode == "all":
        incompatible = probe.omitted_streams("compatible", container_key)
        if incompatible:
            notes.append(
                "Strict all-source mode cannot copy every stream into "
                f"{container_key.upper()} without conversion: {describe_streams(incompatible)}. "
                "Choose All compatible streams, Video + audio, Video only, or MKV."
            )
    if "ffv1" in codecs and container_key == "mp4":
        notes.append(
            "FFV1 remains lossless in MP4 and the finalized MP4 index should expose a frame count to Topaz; "
            "support in other players and editors can vary."
        )
    if "ffv1" in codecs and container_key == "mov":
        notes.append(
            "FFV1/MOV is unusual and some FFmpeg builds warn that it may be unplayable; FFV1/MP4 is preferred for Topaz."
        )
    if "prores" in codecs and container_key == "mp4":
        notes.append("ProRes is normally carried in MOV; choose MOV for broader ProRes compatibility.")
    if container_key == "mkv":
        notes.append("MKV is the broadest-preservation container, but FFV1 frame count may remain unavailable to Topaz.")
    return tuple(notes)


def build_remux_plan(
    source_probe: MediaProbe,
    output: Path,
    container_key: str,
    stream_mode: str,
    *,
    enforce_space: bool = True,
) -> RemuxPlan:
    if container_key not in CONTAINER_PROFILES:
        raise PlanError(f"Unsupported destination container: {container_key}")
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
    report = output.with_suffix(output.suffix + ".remux.json")
    if output.exists() or report.exists():
        raise PlanError("The destination or its audit report already exists; nothing will be overwritten.")
    selected = source_probe.selected_streams(stream_mode, container_key)
    if not selected:
        raise PlanError("The selected stream mode does not include any source streams.")
    if stream_mode == "all" and container_key in {"mp4", "mov"}:
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
    reserve = max(256 * 1024 * 1024, source_probe.size // 100)
    required = source_probe.size + reserve
    if enforce_space and free < required:
        raise PlanError(
            "The destination does not have enough free space for a safe stream copy. "
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
        compatibility_notes=compatibility_notes(source_probe, container_key, stream_mode),
        available_bytes=free,
        required_bytes=required,
    )
