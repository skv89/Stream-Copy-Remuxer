# Stream Copy Remuxer 1.4.0 — Final Resume State

Last updated: 2026-08-20

## Authoritative source and release

- Workspace: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`
- Branch: `codex/transcoding-v1.4.0`
- Baseline commit: `4e687835a968cb02a551f3e8822c29c96a0b34d9`
- Requirements: `TRANSCODING_V1_4_REQUIREMENTS.md`
- Release folder: `release-stream-copy-remuxer-v1.4.0`
- Release ZIP: `Stream-Copy-Remuxer-v1.4.0-Windows-x64.zip`
- Final QA: `qa\release-v1.4.0-onefile-final`
- EXE SHA-256: `6b62ddb01ba051363ba29c5da542a909a23651a0477f11615a43fbe68fb3297a`
- ZIP SHA-256: `4f12c702183366c84f6c011c3182fc7a605e9a76594528eb6032abf5cf108d0f`
- User-owned unrelated untracked paths preserved and excluded: `Launch-Topaz-SLP-Benchmark.ps1`, `SLP26_HIGH_VRAM_INVESTIGATION_RESUME_STATE.md`, `slp_high_vram_override/`, and `tools/`.

## Implemented behavior

- Stream copy remains the default and continues to support MP4, MOV, and MKV.
- Added source-aware ProRes 4444 XQ/422 HQ and DNxHR 444/HQX/HQ MOV modes.
- Added H.264 x264 placebo, H.264 NVENC P7/HQ, HEVC x265 veryslow, HEVC NVENC P7/UHQ, SVT-AV1 preset 0, and AV1 NVENC P7/UHQ MP4 modes.
- H.264 x264 is fixed at 8-bit 4:2:0. H.264 NVENC contains every requested option, including `p7`, `hq`, VBR-CQ, full-resolution multipass, four B-frames, `b_ref_mode=middle`, 27-frame rate-control lookahead, lookahead level 3, spatial AQ off, and temporal AQ on.
- CRF/CQ is editable per selected row, defaults to 12, uses encoder-specific bounds, and blocks invalid input.
- Added reusable high-contrast contextual encoding and stream help.
- Every transcode is explicitly identified as lossy. Selected non-video streams retain the existing stream-copy and compatibility policy.
- Exact resolved encoders, source/output pixel formats, options, quality, commands, probes, and verification results are recorded in `.transcode.json` audit reports.
- Input capability detection now records FFmpeg's exact exposed video encoders.
- Existing optional destination, Show output, drag-and-drop, video-only, compatibility omission, collision prevention, atomic publication, and audit behavior remain covered.

## Final validation evidence

- Full source suite on the Python 3.11/TkDND release runtime: **99 tests passed, 1 hardware-dependent test skipped**.
- The skip is expected on this machine: its current NVIDIA GPU/driver exposes `h264_nvenc` but rejects the explicitly requested `lookahead_level 3` with maximum level 0. The app retains the user's exact settings and reports this during its disposable preflight instead of silently weakening them.
- Real FFmpeg 9.0.1 integration tests passed for stream copy, ProRes, DNxHR, x264, x265, and SVT-AV1, including copied audio and exact output verification.
- Final packaged one-file EXE self-test passed, including TkDND/OLE2 registration, repeated Unicode drag/drop dispatch, help reuse/contrast/content, per-row profile and quality state, fixed containers, video-only mode, common destination, and 100/150/200% DPI layout checks.
- The exact EXE freshly extracted from the ZIP passed the complete packaged self-test and dependency check (`qa\release-v1.4.0-onefile-final\extracted-self-test.json` and `extracted-dependency-check.json`).
- Fresh ZIP extraction and every manifest size/hash check passed (`qa\release-v1.4.0-onefile-final\zip-integrity.json`).
- Main-window and encoding-help previews were visually inspected (`gui-main-preview.png` and `gui-encoding-help-preview.png`).
- `python -m compileall` and `git diff --check` passed after the final source changes.

## Failed methods and retained diagnostics

- Running a bundled Tcl/Tk executable inside the managed filesystem sandbox could not read its extracted `init.tcl`; the same sandbox-only failure reproduced with the previously verified v1.3.2 release. The release and exact extracted-archive gates were therefore rerun outside that filesystem sandbox and passed.
- Failed reports were preserved rather than deleted at `qa\release-v1.4.0-failed-sandbox-tcl-20260820` and `qa\release-v1.4.0-failed-gui-minheight-20260820`.
- The first corrected packaged run exposed a stale self-test assertion that checked the widget's requested height after the user-requested five-row log increase. The assertion now correctly checks the window's configured minimum height; the final package passed.

## Residual risks

- Hardware encoders depend on the installed NVIDIA GPU, driver, and FFmpeg build. Every selected hardware mode runs a disposable preflight and publishes nothing if an option is unsupported.
- ProRes, DNxHR, H.264, HEVC, and AV1 modes are lossy; source-aware selection finds the closest supported class but cannot preserve every source chroma/bit-depth combination exactly.
- Non-video streams are copied rather than transcoded, so an incompatible audio or subtitle codec may be omitted in compatible mode or rejected in strict/video+audio mode.

## Next action

No implementation or release work remains. The verified v1.4.0 folder and ZIP are ready for user testing. Publishing to GitHub is intentionally not performed unless separately authorized for this release.
