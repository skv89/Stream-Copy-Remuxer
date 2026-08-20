# Stream Copy Remuxer v1.3.1 — FFV1 Probe Reliability Requirements

## Authoritative baseline and evidence

- [x] Use the verified v1.3.0 source in `C:\Users\Doug\Documents\ChatGPT\Topaz Video` as the editable baseline.
- [x] Verify all 38 records in `qa\release-v1.3.0-onefile-final\source_manifest.json` before editing.
- [x] Preserve v1.3.0 and every earlier EXE/ZIP; deliver a new v1.3.1 release without overwriting them.
- [x] Preserve a pre-edit checkpoint at `work\stream-copy-remuxer-v1.3.1-baseline-source` and verify every copied hash.
- [x] Treat the user's reported file as the real regression input:
  `D:\-= Chinese Videos =-\The Mystery Files 迷离档案 (1997) 1-20\Mystery.Files.S01E01.1997.1080p.MyTVSuper.WEB-DL.H265.AAC-ZerTV_cropped.mkv`.
- [x] Record its pre-test identity as 21,622,935,574 bytes with last-write time `2026-08-17T00:09:57.4873944-07:00`.
- [x] Reproduce that default FFprobe reports FFV1 1424x1080 with an unknown pixel format, while a 10-second analysis budget reports `yuv420p` in essentially the same wall time.
- [x] Reproduce that a 0.5-second stream-copy MP4 preflight retains FFV1 `yuv420p`, AAC stereo, and an indexed FFV1 frame count.

## Required correction

- [x] Give FFprobe an explicit 10,000,000-microsecond input analysis budget so FFV1 properties can be discovered from initial packets when the container header is insufficient.
- [x] Give FFmpeg preflight and full-remux input opening the same analysis budget, before `-i`, to avoid the corresponding unspecified-pixel-format warning and keep both phases consistent.
- [x] Keep the strict codec/core-property comparison; do not treat unknown source properties as wildcards or otherwise weaken stream-preservation validation.
- [x] Keep `-c copy`; do not decode/re-encode video or audio.
- [x] Keep the existing 120-second FFprobe process timeout and all source-identity, no-overwrite, cleanup, verification, and atomic-promotion safeguards.
- [x] Produce an actionable diagnostic if probing or compatibility checking genuinely fails.

## Regression preservation

- [x] Preserve MP4/MOV/MKV output selection, MP4 default, video+audio/all-stream modes, FFV1-in-MP4 indexing, metadata/chapters, compatibility notes, and audit reports.
- [x] Preserve batch destination behavior, collision-safe `_remux` naming, completed-output locking, Show output, and the resizable Status column.
- [x] Preserve TkDND/OLE2 multi-file drag/drop, Delete-row behavior, Unicode paths, FFmpeg detection/install, GUI responsiveness, cancellation, and CLI modes.
- [x] Preserve the one-line description and verified 100%/150%/200% DPI layout.

## Verification and delivery gates

- [x] Record the unchanged v1.3.0 baseline suite result under warnings-as-errors.
- [x] Add focused unit tests proving the analysis option is present, correctly ordered before `-i`, and does not alter stream-copy mapping or encoding mode.
- [x] Add probe-level regression coverage for parsing the recovered FFV1 pixel format.
- [x] Run the complete source test suite under warnings-as-errors with the pinned Tcl/Tk/TkDND runtime.
- [x] Run the complete source self-test, including real small-file FFV1/AAC remuxes and DPI/TkDND checks.
- [x] Run the corrected probe and exact preflight gate against the user's 20.14 GiB source without creating a full duplicate output.
- [x] Confirm the real-file preflight comparison is exact: source and output both FFV1 1424x1080 `yuv420p`, with AAC 48 kHz stereo.
- [x] Build a new standalone v1.3.1 EXE and ZIP.
- [x] Run staged and freshly ZIP-extracted packaged self-tests and verify archive integrity.
- [x] Verify exact source, EXE, ZIP, package-manifest, and protected-v1.3.0 hashes.
- [x] Complete a skeptical final audit with no unresolved material defect.

## Reliability states

- **WORKING:** implementation or testing remains incomplete.
- **CANDIDATE:** v1.3.1 artifacts exist, but one or more applicable gates remain.
- **VERIFIED:** every applicable gate passes on the exact delivered artifacts.
- **BLOCKED:** an external dependency or authority prevents completion after safe alternatives are exhausted.
