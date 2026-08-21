from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from stream_copy_remuxer.ffmpeg_install import (
    FFmpegInstallError,
    FFmpegRelease,
    download_release_archive,
    extract_release_archive,
    fetch_current_release,
    install_release,
    installed_version_is_older,
    parse_ffmpeg_version,
    validate_installed_pair,
    _promote_staging_directory,
)
from stream_copy_remuxer.models import Toolchain
from stream_copy_remuxer.tools import concise_ffmpeg_version, discover_toolchain


class FakeResponse:
    def __init__(
        self,
        data: bytes,
        url: str,
        *,
        content_length: bool = True,
        reported_length: int | None = None,
    ) -> None:
        self._buffer = io.BytesIO(data)
        self._url = url
        length = len(data) if reported_length is None else reported_length
        self.headers = {"Content-Length": str(length)} if content_length else {}

    def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)

    def close(self) -> None:
        self._buffer.close()

    def geturl(self) -> str:
        return self._url


def make_archive(*, unsafe: bool = False) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("ffmpeg-9.0.1-essentials_build/bin/ffmpeg.exe", b"fake ffmpeg")
        archive.writestr("ffmpeg-9.0.1-essentials_build/bin/ffprobe.exe", b"fake ffprobe")
        archive.writestr("ffmpeg-9.0.1-essentials_build/LICENSE", b"GPL test license")
        if unsafe:
            archive.writestr("../escape.txt", b"unsafe")
    return payload.getvalue()


class FFmpegInstallTests(unittest.TestCase):
    def test_parses_and_compares_release_versions(self) -> None:
        self.assertEqual(parse_ffmpeg_version("ffmpeg version 9.0.1 Copyright"), "9.0.1")
        self.assertEqual(parse_ffmpeg_version("ffmpeg version 8.1 Copyright"), "8.1")
        self.assertTrue(installed_version_is_older("ffmpeg version 8.1 Copyright", "9.0.1"))
        self.assertFalse(installed_version_is_older("ffmpeg version 9.0.1 Copyright", "9.0.1"))
        self.assertIsNone(installed_version_is_older("ffmpeg version N-git", "9.0.1"))
        git_toolchain = Toolchain(
            Path("ffmpeg.exe"),
            Path("ffprobe.exe"),
            "System",
            "ffmpeg version 2026-08-06-git-95c43d7df7-full_build-www.gyan.dev Copyright",
            "ffprobe version 2026-08-06-git-95c43d7df7-full_build-www.gyan.dev Copyright",
        )
        self.assertEqual(concise_ffmpeg_version(git_toolchain), "2026-08-06-git-95c43d7df7-full_build-www.gyan.dev")

    def test_fetches_and_validates_current_release_metadata(self) -> None:
        checksum = "ab" * 32

        def opener(request: object, **_kwargs: object) -> FakeResponse:
            url = str(getattr(request, "full_url"))
            data = b"9.0.1\n" if url.endswith(".ver") else (checksum + "\n").encode()
            return FakeResponse(data, url)

        release = fetch_current_release(opener=opener)
        self.assertEqual(release.version, "9.0.1")
        self.assertEqual(release.sha256, checksum)

    def test_rejects_provider_redirect_to_unexpected_host(self) -> None:
        def opener(_request: object, **_kwargs: object) -> FakeResponse:
            return FakeResponse(b"9.0.1", "https://example.invalid/payload")

        with self.assertRaisesRegex(FFmpegInstallError, "unexpected FFmpeg download address"):
            fetch_current_release(opener=opener)

    def test_download_requires_matching_sha256_and_cleans_failure(self) -> None:
        data = b"archive payload"
        with tempfile.TemporaryDirectory(prefix="ffmpeg-download-test-") as folder:
            destination = Path(folder) / "release.zip"
            release = FFmpegRelease("9.0.1", "0" * 64)
            with self.assertRaisesRegex(FFmpegInstallError, "SHA-256 verification"):
                download_release_archive(
                    release,
                    destination,
                    opener=lambda request, **_kwargs: FakeResponse(data, str(request.full_url)),
                )
            self.assertFalse(destination.exists())

    def test_download_rejects_advertised_length_mismatch_and_cleans_failure(self) -> None:
        data = b"truncated archive"
        checksum = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory(prefix="ffmpeg-length-test-") as folder:
            destination = Path(folder) / "release.zip"
            release = FFmpegRelease("9.0.1", checksum)
            with self.assertRaisesRegex(FFmpegInstallError, "did not match"):
                download_release_archive(
                    release,
                    destination,
                    opener=lambda request, **_kwargs: FakeResponse(
                        data,
                        str(request.full_url),
                        reported_length=len(data) + 100,
                    ),
                )
            self.assertFalse(destination.exists())

    def test_extracts_only_expected_tools_and_docs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-extract-test-") as folder:
            root = Path(folder)
            archive_path = root / "release.zip"
            archive_path.write_bytes(make_archive())
            staging = root / "staging"
            staging.mkdir()
            ffmpeg, ffprobe = extract_release_archive(archive_path, staging)
            self.assertEqual(ffmpeg.read_bytes(), b"fake ffmpeg")
            self.assertEqual(ffprobe.read_bytes(), b"fake ffprobe")
            self.assertTrue((staging / "LICENSE").is_file())
            self.assertFalse((root / "escape.txt").exists())

    def test_rejects_unsafe_archive_member(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-unsafe-test-") as folder:
            root = Path(folder)
            archive_path = root / "release.zip"
            archive_path.write_bytes(make_archive(unsafe=True))
            staging = root / "staging"
            staging.mkdir()
            with self.assertRaisesRegex(FFmpegInstallError, "unsafe path"):
                extract_release_archive(archive_path, staging)
            self.assertFalse((root / "escape.txt").exists())

    def test_rejects_malformed_or_incomplete_archive(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-malformed-test-") as folder:
            root = Path(folder)
            malformed = root / "malformed.zip"
            malformed.write_bytes(b"not a zip")
            staging = root / "staging-malformed"
            staging.mkdir()
            with self.assertRaisesRegex(FFmpegInstallError, "not a readable ZIP"):
                extract_release_archive(malformed, staging)

            incomplete = root / "incomplete.zip"
            with zipfile.ZipFile(incomplete, "w") as archive:
                archive.writestr("ffmpeg-9.0.1/bin/ffmpeg.exe", b"fake ffmpeg")
            staging = root / "staging-incomplete"
            staging.mkdir()
            with self.assertRaisesRegex(FFmpegInstallError, "exactly one bin/ffprobe.exe"):
                extract_release_archive(incomplete, staging)

    def test_installs_to_versioned_app_subfolder_after_validation(self) -> None:
        archive = make_archive()
        checksum = hashlib.sha256(archive).hexdigest()
        release = FFmpegRelease("9.0.1", checksum)

        def validator(bin_directory: Path, expected: str) -> tuple[Path, Path]:
            self.assertEqual(expected, "9.0.1")
            ffmpeg = bin_directory / "ffmpeg.exe"
            ffprobe = bin_directory / "ffprobe.exe"
            self.assertTrue(ffmpeg.is_file())
            self.assertTrue(ffprobe.is_file())
            return ffmpeg, ffprobe

        with tempfile.TemporaryDirectory(prefix="ffmpeg-install-test-") as folder:
            root = Path(folder)
            installed = install_release(
                release,
                root,
                opener=lambda request, **_kwargs: FakeResponse(archive, str(request.full_url)),
                validator=validator,
            )
            self.assertEqual(installed, root / "ffmpeg" / "9.0.1" / "bin" / "ffmpeg.exe")
            self.assertTrue(installed.is_file())
            self.assertFalse(any(path.name.startswith(".installing-") for path in (root / "ffmpeg").iterdir()))

    def test_installed_pair_must_report_the_same_current_release(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-pair-test-") as folder:
            bin_directory = Path(folder)
            (bin_directory / "ffmpeg.exe").write_bytes(b"fake")
            (bin_directory / "ffprobe.exe").write_bytes(b"fake")
            with patch(
                "stream_copy_remuxer.ffmpeg_install._first_version_line",
                side_effect=("ffmpeg version 9.0.1 Copyright", "ffprobe version 8.1 Copyright"),
            ):
                with self.assertRaisesRegex(FFmpegInstallError, "older than the selected release"):
                    validate_installed_pair(bin_directory, "9.0.1")
            with patch(
                "stream_copy_remuxer.ffmpeg_install._first_version_line",
                side_effect=("ffmpeg version 9.0.1 Copyright", "ffprobe version 9.0.1 Copyright"),
            ):
                ffmpeg, ffprobe = validate_installed_pair(bin_directory, "9.0.1")
            self.assertEqual(ffmpeg, bin_directory / "ffmpeg.exe")
            self.assertEqual(ffprobe, bin_directory / "ffprobe.exe")

    def test_discovery_prefers_highest_app_local_version_and_uses_generic_label(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-discovery-test-") as folder:
            root = Path(folder)
            old = root / "ffmpeg" / "8.1" / "bin"
            current = root / "ffmpeg" / "9.0.1" / "bin"
            old.mkdir(parents=True)
            current.mkdir(parents=True)
            for directory in (old, current):
                (directory / "ffmpeg.exe").write_bytes(b"fake")
                (directory / "ffprobe.exe").write_bytes(b"fake")
            with patch("stream_copy_remuxer.tools.application_root", return_value=root), patch(
                "stream_copy_remuxer.tools.tool_version",
                side_effect=lambda path: f"ffmpeg version {path.parents[1].name}",
            ), patch("stream_copy_remuxer.tools.video_encoders", return_value=frozenset()), patch(
                "stream_copy_remuxer.tools._which", return_value=None
            ):
                toolchain = discover_toolchain()
            self.assertEqual(toolchain.ffmpeg, current / "ffmpeg.exe")
            self.assertEqual(toolchain.ffprobe, current / "ffprobe.exe")
            self.assertEqual(toolchain.source, "App local")

    def test_staging_promotion_retries_transient_windows_permission_error(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffmpeg-promotion-test-") as folder:
            root = Path(folder)
            staging = root / ".installing"
            final = root / "9.0.1"
            staging.mkdir()
            real_rename = __import__("os").rename
            attempts = {"count": 0}

            def transient(source: Path, destination: Path) -> None:
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise PermissionError(5, "temporary scanner lock")
                real_rename(source, destination)

            with patch("stream_copy_remuxer.ffmpeg_install.os.rename", side_effect=transient), patch(
                "stream_copy_remuxer.ffmpeg_install.time.sleep"
            ):
                _promote_staging_directory(staging, final)
            self.assertEqual(attempts["count"], 3)
            self.assertTrue(final.is_dir())


if __name__ == "__main__":
    unittest.main()
