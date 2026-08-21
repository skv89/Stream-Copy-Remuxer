from __future__ import annotations

import argparse
import ctypes
import json
import logging
import logging.handlers
import os
import threading
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

from stream_copy_remuxer import __version__
from stream_copy_remuxer.batch import run_batch_plans
from stream_copy_remuxer.engine import RemuxEngine
from stream_copy_remuxer.drop_support import create_root
from stream_copy_remuxer.encoding import (
    AV1_SOFTWARE_PROFILE_KEY,
    COPY_PROFILE_KEY,
    DNXHR_PROFILE_KEY,
    ENCODING_PROFILES,
    H264_NVENC_PROFILE_KEY,
    H264_SOFTWARE_PROFILE_KEY,
    HEVC_SOFTWARE_PROFILE_KEY,
    PRORES_PROFILE_KEY,
    encoder_availability,
)
from stream_copy_remuxer.gui import (
    StreamCopyRemuxerApp,
    run_layout_scaling_self_test,
    run_withdrawn_gui_self_test,
)
from stream_copy_remuxer.models import CONTAINER_PROFILES, RemuxPlan, Toolchain
from stream_copy_remuxer.planning import PlanError, build_remux_plan
from stream_copy_remuxer.probe import probe_media
from stream_copy_remuxer.tools import CREATE_NO_WINDOW, discover_toolchain


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def configure_logging() -> None:
    local = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
    log_dir = local / "Stream Copy Remuxer" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_dir / "stream-copy-remuxer.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError:
        handler = logging.NullHandler()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
        force=True,
    )


def write_json(payload: dict[str, object], output: Path | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output is not None:
        output = output.expanduser().resolve(strict=False)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        print(text)


def require_toolchain(toolchain: Toolchain) -> None:
    if not getattr(toolchain, "ready", False):
        raise RuntimeError("FFmpeg and FFprobe were not found. Install FFmpeg from the GUI or provide explicit CLI paths.")


def run_self_test(toolchain: Toolchain) -> dict[str, object]:
    require_toolchain(toolchain)
    assert toolchain.ffmpeg is not None and toolchain.ffprobe is not None
    checks: dict[str, bool] = {}
    observations: dict[str, object] = {
        "ffmpeg": str(toolchain.ffmpeg),
        "ffprobe": str(toolchain.ffprobe),
        "toolchain_source": toolchain.source,
        "ffmpeg_version": toolchain.ffmpeg_version,
    }
    with tempfile.TemporaryDirectory(prefix="stream-copy-remuxer-self-test-") as folder:
        root = Path(folder)
        source = root / "ffv1-source.mkv"
        second_source = root / "mpeg4-source.avi"
        subtitle_source = root / "ffv1-subrip-source.mkv"
        subtitle_file = root / "traditional.srt"
        destination = root / "batch destination & 输出"
        destination.mkdir()
        output = destination / "ffv1-remux.mp4"
        second_output = destination / "mpeg4-remux.mkv"
        avi_output = destination / "mpeg4-remux.avi"
        subtitle_output = destination / "ffv1-subrip-compatible-remux.mp4"
        video_only_output = destination / "ffv1-video-only-remux.mp4"
        generate = [
            str(toolchain.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=25:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=1000:sample_rate=48000:duration=1",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-pix_fmt",
            "yuv444p12le",
            "-c:v",
            "ffv1",
            "-level",
            "3",
            "-coder",
            "1",
            "-context",
            "1",
            "-slicecrc",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            str(source),
        ]
        generated = subprocess.run(
            generate,
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
        checks["generated_ffv1_mkv"] = generated.returncode == 0 and source.is_file()
        generate_second = [
            str(toolchain.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=176x100:rate=24:duration=1",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=700:sample_rate=48000:duration=1",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-c:a",
            "pcm_s16le",
            "-shortest",
            str(second_source),
        ]
        generated_second = subprocess.run(
            generate_second,
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
        checks["generated_mpeg4_avi"] = generated_second.returncode == 0 and second_source.is_file()
        if not checks["generated_ffv1_mkv"] or not checks["generated_mpeg4_avi"]:
            observations["ffv1_generation_output"] = generated.stdout[-4000:]
            observations["avi_generation_output"] = generated_second.stdout[-4000:]
            return {
                "schema": 1,
                "application": "Stream Copy Remuxer",
                "version": __version__,
                "passed": False,
                "checks": checks,
                "observations": observations,
            }
        subtitle_file.write_text(
            "1\n00:00:00,000 --> 00:00:00,800\nTraditional subtitle test\n",
            encoding="utf-8",
        )
        generate_subtitle_source = [
            str(toolchain.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(source),
            "-f",
            "srt",
            "-i",
            str(subtitle_file),
            "-map",
            "0",
            "-map",
            "1:0",
            "-c",
            "copy",
            "-metadata:s:s:0",
            "language=chi",
            "-metadata:s:s:0",
            "title=Traditional",
            str(subtitle_source),
        ]
        generated_subtitle_source = subprocess.run(
            generate_subtitle_source,
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
        checks["generated_ffv1_subrip_mkv"] = (
            generated_subtitle_source.returncode == 0 and subtitle_source.is_file()
        )
        if not checks["generated_ffv1_subrip_mkv"]:
            observations["subtitle_source_generation_output"] = generated_subtitle_source.stdout[-4000:]
            return {
                "schema": 1,
                "application": "Stream Copy Remuxer",
                "version": __version__,
                "passed": False,
                "checks": checks,
                "observations": observations,
            }
        gui = run_withdrawn_gui_self_test(
            toolchain,
            sample_paths=(source, second_source, subtitle_source),
        )
        checks["withdrawn_gui"] = bool(gui["passed"])
        observations["gui"] = gui
        layout_scaling = run_layout_scaling_self_test(toolchain)
        checks["layout_scaling_100_150_200_percent"] = bool(layout_scaling["passed"])
        observations["layout_scaling"] = layout_scaling

        source_stat = source.stat()
        second_source_stat = second_source.stat()
        subtitle_source_stat = subtitle_source.stat()
        source_probe = probe_media(toolchain.ffprobe, source)
        second_source_probe = probe_media(toolchain.ffprobe, second_source)
        subtitle_source_probe = probe_media(toolchain.ffprobe, subtitle_source)
        checks["source_is_ffv1"] = bool(
            source_probe.video_streams and source_probe.video_streams[0].codec_name == "ffv1"
        )
        checks["source_has_audio"] = bool(source_probe.audio_streams)
        checks["second_source_is_avi"] = second_source_probe.format_name == "avi"
        checks["second_source_is_mpeg4"] = bool(
            second_source_probe.video_streams
            and second_source_probe.video_streams[0].codec_name == "mpeg4"
        )
        checks["subtitle_source_has_subrip"] = any(
            stream.codec_type == "subtitle" and stream.codec_name == "subrip"
            for stream in subtitle_source_probe.streams
        )
        try:
            build_remux_plan(
                subtitle_source_probe,
                destination / "strict-all-should-not-start.mp4",
                "mp4",
                "all",
            )
        except PlanError as exc:
            strict_error = str(exc)
            checks["strict_subrip_mp4_blocked_before_ffmpeg"] = (
                "All compatible streams" in strict_error
                and "Video + audio" in strict_error
                and "Video only" in strict_error
                and "MKV" in strict_error
            )
            observations["strict_subrip_mp4_error"] = strict_error
        else:
            checks["strict_subrip_mp4_blocked_before_ffmpeg"] = False
        plan = build_remux_plan(source_probe, output, "mp4", "av")
        second_plan = build_remux_plan(second_source_probe, second_output, "mkv", "av")
        avi_plan = build_remux_plan(second_source_probe, avi_output, "avi", "av")
        subtitle_plan = build_remux_plan(
            subtitle_source_probe,
            subtitle_output,
            "mp4",
            "compatible",
        )
        video_only_plan = build_remux_plan(
            subtitle_source_probe,
            video_only_output,
            "mp4",
            "video",
        )
        checks["compatible_plan_omits_only_subrip"] = (
            [stream.codec_type for stream in subtitle_plan.selected_source_streams] == ["video", "audio"]
            and [stream.codec_name for stream in subtitle_plan.omitted_source_streams] == ["subrip"]
        )
        checks["video_only_plan_selects_video_and_omits_audio_subrip"] = (
            [stream.codec_type for stream in video_only_plan.selected_source_streams] == ["video"]
            and [stream.codec_type for stream in video_only_plan.omitted_source_streams]
            == ["audio", "subtitle"]
        )
        batch = run_batch_plans(
            toolchain,
            (
                ("ffv1", plan),
                ("avi", second_plan),
                ("avi-output", avi_plan),
                ("subrip", subtitle_plan),
                ("video-only", video_only_plan),
            ),
            cancel_event=threading.Event(),
        )
        checks["batch_five_plans_complete"] = (
            batch.completed == 5 and batch.failed == 0 and not batch.canceled and len(batch.results) == 5
        )
        if not checks["batch_five_plans_complete"]:
            observations["batch_failures"] = list(batch.failures)
            return {
                "schema": 1,
                "application": "Stream Copy Remuxer",
                "version": __version__,
                "passed": False,
                "checks": checks,
                "observations": observations,
            }
        result, second_result, avi_result, subtitle_result, video_only_result = batch.results
        checks["common_destination_outputs"] = (
            result.output.parent == destination
            and second_result.output.parent == destination
            and avi_result.output.parent == destination
            and subtitle_result.output.parent == destination
            and video_only_result.output.parent == destination
        )
        source_after = source.stat()
        second_source_after = second_source.stat()
        subtitle_source_after = subtitle_source.stat()
        checks["output_exists"] = result.output.is_file()
        checks["report_exists"] = result.report.is_file()
        checks["second_output_exists"] = second_result.output.is_file()
        checks["second_report_exists"] = second_result.report.is_file()
        checks["avi_output_exists"] = avi_result.output.is_file()
        checks["avi_report_exists"] = avi_result.report.is_file()
        checks["compatible_output_exists"] = subtitle_result.output.is_file()
        checks["compatible_report_exists"] = subtitle_result.report.is_file()
        checks["video_only_output_exists"] = video_only_result.output.is_file()
        checks["video_only_report_exists"] = video_only_result.report.is_file()
        checks["stream_copy_command"] = "-c" in result.command and "copy" in result.command
        analysis_position = (
            result.command.index("-analyzeduration")
            if "-analyzeduration" in result.command
            else -1
        )
        input_position = result.command.index("-i") if "-i" in result.command else -1
        checks["bounded_input_analysis_before_source"] = (
            0 <= analysis_position < input_position
            and result.command[analysis_position + 1] == "10000000"
        )
        checks["second_stream_copy_command"] = (
            "-c" in second_result.command and "copy" in second_result.command
        )
        checks["avi_stream_copy_command"] = (
            "-c" in avi_result.command
            and avi_result.command[avi_result.command.index("-c") + 1] == "copy"
            and "-f" in avi_result.command
            and avi_result.command[avi_result.command.index("-f") + 1] == "avi"
        )
        compatible_maps = [
            subtitle_result.command[index + 1]
            for index, value in enumerate(subtitle_result.command)
            if value == "-map"
        ]
        checks["compatible_command_explicitly_maps_only_video_audio"] = compatible_maps == ["0:0", "0:1"]
        checks["compatible_stream_copy_command"] = (
            "-c" in subtitle_result.command
            and subtitle_result.command[subtitle_result.command.index("-c") + 1] == "copy"
        )
        video_only_maps = [
            video_only_result.command[index + 1]
            for index, value in enumerate(video_only_result.command)
            if value == "-map"
        ]
        checks["video_only_command_maps_no_audio"] = video_only_maps == ["0:v?"]
        checks["video_only_stream_copy_command"] = (
            "-c" in video_only_result.command
            and video_only_result.command[video_only_result.command.index("-c") + 1] == "copy"
        )
        checks["output_is_ffv1"] = bool(
            result.output_probe.video_streams
            and result.output_probe.video_streams[0].codec_name == "ffv1"
        )
        checks["output_has_audio"] = bool(result.output_probe.audio_streams)
        checks["audio_codec_preserved"] = bool(
            source_probe.audio_streams
            and result.output_probe.audio_streams
            and source_probe.audio_streams[0].codec_name == result.output_probe.audio_streams[0].codec_name
        )
        checks["indexed_frame_count"] = bool(
            result.output_probe.video_streams
            and result.output_probe.video_streams[0].frame_count == 25
        )
        checks["verification_passed"] = result.verification.passed
        checks["second_verification_passed"] = second_result.verification.passed
        checks["avi_output_verification_passed"] = avi_result.verification.passed
        checks["compatible_verification_passed"] = subtitle_result.verification.passed
        checks["video_only_verification_passed"] = video_only_result.verification.passed
        checks["compatible_output_omits_subrip"] = (
            [stream.codec_type for stream in subtitle_result.output_probe.streams] == ["video", "audio"]
        )
        checks["video_only_output_has_only_ffv1_video"] = (
            [stream.codec_type for stream in video_only_result.output_probe.streams] == ["video"]
            and video_only_result.output_probe.video_streams[0].codec_name == "ffv1"
        )
        checks["second_video_codec_preserved"] = bool(
            second_result.output_probe.video_streams
            and second_result.output_probe.video_streams[0].codec_name
            == second_source_probe.video_streams[0].codec_name
        )
        checks["second_audio_codec_preserved"] = bool(
            second_source_probe.audio_streams
            and second_result.output_probe.audio_streams
            and second_result.output_probe.audio_streams[0].codec_name
            == second_source_probe.audio_streams[0].codec_name
        )
        checks["avi_output_codecs_preserved"] = bool(
            avi_result.output_probe.video_streams
            and avi_result.output_probe.audio_streams
            and avi_result.output_probe.video_streams[0].codec_name
            == second_source_probe.video_streams[0].codec_name
            and avi_result.output_probe.audio_streams[0].codec_name
            == second_source_probe.audio_streams[0].codec_name
        )
        checks["multiple_output_containers"] = (
            result.output.suffix.lower() == ".mp4"
            and second_result.output.suffix.lower() == ".mkv"
            and avi_result.output.suffix.lower() == ".avi"
        )
        checks["source_unchanged"] = (
            source_stat.st_size == source_after.st_size
            and source_stat.st_mtime_ns == source_after.st_mtime_ns
        )
        checks["second_source_unchanged"] = (
            second_source_stat.st_size == second_source_after.st_size
            and second_source_stat.st_mtime_ns == second_source_after.st_mtime_ns
        )
        checks["subtitle_source_unchanged"] = (
            subtitle_source_stat.st_size == subtitle_source_after.st_size
            and subtitle_source_stat.st_mtime_ns == subtitle_source_after.st_mtime_ns
        )
        subtitle_report = json.loads(subtitle_result.report.read_text(encoding="utf-8"))
        checks["compatible_report_discloses_omitted_subrip"] = (
            subtitle_report.get("stream_mode") == "compatible"
            and [
                stream.get("codec_name")
                for stream in subtitle_report.get("stream_selection", {}).get("omitted_source_streams", [])
            ]
            == ["subrip"]
            and subtitle_report.get("stream_selection", {}).get("omissions_are_intentional") is True
        )
        video_only_report = json.loads(video_only_result.report.read_text(encoding="utf-8"))
        checks["video_only_report_discloses_audio_and_subrip_omissions"] = (
            video_only_report.get("stream_mode") == "video"
            and [
                stream.get("codec_type")
                for stream in video_only_report.get("stream_selection", {}).get(
                    "omitted_source_streams", []
                )
            ]
            == ["audio", "subtitle"]
            and video_only_report.get("stream_selection", {}).get("omissions_are_intentional") is True
        )

        software_cases = (
            (PRORES_PROFILE_KEY, "mov", "prores", "yuv444p12le", None),
            (DNXHR_PROFILE_KEY, "mov", "dnxhd", "yuv444p10le", None),
            (H264_SOFTWARE_PROFILE_KEY, "mp4", "h264", "yuv420p", 35),
            (HEVC_SOFTWARE_PROFILE_KEY, "mp4", "hevc", "yuv444p12le", 35),
            (AV1_SOFTWARE_PROFILE_KEY, "mp4", "av1", "yuv420p10le", 45),
        )
        transcode_plans: list[tuple[str, RemuxPlan]] = []
        for profile_key, container_key, _codec, _pixel_format, quality in software_cases:
            transcode_output = destination / f"self-test-{profile_key}.{container_key}"
            transcode_plans.append(
                (
                    profile_key,
                    build_remux_plan(
                        source_probe,
                        transcode_output,
                        container_key,
                        "av",
                        video_encoding_key=profile_key,
                        quality=quality,
                        enforce_space=False,
                    ),
                )
            )
        transcode_batch = run_batch_plans(
            toolchain,
            tuple(transcode_plans),
            cancel_event=threading.Event(),
        )
        checks["software_transcode_profiles_complete"] = (
            transcode_batch.completed == len(software_cases)
            and transcode_batch.failed == 0
            and not transcode_batch.canceled
            and len(transcode_batch.results) == len(software_cases)
        )
        observations["software_transcode_batch"] = {
            "completed": transcode_batch.completed,
            "failed": transcode_batch.failed,
            "canceled": transcode_batch.canceled,
            "failures": list(transcode_batch.failures),
        }
        if checks["software_transcode_profiles_complete"]:
            for case, transcode_result in zip(software_cases, transcode_batch.results, strict=True):
                profile_key, _container_key, expected_codec, expected_pixel_format, _quality = case
                output_video = transcode_result.output_probe.video_streams[0]
                checks[f"{profile_key}_verified"] = (
                    transcode_result.verification.passed
                    and output_video.codec_name == expected_codec
                    and output_video.pixel_format == expected_pixel_format
                    and bool(transcode_result.output_probe.audio_streams)
                    and transcode_result.output.with_suffix(
                        transcode_result.output.suffix + ".transcode.json"
                    ).is_file()
                )
        else:
            for profile_key, _container_key, _codec, _pixel_format, _quality in software_cases:
                checks[f"{profile_key}_verified"] = False

        nvenc_plan = build_remux_plan(
            source_probe,
            destination / "self-test-h264-nvenc.mp4",
            "mp4",
            "av",
            video_encoding_key=H264_NVENC_PROFILE_KEY,
            quality=12,
            enforce_space=False,
        )
        nvenc_command = RemuxEngine(toolchain).build_command(
            nvenc_plan,
            nvenc_plan.partial_output,
        )
        requested_nvenc_pairs = {
            "-preset:v:0": "p7",
            "-tune:v:0": "hq",
            "-rc:v:0": "vbr",
            "-cq:v:0": "12",
            "-b:v:0": "0",
            "-multipass:v:0": "fullres",
            "-bf:v:0": "4",
            "-b_ref_mode:v:0": "middle",
            "-rc-lookahead:v:0": "27",
            "-lookahead_level:v:0": "3",
            "-spatial-aq:v:0": "0",
            "-temporal-aq:v:0": "1",
        }
        checks["h264_nvenc_exact_requested_command"] = all(
            flag in nvenc_command
            and nvenc_command[nvenc_command.index(flag) + 1] == expected
            for flag, expected in requested_nvenc_pairs.items()
        )
        observations["h264_nvenc_command"] = list(nvenc_command)
        checks["no_partial_files"] = not any(
            item.is_file() and ("partial" in item.name or "preflight" in item.name)
            for item in root.rglob("*")
        )
        observations["output_probe"] = result.output_probe.to_dict()
        observations["second_output_probe"] = second_result.output_probe.to_dict()
        observations["compatible_output_probe"] = subtitle_result.output_probe.to_dict()
        observations["video_only_output_probe"] = video_only_result.output_probe.to_dict()
        observations["verification"] = result.verification.to_dict()
        observations["second_verification"] = second_result.verification.to_dict()
        observations["compatible_verification"] = subtitle_result.verification.to_dict()
        observations["video_only_verification"] = video_only_result.verification.to_dict()
        observations["batch"] = {
            "completed": batch.completed,
            "failed": batch.failed,
            "canceled": batch.canceled,
            "total": batch.total,
        }
    return {
        "schema": 1,
        "application": "Stream Copy Remuxer",
        "version": __version__,
        "passed": all(checks.values()),
        "checks": checks,
        "observations": observations,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-remux media with stream copy or transcode video using high-quality compatibility profiles."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="Run the bounded GUI and FFV1/MP4 integration self-test.")
    mode.add_argument("--dependency-check", action="store_true", help="Report detected FFmpeg and FFprobe.")
    mode.add_argument("--probe", metavar="MEDIA", type=Path, help="Print a JSON media probe.")
    mode.add_argument("--remux", metavar="MEDIA", type=Path, help="Run a command-line remux or video transcode.")
    parser.add_argument("--open", metavar="MEDIA", type=Path, help="Open this source when the GUI starts.")
    parser.add_argument("--output", type=Path, help="Output media for --remux, or JSON for a diagnostic mode.")
    parser.add_argument("--container", choices=tuple(CONTAINER_PROFILES), default="mp4")
    parser.add_argument("--stream-mode", choices=("av", "video", "compatible", "all"), default="av")
    parser.add_argument(
        "--video-encoding",
        choices=tuple(ENCODING_PROFILES),
        default=COPY_PROFILE_KEY,
        help="Video output profile; defaults to packet-preserving stream copy.",
    )
    parser.add_argument(
        "--quality",
        type=int,
        help="CRF or CQ for profiles that use one; defaults to the profile's Ultra HQ value of 12.",
    )
    parser.add_argument("--ffmpeg", type=Path, help="Explicit ffmpeg.exe; paired ffprobe.exe is preferred.")
    parser.add_argument("--ffprobe", type=Path, help="Explicit ffprobe.exe.")
    return parser


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    configure_logging()
    args = build_parser().parse_args(argv)
    try:
        if args.ffmpeg is not None and not args.ffmpeg.expanduser().is_file():
            raise RuntimeError(f"The requested FFmpeg does not exist: {args.ffmpeg}")
        if args.ffprobe is not None and not args.ffprobe.expanduser().is_file():
            raise RuntimeError(f"The requested FFprobe does not exist: {args.ffprobe}")
        if args.ffmpeg is not None and args.ffprobe is None:
            paired_probe = args.ffmpeg.expanduser().resolve().with_name("ffprobe.exe")
            if not paired_probe.is_file():
                raise RuntimeError(f"A paired FFprobe was not found beside the requested FFmpeg: {paired_probe}")
        if args.ffprobe is not None and args.ffmpeg is None:
            paired_ffmpeg = args.ffprobe.expanduser().resolve().with_name("ffmpeg.exe")
            if not paired_ffmpeg.is_file():
                raise RuntimeError(f"A paired FFmpeg was not found beside the requested FFprobe: {paired_ffmpeg}")
        toolchain = discover_toolchain(ffmpeg=args.ffmpeg, ffprobe=args.ffprobe)
        if args.self_test:
            payload = run_self_test(toolchain)
            write_json(payload, args.output)
            return 0 if payload["passed"] else 1
        if args.dependency_check:
            payload = {
                "schema": 1,
                "application": "Stream Copy Remuxer",
                "version": __version__,
                "passed": toolchain.ready,
                "source": toolchain.source,
                "ffmpeg": str(toolchain.ffmpeg) if toolchain.ffmpeg else None,
                "ffprobe": str(toolchain.ffprobe) if toolchain.ffprobe else None,
                "ffmpeg_version": toolchain.ffmpeg_version,
                "ffprobe_version": toolchain.ffprobe_version,
                "video_encoders": sorted(toolchain.video_encoders),
                "video_profiles": {
                    key: {
                        "available": encoder_availability(toolchain, key)[0],
                        "detail": encoder_availability(toolchain, key)[1],
                    }
                    for key in ENCODING_PROFILES
                },
            }
            write_json(payload, args.output)
            return 0 if toolchain.ready else 1
        if args.probe:
            require_toolchain(toolchain)
            assert toolchain.ffprobe is not None
            write_json(probe_media(toolchain.ffprobe, args.probe).to_dict(), args.output)
            return 0
        if args.remux:
            require_toolchain(toolchain)
            if args.output is None:
                raise RuntimeError("--remux requires --output.")
            assert toolchain.ffprobe is not None
            source_probe = probe_media(toolchain.ffprobe, args.remux)
            plan = build_remux_plan(
                source_probe,
                args.output,
                args.container,
                args.stream_mode,
                video_encoding_key=args.video_encoding,
                quality=args.quality,
            )
            result = RemuxEngine(toolchain).run(
                plan,
                on_status=(lambda text: print(text) if sys.stdout is not None else None),
            )
            payload = {
                "passed": True,
                "output": str(result.output),
                "report": str(result.report),
                "verification": result.verification.to_dict(),
            }
            if sys.stdout is not None:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        enable_dpi_awareness()
        root = create_root()
        StreamCopyRemuxerApp(root, toolchain, start_path=args.open)
        root.mainloop()
        return 0
    except Exception as exc:
        logging.getLogger("stream_copy_remuxer").exception("Fatal application error")
        if args.output is not None and args.self_test:
            try:
                write_json(
                    {
                        "schema": 1,
                        "application": "Stream Copy Remuxer",
                        "version": __version__,
                        "passed": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                    args.output,
                )
            except Exception:
                logging.getLogger("stream_copy_remuxer").exception(
                    "Could not write the failed self-test diagnostic report"
                )
        if sys.stderr is not None:
            print(f"Stream Copy Remuxer: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
