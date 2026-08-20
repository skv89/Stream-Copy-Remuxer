# Stream Copy Remuxer v1.2.0 — GUI QC and Reliability Requirements

## Authoritative baseline and protected artifacts

- Authoritative editable baseline: the v1.1.2 source in `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Baseline source manifest: `qa\release-v1.1.2-onefile-final\source_manifest.json`.
  - Size: 5,356 bytes.
  - SHA-256: `da90a2723dcd97f6ea0a481dfc0c56a20de6cdb9b3f6dce0ead58af50c421deb`.
- Protected v1.1.2 EXE: `release-stream-copy-remuxer-v1.1.2\Stream Copy Remuxer.exe`.
  - Size: 11,604,843 bytes.
  - SHA-256: `ebf3626bbba9f84b329ce17d7991763bc800789b089af7073380921e67d31521`.
- Protected v1.1.2 ZIP: `Stream-Copy-Remuxer-v1.1.2-Windows-x64.zip`.
  - Size: 11,384,860 bytes.
  - SHA-256: `3a16da37254dfcf2b9d4239e67e3a6e75bc96277a5694ae5315b7d0f2a7b04a8`.
- The crashing copy at `D:\Apps\AI created apps\Stream Copy Remuxer\Stream Copy Remuxer.exe` has the same v1.1.2 EXE hash.
- Target: a new versioned Windows 10/11 x64 v1.2.0 release. Existing versioned releases must not be overwritten.

## Requested GUI corrections

- [x] Display the complete description on one visual line at the minimum supported window width and common Windows DPI scales.
- [x] Use DPI-aware queue row heights with adequate vertical padding so glyphs are not clipped.
- [x] Allocate readable widths to every queue heading and data column; retain horizontal scrolling for unusually long content.
- [x] Show the source filename rather than repeating the full path in the visible table cell.
- [x] Remove the `Planned output file` column.
- [x] Always plan GUI outputs beside their source as `<source stem>_remux.<selected extension>`; use `_remux_2`, `_remux_3`, and so on only to avoid overwriting or queue collisions.
- [x] Remove the GUI custom-output and common-output-folder controls because they contradict the fixed beside-source workflow.
- [x] Preserve explicit CLI `--output` behavior for command-line use.
- [x] Move per-file compatibility guidance into a `Compatibility` table column and remove the separate brown guidance block.
- [x] Refresh each row's compatibility text when probing, output-container selection, or stream mode changes.
- [x] Change `Add files…` to `Add files` and update related hints/documentation.
- [x] Keep MP4 as the default and MP4/MOV/MKV as the only GUI output-container choices.
- [x] Keep Delete and Remove selected limited to queue rows; never delete source, output, or report files.
- [x] Keep the table as the primary expanding region and prevent the Details area from consuming disproportionate height.

## Streams dropdown behavior

- [x] The opened Streams dropdown must describe each choice, not merely label it.
- [x] `Video + audio` must state that it copies video/audio streams and excludes subtitle, attachment, and data streams.
- [x] The UI must state that container metadata and chapters remain mapped separately and are not excluded by `Video + audio`.
- [x] `All source streams` must state that it also attempts subtitle, attachment, and data streams and that MP4/MOV may reject unsupported types.
- [x] Preserve the existing FFmpeg mapping semantics: `-map 0:v? -map 0:a?` for video+audio and `-map 0` for all streams, with `-map_metadata 0 -map_chapters 0` in both modes.

## Drag-and-drop crash correction

- [x] Remove the custom Python/ctypes `SetWindowLongPtrW` window-procedure subclass and all production references to it.
- [x] Replace it with a maintained Tk drag-and-drop integration using Windows OLE2 through TkDND.
- [x] Parse multi-file drop payloads as Tcl lists so spaces, braces, ampersands, Unicode, and multiple files remain intact.
- [x] Register the actual packaged GUI as a file-drop target and expose a safe fallback message if registration fails.
- [x] Add stress/regression coverage for repeated multi-file drops and queue mutation without a native fast-fail.
- [x] Record the original Windows crash evidence: Application Error 1000 at 2026-08-17 11:53:05, `ucrtbase.dll`, exception `0xc0000409`, report ID `3e6be82b-52f5-4acf-bd8f-9f61ef8e7f80`.

## FFmpeg detection and app-local installation

- [x] Automatically detect a complete paired FFmpeg/FFprobe toolchain at startup without a manual selection button.
- [x] Honor explicit command-line/environment overrides, then prefer the highest versioned app-local installation before normal system/PATH installations; known application-bundled copies remain a last-resort system fallback.
- [x] Do not identify or advertise another application's FFmpeg copy in the GUI; display only a concise detected version and path/source class.
- [x] Check current stable-release metadata asynchronously so startup and the GUI thread remain responsive.
- [x] As of the implementation baseline, recognize FFmpeg 9.0.1 (released 2026-08-12) as the current stable release; do not hard-code 9.0.1 as permanently current.
- [x] If FFmpeg is missing or older than the fetched current stable version, show an `Install FFmpeg <version>` action.
- [x] Download only after user confirmation, into a versioned subfolder beside the app.
- [x] Use the current release ZIP, version, and SHA-256 endpoints from the gyan.dev Windows-build provider linked by FFmpeg.org.
- [x] Require HTTPS, restrict redirects to the expected provider host, validate metadata, and verify the complete archive SHA-256 before extraction.
- [x] Reject unsafe ZIP entries and install only the paired executables plus available license/readme material through a staged, non-overwriting promotion.
- [x] Validate both installed executables and their matching version before switching the running app to them.
- [x] Reinspect queued files automatically after a successful install.
- [x] Handle offline, denied-write, corrupt-download, checksum-mismatch, malformed-archive, and incomplete-toolchain failures with actionable messages and no partial selected install.
- [x] Update third-party notices and package TkinterDnD2/TkDND licensing; FFmpeg remains an optional user-initiated download, not bundled in the release ZIP.

## Preserved remux safety and behavior

- [x] Preserve stream copy only (`-c copy`) with no encoding controls.
- [x] Preserve per-file preflight, verification, audit report, temporary-file cleanup, atomic promotion, and no-overwrite behavior.
- [x] Preserve sequential batch execution, failure continuation, cancellation, Unicode paths, and active-batch mutation locks.
- [x] Preserve broad FFprobe-based input support and the common file-picker formats.
- [x] Preserve CLI dependency-check, probe, remux, self-test, explicit FFmpeg, and explicit FFprobe options.
- [x] Preserve the exact requested description text and absence of a redundant in-window title.

## Verification and delivery gates

- [x] Record the v1.1.2 baseline suite result and distinguish environment-only Tcl failures from application failures.
- [x] Add focused unit tests for version parsing/comparison, release metadata validation, checksum verification, safe extraction, app-local discovery, fixed output paths, table content, and stream descriptions.
- [x] Run all source tests under warnings-as-errors using a Tcl/Tk and TkDND-capable runtime.
- [x] Run source self-test with real FFmpeg/FFprobe and at least MKV and AVI inputs.
- [x] Inspect geometry metrics at 100%, 150%, and 200% Tk scaling: one-line description, adequate row height, readable headings, and bounded Details height.
- [x] Build a new standalone v1.2.0 EXE and ZIP without modifying v1.1.2.
- [x] Confirm the package contains TkinterDnD2/TkDND and launches with drag-and-drop registered.
- [x] Run the batch-aware self-test on the staged EXE and the freshly ZIP-extracted exact EXE.
- [x] Verify fresh ZIP integrity against its manifest and record exact source/EXE/ZIP hashes.
- [x] Perform a separate skeptical audit for unsafe native hooks, UI regressions, installer security, error recovery, and preservation of remux safety.
- [x] Complete one clean final audit pass with no unresolved material defect.

## Reliability states

- **WORKING:** implementation or verification remains incomplete.
- **CANDIDATE:** a v1.2.0 artifact exists but one or more applicable gates remain.
- **VERIFIED:** every applicable requirement passes on the exact delivered v1.2.0 artifacts.
- **BLOCKED:** an external authority, unavailable runtime, or required capability prevents completion after safe alternatives are exhausted.
