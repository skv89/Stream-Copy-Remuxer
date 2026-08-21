from __future__ import annotations

import argparse
import ctypes
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import Image

from stream_copy_remuxer.batch import BatchItem, STATE_COMPLETE, STATE_READY
from stream_copy_remuxer.encoding import (
    COPY_PROFILE_KEY,
    DNXHR_PROFILE_KEY,
    H264_NVENC_PROFILE_KEY,
    H264_SOFTWARE_PROFILE_KEY,
    HEVC_SOFTWARE_PROFILE_KEY,
    PRORES_PROFILE_KEY,
)
from stream_copy_remuxer.gui import StreamCopyRemuxerApp
from stream_copy_remuxer.models import MediaProbe, StreamInfo
from stream_copy_remuxer.planning import suggest_output
from stream_copy_remuxer.tools import discover_toolchain


class BitmapInfoHeader(ctypes.Structure):
    _fields_ = (
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    )


class BitmapInfo(ctypes.Structure):
    _fields_ = (("bmiHeader", BitmapInfoHeader), ("bmiColors", wintypes.DWORD * 3))


def create_hidden_desktop() -> tuple[object, int]:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    )
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = (wintypes.HANDLE,)
    user32.SetThreadDesktop.restype = wintypes.BOOL
    name = f"StreamCopyRemuxerPreview-{ctypes.windll.kernel32.GetCurrentProcessId()}"
    desktop = user32.CreateDesktopW(name, None, None, 0, 0x01FF, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.SetThreadDesktop(desktop):
        error = ctypes.get_last_error()
        user32.CloseDesktop(desktop)
        raise ctypes.WinError(error)
    return user32, int(desktop)


def capture_window(window_handle: int, output: Path) -> None:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetWindowDC.argtypes = (wintypes.HWND,)
    user32.GetWindowDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = (wintypes.HWND, wintypes.HDC)
    user32.ReleaseDC.restype = ctypes.c_int
    user32.PrintWindow.argtypes = (wintypes.HWND, wintypes.HDC, wintypes.UINT)
    user32.PrintWindow.restype = wintypes.BOOL
    gdi32.CreateCompatibleDC.argtypes = (wintypes.HDC,)
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleBitmap.argtypes = (wintypes.HDC, ctypes.c_int, ctypes.c_int)
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.GetDIBits.argtypes = (
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(BitmapInfo),
        wintypes.UINT,
    )
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)
    gdi32.DeleteObject.restype = wintypes.BOOL
    gdi32.DeleteDC.argtypes = (wintypes.HDC,)
    gdi32.DeleteDC.restype = wintypes.BOOL

    hwnd = int(user32.GetAncestor(wintypes.HWND(window_handle), 2)) or window_handle
    rect = wintypes.RECT()
    if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    window_dc = user32.GetWindowDC(wintypes.HWND(hwnd))
    memory_dc = gdi32.CreateCompatibleDC(window_dc)
    bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
    old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(wintypes.HWND(hwnd), memory_dc, 2):
            raise ctypes.WinError(ctypes.get_last_error())
        info = BitmapInfo()
        info.bmiHeader.biSize = ctypes.sizeof(BitmapInfoHeader)
        info.bmiHeader.biWidth = width
        info.bmiHeader.biHeight = -height
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        info.bmiHeader.biCompression = 0
        buffer = (ctypes.c_ubyte * (width * height * 4))()
        rows = gdi32.GetDIBits(
            memory_dc,
            bitmap,
            0,
            height,
            buffer,
            ctypes.byref(info),
            0,
        )
        if rows != height:
            raise RuntimeError(f"Window capture returned {rows} of {height} rows.")
        image = Image.frombuffer("RGBA", (width, height), buffer, "raw", "BGRA", 0, 1).convert("RGB")
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
    finally:
        gdi32.SelectObject(memory_dc, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(wintypes.HWND(hwnd), window_dc)


def preview_probe(path: Path, *, subtitle: bool, prores: bool = False) -> MediaProbe:
    video_codec = "prores" if prores else "ffv1"
    streams = [
        StreamInfo(
            index=0,
            codec_type="video",
            codec_name=video_codec,
            codec_long_name="Apple ProRes" if prores else "FFmpeg video codec #1",
            width=1920,
            height=1080,
            pixel_format="yuv444p10le",
        ),
        StreamInfo(index=1, codec_type="audio", codec_name="aac", sample_rate=48000, channels=2),
    ]
    if subtitle:
        streams.append(StreamInfo(index=2, codec_type="subtitle", codec_name="subrip"))
    return MediaProbe(
        path=path,
        format_name="matroska,webm",
        format_long_name="Matroska / WebM",
        duration=2700.0,
        size=40_000_000_000,
        modified_ns=1,
        bit_rate=118_000_000,
        streams=tuple(streams),
        chapter_count=12,
    )


def render(output: Path, help_output: Path | None = None) -> None:
    desktop_api, desktop = create_hidden_desktop()
    # A visual preview does not exercise drag-and-drop.  Using a plain Tk root
    # keeps this renderer independent of the development interpreter's tkdnd
    # DLL, while the packaged self-test still validates real TkDND loading.
    root = tk.Tk()
    root.withdraw()
    root.tk.call("tk", "scaling", 4.0 / 3.0)
    app = StreamCopyRemuxerApp(root, discover_toolchain(), check_ffmpeg_updates=False)
    # The packaged build exercises TkDND separately.  Keep the visual fixture
    # representative of the released interface instead of the plain-Tk
    # renderer used to capture it.
    app.queue_hint_var.set("Drag and drop media files here, or use Add files")
    app._clear_log()
    sample_names = (
        "06_Davinci_Temporal_NR_cropped.mkv",
        "07 Journey to the West 西游记 FFV1 cropped.mkv",
        "08 Journey to the West 西游记 FFV1 cropped.mkv",
        "09_Davinci_Temporal_NR_cropped.mkv",
        "10_Davinci_Temporal_NR_cropped.mkv",
        "11 ProRes restoration preview.mov",
    )
    profile_cases = (
        (COPY_PROFILE_KEY, "mp4", None),
        (PRORES_PROFILE_KEY, "mov", None),
        (DNXHR_PROFILE_KEY, "mov", None),
        (H264_SOFTWARE_PROFILE_KEY, "mp4", 12),
        (H264_NVENC_PROFILE_KEY, "mp4", 12),
        (HEVC_SOFTWARE_PROFILE_KEY, "mp4", 12),
    )
    for index, name in enumerate(sample_names, start=1):
        source = Path(r"D:\Chinese Videos\Journey To The West") / name
        item_id = f"preview-{index}"
        encoding_key, container_key, quality = profile_cases[index - 1]
        item = BatchItem(
            item_id=item_id,
            source=source,
            container_key=container_key,
            video_encoding_key=encoding_key,
            quality_value=quality,
        )
        item.media = preview_probe(source, subtitle=index in {2, 4}, prores=index == 6)
        item.output = suggest_output(
            source,
            container_key,
            video_encoding_key=encoding_key,
        )
        item.state = STATE_COMPLETE if index <= 2 else STATE_READY
        item.detail = "Complete — verified" if index <= 2 else "Ready"
        app.items[item_id] = item
        app._item_order.append(item_id)
        app.queue_tree.insert("", "end", iid=item_id, values=app._row_values(item), tags=(item.state,))
    app.queue_tree.selection_set(("preview-2", "preview-3", "preview-4"))
    app._selection_changed()
    app.status_var.set("Inspection complete — 6 files ready")
    app.metrics_var.set("Stream copy and compatibility transcodes are ready; outputs remain beside each source.")
    app._append_log("Added 6 files to the queue.")
    app._append_log("FFprobe inspection completed. Transcoding profiles are explicitly labeled as lossy.")
    app._update_controls()
    root.geometry("+20+20")
    root.deiconify()
    root.update_idletasks()
    root.update()
    capture_window(int(root.winfo_id()), output)
    if help_output is not None:
        app.queue_tree.selection_set("preview-4")
        app._selection_changed()
        app.show_encoding_help()
        assert app._encoding_help_window is not None
        app._encoding_help_window.update_idletasks()
        app._encoding_help_window.update()
        capture_window(int(app._encoding_help_window.winfo_id()), help_output)
    app.close_for_test()
    desktop_api.CloseDesktop(wintypes.HANDLE(desktop))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--help-output", type=Path)
    args = parser.parse_args()
    render(
        args.output.resolve(strict=False),
        args.help_output.resolve(strict=False) if args.help_output else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
