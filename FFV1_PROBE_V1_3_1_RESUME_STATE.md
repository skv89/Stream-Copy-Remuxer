# Stream Copy Remuxer v1.3.1 — FFV1 Probe Reliability Resume State

Last updated: 2026-08-17

## Current state

- Reliability state: **VERIFIED**.
- Project root and writable scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Complete checklist: `FFV1_PROBE_V1_3_1_REQUIREMENTS.md`.
- Authoritative source: verified v1.3.0 project source.
- Baseline source manifest: `qa\release-v1.3.0-onefile-final\source_manifest.json`.
  - Manifest SHA-256: `2c92fc108fee231c8dc698babaafa2937502c3b9aab831057a2dad3486df7453`.
  - Source-set SHA-256: `0799be181cddb8eb89742a48d755ee4068a18efa01cc2d183a08de44b1c05f06`.
  - All 38 source records reverified before editing.
- Pre-edit checkpoint: `work\stream-copy-remuxer-v1.3.1-baseline-source`; all 38 copied files match the v1.3.0 manifest.
- Target release: v1.3.1; v1.3.0 and earlier releases are protected.

## User evidence and reproduced cause

- Screenshot inspected: `C:\Users\Doug\AppData\Local\Temp\codex-clipboard-17aff7d7-884c-42cf-9c43-266d23445ba3.png`.
- Regression input:
  `D:\-= Chinese Videos =-\The Mystery Files 迷离档案 (1997) 1-20\Mystery.Files.S01E01.1997.1080p.MyTVSuper.WEB-DL.H265.AAC-ZerTV_cropped.mkv`.
- Input identity before testing: 21,622,935,574 bytes; last write `2026-08-17T00:09:57.4873944-07:00`.
- Default FFprobe completed in 0.036 seconds but returned no FFV1 `pix_fmt`.
- FFprobe with `-analyzeduration 10000000` completed in 0.034 seconds and returned `yuv420p`; increasing `probesize` alone did not resolve the property.
- A 0.5-second FFmpeg stream-copy preflight with the same analysis option completed in 0.041 seconds and produced a 381,740-byte MP4 containing FFV1 1424x1080 `yuv420p` with 13 indexed frames and AAC 48 kHz stereo.
- Root cause: v1.3.0 correctly performs strict stream-preservation comparisons, but its initial FFprobe receives Matroska's zero analysis-duration default and records an empty pixel format. The preflight output is more completely identified as `yuv420p`, causing a false mismatch.
- This is a probing-depth defect, not re-encoding, codec loss, or MP4 incompatibility.

## Baseline and declared change surface

- Unchanged v1.3.0 baseline suite: **PASS**, 58 tests in 4.131 seconds under warnings-as-errors.
- Intended code surface: `stream_copy_remuxer/probe.py`, the FFmpeg input-option construction in `stream_copy_remuxer/engine.py`, focused tests, version/build defaults, and release documentation.
- Protected behavior: exact preservation matching, final verification, remux engine safety, batch/UI features, FFmpeg installer security, and all prior releases.

## Implementation decision

- Use a bounded 10-second media-analysis budget (`10,000,000` microseconds) for FFprobe and FFmpeg input opening.
- Keep the exact source/preflight and source/final signature comparisons unchanged. This repairs missing source metadata rather than accepting ambiguous mismatches.
- Do not run a full 20.14 GiB duplicate remux solely for this preflight defect; validate the exact corrected preflight path on the real file and validate complete remux/publish behavior with the existing small real-media integration and packaged self-tests.

## Failed or superseded methods

- A full SHA-256 pass over the 20.14 GiB regression input was stopped because it was unnecessary for a read-only preflight diagnosis; size and nanosecond modification identity are the same invariants the application itself protects.
- Raising `probesize` alone to 10, 20, or 50 MB did not reveal the pixel format and is not the selected correction.
- The first exact-command harness tried to print a Unicode JSON command through a CP1252 console and exited before FFmpeg started. The accepted harness writes UTF-8 JSON directly and passed; no media or report was produced by the failed attempt.

## Implemented and verified source state

- Source version: **1.3.1**.
- `stream_copy_remuxer/probe.py` passes `-analyzeduration 10000000` to FFprobe.
- `stream_copy_remuxer/engine.py` passes the same option before `-i` for both preflight and full remux commands.
- The strict preservation implementation in `stream_copy_remuxer/verification.py` is byte-identical to v1.3.0; a new regression explicitly confirms that an unknown source pixel format is not treated as a wildcard.
- New focused probe coverage parses FFV1 1424x1080 `yuv420p`, AAC 48 kHz stereo, verifies command ordering, and confirms the 120-second process timeout remains.
- Final source suite: **PASS**, 60 tests in 4.218 seconds under warnings-as-errors.
- Final source self-test: `qa\source-self-test-v1.3.1-final.json` — **PASS**, all 29 top-level checks, 2 completed remuxes, 0 failures, TkDND registered, and 100%/150%/200% layouts passed.
- Real source probe: `qa\ffv1-real-source-probe-v1.3.1.json` — FFV1 1424x1080 `yuv420p` and AAC 48 kHz stereo recovered.
- Exact real-source preflight gate: `qa\ffv1-real-preflight-gate-v1.3.1.json` — **PASS** in 0.040 seconds; exact core properties, stream copy, analysis-option ordering, positive FFV1 frame count, and unchanged source identity all passed.
- Full remux/publish check on a 2-second stream-copied sample derived from the real source: **PASS**; output and audit report published, every verification check passed, and FFV1/AAC properties were preserved.
- Change-surface audit: 10 of 38 v1.3.0 files changed, all within the declared surface; 28 stayed byte-identical. Core final verification, planning, and FFmpeg installer modules remain byte-identical.
- Protected v1.3.0 EXE/ZIP hashes still match their authoritative values.

## Exact delivered artifacts

- Standalone folder: `release-stream-copy-remuxer-v1.3.1`.
- Standalone EXE: `release-stream-copy-remuxer-v1.3.1\Stream Copy Remuxer.exe`.
  - Size: 11,883,730 bytes.
  - SHA-256: `5631b089e9ba740151b60e4d46dd0b431a0bc27b9239edf139958f45c315a224`.
  - Authenticode: `NotSigned` (accepted existing project limitation).
- ZIP: `Stream-Copy-Remuxer-v1.3.1-Windows-x64.zip`.
  - Size: 11,666,083 bytes.
  - SHA-256: `e8e768310ad72cc78f1b3702230003759c843cad43384ff6199bc978fc72c7fd`.
- The release EXE and freshly ZIP-extracted EXE hashes match exactly.
- The package contains the EXE, README, notices, manifest, and four license files; FFmpeg and FFprobe are not bundled.

## Final packaged and skeptical gates

- Staged packaged self-test: `qa\release-v1.3.1-onefile-final\packaged-self-test.json` — **PASS**.
- Fresh ZIP integrity: `qa\release-v1.3.1-onefile-final\zip-integrity.json` — **PASS**, 8/8 files present and matching the release manifest.
- Freshly extracted EXE self-test: `qa\release-v1.3.1-onefile-final\packaged-self-test-from-zip.json` — **PASS**.
- Staged and extracted self-tests each passed all 29 top-level checks, including bounded input analysis before `-i`, and completed 2/2 real remuxes with 0 failures.
- Freshly extracted EXE real-source probe: `qa\release-v1.3.1-onefile-final\packaged-real-source-probe.json` — **PASS**, FFV1 1424x1080 `yuv420p` and AAC 48 kHz stereo on the exact reported 20.14 GiB source.
- Release manifest records `input_analyze_duration_microseconds: 10000000`; every manifest file hash and size passed fresh archive verification.
- PyInstaller warning review found only expected cross-platform or optional modules; no application module is missing.
- Final source manifest: `qa\release-v1.3.1-onefile-final\source_manifest.json` (excludes itself by design).
- Final skeptical audit: `qa\release-v1.3.1-onefile-final\final-audit.json`.
- The reported source's size and nanosecond modification identity remain unchanged after all probes/preflights.
- Protected v1.3.0 EXE and ZIP remain byte-identical.

## Remaining work and exact next action

- No implementation or verification work remains.
- Exact next action: deliver the v1.3.1 EXE/ZIP and explain the corrected false preflight mismatch.
