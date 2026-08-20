from __future__ import annotations

from collections import Counter

from .models import MediaProbe, VerificationCheck, VerificationResult


def verify_remux(
    source: MediaProbe,
    output: MediaProbe,
    *,
    stream_mode: str,
    container_key: str,
) -> VerificationResult:
    checks: list[VerificationCheck] = []
    warnings: list[str] = []
    selected = source.selected_streams(stream_mode, container_key)
    expected_signatures = Counter(stream.preservation_signature() for stream in selected)
    actual_streams = output.selected_streams(stream_mode, container_key)
    actual_signatures = Counter(stream.preservation_signature() for stream in actual_streams)
    checks.append(
        VerificationCheck(
            "stream codecs and core properties",
            expected_signatures == actual_signatures,
            f"expected {dict(expected_signatures)}; actual {dict(actual_signatures)}",
        )
    )
    if stream_mode == "video":
        checks.append(
            VerificationCheck(
                "video-only output contains no audio",
                not output.audio_streams,
                (
                    "no audio streams detected"
                    if not output.audio_streams
                    else "unexpected output audio stream(s): "
                    + ", ".join(str(stream.index) for stream in output.audio_streams)
                ),
            )
        )
    checks.append(
        VerificationCheck(
            "output file is nonempty",
            output.size > 1024,
            f"output size {output.size:,} bytes",
        )
    )
    if source.duration is not None and output.duration is not None:
        delta = abs(source.duration - output.duration)
        tolerance = max(1.0, source.duration * 0.001)
        checks.append(
            VerificationCheck(
                "timeline duration",
                delta <= tolerance,
                f"source {source.duration:.6f}s; output {output.duration:.6f}s; delta {delta:.6f}s; tolerance {tolerance:.6f}s",
            )
        )
    else:
        warnings.append("A reliable duration was unavailable for one side, so duration equivalence was not checked.")
    checks.append(
        VerificationCheck(
            "chapter count",
            source.chapter_count == output.chapter_count,
            f"source {source.chapter_count}; output {output.chapter_count}",
        )
    )
    ffv1_streams = [stream for stream in output.video_streams if stream.codec_name.lower() == "ffv1"]
    if ffv1_streams and container_key in {"mp4", "mov"}:
        missing = [stream.index for stream in ffv1_streams if not stream.frame_count]
        checks.append(
            VerificationCheck(
                "indexed FFV1 frame count",
                not missing,
                (
                    "all FFV1 video tracks report a positive frame count"
                    if not missing
                    else "no positive frame count for output stream(s): " + ", ".join(map(str, missing))
                ),
            )
        )
    source_title = source.format_tags.get("title") or source.format_tags.get("TITLE")
    output_title = output.format_tags.get("title") or output.format_tags.get("TITLE")
    if source_title and source_title != output_title:
        warnings.append("The destination container did not reproduce the source format title exactly.")
    passed = all(check.passed for check in checks)
    return VerificationResult(passed=passed, checks=tuple(checks), warnings=tuple(warnings))
