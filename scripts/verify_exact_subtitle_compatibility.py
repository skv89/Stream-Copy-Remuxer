from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path

from stream_copy_remuxer import __version__
from stream_copy_remuxer.engine import RemuxEngine
from stream_copy_remuxer.models import MediaProbe, StreamInfo
from stream_copy_remuxer.planning import PlanError, build_remux_plan
from stream_copy_remuxer.probe import probe_media
from stream_copy_remuxer.tools import CREATE_NO_WINDOW, discover_toolchain


def signatures(streams: tuple[StreamInfo, ...]) -> Counter[tuple[object, ...]]:
    return Counter(stream.preservation_signature() for stream in streams)


def mapped_inputs(command: tuple[str, ...]) -> list[str]:
    return [command[index + 1] for index, value in enumerate(command) if value == "-map"]


def run_preflight(
    source_probe: MediaProbe,
    output: Path,
    container_key: str,
    stream_mode: str,
) -> dict[str, object]:
    toolchain = discover_toolchain()
    if not toolchain.ready or toolchain.ffprobe is None:
        raise RuntimeError("FFmpeg and FFprobe are required for the exact-source gate.")
    plan = build_remux_plan(
        source_probe,
        output,
        container_key,
        stream_mode,
        enforce_space=False,
    )
    command = RemuxEngine(toolchain).build_command(
        plan,
        plan.preflight_output,
        preflight=True,
    )
    started = time.monotonic()
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )
    elapsed = time.monotonic() - started
    output_probe = (
        probe_media(toolchain.ffprobe, plan.preflight_output)
        if completed.returncode == 0 and plan.preflight_output.is_file()
        else None
    )
    selected_source = plan.selected_source_streams
    selected_output = (
        output_probe.selected_streams(stream_mode, container_key)
        if output_probe is not None
        else ()
    )
    ffv1_indexed = container_key not in {"mp4", "mov"} or (
        bool(output_probe)
        and all(
            stream.codec_name.lower() != "ffv1" or bool(stream.frame_count)
            for stream in output_probe.video_streams
        )
    )
    checks = {
        "ffmpeg_succeeded": completed.returncode == 0,
        "preflight_output_nonempty": bool(
            plan.preflight_output.is_file() and plan.preflight_output.stat().st_size > 0
        ),
        "stream_copy_only": "-c" in command and command[command.index("-c") + 1] == "copy",
        "selected_stream_properties_preserved": signatures(selected_source) == signatures(selected_output),
        "ffv1_indexed": ffv1_indexed,
    }
    return {
        "container": container_key,
        "stream_mode": stream_mode,
        "elapsed_seconds": round(elapsed, 6),
        "output": str(plan.preflight_output),
        "output_size_bytes": (
            plan.preflight_output.stat().st_size if plan.preflight_output.is_file() else 0
        ),
        "mapped_inputs": mapped_inputs(command),
        "command": list(command),
        "selected_source_streams": [stream.to_dict() for stream in selected_source],
        "omitted_source_streams": [stream.to_dict() for stream in plan.omitted_source_streams],
        "output_streams": (
            [stream.to_dict() for stream in output_probe.streams]
            if output_probe is not None
            else []
        ),
        "checks": checks,
        "passed": all(checks.values()),
        "ffmpeg_output": completed.stdout[-4000:],
    }


def strict_plan_result(
    source_probe: MediaProbe,
    output: Path,
    container_key: str,
) -> dict[str, object]:
    try:
        build_remux_plan(
            source_probe,
            output,
            container_key,
            "all",
            enforce_space=False,
        )
    except PlanError as exc:
        message = str(exc)
        checks = {
            "blocked_before_ffmpeg": True,
            "names_subrip_streams": "subtitle/subrip" in message,
            "offers_compatible_mode": "All compatible streams" in message,
            "offers_video_audio_mode": "Video + audio" in message,
            "offers_video_only_mode": "Video only" in message,
            "offers_mkv": "MKV" in message,
        }
        return {"container": container_key, "message": message, "checks": checks, "passed": all(checks.values())}
    checks = {"blocked_before_ffmpeg": False}
    return {"container": container_key, "message": "No PlanError was raised.", "checks": checks, "passed": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()

    toolchain = discover_toolchain()
    if not toolchain.ready or toolchain.ffprobe is None:
        raise RuntimeError("FFmpeg and FFprobe were not found.")
    source = args.source.expanduser().resolve(strict=True)
    output_directory = args.output_directory.expanduser().resolve(strict=False)
    output_directory.mkdir(parents=True, exist_ok=True)
    report = args.report.expanduser().resolve(strict=False)
    report.parent.mkdir(parents=True, exist_ok=True)

    before = source.stat()
    source_probe = probe_media(toolchain.ffprobe, source)
    cases = [
        run_preflight(source_probe, output_directory / "compatible.mp4", "mp4", "compatible"),
        run_preflight(source_probe, output_directory / "compatible.mov", "mov", "compatible"),
        run_preflight(source_probe, output_directory / "video-only.mp4", "mp4", "video"),
        run_preflight(source_probe, output_directory / "video-only.mov", "mov", "video"),
        run_preflight(source_probe, output_directory / "strict-all.mkv", "mkv", "all"),
    ]
    strict_rejections = [
        strict_plan_result(source_probe, output_directory / "strict-all.mp4", "mp4"),
        strict_plan_result(source_probe, output_directory / "strict-all.mov", "mov"),
    ]
    after = source.stat()
    identity_unchanged = (
        before.st_size == after.st_size
        and before.st_mtime_ns == after.st_mtime_ns
    )
    exact_inventory = [
        (stream.index, stream.codec_type, stream.codec_name)
        for stream in source_probe.streams
    ]
    payload = {
        "schema": 1,
        "application_version": __version__,
        "source": str(source),
        "source_size_bytes": before.st_size,
        "source_modified_ns": before.st_mtime_ns,
        "source_streams": [stream.to_dict() for stream in source_probe.streams],
        "checks": {
            "exact_reported_inventory": exact_inventory
            == [
                (0, "video", "ffv1"),
                (1, "audio", "aac"),
                (2, "subtitle", "subrip"),
                (3, "subtitle", "subrip"),
            ],
            "compatible_mp4_passed": bool(cases[0]["passed"]),
            "compatible_mov_passed": bool(cases[1]["passed"]),
            "video_only_mp4_passed": bool(cases[2]["passed"]),
            "video_only_mov_passed": bool(cases[3]["passed"]),
            "strict_mkv_preserved_all": bool(cases[4]["passed"])
            and cases[4]["mapped_inputs"] == ["0"],
            "strict_mp4_blocked": bool(strict_rejections[0]["passed"]),
            "strict_mov_blocked": bool(strict_rejections[1]["passed"]),
            "compatible_maps_only_video_audio": (
                cases[0]["mapped_inputs"] == ["0:0", "0:1"]
                and cases[1]["mapped_inputs"] == ["0:0", "0:1"]
            ),
            "compatible_omits_both_named_subrip_streams": all(
                [stream["index"] for stream in case["omitted_source_streams"]] == [2, 3]
                for case in cases[:2]
            ),
            "video_only_maps_no_audio": (
                cases[2]["mapped_inputs"] == ["0:v?"]
                and cases[3]["mapped_inputs"] == ["0:v?"]
            ),
            "video_only_omits_aac_and_both_named_subrip_streams": all(
                [stream["index"] for stream in case["omitted_source_streams"]] == [1, 2, 3]
                for case in cases[2:4]
            ),
            "source_identity_unchanged": identity_unchanged,
        },
        "preflight_cases": cases,
        "strict_rejections": strict_rejections,
    }
    payload["passed"] = all(payload["checks"].values())
    report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": payload["passed"], "report": str(report)}, ensure_ascii=False))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
