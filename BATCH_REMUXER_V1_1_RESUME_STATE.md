# Stream Copy Remuxer v1.1.2 — Resume State

Last updated: 2026-08-17

## Current state

- Reliability state: **VERIFIED** for the exact v1.1.2 EXE and ZIP listed below.
- Project root / writable scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Authoritative editable baseline: the verified v1.0.3 source in the project root.
- Baseline source manifest: `qa\release-v1.0.3-onefile-final\source_manifest.json`.
  - SHA-256: `756a37a3ede2ace75f994c5d7059e8ee72e500060282f7a123a0828e04e0c823`.
  - All 24 baseline files rehashed with zero mismatches before edits.
- Protected rollback EXE: `release-stream-copy-remuxer-v1.0.3\Stream Copy Remuxer.exe`.
  - SHA-256: `b71f79807640d43195777930d7e9ef4e39351d0d553f00c641fbc280cfd20f95`.
- Protected rollback ZIP: `Stream-Copy-Remuxer-v1.0.3-Windows-x64.zip`.
  - SHA-256: `6018e37bbcba38ae3eb68887a3df7a9f9e0450eca46c260ec67dc88081885ae9`.
- Both rollback hashes were reverified unchanged at the final gate.
- Declared change surface: application source, tests, batch requirements/resume records, README, release scripts, and new versioned work/QA/release artifacts only.

## Final deliverables

- Executable: `release-stream-copy-remuxer-v1.1.2\Stream Copy Remuxer.exe`
  - Size: 11,604,843 bytes.
  - SHA-256: `ebf3626bbba9f84b329ce17d7991763bc800789b089af7073380921e67d31521`.
  - Authenticode: NotSigned.
- ZIP: `Stream-Copy-Remuxer-v1.1.2-Windows-x64.zip`
  - Size: 11,384,860 bytes.
  - SHA-256: `3a16da37254dfcf2b9d4239e67e3a6e75bc96277a5694ae5315b7d0f2a7b04a8`.
- Release manifest: `release-stream-copy-remuxer-v1.1.2\release_manifest.json`.
- Final source manifest: `qa\release-v1.1.2-onefile-final\source_manifest.json` (excludes itself by design).

## Acceptance and test evidence

- Complete checklist: `BATCH_REMUXER_V1_1_REQUIREMENTS.md` — every requirement checked.
- Baseline regression suite: PASS — 26 tests in 4.435 seconds before edits.
- Final source suite: PASS — 37 tests in 4.631 seconds under `-W error` after the last application/test changes.
- Source self-test: `qa\source-self-test-v1.1.2.json` — PASS.
  - 26/26 top-level checks and 20/20 GUI checks.
  - Size: 10,374 bytes.
  - SHA-256: `d5369fd0c39dfea8af140160b05b8a1389ffe6d9805c6ed57f247a2818769f5a`.
- Staged packaged self-test: `qa\release-v1.1.2-onefile-final\packaged-self-test.json` — PASS, version 1.1.2.
- Freshly ZIP-extracted packaged self-test: `qa\release-v1.1.2-onefile-final\packaged-self-test-from-zip.json` — PASS, version 1.1.2.
- ZIP integrity report: `qa\release-v1.1.2-onefile-final\zip-integrity.json` — PASS, including manifest version, file count, size, and SHA-256 checks.
- Real packaged test coverage includes:
  - a synchronous Unicode `WM_DROPFILES` payload containing two sources;
  - multiple queue rows, MP4 default, Delete-row behavior, exact requested description, absent redundant heading, and the per-row custom-output control;
  - FFV1+AAC/MKV → finalized MP4 with 25 indexed frames;
  - MPEG-4+PCM/AVI → MKV;
  - sequential batch execution, two different output containers, codec preservation, reports, source identity, and no leftover partial/preflight files.
- Existing real integration coverage remains green for MP4/MOV/MKV, long Unicode paths, incompatible attachments, cancellation, output races, insufficient space, source changes, and no-overwrite behavior.
- Static final audit: PASS — zero TODO/FIXME/HACK markers, unsafe shell-process patterns, stale delivery-version strings, or application-module PyInstaller warnings.
- Release reconciliation: PASS — 6 manifest records plus the manifest itself exactly match 7 release files.
- Skeptical audit: PASS after correcting every material finding and rebuilding/retesting the exact v1.1.2 archive.

## Implemented design

- Add files through a multi-select picker or native Windows drag-and-drop.
- Probe files sequentially off the GUI thread and show actual FFprobe input container plus video/audio codecs.
- Apply an MP4/MOV/MKV dropdown to selected rows; initial and new-file default is MP4.
- Write outputs beside each source by default, optionally use one common folder, or assign one exact custom output to a selected row.
- Allocate nonconflicting automatic paths across the queue and fail closed on duplicate/invalid custom outputs.
- Process files sequentially through the original verified `RemuxEngine.run` preflight/copy/verification/promotion boundary.
- Continue after per-file failure, cancel safely, preserve completed outputs, and leave unstarted/failed rows retryable.
- Lock queue-mutating controls during a run and continue draining completion events during close/cancel.
- Delete and Clear affect queue rows only; they never delete media or reports.

## Failed or superseded methods

- The first expanded test run exposed direct background Tk callbacks outside the main loop. Production callbacks were replaced by a polled main-thread event queue.
- Repeated hidden-GUI tests exposed delayed Tcl collection on a worker thread. Probe workers were decoupled from the app object and test interpreters are collected on the main thread.
- The v1.1.0 candidate passed packaged tests but was superseded after audit found close-during-batch stopped draining completion events.
- The v1.1.1 candidate passed packaged tests but was superseded after audit found the prior exact custom-output filename capability had not been preserved.
- v1.1.2 restores that control, makes output replanning fail closed, and passes all source/staged/extracted gates.
- Ruff was checked but is not installed in the verified Python environment. Warnings-as-errors tests, compilation, static searches, PyInstaller analysis, and exact packaged execution were used instead.

## Remaining limitations and risks

- The queue is intentionally sequential and is not persisted after application close.
- Broad file recognition does not mean every input codec can be copied into every output container. The preflight rejects incompatible combinations safely. Real batch tests covered MKV and AVI; every listed legacy extension was not independently encoded and remuxed.
- The native drop handler was exercised with the same Unicode `WM_DROPFILES`/CF_HDROP mechanism used by File Explorer, but a human pointer drag was not performed because foreground desktop control was not authorized.
- Windows can block Explorer drops into an intentionally elevated app; this executable does not request elevation, and Add files remains available.
- Verification avoids a second full-file packet hash pass and no 100+ GiB batch was run. Existing codec/property/index/source checks avoid doubling large-file I/O.
- The executable is unsigned, so Windows may show SmartScreen or an unrecognized-publisher warning.

## Exact next action

Extract `Stream-Copy-Remuxer-v1.1.2-Windows-x64.zip`, open `Stream Copy Remuxer.exe`, drag or add a small representative set, select rows to change MP4/MOV/MKV as needed, and run the batch. Keep original files until the outputs have been validated in the intended software.
