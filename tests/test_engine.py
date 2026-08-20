from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import MethodType

from stream_copy_remuxer.engine import RemuxCancelled, RemuxEngine
from stream_copy_remuxer.models import Toolchain
from stream_copy_remuxer.planning import build_remux_plan

from .helpers import audio_stream, make_probe, subtitle_stream, video_stream


class EngineCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="remux-engine-test-")
        self.root = Path(self.temporary.name)
        self.source = self.root / "source & unicode 測試.mkv"
        self.source.write_bytes(b"source media placeholder")
        executable = Path(__file__).resolve()
        self.toolchain = Toolchain(executable, executable, "test", "test", "test")
        self.engine = RemuxEngine(self.toolchain)
        self.plan = build_remux_plan(make_probe(self.source), self.root / "output.mp4", "mp4", "av")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_command_uses_stream_copy_and_explicit_argument_paths(self) -> None:
        command = self.engine.build_command(self.plan, self.plan.partial_output)
        self.assertIn(str(self.source), command)
        codec_position = command.index("-c")
        self.assertEqual(command[codec_position + 1], "copy")
        self.assertIn("0:v?", command)
        self.assertIn("0:a?", command)
        self.assertNotIn("shell=True", command)
        analysis_position = command.index("-analyzeduration")
        input_position = command.index("-i")
        self.assertLess(analysis_position, input_position)
        self.assertEqual(command[analysis_position + 1], "10000000")

    def test_ffv1_mp4_is_finalized_not_fragmented_or_faststart(self) -> None:
        command = self.engine.build_command(self.plan, self.plan.partial_output)
        joined = " ".join(command).lower()
        self.assertIn("-tag:v:0 ffv1", joined)
        self.assertNotIn("movflags", joined)
        self.assertNotIn("frag_", joined)
        self.assertNotIn("faststart", joined)
        self.assertEqual(command[command.index("-f") + 1], "mp4")

    def test_all_stream_mode_maps_every_stream(self) -> None:
        plan = build_remux_plan(make_probe(self.source), self.root / "all.mkv", "mkv", "all")
        command = self.engine.build_command(plan, plan.partial_output)
        map_positions = [index for index, value in enumerate(command) if value == "-map"]
        self.assertEqual(len(map_positions), 1)
        self.assertEqual(command[map_positions[0] + 1], "0")

    def test_video_only_mode_maps_video_and_uses_stream_copy(self) -> None:
        plan = build_remux_plan(make_probe(self.source), self.root / "video-only.mp4", "mp4", "video")
        command = self.engine.build_command(plan, plan.partial_output)
        mapped = [command[index + 1] for index, value in enumerate(command) if value == "-map"]
        self.assertEqual(mapped, ["0:v?"])
        self.assertNotIn("0:a?", command)
        self.assertEqual(command[command.index("-c") + 1], "copy")

    def test_compatible_mode_maps_exact_supported_stream_indexes(self) -> None:
        probe = make_probe(
            self.source,
            streams=(
                video_stream(index=0),
                audio_stream(index=1),
                subtitle_stream(index=2, codec="subrip"),
                subtitle_stream(index=4, codec="mov_text", title="Supported"),
            ),
        )
        plan = build_remux_plan(probe, self.root / "compatible.mp4", "mp4", "compatible")
        command = self.engine.build_command(plan, plan.partial_output)
        mapped = [command[index + 1] for index, value in enumerate(command) if value == "-map"]
        self.assertEqual(mapped, ["0:0", "0:1", "0:4"])
        self.assertNotIn("0:2", mapped)
        self.assertNotIn("0", mapped)
        self.assertEqual(command[command.index("-c") + 1], "copy")

    def test_cancellation_removes_application_temporary_file(self) -> None:
        cancel_event = threading.Event()

        def canceled_run(_engine: RemuxEngine, command: tuple[str, ...], **_kwargs: object) -> object:
            Path(command[-1]).write_bytes(b"partial")
            cancel_event.set()
            raise RemuxCancelled("test cancellation")

        self.engine._run_process = MethodType(canceled_run, self.engine)  # type: ignore[method-assign]
        with self.assertRaises(RemuxCancelled):
            self.engine.run(self.plan, cancel_event=cancel_event)
        self.assertFalse(self.plan.partial_output.exists())
        self.assertFalse(self.plan.preflight_output.exists())
        self.assertFalse(self.plan.output.exists())

    def test_source_changed_after_inspection_is_rejected_before_ffmpeg(self) -> None:
        original = self.source.stat()
        os.utime(
            self.source,
            ns=(original.st_atime_ns, original.st_mtime_ns + 10_000_000),
        )
        with self.assertRaisesRegex(Exception, "changed after it was inspected"):
            self.engine.run(self.plan)
        self.assertFalse(self.plan.output.exists())
        self.assertFalse(self.plan.partial_output.exists())


if __name__ == "__main__":
    unittest.main()
