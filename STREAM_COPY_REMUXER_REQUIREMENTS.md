# Stream Copy Remuxer v1.0.3 — Requirements and Acceptance Checklist

## Scope and authoritative baseline

- Project root: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`
- Baseline: greenfield project; the Git worktree contained no tracked or user project files when work began.
- Target platform: Windows 10/11 x64.
- Primary use case: remux a large FFV1/Matroska file to a finalized MP4 without decoding or re-encoding, so an indexed frame count is available to Topaz Video.

## Functional requirements

- [x] Select one local source media file and choose MP4, MOV, or MKV output.
- [x] Perform stream copy only (`-c copy`); never expose an encoding mode.
- [x] Default to video + audio streams for MP4/MOV, with an explicit all-streams option.
- [x] Preserve source metadata and chapters where the destination container supports them.
- [x] Suggest a nonconflicting destination and never overwrite a source, final output, or report.
- [x] Run a short container-compatibility preflight before a large remux.
- [x] Show source details, compatibility guidance, progress, elapsed time, speed, and diagnostics.
- [x] Run FFmpeg off the GUI thread and provide orderly cancellation.
- [x] Write to a unique partial file in the destination folder and promote it only after verification.
- [x] Remove application-owned partial/preflight files after cancellation or failure.
- [x] Verify output stream codecs and core properties against the selected source streams.
- [x] For FFV1 in MP4/MOV, require a positive indexed frame count before promotion.
- [x] Write a successful `.remux.json` audit sidecar containing the exact command, tool version, probes, and checks.
- [x] Detect bundled, Topaz Video, Topaz Video AI, PATH, and common standalone FFmpeg installations; permit manual FFmpeg selection.
- [x] Handle Unicode and long ordinary Windows paths without shell interpolation.
- [x] Provide a CLI remux mode and a bounded self-test for repeatable verification.

## Safety and compatibility requirements

- [x] Check destination free space before starting and reject clearly insufficient space.
- [x] Clearly disclose that MP4/MOV cannot carry every Matroska subtitle, data, or attachment stream.
- [x] Clearly disclose that FFV1/MP4 is mathematically lossless but not broadly supported by every player/editor.
- [x] Do not fragment MP4/MOV; finalize the normal movie index needed for frame-count metadata.
- [x] Do not use `faststart`, which would force a costly second rewrite of very large local files.
- [x] Source media remains read-only and unchanged under success, failure, and cancellation.

## Delivery and verification requirements

- [x] Source tests pass.
- [x] Real FFmpeg integration test creates FFV1/MKV, stream-copies it to MP4, and verifies codec retention and frame count.
- [x] Conflict, incompatible-stream, insufficient-space, and cancellation behavior are tested.
- [x] GUI construction/responsiveness self-test passes without showing or taking over the desktop.
- [x] A versioned standalone Windows executable and ZIP are built.
- [x] The exact packaged executable passes its self-test.
- [x] README includes a direct FFmpeg command and operational guidance.
- [x] Final source/release hashes and actual test results are recorded.
- [x] A separate skeptical audit completes with no unresolved material defect.

## Reliability states

- **WORKING:** implementation or testing is incomplete.
- **CANDIDATE:** executable exists but one or more final checks remain.
- **VERIFIED:** every applicable checkbox above has passed on the delivered v1.0.3 artifacts.
- **BLOCKED:** a genuine external dependency or authority issue prevents completion.
