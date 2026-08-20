# Stream Copy Remuxer v1.1.2 — Batch Upgrade Requirements

## Authoritative baseline and scope

- Authoritative editable baseline: the v1.0.3 source in `C:\Users\Doug\Documents\ChatGPT\Topaz Video`, verified against `qa\release-v1.0.3-onefile-final\source_manifest.json`.
- Baseline source-manifest SHA-256: `756a37a3ede2ace75f994c5d7059e8ee72e500060282f7a123a0828e04e0c823`.
- Protected rollback artifacts: `release-stream-copy-remuxer-v1.0.3` and `Stream-Copy-Remuxer-v1.0.3-Windows-x64.zip`; neither may be modified or overwritten.
- Target: a versioned Windows 10/11 x64 v1.1.2 release.

## Requested batch and user-interface behavior

- [x] Accept multiple files from one Browse action.
- [x] Accept multiple files dragged from Windows File Explorer without requiring a third-party runtime.
- [x] Add dropped/browsed files as queue rows and ignore duplicate source paths safely.
- [x] Bind the Delete key on the queue to remove all selected rows from the queue only; never delete source or output files.
- [x] Provide visible Remove selected and Clear queue controls with equivalent safe behavior.
- [x] Show each source filename/path, detected input container, video codec(s), audio codec(s), selected output container, planned output, and state/progress.
- [x] Provide an MP4/MOV/MKV dropdown that applies to selected rows and defaults new rows to MP4.
- [x] Keep MP4, MOV, and MKV as the only output-container choices.
- [x] Support AVI, RM/RMVB, TS/MTS/M2TS, WebM, FLV, WMV/ASF, MPEG/MPG/VOB, OGV/Ogg, 3GP/3G2, MXF, DV, NUT, Y4M, M4V, MKV, MP4, and MOV in the picker, while also accepting any file FFprobe can inspect.
- [x] Remove the large bold in-window `Stream Copy Remuxer` heading.
- [x] Display this exact description: `Certain software such as Topaz Video are more or less compatible with different containers. This app allows changing containers without re-encoding the video or audio.`
- [x] Preserve the application name/version in the title bar.
- [x] Permit an optional common output folder while defaulting each output beside its source.
- [x] Preserve the prior single-file app's ability to choose an exact custom output path for an individual row.
- [x] Preserve the video+audio versus all-streams selection.

## Batch execution and safety behavior

- [x] Probe queue files off the GUI thread and keep the event loop responsive.
- [x] Process ready queue rows sequentially so large files do not contend for disk bandwidth.
- [x] Run the existing per-file compatibility preflight, stream copy, verification, audit-report write, and atomic promotion path for every job.
- [x] Continue to the next queued item after a per-file compatibility/remux failure and report a batch summary.
- [x] Cancel the active FFmpeg process cleanly, remove its application-owned partial files, keep completed outputs, and leave unstarted rows retryable.
- [x] Prevent queue/container/output/toolchain mutation that could desynchronize an active batch.
- [x] Allocate nonconflicting planned outputs across the complete queue, including same-named sources sent to one output folder.
- [x] Check aggregate destination free space before starting the batch.
- [x] Never overwrite a source, existing output, report, or externally appearing destination.
- [x] Preserve Unicode and long ordinary Windows paths without shell interpolation.
- [x] Keep stream copy mandatory (`-c copy`) and never expose encoding controls.
- [x] Preserve finalized, nonfragmented MP4/MOV behavior and FFV1 frame-index verification.

## Compatibility and regression requirements

- [x] Preserve automatic Topaz/system FFmpeg discovery and manual FFmpeg selection.
- [x] Preserve CLI probe, single-file remux, dependency-check, and self-test modes.
- [x] Preserve source identity, codec/property, duration, chapter, and output-index verification.
- [x] Disclose that the selected output container may reject some input codecs/stream types; preflight remains authoritative.
- [x] Preserve the verified v1.0.3 release artifacts unchanged.

## Verification and delivery requirements

- [x] Baseline v1.0.3 tests are recorded before edits.
- [x] Unit tests cover duplicate suppression, output allocation, output-container application, Delete-key removal, and aggregate-space logic.
- [x] GUI tests cover construction, exact description, absent redundant heading, queue columns, MP4 default, drag/drop registration, and responsiveness.
- [x] Real FFmpeg tests cover at least two queued/common input container types and multiple output-container selections without re-encoding.
- [x] Cancellation, failure continuation, active-batch mutation protection, conflicts, and cleanup are tested.
- [x] Full source suite passes under warnings-as-errors.
- [x] A versioned standalone EXE and ZIP are built without overwriting v1.0.3 or superseded candidates.
- [x] The exact v1.1.2 packaged EXE and a freshly ZIP-extracted EXE pass the batch-aware self-test.
- [x] README and bundled release documentation describe the batch workflow and supported input/output behavior.
- [x] Final source, EXE, and ZIP hashes plus actual test results are recorded.
- [x] A separate skeptical audit completes with no unresolved material defect.

## Reliability states

- **WORKING:** implementation or verification remains incomplete.
- **CANDIDATE:** v1.1.2 artifacts exist but one or more final checks remain.
- **VERIFIED:** every applicable checkbox passes on the exact delivered v1.1.2 artifacts.
- **BLOCKED:** an external dependency, authority, or unavailable required capability prevents completion.
