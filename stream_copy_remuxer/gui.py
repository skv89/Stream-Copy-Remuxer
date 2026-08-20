from __future__ import annotations

import gc
import logging
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import Counter
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import __version__
from .batch import (
    STATE_CANCELED,
    STATE_COMPLETE,
    STATE_FAILED,
    STATE_INSPECTING,
    STATE_INVALID,
    STATE_PROCESSING,
    STATE_QUEUED,
    STATE_READY,
    BatchItem,
    allocate_output_paths,
    codec_summary,
    ensure_batch_space,
    input_container_summary,
    run_batch_plans,
    unique_existing_files,
)
from .drop_support import FileDropRegistration, create_root, register_file_drop
from .engine import RemuxCancelled
from .ffmpeg_install import (
    FFmpegInstallCancelled,
    FFmpegRelease,
    fetch_current_release,
    install_release,
    installed_version_is_older,
)
from .models import CONTAINER_PROFILES, MediaProbe, ProgressUpdate, RemuxPlan, RemuxResult, Toolchain
from .planning import PlanError, build_remux_plan, compatibility_notes, describe_streams
from .probe import probe_media
from .tools import application_root, concise_ffmpeg_version, discover_toolchain


DESCRIPTION = (
    "Certain software such as Topaz Video are more or less compatible with different containers. "
    "This app allows changing containers without re-encoding the video or audio."
)

CONTAINER_LABELS = {profile.label: key for key, profile in CONTAINER_PROFILES.items()}
STREAM_MODE_LABELS = {
    "Video + audio — excludes subtitle, attachment, and data streams; keeps metadata and chapters": "av",
    "Video only — excludes audio, subtitle, attachment, and data streams; keeps metadata and chapters": "video",
    "All compatible streams — omits only extras MP4/MOV cannot copy; MKV keeps every stream": "compatible",
    "All source streams (strict) — omits nothing; incompatible MP4/MOV batches are blocked": "all",
}
STREAM_MODE_CONFIRMATION_LABELS = {
    "av": "video + audio",
    "video": "video only (audio and every non-video stream are omitted)",
    "compatible": "all compatible streams (disclosed incompatible extras are omitted)",
    "all": "all source streams (strict; nothing omitted)",
}
COMMON_MEDIA_PATTERN = " ".join(
    (
        "*.mkv", "*.mp4", "*.mov", "*.avi", "*.rm", "*.rmvb", "*.ts", "*.mts",
        "*.m2ts", "*.webm", "*.flv", "*.f4v", "*.wmv", "*.asf", "*.mpg", "*.mpeg",
        "*.mpe", "*.m1v", "*.m2v", "*.vob", "*.ogv", "*.ogg", "*.3gp", "*.3g2",
        "*.mxf", "*.dv", "*.nut", "*.y4m", "*.m4v",
    )
)
STATUS_WIDTH_SAMPLE = "Internal batch error — retryable"
STATUS_MINIMUM_SAMPLE = "Complete — verified"

FolderOpener = Callable[[Path], None]


def open_folder_in_file_manager(directory: Path) -> None:
    """Open one existing directory through the Windows shell without reparsing a file path."""
    directory = Path(directory)
    if not directory.is_dir():
        raise FileNotFoundError(f"The output folder no longer exists: {directory}")
    startfile = getattr(os, "startfile", None)
    if not callable(startfile):
        raise OSError("The Windows folder-opening API is unavailable in this runtime.")
    startfile(str(directory))


def format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    amount = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    for unit in units:
        if abs(amount) < 1024.0 or unit == units[-1]:
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.2f} {unit}"
        amount /= 1024.0
    return f"{value} B"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    whole = max(0, int(round(seconds)))
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:d}:{minutes:02d}:{secs:02d}"


def _probe_worker_loop(
    tasks: queue.Queue[tuple[int, str, Path, Path] | None],
    results: queue.Queue[tuple[str, int, str, object]],
) -> None:
    """Probe without retaining the Tk application on this background thread."""
    while True:
        task = tasks.get()
        if task is None:
            return
        generation, item_id, path, ffprobe = task
        try:
            media = probe_media(ffprobe, path)
        except Exception as exc:
            results.put(("failed", generation, item_id, exc))
        else:
            results.put(("succeeded", generation, item_id, media))


class StreamCopyRemuxerApp:
    def __init__(
        self,
        root: tk.Tk,
        toolchain: Toolchain,
        *,
        start_path: Path | None = None,
        check_ffmpeg_updates: bool = True,
        folder_opener: FolderOpener = open_folder_in_file_manager,
    ) -> None:
        self.root = root
        self.toolchain = toolchain
        self.items: dict[str, BatchItem] = {}
        self._item_order: list[str] = []
        self._item_counter = 0
        self._probe_generation = 1
        self._probe_tasks: queue.Queue[tuple[int, str, Path, Path] | None] = queue.Queue()
        self._probe_results: queue.Queue[tuple[str, int, str, object]] = queue.Queue()
        self._ui_events: queue.Queue[tuple[object, tuple[object, ...]]] = queue.Queue()
        self._ui_after_id: str | None = None
        self._worker: threading.Thread | None = None
        self._cancel_event: threading.Event | None = None
        self._release_thread: threading.Thread | None = None
        self._install_thread: threading.Thread | None = None
        self._install_cancel_event: threading.Event | None = None
        self._installing = False
        self._release_info: FFmpegRelease | None = None
        self._release_check_error = ""
        self._pending_install = False
        self._closing = False
        self._current_item_id: str | None = None
        self._default_container_key = "mp4"
        self._planning_error = ""
        self._folder_opener = folder_opener
        self.last_results: list[RemuxResult] = []

        self.description_var = tk.StringVar(value=DESCRIPTION)
        self.container_var = tk.StringVar(value="MP4")
        self.stream_mode_var = tk.StringVar(value=next(iter(STREAM_MODE_LABELS)))
        self.destination_var = tk.StringVar(value="")
        self.queue_hint_var = tk.StringVar(value="Drag and drop media files here, or use Add files")
        self.tool_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Ready — add media files")
        self.metrics_var = tk.StringVar(value="")

        self._configure_window()
        self._build_widgets()
        self._update_tool_label()
        self._set_running(False)
        self._ui_after_id = self.root.after(20, self._drain_ui_events)
        self._probe_thread = threading.Thread(
            target=_probe_worker_loop,
            args=(self._probe_tasks, self._probe_results),
            name="batch-probe-worker",
            daemon=True,
        )
        self._probe_thread.start()
        self.file_drop: FileDropRegistration = register_file_drop(self.root, self._files_dropped)
        if not self.file_drop.active:
            self.queue_hint_var.set("Use Add files (drag-and-drop could not be initialized).")
            if self.file_drop.error:
                self._append_log(f"Drag-and-drop unavailable: {self.file_drop.error}")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if check_ffmpeg_updates:
            self.root.after(100, self._start_release_check)
        if start_path is not None:
            self.root.after(100, lambda: self.add_files((start_path,)))

    def _configure_window(self) -> None:
        self.root.title(f"Stream Copy Remuxer {__version__}")
        self.root.minsize(1260, 680)
        self.root.geometry("1500x820")
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Subtitle.TLabel", font=("Segoe UI", 9), foreground="#333333")
        style.configure("Section.TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Start.TButton", font=("Segoe UI", 10, "bold"))
        self._tree_font = tkfont.Font(root=self.root, family="Segoe UI", size=10)
        self._heading_font = tkfont.Font(root=self.root, family="Segoe UI", size=10, weight="bold")
        row_height = max(30, int(self._tree_font.metrics("linespace")) + 12)
        style.configure("Batch.Treeview", font=self._tree_font, rowheight=row_height)
        style.configure("Batch.Treeview.Heading", font=self._heading_font)

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        outer.rowconfigure(4, weight=0)
        self.outer_frame = outer

        self.description_label = ttk.Label(
            outer,
            textvariable=self.description_var,
            style="Subtitle.TLabel",
            justify="left",
        )
        self.description_label.grid(row=0, column=0, sticky="w", pady=(0, 12))

        queue_frame = ttk.LabelFrame(outer, text="Files", style="Section.TLabelframe")
        queue_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        queue_frame.rowconfigure(1, weight=1)
        queue_frame.columnconfigure(0, weight=1)

        queue_toolbar = ttk.Frame(queue_frame)
        queue_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 6))
        queue_toolbar.columnconfigure(3, weight=1)
        self.add_button = ttk.Button(queue_toolbar, text="Add files", command=self.browse_files)
        self.add_button.grid(row=0, column=0, padx=(0, 6))
        self.remove_button = ttk.Button(queue_toolbar, text="Remove selected", command=self.remove_selected)
        self.remove_button.grid(row=0, column=1, padx=6)
        self.clear_button = ttk.Button(queue_toolbar, text="Clear queue", command=self.clear_queue)
        self.clear_button.grid(row=0, column=2, padx=6)
        ttk.Label(queue_toolbar, textvariable=self.queue_hint_var, foreground="#555555").grid(
            row=0, column=3, sticky="e", padx=(12, 0)
        )

        columns = (
            "source",
            "input_container",
            "video",
            "audio",
            "output_container",
            "compatibility",
            "status",
        )
        self.queue_tree = ttk.Treeview(
            queue_frame,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=10,
            style="Batch.Treeview",
        )
        headings = {
            "source": "Source file",
            "input_container": "Input container",
            "video": "Video encoding",
            "audio": "Audio encoding",
            "output_container": "Output container",
            "compatibility": "Compatibility",
            "status": "Status",
        }
        status_width = max(240, int(self._tree_font.measure(STATUS_WIDTH_SAMPLE)) + 32)
        status_minimum = max(180, int(self._tree_font.measure(STATUS_MINIMUM_SAMPLE)) + 24)
        widths = {
            "source": 360,
            "input_container": 190,
            "video": 135,
            "audio": 135,
            "output_container": 125,
            "compatibility": 430,
            "status": status_width,
        }
        minimum_widths = {
            "source": 220,
            "input_container": 150,
            "video": 110,
            "audio": 110,
            "output_container": 115,
            "compatibility": 260,
            "status": status_minimum,
        }
        heading_measure = tkfont.Font(root=self.root, family="Segoe UI", size=10, weight="bold")
        for column in columns:
            self.queue_tree.heading(column, text=headings[column])
            readable_width = max(widths[column], int(heading_measure.measure(headings[column])) + 32)
            self.queue_tree.column(
                column,
                width=readable_width,
                minwidth=max(minimum_widths[column], int(heading_measure.measure(headings[column])) + 20),
                stretch=column in {"source", "compatibility", "status"},
            )
        self._queue_headings = headings
        self.queue_tree.grid(row=1, column=0, sticky="nsew", padx=(8, 0), pady=(0, 8))
        queue_scroll_y = ttk.Scrollbar(queue_frame, orient="vertical", command=self.queue_tree.yview)
        queue_scroll_y.grid(row=1, column=1, sticky="ns", padx=(0, 8), pady=(0, 8))
        queue_scroll_x = ttk.Scrollbar(queue_frame, orient="horizontal", command=self.queue_tree.xview)
        queue_scroll_x.grid(row=2, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.queue_tree.configure(yscrollcommand=queue_scroll_y.set, xscrollcommand=queue_scroll_x.set)
        self.queue_tree.tag_configure(STATE_COMPLETE, foreground="#126b23")
        self.queue_tree.tag_configure(STATE_FAILED, foreground="#a00000")
        self.queue_tree.tag_configure(STATE_INVALID, foreground="#a00000")
        self.queue_tree.tag_configure(STATE_PROCESSING, foreground="#005a9c")
        self.queue_tree.bind("<Delete>", self.remove_selected)
        self.queue_tree.bind("<<TreeviewSelect>>", lambda _event: self._selection_changed())

        settings_frame = ttk.LabelFrame(outer, text="Output settings", style="Section.TLabelframe")
        settings_frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        settings_frame.columnconfigure(2, weight=1)
        ttk.Label(settings_frame, text="Output container for selected/new files:").grid(
            row=0, column=0, sticky="w", padx=(10, 6), pady=(9, 5)
        )
        self.container_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.container_var,
            values=tuple(CONTAINER_LABELS),
            state="readonly",
            width=9,
        )
        self.container_combo.grid(row=0, column=1, sticky="w", pady=(9, 5))
        self.container_combo.bind("<<ComboboxSelected>>", lambda _event: self._container_changed())
        ttk.Label(settings_frame, text="Streams:").grid(row=0, column=3, sticky="e", padx=(16, 6), pady=(9, 5))
        self.stream_combo = ttk.Combobox(
            settings_frame,
            textvariable=self.stream_mode_var,
            values=tuple(STREAM_MODE_LABELS),
            state="readonly",
            width=86,
        )
        self.stream_combo.grid(row=0, column=4, sticky="e", padx=(0, 10), pady=(9, 5))
        self.stream_combo.bind("<<ComboboxSelected>>", lambda _event: self._stream_mode_changed())

        ttk.Label(settings_frame, text="Destination folder (blank = beside each source):").grid(
            row=1, column=0, sticky="w", padx=(10, 6), pady=(4, 9)
        )
        self.destination_entry = ttk.Entry(settings_frame, textvariable=self.destination_var)
        self.destination_entry.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(4, 9))
        self.destination_entry.bind("<Return>", self._destination_changed)
        self.destination_entry.bind("<FocusOut>", self._destination_changed)
        destination_buttons = ttk.Frame(settings_frame)
        destination_buttons.grid(row=1, column=4, sticky="e", padx=(8, 10), pady=(4, 9))
        self.destination_browse_button = ttk.Button(
            destination_buttons,
            text="Browse",
            command=self.browse_destination,
        )
        self.destination_browse_button.grid(row=0, column=0, padx=(0, 6))
        self.destination_clear_button = ttk.Button(
            destination_buttons,
            text="Clear",
            command=self.clear_destination,
        )
        self.destination_clear_button.grid(row=0, column=1)

        progress_frame = ttk.LabelFrame(outer, text="Batch progress", style="Section.TLabelframe")
        progress_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        progress_frame.columnconfigure(0, weight=1)
        ttk.Label(progress_frame, textvariable=self.status_var, style="Status.TLabel").grid(
            row=0, column=0, sticky="w", padx=10, pady=(8, 3)
        )
        self.progress = ttk.Progressbar(progress_frame, mode="determinate", maximum=100)
        self.progress.grid(row=1, column=0, sticky="ew", padx=10, pady=3)
        ttk.Label(progress_frame, textvariable=self.metrics_var).grid(
            row=2, column=0, sticky="w", padx=10, pady=(2, 8)
        )

        details_frame = ttk.LabelFrame(outer, text="Details", style="Section.TLabelframe")
        details_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 10))
        details_frame.rowconfigure(0, weight=1)
        details_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(
            details_frame,
            height=10,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            background="#fbfbfb",
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=8)
        log_scroll = ttk.Scrollbar(details_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns", padx=(0, 10), pady=8)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        footer = ttk.Frame(outer)
        footer.grid(row=5, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        self.tool_label = ttk.Label(footer, textvariable=self.tool_var, foreground="#555555")
        self.tool_label.grid(row=0, column=0, sticky="w")
        self.install_ffmpeg_button = ttk.Button(footer, text="Install FFmpeg", command=self.install_ffmpeg)
        self.install_ffmpeg_button.grid(row=1, column=0, sticky="w", pady=(4, 0))
        button_frame = ttk.Frame(footer)
        button_frame.grid(row=0, column=1, rowspan=2, sticky="e")
        self.show_output_button = ttk.Button(button_frame, text="Show output", command=self.show_output)
        self.show_output_button.grid(row=0, column=0, padx=(0, 6))
        self.cancel_button = ttk.Button(button_frame, text="Cancel batch", command=self.cancel)
        self.cancel_button.grid(row=0, column=1, padx=6)
        self.start_button = ttk.Button(
            button_frame,
            text="Start batch",
            command=self.start,
            style="Start.TButton",
        )
        self.start_button.grid(row=0, column=2, padx=(6, 0))
        self.root.update_idletasks()
        required_width = max(1260, self.description_label.winfo_reqwidth() + 28)
        self.root.minsize(required_width, 680)
        table_width = sum(
            int(self.queue_tree.column(column, "width")) for column in self.queue_tree.cget("columns")
        ) + 80
        available_width = max(required_width, self.root.winfo_screenwidth() - 80)
        initial_width = min(max(1500, required_width, table_width), available_width)
        self.root.geometry(f"{initial_width}x820")

    def _update_tool_label(self) -> None:
        if self.toolchain.ready and self.toolchain.ffmpeg:
            version = concise_ffmpeg_version(self.toolchain)
            update = ""
            if self._release_info is not None:
                older = installed_version_is_older(self.toolchain.ffmpeg_version, self._release_info.version)
                if older is not False:
                    update = f" — FFmpeg {self._release_info.version} available"
            self.tool_var.set(
                f"FFmpeg {version} detected ({self.toolchain.source}) — {self.toolchain.ffmpeg}{update}"
            )
        else:
            self.tool_var.set("FFmpeg and FFprobe were not found. Install the current release to continue.")
        self._update_ffmpeg_action()

    def _update_ffmpeg_action(self) -> None:
        if self._installing:
            self.install_ffmpeg_button.configure(text="Installing FFmpeg…", state="disabled")
            self.install_ffmpeg_button.grid()
            return
        if self._release_thread is not None and self._release_thread.is_alive():
            if not self.toolchain.ready:
                self.install_ffmpeg_button.configure(text="Checking current FFmpeg release…", state="disabled")
                self.install_ffmpeg_button.grid()
            else:
                self.install_ffmpeg_button.grid_remove()
            return
        if self._release_info is None:
            if self.toolchain.ready:
                self.install_ffmpeg_button.grid_remove()
            else:
                self.install_ffmpeg_button.configure(text="Install FFmpeg", state="normal")
                self.install_ffmpeg_button.grid()
            return
        older = (
            installed_version_is_older(self.toolchain.ffmpeg_version, self._release_info.version)
            if self.toolchain.ready
            else True
        )
        if not self.toolchain.ready or older is not False:
            self.install_ffmpeg_button.configure(
                text=f"Install FFmpeg {self._release_info.version}",
                state="normal" if not (self._worker and self._worker.is_alive()) else "disabled",
            )
            self.install_ffmpeg_button.grid()
        else:
            self.install_ffmpeg_button.grid_remove()

    def _start_release_check(self) -> None:
        if self._closing or self._installing:
            return
        if self._release_thread is not None and self._release_thread.is_alive():
            return
        self._release_check_error = ""

        def work() -> None:
            try:
                release = fetch_current_release()
            except Exception as exc:
                self._marshal(self._release_check_finished, None, exc)
            else:
                self._marshal(self._release_check_finished, release, None)

        self._release_thread = threading.Thread(target=work, name="ffmpeg-release-check", daemon=True)
        self._release_thread.start()
        self._update_ffmpeg_action()

    def _release_check_finished(
        self,
        release: FFmpegRelease | None,
        error: Exception | None,
    ) -> None:
        self._release_thread = None
        if release is not None:
            self._release_info = release
            self._release_check_error = ""
            self._append_log(f"Current stable FFmpeg release: {release.version}")
        elif error is not None:
            self._release_check_error = str(error)
            self._append_log(f"Could not check the current FFmpeg release: {error}")
        self._update_tool_label()
        if self._pending_install:
            self._pending_install = False
            if release is None:
                if not self._closing:
                    messagebox.showerror(
                        "Could not check FFmpeg",
                        "The current FFmpeg release could not be checked. Verify the internet connection and try again.\n\n"
                        + self._release_check_error,
                        parent=self.root,
                    )
            elif not self._closing:
                self.root.after_idle(self.install_ffmpeg)

    def install_ffmpeg(self) -> None:
        if self._closing or self._installing or (self._worker and self._worker.is_alive()):
            return
        if self._release_info is None:
            self._pending_install = True
            self.status_var.set("Checking the current stable FFmpeg release…")
            self._start_release_check()
            return
        release = self._release_info
        destination = application_root() / "ffmpeg" / release.version
        if not messagebox.askokcancel(
            f"Install FFmpeg {release.version}",
            f"Download the current FFmpeg Windows release (approximately 110 MB) and install it here?\n\n"
            f"{destination}\n\n"
            "The complete download will be verified against the provider's SHA-256 checksum before extraction.",
            parent=self.root,
            icon="info",
        ):
            return
        self._install_cancel_event = threading.Event()
        self._installing = True
        self.status_var.set(f"Downloading FFmpeg {release.version}…")
        self.metrics_var.set("")
        self._update_ffmpeg_action()
        self._update_controls()

        def progress(downloaded: int, total: int | None) -> None:
            self._marshal(self._ffmpeg_install_progress, downloaded, total)

        def work() -> None:
            try:
                ffmpeg = install_release(
                    release,
                    application_root(),
                    on_progress=progress,
                    cancel_event=self._install_cancel_event,
                )
            except Exception as exc:
                self._marshal(self._ffmpeg_install_finished, None, exc)
            else:
                self._marshal(self._ffmpeg_install_finished, ffmpeg, None)

        self._install_thread = threading.Thread(target=work, name="ffmpeg-installer", daemon=True)
        self._install_thread.start()

    def _ffmpeg_install_progress(self, downloaded: int, total: int | None) -> None:
        if not self._installing:
            return
        if total and total > 0:
            percent = min(100.0, downloaded * 100.0 / total)
            self.progress.configure(mode="determinate", value=percent)
            self.metrics_var.set(f"Downloaded {format_bytes(downloaded)} of {format_bytes(total)}")
        else:
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
            self.metrics_var.set(f"Downloaded {format_bytes(downloaded)}")

    def _ffmpeg_install_finished(self, ffmpeg: Path | None, error: Exception | None) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", value=0)
        self._install_thread = None
        self._install_cancel_event = None
        self._installing = False
        if error is not None:
            self._update_ffmpeg_action()
            self._update_controls()
            if self._closing:
                self._destroy()
                return
            if isinstance(error, FFmpegInstallCancelled):
                self.status_var.set("FFmpeg installation canceled")
                self.metrics_var.set("")
                return
            self.status_var.set("FFmpeg installation failed")
            self.metrics_var.set("")
            self._append_log(f"FFmpeg installation failed: {error}")
            messagebox.showerror("FFmpeg installation failed", str(error), parent=self.root)
            return
        assert ffmpeg is not None
        self.toolchain = discover_toolchain(ffmpeg=ffmpeg, ffprobe=ffmpeg.with_name("ffprobe.exe"))
        if not self.toolchain.ready:
            self._ffmpeg_install_finished(None, RuntimeError("The installed FFmpeg toolchain could not be detected."))
            return
        self._update_tool_label()
        self.status_var.set(f"FFmpeg {concise_ffmpeg_version(self.toolchain)} installed and ready")
        self.metrics_var.set("")
        self._append_log(f"Installed and selected FFmpeg: {self.toolchain.ffmpeg}")
        self._reinspect_queue()
        self._update_controls()
        if self._closing:
            self._destroy()
            return
        messagebox.showinfo(
            "FFmpeg installed",
            f"FFmpeg {concise_ffmpeg_version(self.toolchain)} was installed beside the app and is ready.",
            parent=self.root,
        )

    def _container_key(self) -> str:
        return CONTAINER_LABELS.get(self.container_var.get(), self._default_container_key)

    def _stream_mode(self) -> str:
        return STREAM_MODE_LABELS[self.stream_mode_var.get()]

    def _destination_directory(self) -> Path | None:
        text = self.destination_var.get().strip()
        if not text:
            return None
        if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
            text = text[1:-1].strip()
        try:
            destination = Path(text).expanduser().resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            raise PlanError(f"The destination folder path is invalid: {text}") from exc
        if not destination.is_dir():
            raise PlanError(f"The destination folder does not exist: {destination}")
        return destination

    def browse_destination(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        options: dict[str, object] = {
            "parent": self.root,
            "title": "Choose batch destination folder",
            "mustexist": True,
        }
        current = self.destination_var.get().strip()
        if current:
            candidate = Path(current.strip('"\''))
            if candidate.is_dir():
                options["initialdir"] = str(candidate)
        elif self._item_order:
            options["initialdir"] = str(self.items[self._item_order[0]].source.parent)
        selected = filedialog.askdirectory(**options)
        if selected:
            self.destination_var.set(str(Path(selected).resolve(strict=False)))
            self._destination_changed()

    def clear_destination(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self.destination_var.set("")
        if self._refresh_planned_outputs():
            self.status_var.set("Destination cleared — outputs will be written beside each source.")
        self._update_controls()

    def _destination_changed(self, event: tk.Event[tk.Misc] | None = None) -> str:
        if self._worker and self._worker.is_alive():
            return "break"
        if self._refresh_planned_outputs():
            destination = self._destination_directory()
            if destination is None:
                self.status_var.set("Outputs will be written beside each source.")
            else:
                self.destination_var.set(str(destination))
                self.status_var.set(f"Batch destination: {destination}")
        self._update_controls()
        return "break" if event is not None and getattr(event, "keysym", "") == "Return" else ""

    def browse_files(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="Add media files",
            filetypes=[("Common media files", COMMON_MEDIA_PATTERN), ("All files", "*.*")],
        )
        if selected:
            self.add_files(tuple(Path(path) for path in selected))

    def _files_dropped(self, paths: tuple[Path, ...]) -> None:
        self.add_files(paths)

    def add_files(self, paths: tuple[Path, ...] | list[Path]) -> None:
        if self._worker and self._worker.is_alive():
            self.status_var.set("The queue is locked while a batch is running.")
            self.root.bell()
            return
        accepted, duplicates, rejected = unique_existing_files(
            paths,
            existing_paths=(item.source for item in self.items.values()),
        )
        new_ids: list[str] = []
        for path in accepted:
            self._item_counter += 1
            item_id = f"item-{self._item_counter:06d}"
            item = BatchItem(item_id=item_id, source=path, container_key=self._default_container_key)
            self.items[item_id] = item
            self._item_order.append(item_id)
            self.queue_tree.insert("", "end", iid=item_id, values=self._row_values(item), tags=(item.state,))
            if self.toolchain.ffprobe is not None:
                self._probe_tasks.put((self._probe_generation, item_id, path, self.toolchain.ffprobe))
            else:
                self._probe_results.put(
                    ("failed", self._probe_generation, item_id, RuntimeError("FFmpeg + FFprobe are required."))
                )
            new_ids.append(item_id)
        self._refresh_planned_outputs()
        if new_ids:
            self.queue_tree.selection_set(new_ids)
            self.queue_tree.see(new_ids[-1])
            self.status_var.set(f"Inspecting {len(new_ids)} added file(s)…")
            self._append_log(f"Added {len(new_ids)} file(s) to the queue.")
        if duplicates:
            self._append_log(f"Ignored {len(duplicates)} duplicate source path(s).")
        if rejected:
            self._append_log("Ignored non-file path(s): " + "; ".join(str(path) for path in rejected))
        if not accepted and (duplicates or rejected):
            self.status_var.set("No new files were added.")
        self._update_controls()

    def _probe_succeeded(self, generation: int, item_id: str, media: MediaProbe) -> None:
        if generation != self._probe_generation or self._closing or item_id not in self.items:
            return
        item = self.items[item_id]
        item.media = media
        item.state = STATE_READY
        item.detail = "Ready"
        self._refresh_planned_outputs()
        self._update_row(item)
        if not any(entry.state == STATE_INSPECTING for entry in self.items.values()):
            ready_count = sum(entry.can_run for entry in self.items.values())
            self.status_var.set(f"Inspection complete — {ready_count} file(s) ready")
        self._update_controls()

    def _probe_failed(self, generation: int, item_id: str, exc: Exception) -> None:
        if generation != self._probe_generation or self._closing or item_id not in self.items:
            return
        item = self.items[item_id]
        item.media = None
        item.state = STATE_INVALID
        item.detail = "Inspection failed"
        self._update_row(item)
        self._append_log(f"Could not inspect {item.source}: {exc}")
        if not any(entry.state == STATE_INSPECTING for entry in self.items.values()):
            ready_count = sum(entry.can_run for entry in self.items.values())
            self.status_var.set(f"Inspection complete — {ready_count} file(s) ready")
        self._update_controls()

    def _row_values(self, item: BatchItem) -> tuple[str, ...]:
        media = item.media
        return (
            item.source.name,
            input_container_summary(media) if media else ("Invalid" if item.state == STATE_INVALID else "Inspecting…"),
            codec_summary(media, "video") if media else "—",
            codec_summary(media, "audio") if media else "—",
            CONTAINER_PROFILES[item.container_key].label,
            self._compatibility_text(item),
            item.detail,
        )

    def _compatibility_text(self, item: BatchItem) -> str:
        if item.media is None:
            return "Inspection failed" if item.state == STATE_INVALID else "Inspecting…"
        notes = compatibility_notes(item.media, item.container_key, self._stream_mode())
        return " • ".join(notes) if notes else "Preflight will verify this codec/container combination."

    def _update_row(self, item: BatchItem) -> None:
        if self.queue_tree.exists(item.item_id):
            self.queue_tree.item(item.item_id, values=self._row_values(item), tags=(item.state,))

    def _refresh_planned_outputs(self) -> bool:
        if self._worker and self._worker.is_alive():
            return False
        unlocked = [
            self.items[item_id]
            for item_id in self._item_order
            if self.items[item_id].state != STATE_COMPLETE
        ]
        locked = [
            item.output for item in self.items.values() if item.state == STATE_COMPLETE and item.output is not None
        ]
        try:
            destination = self._destination_directory()
            allocations = allocate_output_paths(
                unlocked,
                output_directory=destination,
                locked_outputs=locked,
            )
        except (OSError, PlanError, KeyError) as exc:
            self._planning_error = str(exc)
            self.status_var.set(f"Output planning error: {exc}")
            return False
        self._planning_error = ""
        for item_id, output in allocations.items():
            self.items[item_id].output = output
        for item in self.items.values():
            self._update_row(item)
        return True

    def _selection_changed(self) -> None:
        selected = [self.items[item_id] for item_id in self.queue_tree.selection() if item_id in self.items]
        if selected:
            keys = {item.container_key for item in selected}
            if len(keys) == 1:
                key = next(iter(keys))
                self.container_var.set(CONTAINER_PROFILES[key].label)
                self._default_container_key = key
        self._update_controls()

    def _container_changed(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        key = self._container_key()
        self._default_container_key = key
        selected_ids = [item_id for item_id in self.queue_tree.selection() if item_id in self.items]
        for item_id in selected_ids:
            item = self.items[item_id]
            item.container_key = key
            item.result = None
            if item.media is not None:
                item.state = STATE_READY
                item.detail = "Ready"
        self._refresh_planned_outputs()
        for item_id in selected_ids:
            self._update_row(self.items[item_id])
        self._update_controls()

    def _stream_mode_changed(self) -> None:
        for item in self.items.values():
            self._update_row(item)

    def remove_selected(self, _event: tk.Event[tk.Misc] | None = None) -> str:
        if self._worker and self._worker.is_alive():
            self.status_var.set("The queue is locked while a batch is running.")
            self.root.bell()
            return "break"
        selected = [item_id for item_id in self.queue_tree.selection() if item_id in self.items]
        for item_id in selected:
            self.queue_tree.delete(item_id)
            self.items.pop(item_id, None)
            if item_id in self._item_order:
                self._item_order.remove(item_id)
        if selected:
            self._refresh_planned_outputs()
            self.status_var.set(f"Removed {len(selected)} queue row(s). No source or output files were deleted.")
        self._update_controls()
        return "break"

    def clear_queue(self) -> None:
        if self._worker and self._worker.is_alive():
            self.status_var.set("The queue is locked while a batch is running.")
            self.root.bell()
            return
        for item_id in tuple(self._item_order):
            if self.queue_tree.exists(item_id):
                self.queue_tree.delete(item_id)
        count = len(self._item_order)
        self.items.clear()
        self._item_order.clear()
        self.status_var.set(f"Cleared {count} queue row(s). No media files were deleted.")
        self._update_controls()

    def _reinspect_queue(self) -> None:
        self._probe_generation += 1
        for item_id in self._item_order:
            item = self.items[item_id]
            if item.state == STATE_COMPLETE:
                continue
            item.media = None
            item.result = None
            item.state = STATE_INSPECTING
            item.detail = "Inspecting…"
            self._update_row(item)
            assert self.toolchain.ffprobe is not None
            self._probe_tasks.put((self._probe_generation, item_id, item.source, self.toolchain.ffprobe))
        pending = sum(item.state == STATE_INSPECTING for item in self.items.values())
        if pending:
            self.status_var.set(f"Re-inspecting {pending} file(s) with the installed FFprobe…")
        self._update_controls()

    def _build_batch_plans(self) -> tuple[tuple[str, RemuxPlan], ...]:
        if not self._refresh_planned_outputs():
            raise PlanError(self._planning_error or "The queue's output paths could not be planned safely.")
        plan_records: list[tuple[str, RemuxPlan]] = []
        for item_id in self._item_order:
            item = self.items[item_id]
            if not item.can_run:
                continue
            if item.media is None or item.output is None:
                raise PlanError(f"{item.source.name} does not have a valid inspected source and output.")
            plan = build_remux_plan(
                item.media,
                item.output,
                item.container_key,
                self._stream_mode(),
                enforce_space=False,
            )
            plan_records.append((item_id, plan))
        if not plan_records:
            raise PlanError("No inspected, uncompleted files are ready to process.")
        ensure_batch_space(plan for _item_id, plan in plan_records)
        return tuple(plan_records)

    def _confirmation_text(self, plans: tuple[tuple[str, RemuxPlan], ...]) -> str:
        total_bytes = sum(plan.source_probe.size for _item_id, plan in plans)
        containers = Counter(plan.profile.label for _item_id, plan in plans)
        container_text = ", ".join(f"{label}: {count}" for label, count in sorted(containers.items()))
        examples = [f"• {plan.source_probe.path.name} → {plan.output.name}" for _item_id, plan in plans[:6]]
        if len(plans) > 6:
            examples.append(f"• …and {len(plans) - 6} more")
        omission_lines = [
            f"• {plan.source_probe.path.name}: {describe_streams(plan.omitted_source_streams)}"
            for _item_id, plan in plans
            if plan.omitted_source_streams
        ]
        if len(omission_lines) > 6:
            omitted_file_count = len(omission_lines)
            omission_lines = omission_lines[:6] + [f"• …and {omitted_file_count - 6} more file(s)"]
        omission_text = ""
        if omission_lines:
            omission_text = (
                "\n\nIntentional omissions (listed tracks only; no re-encoding):\n"
                + "\n".join(omission_lines)
            )
        destination = self._destination_directory()
        destination_text = str(destination) if destination is not None else "Beside each source"
        return (
            f"Stream-copy {len(plans)} file(s) sequentially without re-encoding?\n\n"
            f"Input size: {format_bytes(total_bytes)}\n"
            f"Outputs: {container_text}\n"
            f"Destination: {destination_text}\n"
            f"Streams: {STREAM_MODE_CONFIRMATION_LABELS[self._stream_mode()]}\n\n"
            + "\n".join(examples)
            + omission_text
            + "\n\nExisting files are never overwritten. A failed file will not stop later queue items."
        )

    def start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self.toolchain.ready:
            messagebox.showerror("FFmpeg required", "Select a valid FFmpeg + FFprobe toolchain.", parent=self.root)
            return
        if any(item.state == STATE_INSPECTING for item in self.items.values()):
            messagebox.showerror("Inspection in progress", "Wait for all added files to finish inspection.", parent=self.root)
            return
        try:
            plans = self._build_batch_plans()
        except (PlanError, OSError) as exc:
            messagebox.showerror("Cannot start batch", str(exc), parent=self.root)
            return
        if not messagebox.askokcancel(
            "Confirm batch stream copy",
            self._confirmation_text(plans),
            parent=self.root,
            icon="info",
        ):
            return

        self._cancel_event = threading.Event()
        self.last_results = []
        self._clear_log()
        self._append_log("Batch method: sequential FFmpeg -c copy (no re-encoding)")
        for _item_id, plan in plans:
            if plan.omitted_source_streams:
                self._append_log(
                    f"{plan.source_probe.path.name}: intentionally omitting for {plan.profile.label}: "
                    f"{describe_streams(plan.omitted_source_streams)}. No stream will be re-encoded."
                )
        for item_id, _plan in plans:
            item = self.items[item_id]
            item.state = STATE_QUEUED
            item.detail = "Queued"
            self._update_row(item)
        self.progress.configure(mode="determinate", value=0)
        self.metrics_var.set("")
        self.status_var.set(f"Starting batch of {len(plans)} file(s)…")
        self._set_running(True)

        def work() -> None:
            assert self._cancel_event is not None
            try:
                summary = run_batch_plans(
                    self.toolchain,
                    plans,
                    cancel_event=self._cancel_event,
                    on_item_starting=lambda item_id, index, total: self._marshal(
                        self._batch_item_starting, item_id, index, total
                    ),
                    on_item_finished=lambda item_id, result, error: self._marshal(
                        self._batch_item_finished, item_id, result, error
                    ),
                    on_status=lambda item_id, index, total, text: self._marshal(
                        self._batch_item_status, item_id, index, total, text
                    ),
                    on_progress=lambda item_id, index, total, update: self._marshal(
                        self._batch_item_progress, item_id, index, total, update
                    ),
                    on_log=lambda item_id, text: self._marshal(
                        self._append_log,
                        f"[{self.items[item_id].source.name}] {text}",
                    ),
                )
            except Exception as exc:
                self._marshal(self._batch_controller_failed, exc)
                return
            self._marshal(
                self._batch_finished,
                summary.completed,
                summary.failed,
                summary.canceled,
                summary.total,
            )

        self._worker = threading.Thread(target=work, name="batch-remux-worker", daemon=True)
        self._worker.start()

    def _batch_controller_failed(self, exc: Exception) -> None:
        self._worker = None
        self._cancel_event = None
        self._current_item_id = None
        for item in self.items.values():
            if item.state == STATE_PROCESSING:
                item.state = STATE_FAILED
                item.detail = "Internal batch error — retryable"
                self._update_row(item)
            elif item.state == STATE_QUEUED:
                item.state = STATE_READY
                item.detail = "Ready"
                self._update_row(item)
        self._set_running(False)
        logging.getLogger("stream_copy_remuxer.gui").exception(
            "Unexpected batch-controller failure",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        if self._closing:
            self._destroy()
            return
        self.status_var.set("Internal batch error — queue restored for retry")
        self._append_log(f"Internal batch-controller error: {exc}")
        messagebox.showerror(
            "Batch controller error",
            f"The queue was restored for retry. No additional item was started.\n\n{exc}",
            parent=self.root,
        )

    def _batch_item_starting(self, item_id: str, index: int, total: int) -> None:
        if item_id not in self.items:
            return
        self._current_item_id = item_id
        item = self.items[item_id]
        item.state = STATE_PROCESSING
        item.detail = "Starting preflight…"
        self._update_row(item)
        self.queue_tree.selection_set(item_id)
        self.queue_tree.see(item_id)
        self.status_var.set(f"File {index} of {total}: {item.source.name}")
        self.progress.configure(mode="determinate", value=0)
        self.metrics_var.set("")
        self._append_log(f"Starting {index}/{total}: {item.source} → {item.output}")

    def _batch_item_status(self, item_id: str, index: int, total: int, text: str) -> None:
        if item_id not in self.items:
            return
        item = self.items[item_id]
        item.detail = text.replace("…", "...")
        self._update_row(item)
        self.status_var.set(f"File {index} of {total}: {item.source.name} — {text}")
        if "Stream-copying" in text:
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)

    def _batch_item_progress(self, item_id: str, index: int, total: int, update: ProgressUpdate) -> None:
        if item_id not in self.items:
            return
        if update.percent is None:
            if str(self.progress.cget("mode")) != "indeterminate":
                self.progress.configure(mode="indeterminate")
                self.progress.start(12)
        else:
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress["value"] = update.percent
            if update.phase == "remux":
                self.items[item_id].detail = f"Processing {update.percent:.0f}%"
                self._update_row(self.items[item_id])
        pieces = [f"File {index}/{total}", f"Elapsed {format_duration(update.elapsed_seconds)}"]
        if update.media_seconds is not None:
            pieces.append(f"Media {format_duration(update.media_seconds)}")
        if update.bytes_written is not None:
            pieces.append(f"Written {format_bytes(update.bytes_written)}")
        if update.speed:
            pieces.append(f"Speed {update.speed}")
        self.metrics_var.set("  •  ".join(pieces))

    def _batch_item_finished(
        self,
        item_id: str,
        result: RemuxResult | None,
        error: Exception | None,
    ) -> None:
        if item_id not in self.items:
            return
        item = self.items[item_id]
        if result is not None:
            item.result = result
            item.output = result.output
            item.state = STATE_COMPLETE
            item.detail = "Complete — verified"
            self.last_results.append(result)
            self._append_log(f"Verified output: {result.output}")
            self._append_log(f"Audit report: {result.report}")
        elif isinstance(error, RemuxCancelled):
            item.state = STATE_CANCELED
            item.detail = "Canceled — retryable"
            self._append_log(f"Canceled {item.source.name}: {error}")
        else:
            item.state = STATE_FAILED
            item.detail = "Failed — retryable"
            self._append_log(f"Failed {item.source.name}: {error}")
        self._update_row(item)

    def _batch_finished(self, completed: int, failed: int, canceled: bool, total: int) -> None:
        self.progress.stop()
        self._worker = None
        self._cancel_event = None
        self._current_item_id = None
        for item in self.items.values():
            if item.state == STATE_QUEUED:
                item.state = STATE_READY
                item.detail = "Ready"
                self._update_row(item)
        self._set_running(False)
        if self._closing:
            self._destroy()
            return
        self.progress.configure(mode="determinate", value=100 if completed + failed == total and not canceled else 0)
        if canceled:
            self.status_var.set(f"Batch canceled — {completed} complete, {failed} failed, remaining files ready to retry")
        else:
            self.status_var.set(f"Batch finished — {completed} complete, {failed} failed")
        self.metrics_var.set(f"Processed {completed + failed} of {total} file(s)")
        self._update_controls()
        if canceled:
            messagebox.showinfo(
                "Batch canceled",
                f"Completed: {completed}\nFailed: {failed}\nUnstarted files remain ready to retry.",
                parent=self.root,
            )
        elif failed:
            messagebox.showwarning(
                "Batch finished with failures",
                f"Completed: {completed}\nFailed: {failed}\n\nSee the queue and Details for each failure.",
                parent=self.root,
            )
        else:
            messagebox.showinfo(
                "Batch complete",
                f"All {completed} output(s) completed and passed verification.",
                parent=self.root,
            )

    def _set_running(self, running: bool) -> None:
        normal = "disabled" if running else "normal"
        readonly = "disabled" if running else "readonly"
        for widget in (
            self.add_button,
            self.remove_button,
            self.clear_button,
        ):
            widget.configure(state=normal)
        self.container_combo.configure(state=readonly)
        self.stream_combo.configure(state=readonly)
        self.destination_entry.configure(state=normal)
        self.destination_browse_button.configure(state=normal)
        self.destination_clear_button.configure(state=normal)
        self.cancel_button.configure(state="normal" if running else "disabled")
        self._update_ffmpeg_action()
        self._update_controls(running=running)

    def _update_controls(self, *, running: bool | None = None) -> None:
        if running is None:
            running = bool(self._worker and self._worker.is_alive())
        inspecting = any(item.state == STATE_INSPECTING for item in self.items.values())
        can_start = not running and not self._installing and not inspecting and self.toolchain.ready and any(
            item.can_run for item in self.items.values()
        )
        self.start_button.configure(state="normal" if can_start else "disabled")
        self.remove_button.configure(state="normal" if not running and bool(self.queue_tree.selection()) else "disabled")
        self.clear_button.configure(state="normal" if not running and bool(self.items) else "disabled")
        self.destination_entry.configure(state="disabled" if running else "normal")
        self.destination_browse_button.configure(state="disabled" if running else "normal")
        self.destination_clear_button.configure(
            state="normal" if not running and bool(self.destination_var.get().strip()) else "disabled"
        )
        selected_result = any(
            self.items[item_id].result is not None
            for item_id in self.queue_tree.selection()
            if item_id in self.items
        )
        self.show_output_button.configure(
            state="normal" if not running and (selected_result or bool(self.last_results)) else "disabled"
        )

    def cancel(self) -> None:
        if self._cancel_event is not None:
            self.status_var.set("Canceling the active file and removing its partial output…")
            self.cancel_button.configure(state="disabled")
            self._cancel_event.set()

    def show_output(self) -> None:
        result: RemuxResult | None = None
        for item_id in self.queue_tree.selection():
            if item_id in self.items and self.items[item_id].result is not None:
                result = self.items[item_id].result
                break
        if result is None and self.last_results:
            result = self.last_results[-1]
        if result is None:
            return
        output = Path(result.output)
        if not output.is_file():
            messagebox.showerror(
                "Output not found",
                f"The verified output is no longer available:\n\n{output}",
                parent=self.root,
            )
            return
        try:
            self._folder_opener(output.parent)
        except OSError as exc:
            messagebox.showerror(
                "Could not open output folder",
                f"The output folder could not be opened:\n\n{output.parent}\n\n{exc}",
                parent=self.root,
            )

    def _marshal(self, callback: object, *args: object) -> None:
        self._ui_events.put((callback, args))

    def _drain_ui_events(self) -> None:
        for _ in range(250):
            try:
                event, generation, item_id, payload = self._probe_results.get_nowait()
            except queue.Empty:
                break
            if event == "succeeded" and isinstance(payload, MediaProbe):
                self._probe_succeeded(generation, item_id, payload)
            elif event == "failed" and isinstance(payload, Exception):
                self._probe_failed(generation, item_id, payload)
        for _ in range(250):
            try:
                callback, args = self._ui_events.get_nowait()
            except queue.Empty:
                break
            if callable(callback):
                try:
                    callback(*args)
                except Exception as exc:
                    logging.getLogger("stream_copy_remuxer.gui").exception(
                        "Unhandled UI callback failure",
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    try:
                        self.status_var.set("Internal UI error — see the application log")
                    except tk.TclError:
                        pass
        try:
            self._ui_after_id = self.root.after(20, self._drain_ui_events)
        except tk.TclError:
            pass

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text.rstrip() + "\n")
        lines = int(self.log_text.index("end-1c").split(".")[0])
        if lines > 1500:
            self.log_text.delete("1.0", f"{lines - 1200}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def close(self) -> None:
        if self._installing and self._install_thread is not None:
            if not messagebox.askyesno(
                "Cancel FFmpeg installation?",
                "Closing now will cancel the FFmpeg download or staged installation. Continue?",
                parent=self.root,
            ):
                return
            self._closing = True
            self.status_var.set("Canceling FFmpeg installation…")
            if self._install_cancel_event is not None:
                self._install_cancel_event.set()
            return
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno(
                "Cancel active batch?",
                "Closing now will cancel the active FFmpeg process and remove its partial output. Continue?",
                parent=self.root,
            ):
                return
            self._closing = True
            self.cancel()
            return
        self._closing = True
        self._destroy()

    def _destroy(self) -> None:
        self.file_drop.close()
        if self._install_cancel_event is not None:
            self._install_cancel_event.set()
        if self._ui_after_id is not None:
            try:
                self.root.after_cancel(self._ui_after_id)
            except tk.TclError:
                pass
            self._ui_after_id = None
        try:
            while True:
                self._probe_tasks.get_nowait()
        except queue.Empty:
            pass
        self._probe_tasks.put(None)
        try:
            self._probe_thread.join(timeout=1.0)
        except RuntimeError:
            pass
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def close_for_test(self) -> None:
        self._closing = True
        self._destroy()


def _widget_texts(widget: tk.Misc) -> tuple[str, ...]:
    texts: list[str] = []
    for child in widget.winfo_children():
        try:
            text = child.cget("text")
        except (tk.TclError, TypeError):
            text = ""
        if text:
            texts.append(str(text))
        texts.extend(_widget_texts(child))
    return tuple(texts)


def _layout_metrics(app: StreamCopyRemuxerApp) -> dict[str, object]:
    app.root.update_idletasks()
    style = ttk.Style(app.root)

    def named_font(value: object, fallback: str) -> tkfont.Font:
        name = str(value or fallback)
        try:
            return tkfont.nametofont(name, root=app.root)
        except tk.TclError:
            return tkfont.Font(root=app.root, font=name)

    tree_font = named_font(style.lookup("Batch.Treeview", "font"), "TkDefaultFont")
    heading_font = named_font(style.lookup("Batch.Treeview.Heading", "font"), "TkHeadingFont")
    description_font = named_font(style.lookup("Subtitle.TLabel", "font"), "TkDefaultFont")
    row_height = int(style.lookup("Batch.Treeview", "rowheight"))
    heading_widths: dict[str, dict[str, int | bool]] = {}
    for column, heading in app._queue_headings.items():
        width = int(app.queue_tree.column(column, "width"))
        required = int(heading_font.measure(heading)) + 20
        heading_widths[column] = {
            "width": width,
            "required": required,
            "passed": width >= required,
        }
    status_width = int(app.queue_tree.column("status", "width"))
    status_required = int(tree_font.measure(STATUS_WIDTH_SAMPLE)) + 24
    status_stretch = bool(app.queue_tree.column("status", "stretch"))
    minimum_width, minimum_height = app.root.minsize()
    return {
        "tk_scaling": float(app.root.tk.call("tk", "scaling")),
        "description_wraplength": int(float(app.description_label.cget("wraplength") or 0)),
        "description_requested_width": app.description_label.winfo_reqwidth(),
        "description_requested_height": app.description_label.winfo_reqheight(),
        "description_line_height": int(description_font.metrics("linespace")),
        "description_one_line": (
            int(float(app.description_label.cget("wraplength") or 0)) == 0
            and app.description_label.winfo_reqheight() <= int(description_font.metrics("linespace")) + 8
            and minimum_width >= app.description_label.winfo_reqwidth() + 28
        ),
        "tree_row_height": row_height,
        "tree_line_height": int(tree_font.metrics("linespace")),
        "tree_rows_readable": row_height >= int(tree_font.metrics("linespace")) + 8,
        "heading_widths": heading_widths,
        "headings_readable": all(bool(values["passed"]) for values in heading_widths.values()),
        "status_column_width": status_width,
        "status_content_required": status_required,
        "status_content_readable": status_width >= status_required,
        "status_user_resizable": status_stretch,
        "details_rows": int(app.log_text.cget("height")),
        "details_expansion_weight": int(app.outer_frame.grid_rowconfigure(4)["weight"]),
        "details_bounded": (
            int(app.log_text.cget("height")) == 10
            and int(app.outer_frame.grid_rowconfigure(4)["weight"]) == 0
        ),
        "minimum_width": minimum_width,
        "minimum_height": minimum_height,
    }


def run_layout_scaling_self_test(toolchain: Toolchain) -> dict[str, object]:
    observations: dict[str, object] = {}
    passed = True
    original_scaling: float | None = None
    for label, scaling in (("100_percent", 4.0 / 3.0), ("150_percent", 2.0), ("200_percent", 8.0 / 3.0)):
        root = create_root()
        root.withdraw()
        if original_scaling is None:
            original_scaling = float(root.tk.call("tk", "scaling"))
        root.tk.call("tk", "scaling", scaling)
        app = StreamCopyRemuxerApp(root, toolchain, check_ffmpeg_updates=False)
        metrics = _layout_metrics(app)
        observations[label] = metrics
        passed = passed and bool(metrics["description_one_line"])
        passed = passed and bool(metrics["tree_rows_readable"])
        passed = passed and bool(metrics["headings_readable"])
        passed = passed and bool(metrics["status_content_readable"])
        passed = passed and bool(metrics["status_user_resizable"])
        passed = passed and bool(metrics["details_bounded"])
        app.close_for_test()
        del app
        del root
        gc.collect()
    if original_scaling is not None:
        restore_root = create_root()
        restore_root.withdraw()
        restore_root.tk.call("tk", "scaling", original_scaling)
        restore_root.destroy()
        del restore_root
        gc.collect()
    return {"passed": passed, "scales": observations}


def run_withdrawn_gui_self_test(
    toolchain: Toolchain,
    *,
    sample_paths: tuple[Path, ...] = (),
) -> dict[str, object]:
    root = create_root()
    root.withdraw()
    app = StreamCopyRemuxerApp(root, toolchain, check_ffmpeg_updates=False)
    root.update_idletasks()
    event_seen = {"value": False}
    root.after(10, lambda: event_seen.__setitem__("value", True))
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not event_seen["value"]:
        root.update()
        time.sleep(0.005)

    queue_checks: dict[str, bool] = {}
    if sample_paths:
        if app.file_drop.active:
            for _ in range(25):
                app.file_drop.simulate(sample_paths)
                root.update()
        else:
            app.add_files(sample_paths)
        try:
            root.update()
        except tk.TclError:
            pass
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and any(
            item.state == STATE_INSPECTING for item in app.items.values()
        ):
            root.update()
            time.sleep(0.01)
        root.update()
        row_names = [str(app.queue_tree.item(item_id, "values")[0]) for item_id in app.items]
        queue_checks = {
            "tkdnd_drop_adapter_accepted": app.file_drop.active and len(app.items) == len(sample_paths),
            "repeated_drops_stable_and_deduplicated": len(app.items) == len(sample_paths),
            "multiple_rows_added": len(app.items) == len(sample_paths),
            "rows_ready": bool(app.items) and all(item.state == STATE_READY for item in app.items.values()),
            "video_codec_displayed": bool(app.items)
            and all(codec_summary(item.media, "video") != "—" for item in app.items.values() if item.media),
            "mp4_default_for_rows": bool(app.items)
            and all(item.container_key == "mp4" for item in app.items.values()),
            "visible_source_cells_are_filenames": row_names == [path.name for path in sample_paths],
            "outputs_are_beside_sources": all(
                item.output is not None and item.output.parent == item.source.parent
                for item in app.items.values()
            ),
            "outputs_use_remux_suffix": all(
                item.output is not None and item.output.stem.startswith(item.source.stem + "_remux")
                for item in app.items.values()
            ),
            "compatibility_column_populated": all(
                bool(app.queue_tree.item(item_id, "values")[5]) for item_id in app.items
            ),
        }
        with tempfile.TemporaryDirectory(prefix="stream-copy-remuxer-destination-test-") as folder:
            destination = Path(folder)
            app.destination_var.set(str(destination))
            custom_planned = app._refresh_planned_outputs()
            queue_checks["custom_destination_applies_to_all_rows"] = custom_planned and all(
                item.output is not None and item.output.parent == destination
                for item in app.items.values()
            )
            app.clear_destination()
            queue_checks["clear_destination_restores_source_folders"] = (
                app.destination_var.get() == ""
                and all(
                    item.output is not None and item.output.parent == item.source.parent
                    for item in app.items.values()
                )
            )
        compatible_label = next(
            label for label, mode in STREAM_MODE_LABELS.items() if mode == "compatible"
        )
        app.stream_mode_var.set(compatible_label)
        app._stream_mode_changed()
        try:
            compatible_plans = app._build_batch_plans()
            compatible_confirmation = app._confirmation_text(compatible_plans)
        except (OSError, PlanError) as exc:
            compatible_confirmation = str(exc)
            queue_checks["compatible_confirmation_discloses_omissions"] = False
        else:
            expected_omissions = [
                plan
                for _item_id, plan in compatible_plans
                if plan.omitted_source_streams
            ]
            queue_checks["compatible_confirmation_discloses_omissions"] = (
                not expected_omissions
                or (
                    "Intentional omissions" in compatible_confirmation
                    and all(
                        describe_streams(plan.omitted_source_streams) in compatible_confirmation
                        for plan in expected_omissions
                    )
                )
            )
        video_label = next(
            label for label, mode in STREAM_MODE_LABELS.items() if mode == "video"
        )
        app.stream_mode_var.set(video_label)
        app._stream_mode_changed()
        try:
            video_plans = app._build_batch_plans()
            video_confirmation = app._confirmation_text(video_plans)
        except (OSError, PlanError) as exc:
            video_confirmation = str(exc)
            queue_checks["video_only_confirmation_discloses_audio_omissions"] = False
        else:
            expected_video_omissions = [
                plan
                for _item_id, plan in video_plans
                if plan.omitted_source_streams
            ]
            queue_checks["video_only_confirmation_discloses_audio_omissions"] = (
                bool(expected_video_omissions)
                and "video only" in video_confirmation.lower()
                and "Intentional omissions" in video_confirmation
                and all(
                    describe_streams(plan.omitted_source_streams) in video_confirmation
                    for plan in expected_video_omissions
                )
                and any(
                    stream.codec_type == "audio"
                    for plan in expected_video_omissions
                    for stream in plan.omitted_source_streams
                )
            )
        app.stream_mode_var.set(next(iter(STREAM_MODE_LABELS)))
        app._stream_mode_changed()
        app.queue_tree.selection_set(tuple(app.items))
        app.remove_selected()
        queue_checks["delete_key_removes_rows"] = not app.items

    texts = _widget_texts(root)
    expected_columns = (
        "source", "input_container", "video", "audio", "output_container", "compatibility", "status",
    )
    layout = _layout_metrics(app)
    checks = {
        "window_title": root.title().startswith("Stream Copy Remuxer"),
        "minimum_width": root.minsize()[0] <= 1920,
        "minimum_height": root.winfo_reqheight() <= 950,
        "event_loop_responsive": event_seen["value"],
        "exact_description": app.description_var.get() == DESCRIPTION,
        "description_one_line": bool(layout["description_one_line"]),
        "tree_rows_readable": bool(layout["tree_rows_readable"]),
        "headings_readable": bool(layout["headings_readable"]),
        "status_content_readable": bool(layout["status_content_readable"]),
        "status_column_user_resizable": bool(layout["status_user_resizable"]),
        "details_height_bounded": bool(layout["details_bounded"]),
        "details_log_ten_rows": int(layout["details_rows"]) == 10,
        "redundant_heading_absent": "Stream Copy Remuxer" not in texts,
        "queue_columns": tuple(app.queue_tree.cget("columns")) == expected_columns,
        "planned_output_column_absent": "output" not in tuple(app.queue_tree.cget("columns")),
        "mp4_default": app.container_var.get() == "MP4" and app._default_container_key == "mp4",
        "delete_key_bound": bool(app.queue_tree.bind("<Delete>")),
        "legacy_output_controls_absent": not any(
            text in {"Set output…", "Change FFmpeg…"}
            for text in texts
        ),
        "destination_control_present": (
            "Destination folder (blank = beside each source):" in texts
            and app.destination_entry.winfo_exists()
            and app.destination_browse_button.winfo_exists()
            and app.destination_clear_button.winfo_exists()
        ),
        "destination_blank_by_default": app.destination_var.get() == "",
        "add_files_text": str(app.add_button.cget("text")) == "Add files",
        "stream_descriptions": (
            "excludes subtitle, attachment, and data" in tuple(STREAM_MODE_LABELS)[0]
            and "keeps metadata and chapters" in tuple(STREAM_MODE_LABELS)[0]
            and "Video only" in tuple(STREAM_MODE_LABELS)[1]
            and "excludes audio" in tuple(STREAM_MODE_LABELS)[1]
            and "All compatible streams" in tuple(STREAM_MODE_LABELS)[2]
            and "omits only extras" in tuple(STREAM_MODE_LABELS)[2]
            and "strict" in tuple(STREAM_MODE_LABELS)[3]
            and "omits nothing" in tuple(STREAM_MODE_LABELS)[3]
            and tuple(STREAM_MODE_LABELS.values()) == ("av", "video", "compatible", "all")
        ),
        "drag_drop_registered": app.file_drop.active,
        "drag_drop_backend_is_tkdnd_ole2": app.file_drop.backend == "TkDND/OLE2",
        "start_disabled_without_files": str(app.start_button.cget("state")) == "disabled",
        "cancel_disabled_when_idle": str(app.cancel_button.cget("state")) == "disabled",
        "toolchain_displayed": bool(app.tool_var.get()),
        **queue_checks,
    }
    drop_error = app.file_drop.error
    payload = {
        "passed": all(checks.values()),
        "checks": checks,
        "observations": {
            "drag_drop_error": drop_error,
            "tkdnd_version": app.file_drop.version,
            "layout": layout,
        },
    }
    app.close_for_test()
    del app
    del root
    gc.collect()
    return payload
