from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

from .ffmpeg_install import parse_ffmpeg_version
from .models import Toolchain


CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == "nt" else 0


def application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _first_file(candidates: Iterable[Path | None]) -> Path | None:
    seen: set[str] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        try:
            resolved = Path(candidate).expanduser().resolve()
        except (OSError, RuntimeError):
            continue
        key = os.path.normcase(str(resolved))
        if key in seen:
            continue
        seen.add(key)
        if resolved.is_file():
            return resolved
    return None


def _which(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found) if found else None


def _version_directory_key(path: Path) -> tuple[int, int, int, str]:
    pieces = path.name.split("-", 1)[0].split(".")
    try:
        numbers = tuple(int(piece) for piece in pieces)
    except ValueError:
        numbers = ()
    padded = (numbers + (0, 0, 0))[:3]
    return padded[0], padded[1], padded[2], path.name.lower()


def _app_local_ffmpeg_candidates(root: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    install_parent = root / "ffmpeg"
    try:
        version_directories = sorted(
            (path for path in install_parent.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=_version_directory_key,
            reverse=True,
        )
    except OSError:
        version_directories = []
    candidates.extend(path / "bin" / "ffmpeg.exe" for path in version_directories)
    candidates.append(root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe")
    return tuple(candidates)


def tool_version(executable: Path | None, timeout: float = 20.0) -> str:
    if executable is None:
        return "Not found"
    try:
        result = subprocess.run(
            [str(executable), "-version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=CREATE_NO_WINDOW,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Unavailable: {exc}"
    line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "Version unavailable")
    return line


def _source_label(path: Path | None, root: Path) -> str:
    if path is None:
        return "Not found"
    for local_root in (root / "ffmpeg", root / "tools" / "ffmpeg"):
        try:
            path.resolve().relative_to(local_root.resolve())
            return "App local"
        except (OSError, ValueError):
            pass
    return "System"


def discover_toolchain(
    *,
    ffmpeg: Path | None = None,
    ffprobe: Path | None = None,
) -> Toolchain:
    root = application_root()
    environment_ffmpeg = os.environ.get("STREAM_COPY_REMUXER_FFMPEG")
    environment_ffprobe = os.environ.get("STREAM_COPY_REMUXER_FFPROBE")
    app_local_ffmpeg = _app_local_ffmpeg_candidates(root)
    resolved_ffmpeg = _first_file(
        (
            ffmpeg,
            Path(environment_ffmpeg) if environment_ffmpeg else None,
            *app_local_ffmpeg,
            _which("ffmpeg.exe"),
            _which("ffmpeg"),
            Path(r"C:\Program Files (x86)\FFMPEG\ffmpeg.exe"),
            Path(r"C:\Program Files\FFmpeg\bin\ffmpeg.exe"),
            Path(r"C:\Program Files\Topaz Labs LLC\Topaz Video\ffmpeg.exe"),
            Path(r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\ffmpeg.exe"),
        )
    )
    paired_probe = resolved_ffmpeg.with_name("ffprobe.exe") if resolved_ffmpeg else None
    resolved_ffprobe = _first_file(
        (
            ffprobe,
            Path(environment_ffprobe) if environment_ffprobe else None,
            paired_probe,
            *(candidate.with_name("ffprobe.exe") for candidate in app_local_ffmpeg),
            _which("ffprobe.exe"),
            _which("ffprobe"),
            Path(r"C:\Program Files (x86)\FFMPEG\ffprobe.exe"),
            Path(r"C:\Program Files\FFmpeg\bin\ffprobe.exe"),
            Path(r"C:\Program Files\Topaz Labs LLC\Topaz Video\ffprobe.exe"),
            Path(r"C:\Program Files\Topaz Labs LLC\Topaz Video AI\ffprobe.exe"),
        )
    )
    return Toolchain(
        ffmpeg=resolved_ffmpeg,
        ffprobe=resolved_ffprobe,
        source=_source_label(resolved_ffmpeg, root),
        ffmpeg_version=tool_version(resolved_ffmpeg),
        ffprobe_version=tool_version(resolved_ffprobe),
    )


def toolchain_from_ffmpeg(path: Path) -> Toolchain:
    path = Path(path).expanduser().resolve()
    paired = path.with_name("ffprobe.exe")
    if path.name.lower() != "ffmpeg.exe" or not path.is_file():
        raise ValueError("Select a valid ffmpeg.exe file.")
    if not paired.is_file():
        raise ValueError(f"A matching ffprobe.exe was not found beside FFmpeg: {paired}")
    return discover_toolchain(ffmpeg=path, ffprobe=paired)


def concise_ffmpeg_version(toolchain: Toolchain) -> str:
    parsed = parse_ffmpeg_version(toolchain.ffmpeg_version)
    if parsed:
        return parsed
    match = re.search(r"(?im)^\s*ffmpeg\s+version\s+(\S+)", toolchain.ffmpeg_version)
    return match.group(1) if match else "unknown version"
