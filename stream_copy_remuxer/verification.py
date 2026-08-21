from __future__ import annotations

from collections import Counter
from fractions import Fraction

from .models import MediaProbe, ResolvedVideoEncoding, VerificationCheck, VerificationResult


def _frame_rates_match(expected: str, actual: str) -> bool:
    try:
        first = Fraction(expected)
        second = Fraction(actual)
    except (ValueError, ZeroDivisionError):
        return expected == actual
    if first <= 0 or second <= 0:
        return first == second
    return abs(float(first - second)) <= max(0.001, float(first) * 0.0001)


def _normalized_profile(value: str) -> str:
    return " ".join(value.upper().replace("_", " ").split())


def verify_remux(
    source: MediaProbe,
    output: MediaProbe,
    *,
    stream_mode: str,
    container_key: str,
    resolved_video_encodings: tuple[ResolvedVideoEncoding, ...] = (),
    check_timeline: bool = True,
    check_chapters: bool = True,
) -> VerificationResult:
    checks: list[VerificationCheck] = []
    warnings: list[str] = []
    selected = source.selected_streams(stream_mode, container_key)
    actual_streams = output.selected_streams(stream_mode, container_key)
    if not resolved_video_encodings:
        expected_signatures = Counter(stream.preservation_signature() for stream in selected)
        actual_signatures = Counter(stream.preservation_signature() for stream in actual_streams)
        checks.append(
            VerificationCheck(
                "stream codecs and core properties",
                expected_signatures == actual_signatures,
                f"expected {dict(expected_signatures)}; actual {dict(actual_signatures)}",
            )
        )
    else:
        expected_non_video = Counter(
            stream.preservation_signature() for stream in selected if stream.codec_type != "video"
        )
        actual_non_video = Counter(
            stream.preservation_signature() for stream in actual_streams if stream.codec_type != "video"
        )
        checks.append(
            VerificationCheck(
                "copied non-video stream codecs and core properties",
                expected_non_video == actual_non_video,
                f"expected {dict(expected_non_video)}; actual {dict(actual_non_video)}",
            )
        )
        actual_video = tuple(stream for stream in actual_streams if stream.codec_type == "video")
        checks.append(
            VerificationCheck(
                "transcoded video stream count",
                len(actual_video) == len(resolved_video_encodings),
                f"expected {len(resolved_video_encodings)}; actual {len(actual_video)}",
            )
        )
        source_by_index = {stream.index: stream for stream in source.video_streams}
        for position, resolved in enumerate(resolved_video_encodings):
            expected_source = source_by_index[resolved.source_stream_index]
            actual = actual_video[position] if position < len(actual_video) else None
            codec_ok = actual is not None and actual.codec_name.lower() == resolved.codec_name.lower()
            geometry_ok = actual is not None and (
                actual.width,
                actual.height,
            ) == (
                expected_source.width,
                expected_source.height,
            )
            pixel_ok = actual is not None and actual.pixel_format.lower() == resolved.expected_pixel_format.lower()
            profile_ok = (
                actual is not None
                and (
                    not resolved.expected_profile
                    or _normalized_profile(actual.profile) == _normalized_profile(resolved.expected_profile)
                )
            )
            tag_ok = (
                actual is not None
                and (
                    not resolved.expected_codec_tag
                    or actual.codec_tag_string.lower() == resolved.expected_codec_tag.lower()
                )
            )
            rate_ok = actual is not None and _frame_rates_match(
                expected_source.frame_rate,
                actual.frame_rate,
            )
            passed = codec_ok and geometry_ok and pixel_ok and profile_ok and tag_ok and rate_ok
            actual_detail = "missing" if actual is None else (
                f"codec={actual.codec_name}, profile={actual.profile or '(none)'}, "
                f"tag={actual.codec_tag_string or '(none)'}, {actual.width}x{actual.height}, "
                f"pix_fmt={actual.pixel_format or '(none)'}, rate={actual.frame_rate or '(none)'}"
            )
            checks.append(
                VerificationCheck(
                    f"transcoded video stream {position}",
                    passed,
                    (
                        f"expected codec={resolved.codec_name}, profile={resolved.expected_profile or '(any)'}, "
                        f"tag={resolved.expected_codec_tag or '(any)'}, "
                        f"{expected_source.width}x{expected_source.height}, "
                        f"pix_fmt={resolved.expected_pixel_format}, rate={expected_source.frame_rate}; "
                        f"actual {actual_detail}"
                    ),
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
    if check_timeline and source.duration is not None and output.duration is not None:
        delta = abs(source.duration - output.duration)
        tolerance = max(1.0, source.duration * 0.001)
        checks.append(
            VerificationCheck(
                "timeline duration",
                delta <= tolerance,
                f"source {source.duration:.6f}s; output {output.duration:.6f}s; delta {delta:.6f}s; tolerance {tolerance:.6f}s",
            )
        )
    elif check_timeline:
        warnings.append("A reliable duration was unavailable for one side, so duration equivalence was not checked.")
    if check_chapters:
        checks.append(
            VerificationCheck(
                "chapter count",
                source.chapter_count == output.chapter_count,
                f"source {source.chapter_count}; output {output.chapter_count}",
            )
        )
    ffv1_streams = [stream for stream in output.video_streams if stream.codec_name.lower() == "ffv1"]
    if not resolved_video_encodings and ffv1_streams and container_key in {"mp4", "mov"}:
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
