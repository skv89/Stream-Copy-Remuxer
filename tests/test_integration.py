from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from stream_copy_remuxer.engine import ContainerCompatibilityError, RemuxCancelled, RemuxEngine, RemuxError
from stream_copy_remuxer.planning import PlanError, build_remux_plan
from stream_copy_remuxer.probe import probe_media
from stream_copy_remuxer.tools import CREATE_NO_WINDOW, discover_toolchain


class FFmpegIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.toolchain = discover_toolchain()
        if not cls.toolchain.ready:
            raise unittest.SkipTest("FFmpeg + FFprobe are unavailable")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="remux-integration-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _run_ffmpeg(self, arguments: list[str]) -> subprocess.CompletedProcess[str]:
        assert self.toolchain.ffmpeg is not None
        return subprocess.run(
            [str(self.toolchain.ffmpeg), "-hide_banner", "-nostdin", "-y", *arguments],
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

    def _make_ffv1(self, path: Path, *, with_audio: bool = False) -> None:
        arguments = [
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x90:rate=25:duration=1",
        ]
        if with_audio:
            arguments += [
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=48000:duration=1",
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
            ]
        arguments += [
            "-pix_fmt",
            "yuv444p12le",
            "-c:v",
            "ffv1",
            "-level",
            "3",
        ]
        if with_audio:
            arguments += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        arguments.append(str(path))
        result = self._run_ffmpeg(arguments)
        self.assertEqual(result.returncode, 0, result.stdout)

    def _make_ffv1_with_subrip(self, path: Path) -> None:
        base = path.with_name(path.stem + "-base.mkv")
        subtitle = path.with_suffix(".srt")
        self._make_ffv1(base, with_audio=True)
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:00,800\nTraditional subtitle test\n",
            encoding="utf-8",
        )
        result = self._run_ffmpeg(
            [
                "-i",
                str(base),
                "-f",
                "srt",
                "-i",
                str(subtitle),
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
                str(path),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def _make_mp4_with_mov_text(self, path: Path) -> None:
        subtitle = path.with_suffix(".srt")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:00,800\nCompatible subtitle test\n",
            encoding="utf-8",
        )
        result = self._run_ffmpeg(
            [
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=160x90:rate=25:duration=1",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=800:sample_rate=48000:duration=1",
                "-f",
                "srt",
                "-i",
                str(subtitle),
                "-map",
                "0:v:0",
                "-map",
                "1:a:0",
                "-map",
                "2:s:0",
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                "-c:a",
                "aac",
                "-c:s",
                "mov_text",
                "-shortest",
                str(path),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_real_ffv1_mkv_to_mp4_stream_copy(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "source 測試.mkv"
        output = self.root / "output 測試.mp4"
        self._make_ffv1(source, with_audio=True)
        source_before = source.stat()
        plan = build_remux_plan(probe_media(self.toolchain.ffprobe, source), output, "mp4", "av")
        result = RemuxEngine(self.toolchain).run(plan)
        source_after = source.stat()
        self.assertTrue(result.verification.passed)
        self.assertEqual(result.output, output)
        self.assertEqual(result.output_probe.path, output)
        self.assertEqual(result.output_probe.video_streams[0].codec_name, "ffv1")
        self.assertEqual(result.output_probe.video_streams[0].frame_count, 25)
        self.assertEqual(len(result.output_probe.audio_streams), 1)
        self.assertEqual(result.output_probe.audio_streams[0].codec_name, "aac")
        self.assertEqual(source_before.st_size, source_after.st_size)
        self.assertEqual(source_before.st_mtime_ns, source_after.st_mtime_ns)
        self.assertTrue(output.with_suffix(".mp4.remux.json").is_file())
        self.assertFalse(any("partial" in item.name or "preflight" in item.name for item in self.root.iterdir()))

    def test_real_mov_and_mkv_destinations(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "source.mkv"
        self._make_ffv1(source)
        source_probe = probe_media(self.toolchain.ffprobe, source)
        for container, extension in (("mov", ".mov"), ("mkv", ".mkv")):
            with self.subTest(container=container):
                output = self.root / f"remuxed{extension}"
                plan = build_remux_plan(source_probe, output, container, "av")
                result = RemuxEngine(self.toolchain).run(plan)
                self.assertTrue(result.verification.passed)
                self.assertEqual(result.output_probe.video_streams[0].codec_name, "ffv1")
                if container == "mov":
                    self.assertEqual(result.output_probe.video_streams[0].frame_count, 25)

    def test_long_unicode_source_and_destination_paths(self) -> None:
        assert self.toolchain.ffprobe is not None
        nested = self.root / ("長いフォルダー-" + "a" * 42) / ("nested-" + "b" * 42)
        nested.mkdir(parents=True)
        source = nested / ("源-" + "c" * 32 + ".mkv")
        output = nested / ("出力-" + "d" * 30 + ".mp4")
        self._make_ffv1(source)
        plan = build_remux_plan(probe_media(self.toolchain.ffprobe, source), output, "mp4", "av")
        result = RemuxEngine(self.toolchain).run(plan)
        self.assertTrue(result.verification.passed)
        self.assertEqual(result.output_probe.video_streams[0].frame_count, 25)

    def test_incompatible_attachment_is_rejected_during_strict_planning(self) -> None:
        assert self.toolchain.ffprobe is not None
        video = self.root / "video.mkv"
        source = self.root / "with-attachment.mkv"
        attachment = self.root / "note.txt"
        output = self.root / "should-not-exist.mp4"
        self._make_ffv1(video)
        attachment.write_text("attachment", encoding="utf-8")
        result = self._run_ffmpeg(
            [
                "-i",
                str(video),
                "-map",
                "0",
                "-c",
                "copy",
                "-attach",
                str(attachment),
                "-metadata:s:t",
                "mimetype=text/plain",
                str(source),
            ]
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        with self.assertRaisesRegex(PlanError, "All compatible streams"):
            build_remux_plan(probe_media(self.toolchain.ffprobe, source), output, "mp4", "all")
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".mp4.remux.json").exists())
        self.assertFalse(any("partial" in item.name or "preflight" in item.name for item in self.root.iterdir()))

    def test_compatible_mode_omits_subrip_and_stream_copies_ffv1_aac_to_mp4_and_mov(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "with-subrip.mkv"
        self._make_ffv1_with_subrip(source)
        source_probe = probe_media(self.toolchain.ffprobe, source)
        subtitle_streams = [stream for stream in source_probe.streams if stream.codec_type == "subtitle"]
        self.assertEqual(len(subtitle_streams), 1)
        self.assertEqual(subtitle_streams[0].codec_name, "subrip")

        with self.assertRaisesRegex(PlanError, "without re-encoding"):
            build_remux_plan(source_probe, self.root / "strict.mp4", "mp4", "all")

        for container, extension in (("mp4", ".mp4"), ("mov", ".mov")):
            with self.subTest(container=container):
                output = self.root / f"compatible-{container}{extension}"
                plan = build_remux_plan(source_probe, output, container, "compatible")
                self.assertEqual([stream.codec_type for stream in plan.selected_source_streams], ["video", "audio"])
                self.assertEqual([stream.codec_name for stream in plan.omitted_source_streams], ["subrip"])
                result = RemuxEngine(self.toolchain).run(plan)
                self.assertTrue(result.verification.passed)
                self.assertEqual([stream.codec_type for stream in result.output_probe.streams], ["video", "audio"])
                self.assertEqual(result.output_probe.video_streams[0].codec_name, "ffv1")
                self.assertEqual(result.output_probe.audio_streams[0].codec_name, "aac")
                mapped = [
                    result.command[index + 1]
                    for index, value in enumerate(result.command)
                    if value == "-map"
                ]
                self.assertEqual(mapped, ["0:0", "0:1"])
                report = json.loads(result.report.read_text(encoding="utf-8"))
                self.assertEqual(report["stream_mode"], "compatible")
                self.assertEqual(
                    [stream["codec_name"] for stream in report["stream_selection"]["omitted_source_streams"]],
                    ["subrip"],
                )
                self.assertTrue(report["stream_selection"]["omissions_are_intentional"])

    def test_compatible_mode_retains_mov_text_in_mp4_and_mov(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "with-mov-text.mp4"
        self._make_mp4_with_mov_text(source)
        source_probe = probe_media(self.toolchain.ffprobe, source)
        self.assertEqual(
            [stream.codec_name for stream in source_probe.streams],
            ["mpeg4", "aac", "mov_text"],
        )
        for container, extension in (("mp4", ".mp4"), ("mov", ".mov")):
            with self.subTest(container=container):
                output = self.root / f"mov-text-{container}{extension}"
                plan = build_remux_plan(source_probe, output, container, "compatible")
                self.assertEqual([stream.index for stream in plan.selected_source_streams], [0, 1, 2])
                self.assertFalse(plan.omitted_source_streams)
                result = RemuxEngine(self.toolchain).run(plan)
                self.assertTrue(result.verification.passed)
                self.assertEqual(
                    [stream.codec_name for stream in result.output_probe.streams],
                    ["mpeg4", "aac", "mov_text"],
                )

    def test_video_only_mode_stream_copies_ffv1_and_removes_audio_and_subtitles(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "video-only-source.mkv"
        self._make_ffv1_with_subrip(source)
        source_probe = probe_media(self.toolchain.ffprobe, source)
        output = self.root / "video-only.mp4"
        plan = build_remux_plan(source_probe, output, "mp4", "video")
        self.assertEqual([stream.codec_type for stream in plan.selected_source_streams], ["video"])
        self.assertEqual(
            [stream.codec_type for stream in plan.omitted_source_streams],
            ["audio", "subtitle"],
        )
        result = RemuxEngine(self.toolchain).run(plan)
        self.assertTrue(result.verification.passed)
        self.assertEqual([stream.codec_type for stream in result.output_probe.streams], ["video"])
        self.assertEqual(result.output_probe.video_streams[0].codec_name, "ffv1")
        mapped = [
            result.command[index + 1]
            for index, value in enumerate(result.command)
            if value == "-map"
        ]
        self.assertEqual(mapped, ["0:v?"])
        self.assertEqual(result.command[result.command.index("-c") + 1], "copy")
        report = json.loads(result.report.read_text(encoding="utf-8"))
        self.assertEqual(report["stream_mode"], "video")
        self.assertEqual(
            [stream["codec_type"] for stream in report["stream_selection"]["omitted_source_streams"]],
            ["audio", "subtitle"],
        )
        self.assertTrue(report["stream_selection"]["omissions_are_intentional"])

    def test_destination_appearing_during_run_is_not_overwritten(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "source.mkv"
        output = self.root / "claimed-destination.mp4"
        self._make_ffv1(source)
        plan = build_remux_plan(probe_media(self.toolchain.ffprobe, source), output, "mp4", "av")

        def claim_destination(status: str) -> None:
            if status == "Publishing verified output…":
                output.write_bytes(b"user-created-during-remux")

        with self.assertRaisesRegex(RemuxError, "appeared while remuxing"):
            RemuxEngine(self.toolchain).run(plan, on_status=claim_destination)
        self.assertEqual(output.read_bytes(), b"user-created-during-remux")
        self.assertFalse(output.with_suffix(".mp4.remux.json").exists())
        self.assertFalse(any("partial" in item.name or "preflight" in item.name for item in self.root.iterdir()))

    def test_cancel_before_full_copy_publishes_nothing(self) -> None:
        assert self.toolchain.ffprobe is not None
        source = self.root / "source.mkv"
        output = self.root / "canceled.mp4"
        self._make_ffv1(source)
        plan = build_remux_plan(probe_media(self.toolchain.ffprobe, source), output, "mp4", "av")
        cancel = threading.Event()

        def cancel_at_full_copy(status: str) -> None:
            if status.startswith("Stream-copying"):
                cancel.set()

        with self.assertRaises(RemuxCancelled):
            RemuxEngine(self.toolchain).run(plan, cancel_event=cancel, on_status=cancel_at_full_copy)
        self.assertFalse(output.exists())
        self.assertFalse(output.with_suffix(".mp4.remux.json").exists())
        self.assertFalse(any("partial" in item.name or "preflight" in item.name for item in self.root.iterdir()))


if __name__ == "__main__":
    unittest.main()
