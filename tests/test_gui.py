from __future__ import annotations

import gc
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from stream_copy_remuxer.batch import STATE_COMPLETE
from stream_copy_remuxer.drop_support import create_root
from stream_copy_remuxer.ffmpeg_install import FFmpegRelease
from stream_copy_remuxer.gui import (
    DESCRIPTION,
    STREAM_MODE_LABELS,
    StreamCopyRemuxerApp,
    open_folder_in_file_manager,
    run_layout_scaling_self_test,
    run_withdrawn_gui_self_test,
)
from stream_copy_remuxer.tools import discover_toolchain
from stream_copy_remuxer.models import Toolchain
from stream_copy_remuxer.planning import build_remux_plan

from .helpers import make_probe


class GuiTests(unittest.TestCase):
    def test_windows_folder_opener_passes_exact_existing_directory_to_shell(self) -> None:
        with tempfile.TemporaryDirectory(prefix="remux-folder-opener-test-") as folder:
            directory = Path(folder) / "输出 folder & complete"
            directory.mkdir()
            with patch("stream_copy_remuxer.gui.os.startfile", create=True) as startfile:
                open_folder_in_file_manager(directory)
            startfile.assert_called_once_with(str(directory))
            with self.assertRaisesRegex(FileNotFoundError, "no longer exists"):
                open_folder_in_file_manager(directory / "missing")

    def test_withdrawn_gui_constructs_and_processes_events(self) -> None:
        result = run_withdrawn_gui_self_test(discover_toolchain())
        self.assertTrue(result["passed"], result)

    def test_layout_is_readable_at_common_windows_scaling_levels(self) -> None:
        result = run_layout_scaling_self_test(discover_toolchain())
        self.assertTrue(result["passed"], result)

    def test_selected_rows_receive_dropdown_container_and_delete_removes_only_rows(self) -> None:
        with tempfile.TemporaryDirectory(prefix="remux-gui-queue-test-") as folder:
            first = Path(folder) / "first.avi"
            second = Path(folder) / "second.rmvb"
            first.write_bytes(b"not real media one")
            second.write_bytes(b"not real media two")
            root = create_root()
            root.withdraw()
            app = StreamCopyRemuxerApp(root, discover_toolchain(), check_ffmpeg_updates=False)
            app.add_files((first, second))
            item_ids = tuple(app.items)
            self.assertEqual(len(item_ids), 2)
            self.assertTrue(all(item.container_key == "mp4" for item in app.items.values()))
            app.queue_tree.selection_set(item_ids)
            app.container_var.set("MOV")
            app._container_changed()
            self.assertTrue(all(item.container_key == "mov" for item in app.items.values()))
            self.assertTrue(app.queue_tree.bind("<Delete>"))
            class ActiveWorker:
                @staticmethod
                def is_alive() -> bool:
                    return True

            app._worker = ActiveWorker()  # type: ignore[assignment]
            app.remove_selected()
            self.assertEqual(len(app.items), 2)
            app._worker = None
            self.assertTrue(app._refresh_planned_outputs())
            self.assertTrue(
                all(
                    item.output is not None
                    and item.output.parent == item.source.parent
                    and item.output.stem.startswith(item.source.stem + "_remux")
                    for item in app.items.values()
                )
            )
            completed_output = app.items[item_ids[0]].output
            self.assertIsNotNone(completed_output)
            app.items[item_ids[0]].state = STATE_COMPLETE
            app.items[item_ids[0]].detail = "Complete — verified"
            destination = Path(folder) / "batch output"
            destination.mkdir()
            app.destination_var.set(str(destination))
            app._destination_changed()
            self.assertEqual(app.items[item_ids[0]].output, completed_output)
            self.assertEqual(app.items[item_ids[1]].output.parent, destination)
            confirmation_plan = build_remux_plan(
                make_probe(first),
                destination / "first_remux.mov",
                "mov",
                "av",
                enforce_space=False,
            )
            self.assertIn(
                f"Destination: {destination.resolve(strict=False)}",
                app._confirmation_text(((item_ids[0], confirmation_plan),)),
            )
            app.clear_destination()
            self.assertEqual(app.destination_var.get(), "")
            self.assertTrue(
                all(item.output is not None and item.output.parent == item.source.parent for item in app.items.values())
            )
            app.destination_var.set(str(Path(folder) / "missing destination"))
            self.assertFalse(app._refresh_planned_outputs())
            self.assertIn("destination folder does not exist", app._planning_error)
            app.destination_var.set("")
            self.assertTrue(app._refresh_planned_outputs())
            app._set_running(True)
            self.assertEqual(str(app.destination_entry.cget("state")), "disabled")
            self.assertEqual(str(app.destination_browse_button.cget("state")), "disabled")
            self.assertEqual(str(app.destination_clear_button.cget("state")), "disabled")
            app._set_running(False)
            self.assertNotIn("output", tuple(app.queue_tree.cget("columns")))
            self.assertIn("compatibility", tuple(app.queue_tree.cget("columns")))
            self.assertTrue(bool(app.queue_tree.column("status", "stretch")))
            self.assertGreaterEqual(
                int(app.queue_tree.column("status", "width")),
                int(app._tree_font.measure("Complete — verified")) + 24,
            )
            app.remove_selected()
            self.assertFalse(app.items)
            self.assertTrue(first.is_file())
            self.assertTrue(second.is_file())
            app.close_for_test()
            del app
            del root
            gc.collect()

    def test_show_output_opens_selected_verified_outputs_exact_parent_folder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="remux-show-output-test-") as folder:
            root_path = Path(folder)
            source = root_path / "source.mkv"
            source.write_bytes(b"source")
            selected_folder = root_path / "选择 output & finished"
            selected_folder.mkdir()
            selected_output = selected_folder / "selected_remux.mp4"
            selected_output.write_bytes(b"output")
            latest_folder = root_path / "latest"
            latest_folder.mkdir()
            latest_output = latest_folder / "latest_remux.mp4"
            latest_output.write_bytes(b"latest")
            opened: list[Path] = []
            root = create_root()
            root.withdraw()
            app = StreamCopyRemuxerApp(
                root,
                discover_toolchain(),
                check_ffmpeg_updates=False,
                folder_opener=opened.append,
            )
            app.add_files((source,))
            item_id = next(iter(app.items))
            app.items[item_id].result = SimpleNamespace(output=selected_output)  # type: ignore[assignment]
            app.last_results = [SimpleNamespace(output=latest_output)]  # type: ignore[list-item]
            app.queue_tree.selection_set(item_id)
            app.show_output()
            self.assertEqual(opened, [selected_folder])

            app.queue_tree.selection_remove(item_id)
            app.show_output()
            self.assertEqual(opened, [selected_folder, latest_folder])

            app.queue_tree.selection_set(item_id)
            selected_output.unlink()
            with patch("stream_copy_remuxer.gui.messagebox.showerror") as showerror:
                app.show_output()
            showerror.assert_called_once()
            self.assertEqual(opened, [selected_folder, latest_folder])
            app.close_for_test()
            del app
            del root
            gc.collect()

    def test_exact_requested_description(self) -> None:
        self.assertEqual(
            DESCRIPTION,
            "Certain software such as Topaz Video are more or less compatible with different containers. "
            "This app allows changing containers without re-encoding the video or audio.",
        )

    def test_stream_dropdown_describes_included_and_excluded_content(self) -> None:
        labels = tuple(STREAM_MODE_LABELS)
        self.assertIn("excludes subtitle, attachment, and data", labels[0])
        self.assertIn("keeps metadata and chapters", labels[0])
        self.assertIn("Video only", labels[1])
        self.assertIn("excludes audio", labels[1])
        self.assertIn("All compatible streams", labels[2])
        self.assertIn("omits only extras", labels[2])
        self.assertIn("strict", labels[3])
        self.assertIn("omits nothing", labels[3])
        self.assertEqual(tuple(STREAM_MODE_LABELS.values()), ("av", "video", "compatible", "all"))

    def test_details_log_is_five_rows_taller(self) -> None:
        root = create_root()
        root.withdraw()
        app = StreamCopyRemuxerApp(root, discover_toolchain(), check_ffmpeg_updates=False)
        self.assertEqual(int(app.log_text.cget("height")), 10)
        app.close_for_test()
        del app
        del root
        gc.collect()

    def test_install_action_appears_for_missing_or_uncomparable_ffmpeg(self) -> None:
        root = create_root()
        root.withdraw()
        toolchain = Toolchain(
            Path("ffmpeg.exe"),
            Path("ffprobe.exe"),
            "System",
            "ffmpeg version 2026-08-06-git-test",
            "ffprobe version 2026-08-06-git-test",
        )
        app = StreamCopyRemuxerApp(root, toolchain, check_ffmpeg_updates=False)
        app._release_info = FFmpegRelease("9.0.1", "a" * 64)
        app._update_tool_label()
        root.update_idletasks()
        self.assertEqual(str(app.install_ffmpeg_button.cget("text")), "Install FFmpeg 9.0.1")
        self.assertTrue(app.install_ffmpeg_button.winfo_ismapped() or app.install_ffmpeg_button.winfo_manager())
        app.close_for_test()
        del app
        del root
        gc.collect()

    def test_closing_state_still_drains_worker_completion_events(self) -> None:
        root = create_root()
        root.withdraw()
        app = StreamCopyRemuxerApp(root, discover_toolchain(), check_ffmpeg_updates=False)
        destroyed = {"value": False}
        original_destroy = app._destroy
        app._destroy = lambda: destroyed.__setitem__("value", True)  # type: ignore[method-assign]
        app._closing = True
        app._marshal(app._batch_finished, 0, 0, True, 1)
        app._drain_ui_events()
        self.assertTrue(destroyed["value"])
        app._closing = False
        app._destroy = original_destroy  # type: ignore[method-assign]
        app.close_for_test()
        del app
        del root
        gc.collect()


if __name__ == "__main__":
    unittest.main()
