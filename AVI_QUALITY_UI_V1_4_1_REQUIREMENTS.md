# Stream Copy Remuxer 1.4.1 — AVI and conditional Quality controls

Date: 2026-08-20

## Authoritative source

- Workspace: `C:\Users\Doug\Documents\ChatGPT\Topaz Video`
- Branch: `codex/transcoding-v1.4.0`
- Baseline commit: `4e687835a968cb02a551f3e8822c29c96a0b34d9` (`v1.3.2`)
- Current authoritative implementation: the verified v1.4.0 working tree described by `TRANSCODING_V1_4_RESUME_STATE.md`
- Protected release: `release-stream-copy-remuxer-v1.4.0` and its v1.4.0 ZIP must remain unchanged

## Requested changes

1. Hide the Quality label and entry whenever the selected video output profile has no adjustable CRF/CQ value.
2. Show the Quality label and entry for every profile that accepts CRF or CQ.
3. Add AVI as an output-container choice for Stream Copy.
4. Keep every transcoding profile on its existing fixed container; AVI must not become a transcode destination.

## Compatibility and preservation requirements

- AVI uses FFmpeg's `avi` muxer and the `.avi` extension.
- Stream Copy remains the default and MP4 remains the default container.
- AVI uses the existing disposable preflight, verification, collision avoidance, atomic publication, audit report, destination-folder, and batch behavior.
- In All compatible streams mode, AVI conservatively keeps video/audio and omits subtitle, attachment, and data streams.
- In All source streams (strict) mode, a known AVI-incompatible extra stream blocks planning before FFmpeg starts.
- MP4/MOV/MKV behavior and all video-transcoding encoder settings remain unchanged.
- Existing user-owned and unrelated workspace changes remain untouched.

## Acceptance checklist

- [x] Quality widgets are absent from the layout for Stream Copy, ProRes, and DNxHR.
- [x] Quality widgets reappear with the correct CRF/CQ label and editable state for adjustable profiles.
- [x] AVI appears in the GUI container dropdown while Stream Copy is selected.
- [x] Selecting AVI updates selected Stream Copy rows and produces `_remux.avi` planned paths.
- [x] Switching to a transcode profile forces its existing MP4/MOV container and disables the container dropdown.
- [x] Returning to Stream Copy restores the remembered AVI selection.
- [x] CLI `--container avi` is accepted.
- [x] Unit tests cover AVI naming, muxer selection, compatible/strict stream behavior, and conditional Quality visibility.
- [x] A real FFmpeg/FFprobe integration test creates and verifies an AVI stream-copy output.
- [x] The complete source suite passes except only explicitly documented hardware-dependent skips.
- [x] The exact packaged v1.4.1 executable and ZIP pass the release verification gate.
- [x] Final diff and release artifact audit find no unexplained changes outside this patch.
