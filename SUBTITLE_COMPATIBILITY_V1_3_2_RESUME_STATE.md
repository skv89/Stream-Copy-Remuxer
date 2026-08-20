# Stream Copy Remuxer 1.3.2 — resume state

## Current state

- Reliability state: **VERIFIED**.
- Project root: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Writable scope: the project root.
- Requirements: `SUBTITLE_COMPATIBILITY_V1_3_2_REQUIREMENTS.md`.

## Authoritative source and protection

- Authoritative baseline manifest: `qa\release-v1.3.1-onefile-final\source_manifest.json`.
- Manifest SHA-256: `b2e979606bb44beb5fef5ccfb8135193dbb00cccc1359d421fff9182b0072470`.
- Source-set SHA-256: `a08244511961ebad692d1f4afcfb532bb158a6ab5b94bc6140cc0d9006b6c4ea`.
- All 41 current source records independently matched the manifest before editing.
- Verified baseline checkpoint: `work\stream-copy-remuxer-v1.3.2-baseline-source` (41 copied records, 0 hash mismatches).
- Protected v1.3.1 EXE SHA-256: `5631b089e9ba740151b60e4d46dd0b431a0bc27b9239edf139958f45c315a224`.
- Protected v1.3.1 ZIP SHA-256: `e8e768310ad72cc78f1b3702230003759c843cad43384ff6199bc978fc72c7fd`.
- Exact regression source must remain read-only and identity-protected by size plus nanosecond mtime.

## Diagnosis

- Exact-source probe inventory: stream 0 FFV1 video, stream 1 AAC audio, streams 2 and 3 SubRip subtitles (Traditional and Simplified).
- The user selected `All source streams`. FFmpeg correctly rejects copied SubRip in both MP4 and MOV.
- This is distinct from the v1.3.1 pixel-format defect. FFV1 now probes correctly; the remaining failure is a real container/stream incompatibility.
- Subtitle conversion to `mov_text` would violate the requested `-c copy` / no-re-encoding contract.
- Selected design: add compatibility-aware and video-only modes with explicit omission disclosure, and retain strict all-stream mode so no stream is ever silently discarded.
- Video-only is a user-requested maximum-compatibility option: it copies video and deliberately excludes audio, subtitle, attachment, and data streams.
- Details log has been increased from 5 rows to 10.

## Baseline testing

- Correct non-GUI and integration behavior passed before edits.
- Two attempted general source-suite runtimes exposed environment-only GUI failures:
  - Python 3.14 lacks a usable Tcl installation and cannot create Tk.
  - The Python 3.11 build virtual environment cannot load TkDND outside the packaged runtime.
  - Python 3.13's installed TkDND DLL reports a bitness mismatch.
- These six GUI-runtime errors are baseline environment failures, not application regressions. The final packaged executable self-test remains the authoritative GUI/TkDND gate, as in v1.3.1.
- The v1.3.1 packaged self-test and recorded final audit were already verified; final v1.3.2 source logic tests will be separated from packaged GUI tests where necessary.

## Declared change surface

- Expected production changes: `stream_copy_remuxer/models.py`, `planning.py`, `engine.py`, `verification.py`, `gui.py`, version metadata, CLI/self-test, build/verification scripts, README/notices.
- Expected test changes: planning, engine, verification, GUI, integration, and helper fixtures.
- New requirements/resume and final QA records are authorized.
- Protected behavior: source safety, strict verification, `-c copy`, FFV1 handling, batch/UI/output/installer behavior, and all v1.3.1 artifacts.

## Acceptance status

- [x] Authoritative v1.3.1 baseline identified and independently verified.
- [x] Pre-edit checkpoint created and hash-verified.
- [x] Exact source stream inventory and failure mechanism established.
- [x] Compatibility-aware selection implemented.
- [x] Video-only selection and disclosure implemented.
- [x] Strict all-stream early diagnostic implemented.
- [x] Details log increased from 5 to 10 rows.
- [x] Focused/unit/integration tests pass: 68 source tests under warnings-as-errors, including real FFmpeg video-only output.
- [x] Exact-source MP4/MOV/MKV gates pass: compatible MP4/MOV, video-only MP4/MOV, strict MKV preservation, and strict MP4/MOV early rejection.
- [x] v1.3.2 package and ZIP pass final release checks: staged and freshly extracted self-tests each passed 49 top-level checks, 42 GUI checks, four remux plans, and all DPI/layout checks.
- [x] Final audit is clean.

## Failed or superseded methods

- `python -m unittest discover -s tests` was incorrect for tests using package-relative imports; use `-s tests -t .`.
- Direct execution of `scripts\verify_exact_subtitle_compatibility.py` does not establish the project package root; invoke it as `python -m scripts.verify_exact_subtitle_compatibility`.
- The unbundled local Python/Tk combinations listed above cannot currently run the six GUI tests. Do not treat those environment failures as code failures or repeatedly rerun them unchanged. Use logic tests plus the packaged GUI/TkDND self-test and DPI audit.
- Running a frozen Tcl/Tk executable inside the Codex filesystem sandbox currently denies Tcl's native read of its bundled `init.tcl`; even the unchanged v1.3.1 EXE reproduces this environment-only error. The v1.3.2 staged and freshly extracted hidden GUI self-tests both pass outside that sandbox boundary under the normal Windows execution context.

## Exact next action

Deliver `release-stream-copy-remuxer-v1.3.2\Stream Copy Remuxer.exe` and `Stream-Copy-Remuxer-v1.3.2-Windows-x64.zip` with the verified usage guidance in `README.md`.
