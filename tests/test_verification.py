from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stream_copy_remuxer.models import StreamInfo
from stream_copy_remuxer.verification import verify_remux

from .helpers import audio_stream, make_probe, subtitle_stream, video_stream


class VerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="remux-verify-test-")
        self.root = Path(self.temporary.name)
        self.source_path = self.root / "source.mkv"
        self.output_path = self.root / "output.mp4"
        self.source_path.write_bytes(b"s" * 4096)
        self.output_path.write_bytes(b"o" * 4096)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_ffv1_mp4_passes_with_positive_frame_count(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(), audio_stream()))
        output = make_probe(
            self.output_path,
            streams=(video_stream(frame_count=250), audio_stream()),
        )
        result = verify_remux(source, output, stream_mode="av", container_key="mp4")
        self.assertTrue(result.passed)

    def test_ffv1_mp4_fails_without_indexed_frame_count(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(),))
        output = make_probe(self.output_path, streams=(video_stream(frame_count=None),))
        result = verify_remux(source, output, stream_mode="av", container_key="mp4")
        self.assertFalse(result.passed)
        self.assertTrue(any(check.name == "indexed FFV1 frame count" and not check.passed for check in result.checks))

    def test_codec_change_fails(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(codec="ffv1"),))
        output = make_probe(self.output_path, streams=(video_stream(codec="h264", frame_count=250),))
        result = verify_remux(source, output, stream_mode="av", container_key="mp4")
        self.assertFalse(result.passed)

    def test_core_video_property_change_fails(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(),))
        changed = StreamInfo(
            index=0,
            codec_type="video",
            codec_name="ffv1",
            width=1280,
            height=720,
            pixel_format="yuv444p12le",
            frame_count=250,
        )
        output = make_probe(self.output_path, streams=(changed,))
        self.assertFalse(verify_remux(source, output, stream_mode="av", container_key="mp4").passed)

    def test_unknown_source_pixel_format_does_not_become_a_wildcard(self) -> None:
        source_video = StreamInfo(
            index=0,
            codec_type="video",
            codec_name="ffv1",
            width=1424,
            height=1080,
            pixel_format="",
        )
        output_video = StreamInfo(
            index=0,
            codec_type="video",
            codec_name="ffv1",
            width=1424,
            height=1080,
            pixel_format="yuv420p",
            frame_count=13,
        )
        source = make_probe(self.source_path, streams=(source_video,))
        output = make_probe(self.output_path, streams=(output_video,))
        result = verify_remux(source, output, stream_mode="av", container_key="mp4")
        self.assertFalse(result.passed)
        property_check = next(
            check for check in result.checks if check.name == "stream codecs and core properties"
        )
        self.assertFalse(property_check.passed)

    def test_av_mode_ignores_container_created_data_track(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(), audio_stream()))
        chapter_track = StreamInfo(index=2, codec_type="data", codec_name="bin_data")
        output = make_probe(
            self.output_path,
            streams=(video_stream(frame_count=250), audio_stream(), chapter_track),
        )
        self.assertTrue(verify_remux(source, output, stream_mode="av", container_key="mp4").passed)

    def test_compatible_mode_verifies_exact_planned_stream_set(self) -> None:
        source = make_probe(
            self.source_path,
            streams=(video_stream(), audio_stream(), subtitle_stream(codec="subrip")),
        )
        output = make_probe(
            self.output_path,
            streams=(video_stream(frame_count=250), audio_stream()),
        )
        result = verify_remux(source, output, stream_mode="compatible", container_key="mp4")
        self.assertTrue(result.passed, result)

    def test_compatible_mode_still_rejects_selected_codec_change(self) -> None:
        source = make_probe(
            self.source_path,
            streams=(video_stream(), audio_stream(), subtitle_stream(codec="subrip")),
        )
        output = make_probe(
            self.output_path,
            streams=(video_stream(codec="h264", frame_count=250), audio_stream()),
        )
        result = verify_remux(source, output, stream_mode="compatible", container_key="mp4")
        self.assertFalse(result.passed)

    def test_video_only_mode_ignores_intentionally_omitted_audio_and_subtitles(self) -> None:
        source = make_probe(
            self.source_path,
            streams=(video_stream(), audio_stream(), subtitle_stream(codec="subrip")),
        )
        output = make_probe(self.output_path, streams=(video_stream(frame_count=250),))
        result = verify_remux(source, output, stream_mode="video", container_key="mp4")
        self.assertTrue(result.passed, result)

    def test_video_only_mode_still_rejects_video_codec_change(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(), audio_stream()))
        output = make_probe(
            self.output_path,
            streams=(video_stream(codec="h264", frame_count=250),),
        )
        self.assertFalse(verify_remux(source, output, stream_mode="video", container_key="mp4").passed)

    def test_video_only_mode_rejects_an_unexpected_output_audio_stream(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(), audio_stream()))
        output = make_probe(
            self.output_path,
            streams=(video_stream(frame_count=250), audio_stream()),
        )
        result = verify_remux(source, output, stream_mode="video", container_key="mp4")
        self.assertFalse(result.passed)
        self.assertTrue(
            any(check.name == "video-only output contains no audio" and not check.passed for check in result.checks)
        )

    def test_chapter_loss_fails(self) -> None:
        source = make_probe(self.source_path, streams=(video_stream(),), chapters=3)
        output = make_probe(self.output_path, streams=(video_stream(frame_count=250),), chapters=0)
        self.assertFalse(verify_remux(source, output, stream_mode="av", container_key="mp4").passed)


if __name__ == "__main__":
    unittest.main()
