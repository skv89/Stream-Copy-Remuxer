from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import threading
import time
import uuid
from collections import Counter
from collections import deque
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import __version__
from .models import (
    ProgressUpdate,
    RemuxPlan,
    RemuxResult,
    Toolchain,
    VerificationCheck,
    VerificationResult,
)
from .probe import INPUT_ANALYZE_DURATION_MICROSECONDS, probe_media
from .tools import CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW
from .verification import verify_remux


class RemuxError(RuntimeError):
    pass


class RemuxCancelled(RemuxError):
    pass


class ContainerCompatibilityError(RemuxError):
    pass


class RemuxVerificationError(RemuxError):
    pass


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[ProgressUpdate], None]
LogCallback = Callable[[str], None]


@dataclass(frozen=True)
class _ProcessOutcome:
    returncode: int
    diagnostics: tuple[str, ...]


_PROGRESS_KEYS = {
    "bitrate",
    "drop_frames",
    "dup_frames",
    "fps",
    "frame",
    "out_time",
    "out_time_ms",
    "out_time_us",
    "progress",
    "speed",
    "stream_0_0_q",
    "total_size",
}


def command_display(command: tuple[str, ...] | list[str]) -> str:
    return subprocess.list2cmdline(list(command))


def _safe_callback(callback: Callable[..., None] | None, *args: object) -> None:
    if callback is None:
        return
    try:
        callback(*args)
    except Exception:
        # UI/reporting callbacks must never compromise the media operation.
        pass


def _positive_int(value: str | None) -> int | None:
    try:
        parsed = int(value or "")
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


class RemuxEngine:
    def __init__(self, toolchain: Toolchain) -> None:
        if not toolchain.ready or toolchain.ffmpeg is None or toolchain.ffprobe is None:
            raise RemuxError("FFmpeg and FFprobe are required.")
        self.toolchain = toolchain
        self._promotion_lock = threading.Lock()

    def build_command(self, plan: RemuxPlan, destination: Path, *, preflight: bool = False) -> tuple[str, ...]:
        assert self.toolchain.ffmpeg is not None
        command = [
            str(self.toolchain.ffmpeg),
            "-hide_banner",
            "-nostdin",
            "-n",
            "-loglevel",
            "warning",
            "-analyzeduration",
            str(INPUT_ANALYZE_DURATION_MICROSECONDS),
            "-i",
            str(plan.source_probe.path),
        ]
        if plan.stream_mode == "video":
            command += ["-map", "0:v?"]
        elif plan.stream_mode == "av":
            command += ["-map", "0:v?", "-map", "0:a?"]
        elif plan.stream_mode == "compatible":
            for stream in plan.selected_source_streams:
                command += ["-map", f"0:{stream.index}"]
        else:
            command += ["-map", "0"]
        command += [
            "-map_metadata",
            "0",
            "-map_chapters",
            "0",
            "-c",
            "copy",
        ]
        if plan.profile.key in {"mp4", "mov"}:
            selected_video = [
                stream
                for stream in plan.selected_source_streams
                if stream.codec_type == "video"
            ]
            for output_video_index, stream in enumerate(selected_video):
                if stream.codec_name.lower() == "ffv1":
                    command += [f"-tag:v:{output_video_index}", "FFV1"]
        if preflight:
            command += ["-t", "0.5"]
        command += [
            "-max_muxing_queue_size",
            "4096",
            "-stats_period",
            "0.5",
            "-progress",
            "pipe:1",
            "-nostats",
            "-f",
            plan.profile.muxer,
            str(destination),
        ]
        return tuple(command)

    def _terminate(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=2.0)
                return
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            process.terminate()
            process.wait(timeout=2.0)
            return
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            process.kill()
            process.wait(timeout=5.0)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _run_process(
        self,
        command: tuple[str, ...],
        *,
        phase: str,
        duration: float | None,
        cancel_event: threading.Event,
        on_progress: ProgressCallback | None,
        on_log: LogCallback | None,
    ) -> _ProcessOutcome:
        creationflags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        try:
            process = subprocess.Popen(
                list(command),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise RemuxError(f"Could not start FFmpeg: {exc}") from exc
        if process.stdout is None:
            self._terminate(process)
            raise RemuxError("FFmpeg output monitoring could not be initialized.")

        line_queue: queue.Queue[str | None] = queue.Queue()

        def reader() -> None:
            try:
                for line in process.stdout:
                    line_queue.put(line.rstrip("\r\n"))
            finally:
                line_queue.put(None)

        reader_thread = threading.Thread(target=reader, name="ffmpeg-output-reader", daemon=True)
        reader_thread.start()
        diagnostics: deque[str] = deque(maxlen=400)
        progress_values: dict[str, str] = {}
        reader_finished = False
        canceled = False
        start = time.monotonic()

        while True:
            if cancel_event.is_set() and process.poll() is None and not canceled:
                canceled = True
                self._terminate(process)
            try:
                line = line_queue.get(timeout=0.1)
            except queue.Empty:
                line = ""
            if line is None:
                reader_finished = True
            elif line:
                key, separator, value = line.partition("=")
                if separator and key in _PROGRESS_KEYS:
                    progress_values[key] = value
                    if key == "progress":
                        raw_time = progress_values.get("out_time_us") or progress_values.get("out_time_ms")
                        microseconds = _positive_int(raw_time)
                        media_seconds = microseconds / 1_000_000 if microseconds is not None else None
                        percent = None
                        if duration and duration > 0 and media_seconds is not None:
                            percent = min(100.0, max(0.0, media_seconds * 100.0 / duration))
                        _safe_callback(
                            on_progress,
                            ProgressUpdate(
                                phase=phase,
                                elapsed_seconds=time.monotonic() - start,
                                media_seconds=media_seconds,
                                percent=percent,
                                bytes_written=_positive_int(progress_values.get("total_size")),
                                speed=progress_values.get("speed", ""),
                            ),
                        )
                        progress_values.clear()
                else:
                    diagnostics.append(line)
                    _safe_callback(on_log, line)
            if process.poll() is not None and reader_finished and line_queue.empty():
                break

        reader_thread.join(timeout=1.0)
        try:
            process.stdout.close()
        except OSError:
            pass
        if canceled or cancel_event.is_set():
            raise RemuxCancelled("Remux canceled; no final output was created.")
        return _ProcessOutcome(process.returncode or 0, tuple(diagnostics))

    @staticmethod
    def _failure_detail(outcome: _ProcessOutcome) -> str:
        useful = [line for line in outcome.diagnostics if line.strip()]
        return "\n".join(useful[-12:]) if useful else f"FFmpeg exited with code {outcome.returncode}."

    @staticmethod
    def _remove_owned(path: Path) -> bool:
        for _ in range(4):
            try:
                path.unlink()
                return True
            except FileNotFoundError:
                return True
            except OSError:
                time.sleep(0.1)
        return not path.exists()

    def _publish(
        self,
        plan: RemuxPlan,
        report_payload: dict[str, object],
        cancel_event: threading.Event,
        expected_source_identity: tuple[int, int],
    ) -> None:
        report_temp = plan.report_output.with_name(
            f".{plan.report_output.name}.{uuid.uuid4().hex[:8]}.partial"
        )
        report_temp.write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            with self._promotion_lock:
                if cancel_event.is_set():
                    raise RemuxCancelled("Remux canceled before final promotion; no final output was created.")
                current_source = plan.source_probe.path.stat()
                if (current_source.st_size, current_source.st_mtime_ns) != expected_source_identity:
                    raise RemuxVerificationError(
                        "The source changed before final promotion, so no final output was published."
                    )
                if plan.output.exists() or plan.report_output.exists():
                    raise RemuxError(
                        "The final output or audit report appeared while remuxing; nothing was overwritten."
                    )
                partial_stat = plan.partial_output.stat()
                try:
                    os.rename(plan.partial_output, plan.output)
                except FileExistsError as exc:
                    raise RemuxError("The final output appeared during promotion and was not overwritten.") from exc
                try:
                    os.rename(report_temp, plan.report_output)
                except Exception:
                    try:
                        final_stat = plan.output.stat()
                        if (
                            final_stat.st_dev,
                            final_stat.st_ino,
                            final_stat.st_size,
                        ) == (
                            partial_stat.st_dev,
                            partial_stat.st_ino,
                            partial_stat.st_size,
                        ):
                            plan.output.unlink()
                    except OSError:
                        pass
                    raise
        finally:
            if not self._remove_owned(report_temp):
                raise RemuxError(f"Could not remove the temporary audit file: {report_temp}")

    def run(
        self,
        plan: RemuxPlan,
        *,
        cancel_event: threading.Event | None = None,
        on_status: StatusCallback | None = None,
        on_progress: ProgressCallback | None = None,
        on_log: LogCallback | None = None,
    ) -> RemuxResult:
        cancel_event = cancel_event or threading.Event()
        started_monotonic = time.monotonic()
        started_utc = datetime.now(timezone.utc)
        source_stat = plan.source_probe.path.stat()
        if (
            source_stat.st_size != plan.source_probe.size
            or source_stat.st_mtime_ns != plan.source_probe.modified_ns
        ):
            raise RemuxVerificationError(
                "The source changed after it was inspected. Inspect the source again before starting."
            )
        command = self.build_command(plan, plan.partial_output)
        preflight_command = self.build_command(plan, plan.preflight_output, preflight=True)
        for owned in (plan.partial_output, plan.preflight_output):
            if owned.exists():
                raise RemuxError(f"Unexpected application temporary-file conflict: {owned}")
        try:
            _safe_callback(on_status, "Checking destination-container compatibility…")
            preflight = self._run_process(
                preflight_command,
                phase="preflight",
                duration=min(plan.source_probe.duration or 0.5, 0.5),
                cancel_event=cancel_event,
                on_progress=on_progress,
                on_log=on_log,
            )
            if preflight.returncode != 0:
                raise ContainerCompatibilityError(
                    f"The selected streams cannot be copied into {plan.profile.label}.\n\n"
                    + self._failure_detail(preflight)
                )
            if not plan.preflight_output.is_file() or plan.preflight_output.stat().st_size == 0:
                raise ContainerCompatibilityError("The container preflight did not create a readable test output.")
            assert self.toolchain.ffprobe is not None
            try:
                preflight_probe = probe_media(self.toolchain.ffprobe, plan.preflight_output)
            except Exception as exc:
                raise ContainerCompatibilityError(
                    f"The {plan.profile.label} preflight output could not be read: {exc}"
                ) from exc
            selected_source = plan.selected_source_streams
            selected_preflight = preflight_probe.selected_streams(
                plan.stream_mode,
                plan.profile.key,
            )
            expected_preflight = Counter(stream.preservation_signature() for stream in selected_source)
            actual_preflight = Counter(stream.preservation_signature() for stream in selected_preflight)
            if expected_preflight != actual_preflight:
                raise ContainerCompatibilityError(
                    f"The {plan.profile.label} preflight did not preserve the selected stream codecs and properties. "
                    f"Expected {dict(expected_preflight)}; actual {dict(actual_preflight)}."
                )
            if plan.profile.key in {"mp4", "mov"}:
                missing_ffv1_index = [
                    stream.index
                    for stream in preflight_probe.video_streams
                    if stream.codec_name.lower() == "ffv1" and not stream.frame_count
                ]
                if missing_ffv1_index:
                    raise ContainerCompatibilityError(
                        f"The {plan.profile.label} preflight retained FFV1 but did not expose an indexed frame count; "
                        "this output would not address the Topaz startup problem."
                    )
            if not self._remove_owned(plan.preflight_output):
                raise RemuxError(
                    f"Could not remove the container-preflight file: {plan.preflight_output}"
                )

            if cancel_event.is_set():
                raise RemuxCancelled("Remux canceled; no final output was created.")
            _safe_callback(on_status, "Stream-copying media (no re-encoding)…")
            outcome = self._run_process(
                command,
                phase="remux",
                duration=plan.source_probe.duration,
                cancel_event=cancel_event,
                on_progress=on_progress,
                on_log=on_log,
            )
            if outcome.returncode != 0:
                raise RemuxError("FFmpeg could not complete the remux.\n\n" + self._failure_detail(outcome))
            if not plan.partial_output.is_file() or plan.partial_output.stat().st_size == 0:
                raise RemuxError("FFmpeg reported success but did not create a nonempty output.")
            if cancel_event.is_set():
                raise RemuxCancelled("Remux canceled; no final output was created.")

            _safe_callback(on_status, "Verifying streams, duration, and container index…")
            output_probe = probe_media(self.toolchain.ffprobe, plan.partial_output)
            verification = verify_remux(
                plan.source_probe,
                output_probe,
                stream_mode=plan.stream_mode,
                container_key=plan.profile.key,
            )
            current_source_stat = plan.source_probe.path.stat()
            source_unchanged = (
                source_stat.st_size == current_source_stat.st_size
                and source_stat.st_mtime_ns == current_source_stat.st_mtime_ns
            )
            checks = verification.checks + (
                VerificationCheck(
                    "source remained unchanged",
                    source_unchanged,
                    (
                        f"size {current_source_stat.st_size:,} bytes; mtime_ns {current_source_stat.st_mtime_ns}"
                    ),
                ),
            )
            verification = VerificationResult(
                passed=all(check.passed for check in checks),
                checks=checks,
                warnings=verification.warnings,
            )
            if not verification.passed:
                failures = "\n".join(
                    f"• {check.name}: {check.detail}" for check in verification.checks if not check.passed
                )
                raise RemuxVerificationError(
                    "The remux finished, but verification failed, so no final output was published.\n\n" + failures
                )

            finished_utc = datetime.now(timezone.utc)
            elapsed = time.monotonic() - started_monotonic
            report_payload: dict[str, object] = {
                "schema": 1,
                "application": "Stream Copy Remuxer",
                "version": __version__,
                "method": "FFmpeg stream copy; no decoding or re-encoding",
                "started_utc": started_utc.isoformat(),
                "finished_utc": finished_utc.isoformat(),
                "elapsed_seconds": elapsed,
                "source": plan.source_probe.to_dict(),
                "output": output_probe.to_dict(path=plan.output),
                "destination_container": plan.profile.key,
                "stream_mode": plan.stream_mode,
                "stream_selection": {
                    "selected_source_streams": [
                        stream.to_dict() for stream in plan.selected_source_streams
                    ],
                    "omitted_source_streams": [
                        stream.to_dict() for stream in plan.omitted_source_streams
                    ],
                    "omissions_are_intentional": bool(plan.omitted_source_streams),
                },
                "compatibility_notes": list(plan.compatibility_notes),
                "space": {
                    "available_bytes_at_plan_time": plan.available_bytes,
                    "required_bytes_estimate": plan.required_bytes,
                },
                "toolchain": {
                    "source": self.toolchain.source,
                    "ffmpeg": str(self.toolchain.ffmpeg),
                    "ffprobe": str(self.toolchain.ffprobe),
                    "ffmpeg_version": self.toolchain.ffmpeg_version,
                    "ffprobe_version": self.toolchain.ffprobe_version,
                },
                "command": list(command),
                "command_display": command_display(command),
                "verification": verification.to_dict(),
            }
            _safe_callback(on_status, "Publishing verified output…")
            self._publish(
                plan,
                report_payload,
                cancel_event,
                (source_stat.st_size, source_stat.st_mtime_ns),
            )
            output_probe = replace(output_probe, path=plan.output)
            _safe_callback(on_progress, ProgressUpdate("complete", elapsed, percent=100.0))
            _safe_callback(on_status, "Remux complete and verified.")
            return RemuxResult(
                output=plan.output,
                report=plan.report_output,
                output_probe=output_probe,
                verification=verification,
                elapsed_seconds=elapsed,
                command=command,
            )
        except Exception as exc:
            leftovers = [
                path
                for path in (plan.preflight_output, plan.partial_output)
                if not self._remove_owned(path)
            ]
            if leftovers:
                raise RemuxError(
                    f"{exc}\n\nThe following application-owned temporary file(s) could not be removed: "
                    + "; ".join(str(path) for path in leftovers)
                ) from exc
            raise
