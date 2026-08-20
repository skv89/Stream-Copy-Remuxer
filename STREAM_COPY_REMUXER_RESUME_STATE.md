# Stream Copy Remuxer — Resume State

Last updated: 2026-08-17

## Current state

- Reliability state: **VERIFIED** for Stream Copy Remuxer v1.0.3.
- Project root / writable scope: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`
- Authoritative baseline: greenfield project; Git reported `No commits yet on master` and no project files.
- Protected originals: all user media, Topaz Video files, and the existing Video Crop Tool project are read-only references and outside the change surface.
- Declared change surface: new files inside this project root only.

## Environment established

- Python: 3.11.9 x64 (`Video corrections\work\pyinstaller311-env`), Tcl/Tk 8.6.12.
- PyInstaller: 6.16.0.
- Preferred runtime: Topaz Video FFmpeg/FFprobe 8.1 at `C:\Program Files\Topaz Labs LLC\Topaz Video`.
- Fallback system FFmpeg is also present at `C:\Program Files (x86)\FFMPEG`.
- Free space at inspection: C: 143,641,378,816 bytes; D: 6,573,472,546,816 bytes.

## Acceptance status

- Requirements captured: PASS.
- Architecture and implementation: PASS for v1.0.3.
- Source/unit/integration tests: PASS — 26 tests under `-W error`.
- Real integrations: PASS — FFV1+AAC/MKV → MP4, FFV1 → MOV, FFV1 → MKV, long Unicode paths, incompatible attachment rejection, cancellation, conflict, and source-change paths.
- Packaged executable self-test: PASS in the staged release and again from a fresh extraction of the final ZIP.
- Fresh ZIP manifest/hash comparison: PASS.
- Skeptical audit and final release gate: PASS with no unresolved material defect in the application.

## Latest validated checkpoint

- Final executable: `C:\Users\Doug\Documents\ChatGPT\Topaz Video\release-stream-copy-remuxer-v1.0.3\Stream Copy Remuxer.exe`
  - Size: 11,574,880 bytes
  - SHA-256: `b71f79807640d43195777930d7e9ef4e39351d0d553f00c641fbc280cfd20f95`
- Final ZIP: `C:\Users\Doug\Documents\ChatGPT\Topaz Video\Stream-Copy-Remuxer-v1.0.3-Windows-x64.zip`
  - Size: 11,354,241 bytes
  - SHA-256: `6018e37bbcba38ae3eb68887a3df7a9f9e0450eca46c260ec67dc88081885ae9`
- Release manifest: `release-stream-copy-remuxer-v1.0.3\release_manifest.json`.
- Source self-test: `qa\source-self-test-v1.0.3.json` — PASS with FFV1 and AAC retained and 25/25 indexed frames.
- Exact extracted-release test: `qa\release-v1.0.3-onefile-final\packaged-self-test-from-zip.json` — PASS.
- ZIP integrity report: `qa\release-v1.0.3-onefile-final\zip-integrity.json` — PASS.

## Failed or superseded methods

- Initial test pass emitted an unclosed FFmpeg stdout `ResourceWarning`; the handle cleanup was corrected and the complete 21-test suite then passed under `-W error`.
- First PyInstaller attempt failed before creating a release because PyInstaller probed inaccessible `AppData\Roaming\Python\Python311\site-packages`; the build is being isolated with a workspace-local `PYTHONUSERBASE`, matching the proven Video Crop Tool build approach.
- Removal of the empty first-attempt QA directory was declined by the managed sandbox. It is preserved; the corrected build uses fresh `build2` and `final` paths without deleting or overwriting failed-build evidence.
- The build2 executable was created successfully, but the first packaged self-test invocation exited 2 because `Start-Process` split an absolute output path containing spaces. The unchanged candidate passed a packaged dependency check; finalization now uses a relative QA argument plus an explicit working directory.
- The unchanged v1.0.0 candidate still exited during its self-test, proving the failure was not only argument splitting. It is explicitly marked REJECTED. v1.0.1 forces application logging and writes a failed self-test JSON with traceback; its build remains staged under `work` until packaged tests pass.
- The v1.0.1 one-file traceback proved Tcl could not use its `init.tcl` after `_MEI` extraction even though the archive table contained it. After two one-file runtime failures, that method was disqualified; build4 uses PyInstaller's portable one-folder mode and preserves every failed candidate/report.
- Direct Tcl diagnostics proved the failures were caused by Codex sandbox native-file filtering, not packaging: both the v1.0.1 portable and preserved one-file candidates passed under Doug's normal Windows identity. v1.0.2 therefore returns to the simpler single EXE and adds source identity plus cleanup-failure safeguards found during audit.
- Final audit expanded real coverage to AAC audio preservation, MOV and MKV outputs, and long Unicode paths. Those checks pass in source; v1.0.3 is the intended final single-EXE release and supersedes prior candidates/releases.

## Assumptions and risks

- One-file-at-a-time operation is intentionally selected to keep the GUI simple and reduce mistakes with 100+ GiB outputs.
- FFV1 in finalized MP4 is supported by the detected Topaz FFmpeg, but third-party player/editor compatibility can vary.
- Stream-copy verification proves codec/property preservation and the no-encode command path; it intentionally avoids a second full-file packet hash scan.
- The executable is not Authenticode-signed, so Windows may show a SmartScreen/unrecognized-publisher warning.
- A full 100+ GiB remux and the resulting Topaz startup time have not yet been measured; the short FFV1 test proves the mechanism and indexed metadata, not the full-file performance outcome.

## Exact next action

After the current Topaz job finishes, extract the v1.0.3 ZIP, remux one existing cropped FFV1/MKV to MP4, and compare Topaz's loading time. Keep the MKV until the MP4 result has been validated in the actual workflow.
