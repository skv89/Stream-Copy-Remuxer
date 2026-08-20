# Stream Copy Remuxer v1.3.0 — Output Location and Status-Column Resume State

Last updated: 2026-08-17

## Current state

- Reliability state: **VERIFIED**.
- Project root and writable scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Complete checklist: `DESTINATION_OUTPUT_V1_3_REQUIREMENTS.md`.
- Authoritative source: verified v1.2.0 project source.
- Baseline manifest: `qa\release-v1.2.0-onefile-final\source_manifest.json`.
  - Manifest SHA-256: `c3e75a87b45042c584092f53dc840bc6cbccd9aa2e2b3d4711bd059da5b8aeed`.
  - Source-set SHA-256: `c71c7c1b4f0d4e89bacf190cdef42139bb472feb2b72af6ca5a43843e1d2c911`.
- Pre-edit source checkpoint: `work\stream-copy-remuxer-v1.3.0-baseline-source`; all 36 copied files match the v1.2.0 manifest.
- Protected v1.2.0 EXE SHA-256: `d5604a07bf987dacfecbe51e654aa3f3c15c4b8166e6382a2ced955b3af74873`.
- Protected v1.2.0 ZIP SHA-256: `cf8fa77c42823a58818b8359a3420d84d5b4c0f8e85ed26674725f3721da67bc`.
- Target release: v1.3.0.

## User evidence and baseline behavior

- Screenshots inspected:
  - `C:\Users\Doug\AppData\Local\Temp\codex-clipboard-342372ed-ab28-4c36-ab07-41356008c7a9.png`.
  - `C:\Users\Doug\AppData\Local\Temp\codex-clipboard-8e35e300-8ea7-4f64-9307-e532e76e7d3d.png`.
- `Show output` currently launches `explorer.exe` with a combined `/select,<output>` argument. On the user's valid Unicode output path, Explorer opens Documents instead of the output folder.
- Status is the last Treeview column and is configured with `stretch=False`, leaving it fixed and difficult or impossible to enlarge at the trailing edge.
- The planning layer already supports an optional output directory, but the batch allocator and v1.2.0 GUI intentionally do not expose or pass it.
- Baseline native command: `python -W error -m unittest discover -s tests -t .`.
  - Result: **PASS**, 54 tests in 5.054 seconds.

## Declared change surface

- `stream_copy_remuxer.gui`: output-folder opening, destination controls/state, planning integration, Status column sizing, confirmation text, GUI self-tests.
- `stream_copy_remuxer.batch`: optional common destination passed through to collision-safe planning.
- Focused tests, documentation, version, build/verification defaults, preview tooling, and new v1.3.0 QA/release artifacts.
- Remux engine, probe model, verification rules, FFmpeg installer security, prior releases, and unrelated Topaz investigation files are protected unless a regression test demonstrates a required correction.

## Implementation decisions

- Version v1.3.0 is used because the optional common destination is a new user-facing feature, while the output-folder and Status fixes are included in the same compatible release.
- Blank destination means `None` internally and preserves per-source output folders.
- A nonblank destination applies to all uncompleted rows; completed rows retain their recorded outputs.
- `Show output` will open the exact result's parent directory through a test-injectable Windows folder opener.
- Status will be stretchable and sized using the active Treeview font so normal status text is visible at common DPI scales.

## Implemented and verified source state

- Source version: **1.3.0**.
- `Show output` opens the selected completed output's exact parent folder, or the latest completed output folder when no completed row is selected, through `os.startfile`.
- The Status column is stretchable and its DPI-aware initial/minimum widths cover normal status text.
- Output settings include a blank-by-default destination entry plus Browse and Clear controls.
- Blank planning remains beside each source; a nonblank existing directory receives all uncompleted batch outputs with collision-safe suffixes.
- Completed outputs remain locked when the destination changes, and destination controls are locked while a batch is active.
- Full pinned-runtime suite: **PASS**, 58 tests in 5.049 seconds under warnings-as-errors.
- Exact source self-test: `qa\source-self-test-v1.3.0-final.json` — **PASS**; 2 completed, 0 failed; TkDND registered; common-destination and 100%/150%/200% DPI checks passed.
- Inspected GUI preview: `qa\gui-preview-v1.3.0-working.png` — one-line description, blank destination control, readable Status column, and bounded layout confirmed.
- Bytecode compilation under warnings-as-errors: **PASS**.
- Static scan found no application use of `explorer.exe`, `/select,`, `shell=True`, `os.system`, or unresolved TODO/FIXME/HACK markers.
- Protected v1.2.0 EXE and ZIP hashes still match their authoritative values.
- Non-authoritative system Python 3.14 lacks TkinterDnD2 and cannot run the drag/drop gate; the pinned Python 3.11/TkinterDnD2 0.6.2 build runtime is the authoritative test/build environment.

## Exact delivered artifacts

- Standalone folder: `release-stream-copy-remuxer-v1.3.0`.
- Standalone EXE: `release-stream-copy-remuxer-v1.3.0\Stream Copy Remuxer.exe`.
  - Size: 11,884,883 bytes.
  - SHA-256: `4233b9a5ffab91d6bfd690ab4b39e789729835e1b005b5807b5b0d4598beb70e`.
  - Authenticode: `NotSigned` (accepted existing project limitation).
- ZIP: `Stream-Copy-Remuxer-v1.3.0-Windows-x64.zip`.
  - Size: 11,667,070 bytes.
  - SHA-256: `4572966cc7113c348523415c292bd0bf6f62e4000f5374b1aedddb6da6bb2893`.
- The release EXE and freshly ZIP-extracted EXE hashes match exactly.
- The package contains the EXE, README, notices, manifest, and four license files; it does not bundle FFmpeg or FFprobe.

## Final release gates

- Staged packaged self-test: `qa\release-v1.3.0-onefile-final\packaged-self-test.json` — **PASS**.
- Fresh ZIP integrity: `qa\release-v1.3.0-onefile-final\zip-integrity.json` — **PASS**, 8/8 files present and matching the release manifest.
- Freshly extracted EXE self-test: `qa\release-v1.3.0-onefile-final\packaged-self-test-from-zip.json` — **PASS**.
- Staged and extracted self-tests each completed 2/2 real FFmpeg remuxes with 0 failures and passed all 28 top-level checks.
- PyInstaller warning review: only expected cross-platform or optional modules were listed; no application module was missing.
- Skeptical change-surface audit: 11 of 36 v1.2.0 baseline files changed, all within the declared surface; 25 remained byte-identical. The remux engine, probe, core planning, and FFmpeg installer remained byte-identical.
- Final source manifest: `qa\release-v1.3.0-onefile-final\source_manifest.json` (excludes itself by design).
- Final audit: `qa\release-v1.3.0-onefile-final\final-audit.json`.
- Protected v1.2.0 artifacts remained byte-identical after release creation.

## Remaining work and exact next action

- No implementation or verification work remains.
- Exact next action: deliver the v1.3.0 EXE/ZIP paths and verification summary to the user.
