from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable


RELEASE_ARCHIVE_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
RELEASE_VERSION_URL = RELEASE_ARCHIVE_URL + ".ver"
RELEASE_CHECKSUM_URL = RELEASE_ARCHIVE_URL + ".sha256"
RELEASE_INFORMATION_URL = "https://ffmpeg.org/download.html"
ALLOWED_PROVIDER_HOSTS = frozenset({"gyan.dev", "www.gyan.dev"})
MAX_METADATA_BYTES = 16 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_MEMBER_BYTES = 384 * 1024 * 1024
MAX_SELECTED_BYTES = 768 * 1024 * 1024
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

ProgressCallback = Callable[[int, int | None], None]


class FFmpegInstallError(RuntimeError):
    pass


class FFmpegInstallCancelled(FFmpegInstallError):
    pass


@dataclass(frozen=True)
class FFmpegRelease:
    version: str
    sha256: str
    archive_url: str = RELEASE_ARCHIVE_URL


def _numeric_version(value: str) -> tuple[int, int, int] | None:
    match = re.fullmatch(r"\s*(\d+)\.(\d+)(?:\.(\d+))?\s*", value)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def validate_release_version(value: str) -> str:
    value = value.strip()
    if _numeric_version(value) is None:
        raise FFmpegInstallError(f"The release provider returned an invalid FFmpeg version: {value!r}")
    return value


def _parse_tool_version(version_output: str, tool_name: str) -> str | None:
    match = re.search(
        rf"(?im)^\s*{re.escape(tool_name)}\s+version\s+(?:n)?(?P<version>\d+\.\d+(?:\.\d+)?)",
        version_output,
    )
    return match.group("version") if match else None


def parse_ffmpeg_version(version_output: str) -> str | None:
    return _parse_tool_version(version_output, "ffmpeg")


def installed_version_is_older(version_output: str, release_version: str) -> bool | None:
    installed = parse_ffmpeg_version(version_output)
    installed_parts = _numeric_version(installed or "")
    release_parts = _numeric_version(release_version)
    if installed_parts is None or release_parts is None:
        return None
    return installed_parts < release_parts


def _validate_provider_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or (parsed.hostname or "").lower() not in ALLOWED_PROVIDER_HOSTS:
        raise FFmpegInstallError(f"Refusing an unexpected FFmpeg download address: {url}")
    if parsed.username or parsed.password:
        raise FFmpegInstallError("Refusing an FFmpeg download address containing credentials.")


def _open_provider_url(
    url: str,
    *,
    timeout: float,
    opener: Callable[..., object] | None = None,
) -> object:
    _validate_provider_url(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Stream-Copy-Remuxer/1.2"},
        method="GET",
    )
    response = (opener or urllib.request.urlopen)(request, timeout=timeout)
    final_url = getattr(response, "geturl", lambda: url)()
    try:
        _validate_provider_url(str(final_url))
    except Exception:
        close = getattr(response, "close", None)
        if callable(close):
            close()
        raise
    return response


def _read_small_text(
    url: str,
    *,
    timeout: float,
    opener: Callable[..., object] | None,
) -> str:
    response = _open_provider_url(url, timeout=timeout, opener=opener)
    try:
        data = response.read(MAX_METADATA_BYTES + 1)  # type: ignore[attr-defined]
    finally:
        response.close()  # type: ignore[attr-defined]
    if len(data) > MAX_METADATA_BYTES:
        raise FFmpegInstallError("The FFmpeg release metadata response was unexpectedly large.")
    try:
        return data.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError as exc:
        raise FFmpegInstallError("The FFmpeg release metadata was not valid UTF-8.") from exc


def fetch_current_release(
    *,
    timeout: float = 20.0,
    opener: Callable[..., object] | None = None,
) -> FFmpegRelease:
    version = validate_release_version(
        _read_small_text(RELEASE_VERSION_URL, timeout=timeout, opener=opener)
    )
    checksum_text = _read_small_text(RELEASE_CHECKSUM_URL, timeout=timeout, opener=opener)
    checksum_match = re.search(r"(?i)(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])", checksum_text)
    if checksum_match is None:
        raise FFmpegInstallError("The release provider returned an invalid SHA-256 checksum.")
    return FFmpegRelease(version=version, sha256=checksum_match.group(0).lower())


def _cancel_requested(cancel_event: object | None) -> bool:
    is_set = getattr(cancel_event, "is_set", None)
    return bool(callable(is_set) and is_set())


def download_release_archive(
    release: FFmpegRelease,
    destination: Path,
    *,
    timeout: float = 30.0,
    opener: Callable[..., object] | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: object | None = None,
) -> None:
    destination = Path(destination)
    if destination.exists():
        raise FFmpegInstallError(f"Refusing to overwrite an existing download: {destination}")
    response = _open_provider_url(release.archive_url, timeout=timeout, opener=opener)
    try:
        raw_length = response.headers.get("Content-Length")  # type: ignore[attr-defined]
        try:
            expected_size = int(raw_length) if raw_length else None
        except (TypeError, ValueError):
            expected_size = None
        if expected_size is not None and (expected_size <= 0 or expected_size > MAX_ARCHIVE_BYTES):
            raise FFmpegInstallError(
                f"The FFmpeg archive size is outside the allowed range: {expected_size:,} bytes."
            )
        digest = hashlib.sha256()
        downloaded = 0
        with destination.open("xb") as output:
            while True:
                if _cancel_requested(cancel_event):
                    raise FFmpegInstallCancelled("FFmpeg installation was canceled.")
                chunk = response.read(1024 * 1024)  # type: ignore[attr-defined]
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_ARCHIVE_BYTES:
                    raise FFmpegInstallError("The FFmpeg archive exceeded the allowed download size.")
                digest.update(chunk)
                output.write(chunk)
                if on_progress is not None:
                    on_progress(downloaded, expected_size)
    except Exception:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise
    finally:
        response.close()  # type: ignore[attr-defined]
    if downloaded == 0:
        destination.unlink(missing_ok=True)
        raise FFmpegInstallError("The FFmpeg download was empty.")
    if expected_size is not None and downloaded != expected_size:
        destination.unlink(missing_ok=True)
        raise FFmpegInstallError(
            "The FFmpeg download size did not match the provider's response. "
            f"Expected {expected_size:,} bytes; received {downloaded:,}."
        )
    actual = digest.hexdigest().lower()
    if actual != release.sha256.lower():
        destination.unlink(missing_ok=True)
        raise FFmpegInstallError(
            "The FFmpeg download failed SHA-256 verification. "
            f"Expected {release.sha256.lower()}; received {actual}."
        )


def _safe_archive_name(info: zipfile.ZipInfo) -> PurePosixPath:
    raw = info.filename.replace("\\", "/")
    path = PurePosixPath(raw)
    parts = path.parts
    if not parts or path.is_absolute() or any(part in {"", ".", ".."} for part in parts):
        raise FFmpegInstallError(f"The FFmpeg archive contains an unsafe path: {info.filename}")
    if ":" in parts[0]:
        raise FFmpegInstallError(f"The FFmpeg archive contains a drive-qualified path: {info.filename}")
    mode = (info.external_attr >> 16) & 0o170000
    if mode == 0o120000:
        raise FFmpegInstallError(f"The FFmpeg archive contains an unsupported symbolic link: {info.filename}")
    if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
        raise FFmpegInstallError(f"The FFmpeg archive member is unexpectedly large: {info.filename}")
    return path


def _copy_member(archive: zipfile.ZipFile, info: zipfile.ZipInfo, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info, "r") as source, destination.open("xb") as output:
        shutil.copyfileobj(source, output, length=1024 * 1024)
    if destination.stat().st_size != info.file_size or info.file_size == 0:
        raise FFmpegInstallError(f"The extracted FFmpeg file was incomplete: {destination.name}")


def extract_release_archive(archive_path: Path, staging_directory: Path) -> tuple[Path, Path]:
    archive_path = Path(archive_path)
    staging_directory = Path(staging_directory)
    if any(staging_directory.iterdir()):
        raise FFmpegInstallError(f"The FFmpeg staging folder is not empty: {staging_directory}")
    try:
        archive = zipfile.ZipFile(archive_path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise FFmpegInstallError("The downloaded FFmpeg archive is not a readable ZIP file.") from exc
    with archive:
        members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        selected_bytes = 0
        for info in archive.infolist():
            safe_path = _safe_archive_name(info)
            if info.is_dir():
                continue
            selected_bytes += info.file_size
            if selected_bytes > MAX_SELECTED_BYTES:
                raise FFmpegInstallError("The FFmpeg archive expands beyond the allowed safety limit.")
            members.append((info, safe_path))

        def executable_member(name: str) -> zipfile.ZipInfo:
            matches = [
                info
                for info, path in members
                if len(path.parts) >= 3
                and path.parts[-2].lower() == "bin"
                and path.name.lower() == name
            ]
            if len(matches) != 1:
                raise FFmpegInstallError(
                    f"The FFmpeg archive must contain exactly one bin/{name}; found {len(matches)}."
                )
            return matches[0]

        ffmpeg_info = executable_member("ffmpeg.exe")
        ffprobe_info = executable_member("ffprobe.exe")
        bin_directory = staging_directory / "bin"
        ffmpeg = bin_directory / "ffmpeg.exe"
        ffprobe = bin_directory / "ffprobe.exe"
        _copy_member(archive, ffmpeg_info, ffmpeg)
        _copy_member(archive, ffprobe_info, ffprobe)

        documentation_names = {"license", "license.txt", "copying", "copying.txt", "readme", "readme.txt", "readme.md"}
        copied_names: set[str] = set()
        for info, path in members:
            name = path.name.lower()
            if name not in documentation_names or info.file_size > 4 * 1024 * 1024:
                continue
            destination_name = path.name
            key = destination_name.lower()
            if key in copied_names:
                continue
            _copy_member(archive, info, staging_directory / destination_name)
            copied_names.add(key)
    return ffmpeg, ffprobe


def _first_version_line(executable: Path, timeout: float = 20.0) -> str:
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
        raise FFmpegInstallError(f"The installed executable could not be started: {executable}: {exc}") from exc
    line = next((item.strip() for item in result.stdout.splitlines() if item.strip()), "")
    if result.returncode != 0 or not line:
        raise FFmpegInstallError(f"The installed executable did not report a valid version: {executable}")
    return line


def validate_installed_pair(bin_directory: Path, expected_version: str) -> tuple[Path, Path]:
    bin_directory = Path(bin_directory)
    ffmpeg = bin_directory / "ffmpeg.exe"
    ffprobe = bin_directory / "ffprobe.exe"
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise FFmpegInstallError("The installed FFmpeg folder is missing ffmpeg.exe or ffprobe.exe.")
    ffmpeg_line = _first_version_line(ffmpeg)
    ffprobe_line = _first_version_line(ffprobe)
    ffmpeg_version = _parse_tool_version(ffmpeg_line, "ffmpeg")
    ffprobe_version = _parse_tool_version(ffprobe_line, "ffprobe")
    if ffmpeg_version is None:
        raise FFmpegInstallError(f"The installed FFmpeg version could not be parsed: {ffmpeg_line}")
    if ffprobe_version is None:
        raise FFmpegInstallError(f"The installed FFprobe version could not be parsed: {ffprobe_line}")
    ffmpeg_parts = _numeric_version(ffmpeg_version)
    ffprobe_parts = _numeric_version(ffprobe_version)
    expected_parts = _numeric_version(expected_version)
    if (
        ffmpeg_parts is None
        or ffprobe_parts is None
        or expected_parts is None
        or ffmpeg_parts < expected_parts
        or ffprobe_parts < expected_parts
    ):
        raise FFmpegInstallError(
            "The installed tools are older than the selected release: "
            f"FFmpeg {ffmpeg_version}, FFprobe {ffprobe_version}; expected {expected_version} or newer."
        )
    if ffmpeg_parts != ffprobe_parts:
        raise FFmpegInstallError(
            "The installed FFmpeg and FFprobe executables do not report the same release: "
            f"FFmpeg {ffmpeg_version}, FFprobe {ffprobe_version}."
        )
    return ffmpeg, ffprobe


def _validated_existing_install(
    final_directory: Path,
    release: FFmpegRelease,
    validator: Callable[[Path, str], tuple[Path, Path]],
) -> Path | None:
    if not final_directory.is_dir():
        return None
    try:
        ffmpeg, _ffprobe = validator(final_directory / "bin", release.version)
    except Exception:
        return None
    return ffmpeg


def _promote_staging_directory(staging: Path, final_directory: Path) -> None:
    """Rename within one folder, tolerating short-lived Windows scanner locks."""
    last_error: OSError | None = None
    for attempt in range(21):
        if final_directory.exists():
            raise FFmpegInstallError(
                f"The FFmpeg destination appeared during installation and was not overwritten: {final_directory}"
            )
        try:
            os.rename(staging, final_directory)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == 20:
                break
            time.sleep(0.25)
        except OSError:
            raise
    assert last_error is not None
    raise last_error


def install_release(
    release: FFmpegRelease,
    application_directory: Path,
    *,
    opener: Callable[..., object] | None = None,
    on_progress: ProgressCallback | None = None,
    cancel_event: object | None = None,
    validator: Callable[[Path, str], tuple[Path, Path]] = validate_installed_pair,
) -> Path:
    validate_release_version(release.version)
    if not re.fullmatch(r"(?i)[0-9a-f]{64}", release.sha256):
        raise FFmpegInstallError("The requested FFmpeg release checksum is invalid.")
    application_directory = Path(application_directory).resolve(strict=True)
    install_parent = application_directory / "ffmpeg"
    try:
        install_parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise FFmpegInstallError(
            f"The app folder is not writable. Extract the app to a writable folder and try again: {application_directory}"
        ) from exc

    primary = install_parent / release.version
    existing = _validated_existing_install(primary, release, validator)
    if existing is not None:
        return existing
    final_directory = primary if not primary.exists() else install_parent / f"{release.version}-{release.sha256[:8]}"
    existing = _validated_existing_install(final_directory, release, validator)
    if existing is not None:
        return existing
    if final_directory.exists():
        raise FFmpegInstallError(
            f"An invalid FFmpeg installation already occupies the safe destination: {final_directory}"
        )

    staging = install_parent / f".installing-{release.version}-{uuid.uuid4().hex[:10]}"
    staging.mkdir()
    promoted = False
    try:
        with tempfile.TemporaryDirectory(prefix=".ffmpeg-download-", dir=install_parent) as temporary:
            archive_path = Path(temporary) / "ffmpeg-release-essentials.zip"
            download_release_archive(
                release,
                archive_path,
                opener=opener,
                on_progress=on_progress,
                cancel_event=cancel_event,
            )
            if _cancel_requested(cancel_event):
                raise FFmpegInstallCancelled("FFmpeg installation was canceled.")
            ffmpeg, _ffprobe = extract_release_archive(archive_path, staging)
        validator(staging / "bin", release.version)
        if _cancel_requested(cancel_event):
            raise FFmpegInstallCancelled("FFmpeg installation was canceled.")
        _promote_staging_directory(staging, final_directory)
        promoted = True
        return final_directory / "bin" / ffmpeg.name
    except OSError as exc:
        raise FFmpegInstallError(f"FFmpeg could not be installed beside the app: {exc}") from exc
    finally:
        if not promoted and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
