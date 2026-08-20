from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import traceback
from pathlib import Path

from stream_copy_remuxer.ffmpeg_install import (
    fetch_current_release,
    install_release,
    parse_ffmpeg_version,
    validate_installed_pair,
)
from stream_copy_remuxer.tools import tool_version


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run() -> dict[str, object]:
    release = fetch_current_release()
    progress = {"downloaded_bytes": 0, "content_length": None}

    def updated(downloaded: int, total: int | None) -> None:
        progress["downloaded_bytes"] = downloaded
        progress["content_length"] = total

    with tempfile.TemporaryDirectory(prefix="stream-copy-remuxer-real-install-") as folder:
        root = Path(folder)
        installed = install_release(release, root, on_progress=updated)
        ffmpeg, ffprobe = validate_installed_pair(installed.parent, release.version)

        def refuse_network(*_args: object, **_kwargs: object) -> object:
            raise AssertionError("A valid existing app-local release should be reused without downloading again.")

        reused = install_release(release, root, opener=refuse_network)
        version_line = tool_version(ffmpeg)
        parsed = parse_ffmpeg_version(version_line)
        license_files = sorted(
            path.name for path in installed.parents[1].iterdir() if path.is_file() and "license" in path.name.lower()
        )
        leftovers = sorted(
            path.name for path in installed.parents[2].iterdir() if path.name.startswith(".")
        )
        checks = {
            "release_metadata_valid": bool(release.version and len(release.sha256) == 64),
            "archive_downloaded": int(progress["downloaded_bytes"] or 0) > 0,
            "content_length_honored": (
                progress["content_length"] is None
                or progress["downloaded_bytes"] == progress["content_length"]
            ),
            "ffmpeg_installed": ffmpeg.is_file(),
            "ffprobe_installed": ffprobe.is_file(),
            "version_matches_release": parsed == release.version,
            "versioned_app_subfolder": installed == root / "ffmpeg" / release.version / "bin" / "ffmpeg.exe",
            "license_material_preserved": bool(license_files),
            "existing_install_reused_without_network": reused == installed,
            "no_staging_leftovers": not leftovers,
        }
        return {
            "schema": 1,
            "application": "Stream Copy Remuxer",
            "test": "real FFmpeg installer smoke test",
            "passed": all(checks.values()),
            "checks": checks,
            "release": {
                "version": release.version,
                "sha256": release.sha256,
                "archive_url": release.archive_url,
            },
            "download": progress,
            "installed": {
                "relative_ffmpeg": str(installed.relative_to(root)),
                "ffmpeg_size": ffmpeg.stat().st_size,
                "ffmpeg_sha256": file_hash(ffmpeg),
                "ffprobe_size": ffprobe.stat().st_size,
                "ffprobe_sha256": file_hash(ffprobe),
                "version_line": version_line,
                "license_files": license_files,
            },
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        payload = run()
    except Exception as exc:
        payload = {
            "schema": 1,
            "application": "Stream Copy Remuxer",
            "test": "real FFmpeg installer smoke test",
            "passed": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    output = args.output.resolve(strict=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
