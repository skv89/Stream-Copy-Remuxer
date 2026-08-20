# Stream Copy Remuxer v1.3.0 — Output Location and Status-Column Requirements

## Authoritative baseline and preservation

- Authoritative editable baseline: the verified v1.2.0 source in `C:\Users\Doug\Documents\ChatGPT\Topaz Video`.
- Baseline source manifest: `qa\release-v1.2.0-onefile-final\source_manifest.json`.
  - Manifest SHA-256: `c3e75a87b45042c584092f53dc840bc6cbccd9aa2e2b3d4711bd059da5b8aeed`.
  - Source-set SHA-256: `c71c7c1b4f0d4e89bacf190cdef42139bb472feb2b72af6ca5a43843e1d2c911`.
- Verified pre-edit checkpoint: `work\stream-copy-remuxer-v1.3.0-baseline-source` (36 files rehashed against the manifest).
- Protected v1.2.0 EXE SHA-256: `d5604a07bf987dacfecbe51e654aa3f3c15c4b8166e6382a2ced955b3af74873`.
- Protected v1.2.0 ZIP SHA-256: `cf8fa77c42823a58818b8359a3420d84d5b4c0f8e85ed26674725f3721da67bc`.
- Target: a new v1.3.0 Windows x64 release; v1.2.0 and earlier artifacts must not be overwritten.
- The newest request supersedes v1.2.0's prior rule that the GUI could not expose a common destination folder. Beside-source output remains the blank/default behavior.

## Show output behavior

- [x] `Show output` opens the actual parent folder of the selected completed row's verified output.
- [x] If no selected row has a completed result, it opens the parent folder of the most recent verified output.
- [x] Use the Windows shell's direct folder-opening API rather than relying on fragile `explorer.exe /select,<path>` argument parsing.
- [x] Support spaces, Unicode, parentheses, ampersands, and other valid Windows path characters.
- [x] If the output or its parent folder no longer exists, show an actionable error instead of silently opening an unrelated folder.
- [x] Add an automated regression test that captures and compares the exact folder passed to the opener.

## Resizable and readable Status column

- [x] Configure the Status column as stretchable/user-resizable rather than fixed.
- [x] Give Status an initial and minimum width sufficient for normal complete/failed/canceled text at supported DPI scales.
- [x] Preserve horizontal scrolling and the other readable column widths.
- [x] Add GUI/self-test assertions for the Status stretch option and content-width allowance.

## Optional batch destination folder

- [x] Add a `Destination folder (blank = beside each source):` input in Output settings.
- [x] The destination value is blank on every app start by default.
- [x] Provide `Browse` and `Clear` controls; Browse accepts an existing folder and Clear restores blank/default behavior.
- [x] A typed nonblank destination must resolve to an existing directory before planning or starting.
- [x] When blank, every uncompleted row is planned beside its own source with `_remux`, `_remux_2`, and later collision-safe suffixes.
- [x] When nonblank, every uncompleted row in the batch is planned into that common destination with the same suffix and collision protections.
- [x] Do not add a destination-path column or repeat the folder in each table row.
- [x] Refresh planned paths when the destination is browsed, cleared, entered, or loses focus.
- [x] Show the effective destination policy in the batch confirmation.
- [x] Lock the destination entry and its Browse/Clear controls while a batch is active.
- [x] Preserve completed results and never move or delete an already completed output when the setting changes.
- [x] Ensure aggregate free-space checks group the resulting plans by their actual destination volume.
- [x] Add focused tests for blank/default placement, common-folder placement, same-stem collisions, invalid folders, clear-to-default behavior, and active-batch locking.

## Preserved behavior and regression controls

- [x] Preserve stream copy only (`-c copy`), preflight, verification, reports, atomic promotion, no-overwrite behavior, and cleanup.
- [x] Preserve MP4 default, MP4/MOV/MKV outputs, stream descriptions, compatibility column, and filename-only source cells.
- [x] Preserve TkDND/OLE2 drag-and-drop, repeated multi-file drops, Delete-row behavior, FFmpeg detection/install, CLI modes, and Unicode paths.
- [x] Preserve the one-line description, DPI-aware row heights/headings, bounded Details area, and no redundant in-window title.
- [x] Keep the CLI `--output` workflow unchanged.

## Verification and delivery gates

- [x] Record the unchanged v1.2.0 baseline test result.
- [x] Run all source tests under warnings-as-errors using the Tcl/Tk/TkDND-capable runtime.
- [x] Run the real two-file source self-test and the 100%/150%/200% layout audit.
- [x] Produce and inspect a new GUI preview showing the destination controls and readable Status column.
- [x] Build a new standalone v1.3.0 EXE and ZIP without modifying prior releases.
- [x] Run the staged packaged self-test and the freshly ZIP-extracted exact-EXE self-test.
- [x] Verify ZIP integrity, package contents, release manifest, and exact source/EXE/ZIP hashes.
- [x] Perform a separate skeptical audit of folder opening, destination planning, table resizing, error paths, remux safety, and regressions.
- [x] Complete one clean final audit pass with no unresolved material defect.

## Reliability states

- **WORKING:** implementation or testing remains incomplete.
- **CANDIDATE:** v1.3.0 artifacts exist, but one or more applicable gates remain.
- **VERIFIED:** all requirements pass on the exact delivered artifacts.
- **BLOCKED:** an external authority or unavailable required capability prevents completion after safe alternatives are exhausted.
