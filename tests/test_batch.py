from __future__ import annotations

import shutil
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from stream_copy_remuxer.batch import (
    BatchItem,
    allocate_output_paths,
    codec_summary,
    ensure_batch_space,
    input_container_summary,
    run_batch_plans,
    unique_existing_files,
)
from stream_copy_remuxer.engine import RemuxCancelled
from stream_copy_remuxer.models import RemuxResult, Toolchain
from stream_copy_remuxer.planning import PlanError, build_remux_plan

from .helpers import make_probe


class BatchModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="remux-batch-test-")
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_unique_existing_files_rejects_duplicates_and_nonfiles(self) -> None:
        first = self.root / "first.avi"
        second = self.root / "second.ts"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        accepted, duplicates, rejected = unique_existing_files(
            (first, first, second, self.root / "missing.webm"),
            existing_paths=(second,),
        )
        self.assertEqual(accepted, (first.resolve(),))
        self.assertEqual(len(duplicates), 2)
        self.assertEqual(len(rejected), 1)

    def test_output_allocation_avoids_same_stem_beside_source_collisions(self) -> None:
        source_folder = self.root / "sources"
        source_folder.mkdir()
        first = source_folder / "clip.avi"
        second = source_folder / "clip.ts"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        items = (
            BatchItem("one", first, "mp4"),
            BatchItem("two", second, "mp4"),
        )
        allocated = allocate_output_paths(items)
        self.assertEqual(allocated["one"], source_folder / "clip_remux.mp4")
        self.assertEqual(allocated["two"], source_folder / "clip_remux_2.mp4")

    def test_output_allocation_uses_common_destination_and_avoids_collisions(self) -> None:
        first_folder = self.root / "first-source"
        second_folder = self.root / "second-source"
        destination = self.root / "destination"
        first_folder.mkdir()
        second_folder.mkdir()
        destination.mkdir()
        first = first_folder / "clip.avi"
        second = second_folder / "clip.ts"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        allocated = allocate_output_paths(
            (BatchItem("one", first, "mp4"), BatchItem("two", second, "mp4")),
            output_directory=destination,
        )
        self.assertEqual(allocated["one"], destination / "clip_remux.mp4")
        self.assertEqual(allocated["two"], destination / "clip_remux_2.mp4")

    def test_output_allocation_rejects_missing_common_destination(self) -> None:
        source = self.root / "source.avi"
        source.write_bytes(b"source")
        with self.assertRaisesRegex(PlanError, "destination folder does not exist"):
            allocate_output_paths(
                (BatchItem("one", source, "mp4"),),
                output_directory=self.root / "missing",
            )

    def test_output_allocation_respects_per_row_container(self) -> None:
        first = self.root / "one.rmvb"
        second = self.root / "two.webm"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        allocated = allocate_output_paths(
            (BatchItem("one", first, "mov"), BatchItem("two", second, "mkv"))
        )
        self.assertEqual(allocated["one"].suffix, ".mov")
        self.assertEqual(allocated["two"].suffix, ".mkv")

    def test_container_and_codec_summaries_use_probe_data(self) -> None:
        source = self.root / "movie.avi"
        source.write_bytes(b"media")
        probe = replace(
            make_probe(source),
            format_name="avi",
            format_long_name="AVI (Audio Video Interleaved)",
        )
        self.assertEqual(input_container_summary(probe), "AVI (Audio Video Interleaved) (AVI)")
        self.assertEqual(codec_summary(probe, "video"), "FFV1")
        self.assertEqual(codec_summary(probe, "audio"), "AAC")

    def test_batch_space_aggregates_outputs_on_one_volume(self) -> None:
        first = self.root / "first.mkv"
        second = self.root / "second.mkv"
        first.write_bytes(b"a")
        second.write_bytes(b"b")
        plans = (
            build_remux_plan(make_probe(first, size=1000), self.root / "first.mp4", "mp4", "av", enforce_space=False),
            build_remux_plan(
                make_probe(second, size=2000),
                self.root / "second-output.mkv",
                "mkv",
                "av",
                enforce_space=False,
            ),
        )
        disk = shutil._ntuple_diskusage(total=2_000_000_000, used=0, free=2_000_000_000)
        with patch("stream_copy_remuxer.batch.shutil.disk_usage", return_value=disk):
            requirements = ensure_batch_space(plans)
        self.assertEqual(len(requirements), 1)
        self.assertEqual(requirements[0].item_count, 2)
        self.assertEqual(requirements[0].required_bytes, 3000 + 256 * 1024 * 1024)

    def test_batch_space_rejects_insufficient_aggregate_space(self) -> None:
        source = self.root / "source.mkv"
        source.write_bytes(b"source")
        plan = build_remux_plan(
            make_probe(source, size=500_000_000),
            self.root / "output.mp4",
            "mp4",
            "av",
            enforce_space=False,
        )
        disk = shutil._ntuple_diskusage(total=1000, used=900, free=100)
        with patch("stream_copy_remuxer.batch.shutil.disk_usage", return_value=disk):
            with self.assertRaisesRegex(PlanError, "enough free space for this batch"):
                ensure_batch_space((plan,))

    def test_batch_runner_continues_after_one_file_fails(self) -> None:
        first = self.root / "first.mkv"
        second = self.root / "second.mkv"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        plans = (
            ("first", build_remux_plan(make_probe(first), self.root / "first.mp4", "mp4", "av", enforce_space=False)),
            ("second", build_remux_plan(make_probe(second), self.root / "second.mp4", "mp4", "av", enforce_space=False)),
        )
        result = Mock(spec=RemuxResult)
        calls: list[str] = []
        finished: list[tuple[str, bool, bool]] = []

        class FakeEngine:
            def run(self, plan: object, **_kwargs: object) -> RemuxResult:
                output_name = Path(getattr(plan, "output")).name
                calls.append(output_name)
                if output_name == "first.mp4":
                    raise RuntimeError("intentional first-file failure")
                return result

        summary = run_batch_plans(
            Toolchain(Path(__file__), Path(__file__), "test"),
            plans,
            cancel_event=threading.Event(),
            engine_factory=lambda _toolchain: FakeEngine(),  # type: ignore[arg-type]
            on_item_finished=lambda item_id, item_result, error: finished.append(
                (item_id, item_result is not None, error is not None)
            ),
        )
        self.assertEqual(calls, ["first.mp4", "second.mp4"])
        self.assertEqual(summary.completed, 1)
        self.assertEqual(summary.failed, 1)
        self.assertFalse(summary.canceled)
        self.assertEqual(finished, [("first", False, True), ("second", True, False)])

    def test_batch_runner_stops_after_cancellation(self) -> None:
        first = self.root / "first.mkv"
        second = self.root / "second.mkv"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        plans = (
            ("first", build_remux_plan(make_probe(first), self.root / "first.mp4", "mp4", "av", enforce_space=False)),
            ("second", build_remux_plan(make_probe(second), self.root / "second.mp4", "mp4", "av", enforce_space=False)),
        )
        calls: list[str] = []

        class CancelingEngine:
            def run(self, plan: object, **_kwargs: object) -> RemuxResult:
                calls.append(Path(getattr(plan, "output")).name)
                raise RemuxCancelled("intentional cancellation")

        summary = run_batch_plans(
            Toolchain(Path(__file__), Path(__file__), "test"),
            plans,
            cancel_event=threading.Event(),
            engine_factory=lambda _toolchain: CancelingEngine(),  # type: ignore[arg-type]
        )
        self.assertEqual(calls, ["first.mp4"])
        self.assertTrue(summary.canceled)
        self.assertEqual(summary.completed, 0)
        self.assertEqual(summary.failed, 0)


if __name__ == "__main__":
    unittest.main()
