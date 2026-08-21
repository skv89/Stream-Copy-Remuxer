from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stream_copy_remuxer.encoding import H264_SOFTWARE_PROFILE_KEY, PRORES_PROFILE_KEY
from stream_copy_remuxer.models import StreamInfo
from stream_copy_remuxer.planning import PlanError, build_remux_plan, suggest_output

from .helpers import audio_stream, make_probe, subtitle_stream, video_stream


class PlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="remux-plan-test-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "源 & source.mkv"
        self.source.write_bytes(b"source media placeholder")
        self.probe = make_probe(self.source)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_suggest_output_never_selects_existing_file_or_report(self) -> None:
        first = self.root / "源 & source_remux.mp4"
        first.write_bytes(b"existing")
        second = self.root / "源 & source_remux_2.mp4"
        second.with_suffix(".mp4.remux.json").write_text("{}", encoding="utf-8")
        self.assertEqual(suggest_output(self.source, "mp4"), self.root / "源 & source_remux_3.mp4")

    def test_builds_unique_same_folder_temporary_paths(self) -> None:
        output = self.root / "result.mp4"
        plan = build_remux_plan(self.probe, output, "mp4", "av")
        self.assertEqual(plan.partial_output.parent, output.parent)
        self.assertEqual(plan.preflight_output.parent, output.parent)
        self.assertTrue(plan.partial_output.name.endswith(".partial.mp4"))
        self.assertTrue(plan.preflight_output.name.endswith(".preflight.mp4"))
        self.assertNotEqual(plan.partial_output, plan.preflight_output)

    def test_rejects_source_as_destination(self) -> None:
        mp4_source = self.root / "same.mp4"
        mp4_source.write_bytes(b"source")
        with self.assertRaisesRegex(PlanError, "cannot be the source"):
            build_remux_plan(make_probe(mp4_source), mp4_source, "mp4", "av")

    def test_rejects_existing_destination_and_report(self) -> None:
        output = self.root / "result.mp4"
        output.write_bytes(b"user data")
        with self.assertRaisesRegex(PlanError, "nothing will be overwritten"):
            build_remux_plan(self.probe, output, "mp4", "av")
        output.unlink()
        output.with_suffix(".mp4.remux.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(PlanError, "nothing will be overwritten"):
            build_remux_plan(self.probe, output, "mp4", "av")

    def test_rejects_wrong_extension(self) -> None:
        with self.assertRaisesRegex(PlanError, "must use the .mp4 extension"):
            build_remux_plan(self.probe, self.root / "result.mkv", "mp4", "av")

    def test_rejects_insufficient_free_space(self) -> None:
        tiny_space = shutil._ntuple_diskusage(total=1000, used=900, free=100)
        with patch("stream_copy_remuxer.planning.shutil.disk_usage", return_value=tiny_space):
            with self.assertRaisesRegex(PlanError, "not have enough free space"):
                build_remux_plan(self.probe, self.root / "result.mp4", "mp4", "av")

    def test_video_audio_mode_discloses_omitted_streams(self) -> None:
        subtitle = StreamInfo(index=2, codec_type="subtitle", codec_name="subrip")
        probe = make_probe(self.source, streams=self.probe.streams + (subtitle,))
        plan = build_remux_plan(probe, self.root / "result.mp4", "mp4", "av")
        self.assertTrue(any("omit" in note and "#2 subtitle/subrip" in note for note in plan.compatibility_notes))

    def test_video_only_mode_selects_video_and_discloses_every_non_video_stream(self) -> None:
        probe = make_probe(
            self.source,
            streams=(
                video_stream(index=0),
                audio_stream(index=1),
                subtitle_stream(index=2, codec="subrip", language="chi", title="Traditional"),
            ),
        )
        plan = build_remux_plan(probe, self.root / "video-only.mp4", "mp4", "video")
        self.assertEqual([stream.index for stream in plan.selected_source_streams], [0])
        self.assertEqual([stream.index for stream in plan.omitted_source_streams], [1, 2])
        joined = " ".join(plan.compatibility_notes)
        self.assertIn("#1 audio/aac", joined)
        self.assertIn('#2 subtitle/subrip ("Traditional", language chi)', joined)
        self.assertIn("No stream will be re-encoded", joined)

    def test_compatible_mode_discloses_exact_omissions_and_retains_safe_subtitle(self) -> None:
        probe = make_probe(
            self.source,
            streams=(
                video_stream(index=0),
                audio_stream(index=1),
                subtitle_stream(index=2, codec="subrip", language="chi", title="Traditional"),
                subtitle_stream(index=3, codec="mov_text", language="eng", title="Signs"),
            ),
        )
        plan = build_remux_plan(probe, self.root / "compatible.mp4", "mp4", "compatible")
        self.assertEqual([stream.index for stream in plan.selected_source_streams], [0, 1, 3])
        self.assertEqual([stream.index for stream in plan.omitted_source_streams], [2])
        joined = " ".join(plan.compatibility_notes)
        self.assertIn('#2 subtitle/subrip ("Traditional", language chi)', joined)
        self.assertIn("No stream will be re-encoded", joined)

    def test_compatible_mkv_keeps_every_source_stream(self) -> None:
        subtitle = subtitle_stream(index=2, codec="subrip")
        probe = make_probe(self.source, streams=self.probe.streams + (subtitle,))
        plan = build_remux_plan(probe, self.root / "compatible.mkv", "mkv", "compatible")
        self.assertEqual(plan.selected_source_streams, probe.streams)
        self.assertFalse(plan.omitted_source_streams)

    def test_avi_stream_copy_uses_avi_muxer_and_omits_extra_streams_in_compatible_mode(self) -> None:
        probe = make_probe(
            self.source,
            streams=(
                video_stream(index=0),
                audio_stream(index=1),
                subtitle_stream(index=2, codec="mov_text", language="eng"),
                subtitle_stream(index=3, codec="subrip", language="chi"),
            ),
        )
        plan = build_remux_plan(probe, self.root / "compatible.avi", "avi", "compatible")
        self.assertEqual(plan.profile.muxer, "avi")
        self.assertEqual([stream.index for stream in plan.selected_source_streams], [0, 1])
        self.assertEqual([stream.index for stream in plan.omitted_source_streams], [2, 3])
        self.assertIn("legacy compatibility container", " ".join(plan.compatibility_notes))
        self.assertEqual(suggest_output(self.source, "avi"), self.root / "源 & source_remux.avi")

    def test_strict_all_mode_blocks_known_incompatible_avi_extra_streams(self) -> None:
        subtitle = subtitle_stream(index=2, codec="subrip", title="Traditional")
        probe = make_probe(self.source, streams=self.probe.streams + (subtitle,))
        with self.assertRaisesRegex(PlanError, "AVI cannot stream-copy every source stream"):
            build_remux_plan(probe, self.root / "strict.avi", "avi", "all")

    def test_strict_all_mode_blocks_known_incompatible_mp4_stream_before_ffmpeg(self) -> None:
        subtitle = subtitle_stream(index=2, codec="subrip", title="Traditional")
        probe = make_probe(self.source, streams=self.probe.streams + (subtitle,))
        with self.assertRaisesRegex(
            PlanError,
            "All compatible streams.*Video \\+ audio.*Video only.*MKV",
        ):
            build_remux_plan(probe, self.root / "strict.mp4", "mp4", "all")

    def test_ffv1_mp4_note_discloses_compatibility(self) -> None:
        plan = build_remux_plan(self.probe, self.root / "result.mp4", "mp4", "av")
        joined = " ".join(plan.compatibility_notes)
        self.assertIn("remains lossless", joined)
        self.assertIn("frame count", joined)

    def test_transcode_plan_resolves_profile_quality_suffix_and_audit_path(self) -> None:
        output = self.root / "result.mp4"
        plan = build_remux_plan(
            self.probe,
            output,
            "mp4",
            "av",
            video_encoding_key=H264_SOFTWARE_PROFILE_KEY,
            quality=17,
            enforce_space=False,
        )
        self.assertFalse(plan.is_stream_copy)
        self.assertTrue(plan.is_lossy)
        self.assertEqual(plan.quality_value, 17)
        self.assertEqual(plan.report_output, self.root / "result.mp4.transcode.json")
        self.assertEqual(plan.resolved_video_encodings[0].encoder_name, "libx264")
        self.assertEqual(plan.resolved_video_encodings[0].pixel_format, "yuv420p")
        self.assertIn("lossy", " ".join(plan.compatibility_notes))
        self.assertEqual(
            suggest_output(
                self.source,
                "mp4",
                video_encoding_key=H264_SOFTWARE_PROFILE_KEY,
            ),
            self.root / "源 & source_h264_x264.mp4",
        )

    def test_fixed_container_profile_rejects_mismatch_and_accepts_mov(self) -> None:
        with self.assertRaisesRegex(PlanError, "requires MOV"):
            build_remux_plan(
                self.probe,
                self.root / "prores.mp4",
                "mp4",
                "av",
                video_encoding_key=PRORES_PROFILE_KEY,
                enforce_space=False,
            )
        plan = build_remux_plan(
            self.probe,
            self.root / "prores.mov",
            "mov",
            "av",
            video_encoding_key=PRORES_PROFILE_KEY,
            enforce_space=False,
        )
        self.assertEqual(plan.profile.key, "mov")
        self.assertIn("ProRes 4444 XQ", plan.resolved_video_encodings[0].label)


if __name__ == "__main__":
    unittest.main()
