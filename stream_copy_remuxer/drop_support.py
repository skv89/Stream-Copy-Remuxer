from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Callable, Iterable

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
except ImportError:  # A source-only CLI install can still use non-GUI modes.
    COPY = "copy"
    DND_FILES = "DND_Files"
    TkinterDnD = None  # type: ignore[assignment]


DropCallback = Callable[[tuple[Path, ...]], None]


def create_root() -> tk.Tk:
    if TkinterDnD is None:
        return tk.Tk()
    return TkinterDnD.Tk()


def parse_drop_paths(root: tk.Misc, data: object) -> tuple[Path, ...]:
    if isinstance(data, (tuple, list)):
        values = tuple(str(value) for value in data)
    else:
        values = tuple(str(value) for value in root.tk.splitlist(str(data)))
    return tuple(Path(value) for value in values if value)


class FileDropRegistration:
    """TkDND/OLE2 file-drop registration without Python WNDPROC subclassing."""

    backend = "TkDND/OLE2"

    def __init__(self, root: tk.Tk, callback: DropCallback) -> None:
        self.root = root
        self.callback = callback
        self.active = False
        self.error = ""
        self.version = str(getattr(root, "TkdndVersion", ""))
        self._register()

    def _register(self) -> None:
        register = getattr(self.root, "drop_target_register", None)
        bind = getattr(self.root, "dnd_bind", None)
        if not callable(register) or not callable(bind):
            self.error = "TkDND is not available in this application runtime."
            return

        def dropped(event: object) -> str:
            try:
                paths = parse_drop_paths(self.root, getattr(event, "data", ""))
                if paths:
                    self.root.after_idle(self.callback, paths)
            except (tk.TclError, OSError, ValueError) as exc:
                self.error = f"Could not read dropped files: {exc}"
            return str(COPY)

        try:
            register(DND_FILES)
            bind("<<Drop>>", dropped)
        except (tk.TclError, RuntimeError) as exc:
            self.error = str(exc)
            return
        self.active = True

    def simulate(self, paths: Iterable[Path]) -> None:
        """Exercise the same Tcl-list parser and deferred callback used by a native drop."""
        path_list = tuple(str(Path(path)) for path in paths)
        if not path_list:
            raise ValueError("At least one path is required for a simulated drop.")
        tcl_list = self.root.tk.call("list", *path_list)
        parsed = parse_drop_paths(self.root, tcl_list)
        self.root.after_idle(self.callback, parsed)

    def close(self) -> None:
        if not self.active:
            return
        unregister = getattr(self.root, "drop_target_unregister", None)
        try:
            if callable(unregister):
                unregister()
        except tk.TclError:
            pass
        self.active = False
        self.callback = lambda _paths: None


def register_file_drop(root: tk.Tk, callback: DropCallback) -> FileDropRegistration:
    return FileDropRegistration(root, callback)
