# Stream Copy Remuxer 1.3.2 — stream compatibility and log-height requirements

## Authoritative baseline

- Application source: the 41 files recorded by `qa/release-v1.3.1-onefile-final/source_manifest.json`.
- Baseline source-set SHA-256: `a08244511961ebad692d1f4afcfb532bb158a6ab5b94bc6140cc0d9006b6c4ea`.
- Verified pre-edit checkpoint: `work/stream-copy-remuxer-v1.3.2-baseline-source` (41 of 41 hashes match).
- Protected release artifacts: the existing v1.3.1 EXE and ZIP must remain byte-identical.
- Exact regression source: `D:\-= Chinese Videos =-\The Mystery Files 迷离档案 (1997) 1-20\Mystery.Files.S01E01.1997.1080p.MyTVSuper.WEB-DL.H265.AAC-ZerTV_cropped.mkv`.

## Established failure

- The v1.3.1 FFV1 pixel-format correction works: the source probes as FFV1 1424x1080 `yuv420p` with AAC audio.
- The exact source also has two SubRip subtitle streams, indexes 2 and 3, titled Traditional and Simplified.
- With strict all-stream selection, FFmpeg rejects both MP4 and MOV because neither muxer can stream-copy SubRip.
- Converting SubRip to `mov_text` would be subtitle re-encoding and is outside this application's no-re-encoding contract.

## Requested changes

- [x] Make the Details log five visible rows taller: increase its configured height from 5 rows to 10 rows.
- [x] Make the reported MP4/MOV workflow succeed without re-encoding and without silently discarding streams.

## Loss-safe stream-selection behavior

- [x] Preserve `Video + audio` mode and its existing explicit omission disclosure.
- [x] Add `Video only` mode for maximum container compatibility. It must select every video stream, omit audio and every other non-video source stream, and never re-encode selected video.
- [x] Add `All compatible streams` mode. It must select every source stream that the chosen output container can safely stream-copy under the app's declared compatibility rules.
- [x] For MP4/MOV, compatible mode must retain all video and audio streams, retain explicitly supported subtitle codecs, and omit incompatible subtitle, attachment, and data streams.
- [x] For MKV, compatible mode must retain all source streams.
- [x] Preserve a separate `All source streams (strict)` mode that maps every source stream and may fail rather than silently omit anything.
- [x] The GUI label, Compatibility table column, confirmation dialog, Details log, and JSON audit report must clearly disclose compatible-mode and video-only omissions, including stream index, type, codec, and available title/language.
- [x] Strict all-stream planning for a known incompatible MP4/MOV non-A/V stream must fail before starting FFmpeg with an actionable message directing the user to compatible mode, video+audio mode, video-only mode, or MKV.
- [x] Every FFmpeg media mapping must remain explicit and every successful operation must still use `-c copy` only.
- [x] Verification must compare the exact planned source-stream set with the relevant output stream set; compatible mode must not weaken codec/core-property checks.

## Preservation requirements

- [x] Preserve batch processing, drag-and-drop, Delete-key behavior, output naming, optional destination folder, Show output behavior, FFmpeg detection/installation, progress/cancellation, source identity checks, non-overwrite behavior, and existing container choices.
- [x] Preserve the default MP4 output and default Video + audio stream mode.
- [x] Preserve metadata and chapters under all modes.
- [x] Do not modify or overwrite the exact regression source.
- [x] Do not overwrite or alter v1.3.1 deliverables.

## Verification and release gates

- [x] Baseline failures caused only by local unbundled Tk/TkDND runtime limitations are recorded separately; non-GUI baseline tests pass.
- [x] Unit tests cover compatible and video-only stream selection, exact mapping, omission disclosure, strict-mode early rejection, verification, and the 10-row Details log.
- [x] Integration tests prove SubRip is omitted in compatible MP4/MOV mode with FFV1/AAC retained, prove video-only removes audio and subtitles while stream-copying FFV1, and prove strict all-stream behavior remains loss-safe.
- [x] Exact-source MP4 and MOV compatible-mode preflights pass while retaining FFV1/AAC and omitting both disclosed SubRip streams.
- [x] Exact-source MP4 and MOV video-only preflights pass while retaining FFV1 and omitting AAC plus both disclosed SubRip streams.
- [x] Exact-source strict MP4/MOV planning is rejected before FFmpeg with actionable diagnostics.
- [x] Exact-source MKV strict-mode preflight preserves all four streams.
- [x] Source file size and nanosecond modification time remain unchanged.
- [x] Source self-test, packaged self-test, extracted-package self-test, archive integrity, and DPI/layout audit pass on v1.3.2.
- [x] Final source and release manifests are generated and independently reverified.
- [x] A final skeptical change-surface audit finds no unexplained regression.

## Completion states

- **WORKING:** implementation or testing remains.
- **CANDIDATE:** v1.3.2 artifacts exist but a release or audit gate remains.
- **VERIFIED:** every applicable requirement above passes on the exact delivered ZIP/EXE after the last material change.
- **BLOCKED:** a genuine external dependency prevents completion after safe alternatives are exhausted.
