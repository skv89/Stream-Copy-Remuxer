# Stream Copy Remuxer 1.4.1

Certain software such as Topaz Video are more or less compatible with different containers. This app allows changing containers without re-encoding the video or audio.

Stream Copy Remuxer is a Windows batch front end for FFmpeg. Stream copy remains the default: it changes the container around existing encoded packets without decoding or re-encoding them. Version 1.4.x also includes clearly labeled, optional video-transcoding profiles for applications that cannot import the source codec even after a remux. Transcoding decodes and re-encodes video and should be treated as lossy; selected non-video streams are still copied when the output container supports them.

## What's new in 1.4.1

- AVI is available as a Stream Copy output container alongside MP4, MOV, and MKV. The disposable preflight still decides whether the selected codecs can actually be carried by AVI without conversion.
- CRF/CQ controls are now shown only for encoders that use them. Stream Copy, ProRes, and DNxHR no longer display an inapplicable disabled quality field.

## What's new in 1.4.0

- Source-aware ProRes and DNxHR MOV outputs choose the closest supported class from each source video's detected chroma family, bit depth, RGB family, and alpha presence.
- Software and NVIDIA NVENC choices are available for H.264, HEVC, and AV1.
- H.264 software uses `libx264`, 8-bit 4:2:0, and the requested `placebo` preset for maximum compatibility and compression effort.
- H.264 NVENC uses the requested P7/HQ, VBR-CQ, full-resolution multipass, four B-frames, middle B-reference mode, 27-frame rate-control lookahead, lookahead level 3, spatial AQ off, and temporal AQ on.
- CRF/CQ is user-editable with encoder-specific validation and an Ultra HQ default of 12.
- **Encoding help** opens a reusable, high-contrast window that explains the current selection, every output profile, CRF/CQ, container behavior, copied streams, and detected encoder availability.
- Each queue row shows its planned output video profile and resolved pixel format. Codec-specific output names and `.transcode.json` audit reports keep transcoded results distinct from `_remux` outputs.

All existing 1.3.2 stream-copy safeguards remain: compatible-stream omission, video-only mode, exact stream mapping, disposable preflight, verified atomic publication, optional common destination, drag-and-drop, and automatic FFmpeg detection/installation.

## Batch workflow

1. Extract the release ZIP and open `Stream Copy Remuxer.exe`.
2. Drag multiple media files from File Explorer onto the window, or choose **Add files** and select several files.
3. Wait while FFprobe fills each row's detected input container, video encoding, audio encoding, and compatibility guidance.
4. Select one or more rows and choose a **Video output** mode. New rows default to **Stream copy — no re-encoding**.
5. For stream copy, choose MP4, MOV, MKV, or AVI. Transcoding profiles automatically set their required output container: ProRes/DNxHR use MOV; H.264/HEVC/AV1 use MP4.
6. For a CRF/CQ profile, enter the desired whole-number quality value. The value is applied to selected rows.
7. Choose the stream mode:
   - **Video + audio** keeps every video and audio track, but excludes subtitle, attachment, and data tracks.
   - **Video only** keeps only video and removes audio plus every other non-video stream for maximum compatibility.
   - **All compatible streams** keeps every conservatively supported track and explicitly omits incompatible MP4/MOV/AVI extras. MKV keeps every source stream.
   - **All source streams (strict)** omits nothing and blocks a known-incompatible MP4/MOV/AVI operation before FFmpeg starts.
8. Optionally choose one common **Destination folder**. Leave it blank to place each output beside its source.
9. Choose **Start batch**, review the exact outputs, modes, destinations, stream omissions, and lossy-transcode warning, then confirm.

Rows run sequentially to avoid competing for disk bandwidth. A per-file failure is recorded in that row and does not stop later files. Select queue rows and press **Delete** (or choose **Remove selected**) to remove only those rows; no source, completed output, or report is deleted.

After completion, **Show output** opens the actual folder containing the selected verified output. If no completed row is selected, it opens the most recently verified output folder.

## Video output profiles

| Video output | Container | Automatic pixel-format/class behavior | Quality control |
|---|---|---|---|
| Stream copy | MP4, MOV, MKV, or AVI | Video packets are unchanged | None; the quality controls are hidden |
| ProRes source-aware | MOV | RGB, 4:4:4, or alpha → ProRes 4444 XQ; other sources → ProRes 422 HQ. `prores_ks` accepts 10-bit input; FFprobe commonly reports decoded XQ as 12-bit. Alpha is retained by the XQ path. | Fixed high-quality lossy class |
| DNxHR source-aware | MOV | RGB/4:4:4/alpha → DNxHR 444 10-bit; other >8-bit → HQX 4:2:2 10-bit; other 8-bit → HQ 4:2:2 8-bit. DNxHR cannot retain alpha, so alpha loss is disclosed and ProRes 4444 XQ is recommended when alpha matters. | Fixed high-quality lossy class |
| H.264 x264 | MP4 | Always 8-bit 4:2:0 for maximum compatibility; `libx264 -preset placebo -profile high` | CRF 0–51, default 12 |
| H.264 NVENC | MP4 | Always 8-bit 4:2:0 for maximum compatibility | CQ 0–51, default 12 |
| HEVC x265 | MP4 | Closest supported planar chroma/bit-depth path; `libx265 -preset veryslow`; alpha is discarded | CRF 0–51, default 12 |
| HEVC NVENC | MP4 | Closest supported NVENC chroma/bit-depth path; P7/UHQ VBR-CQ | CQ 0–51, default 12 |
| AV1 SVT-AV1 | MP4 | 4:2:0 at 8 or 10 bit; `libsvtav1 -preset 0`; alpha is discarded | CRF 0–63, default 12 |
| AV1 NVENC | MP4 | Closest supported NVENC chroma/bit-depth path; P7/UHQ VBR-CQ | CQ 0–63, default 12 |

The exact encoder must be exposed by the detected FFmpeg build. Hardware modes additionally require a compatible NVIDIA GPU and driver. The app checks the encoder list immediately and performs a one-second disposable preflight before the full transcode, so unsupported GPU options fail early without publishing an output.

### H.264 NVENC Ultra HQ command profile

The H.264 NVENC mode preserves these requested settings:

```text
-c:v h264_nvenc -pix_fmt yuv420p
-preset p7 -tune hq -rc vbr -cq <user CQ> -b:v 0
-multipass fullres -bf 4 -b_ref_mode middle
-rc-lookahead 27 -lookahead_level 3
-spatial-aq 0 -temporal-aq 1 -profile high
```

`b_ref_mode=middle` is the hierarchical middle B-reference option exposed by FFmpeg 9.0.1. A GPU/driver that advertises `h264_nvenc` can still reject `lookahead_level 3`; the preflight reports the exact driver message rather than silently lowering the requested setting.

## CRF and CQ guidance

Lower numbers retain more detail and usually create larger files. The default 12 is an Ultra HQ setting and can create very large files. As a starting guide:

- 12: Ultra HQ; slow/large, intended when quality is prioritized over size.
- 16–18: still very high quality for many sources.
- 20–23: a more typical delivery range.

Content, resolution, grain, and encoder differ, so there is no universal visual equivalence between CRF and CQ. NVENC CQ 0 means automatic selection, not lossless. Software value 0 is accepted, but pixel-format conversion and codec behavior mean the app still treats every transcode as potentially lossy; use stream copy or a true lossless workflow when mathematical preservation is required.

The x264 `placebo`, x265 `veryslow`, and SVT-AV1 preset 0 modes can be extremely slow. Their primary purpose here is maximum software encoding effort, as requested, not fast delivery.

## Output names and containers

With a blank Destination folder, outputs are placed beside each source. With a common destination, all uncompleted rows are placed in that folder. Names use:

- `_remux` for stream copy;
- `_prores`, `_dnxhr`, `_h264_x264`, `_h264_nvenc`, `_hevc_x265`, `_hevc_nvenc`, `_av1_svt`, or `_av1_nvenc` for transcoding.

If a proposed media path or audit report already exists—or same-stem inputs would collide—the app adds `_2`, `_3`, and so on. Existing files are never overwritten. Stream-copy reports end in `.remux.json`; transcode reports end in `.transcode.json`.

The file picker includes MKV, MP4, MOV, AVI, RM/RMVB, TS/MTS/M2TS, WebM, FLV/F4V, WMV/ASF, MPG/MPEG/VOB, OGV/Ogg, 3GP/3G2, MXF, DV, NUT, Y4M, and M4V. **All files** and drag-and-drop accept any other file that the detected FFprobe can inspect.

Input recognition is not the same as output compatibility. AVI is a legacy container and is especially limited with modern codecs and extra streams. A short preflight tests the actual selected streams, encoder, and destination muxer before the full operation.

## Verification and file safety

For every row, the app:

- passes paths as explicit process arguments and never through a shell;
- checks the source identity again immediately before work and before publication;
- runs a disposable container/encoder preflight;
- writes to a unique application-owned partial file in the destination folder;
- never overwrites a source, output, report, or destination that appears during processing;
- verifies copied non-video codecs/properties and the planned transcoded video codec, profile, tag, dimensions, pixel format, and frame rate;
- verifies timeline duration and chapters on the complete output;
- requires stream-copied FFV1 in MP4/MOV to expose a positive indexed frame count;
- promotes the partial file atomically only after verification passes; and
- writes the exact command, probes, selected/omitted streams, resolved encoder settings, quality value, space estimates, and checks to the adjacent JSON audit report.

Before starting, aggregate free space is checked per destination volume. Stream copy reserves approximately one source-sized output plus a safety margin. Transcoding uses a conservative profile/resolution estimate and refines it from the disposable preflight. These are safety estimates, not guaranteed final sizes.

Cancel stops the active FFmpeg process and removes its partial/preflight files. Already completed outputs remain intact; unstarted rows return to a retryable state.

## Stream selection details

Stream copy uses `-c copy` for every selected stream. In a transcoding profile, every selected video stream receives its resolved encoder independently, while selected audio/subtitle/data streams use stream copy.

**Video + audio** selects video and audio and maps container metadata/chapters. **Video only** selects video and maps metadata/chapters. **All compatible streams** maps exact inspected stream indexes, allowing known-incompatible extras to be named and omitted; AVI conservatively omits subtitle, attachment, and data tracks in this mode. **All source streams (strict)** requests every source stream and blocks known-incompatible MP4/MOV/AVI combinations instead of silently dropping data.

For example, an FFV1/AAC/SubRip MKV going to MP4 in compatible mode maps video and audio only. The confirmation, Details log, table, and audit report name the omitted SubRip track.

## FFmpeg detection and installation

At startup, the app automatically detects a paired `ffmpeg.exe` and `ffprobe.exe` in this order:

1. explicit command-line or environment paths;
2. the highest versioned `ffmpeg\<version>\bin` installation beside the app;
3. a legacy app-local `tools\ffmpeg\bin` folder;
4. FFmpeg on `PATH` and common standalone installation folders; and
5. known application-bundled copies as a last-resort fallback.

The GUI reports the detected version, generic source class, and path. It also inspects that exact build's video encoder list for profile availability.

The app checks stable-release metadata in the background. If FFmpeg is missing or older, **Install FFmpeg `<version>`** appears. Installation is user-confirmed, downloads the current release-essentials ZIP from gyan.dev, verifies provider metadata and SHA-256, rejects unsafe ZIP paths, validates `ffmpeg.exe`/`ffprobe.exe`, and installs them into a versioned subfolder beside the app. The release ZIP does not bundle FFmpeg.

## Drag-and-drop

Native File Explorer drag-and-drop uses TkinterDnD2/TkDND's Windows OLE2 integration. Multi-file payloads are parsed as Tcl lists so spaces, braces, ampersands, and Unicode paths remain intact. Windows normally blocks drag-and-drop between processes at different integrity levels; run Explorer and the app at the same elevation level or use **Add files**.

## Command-line modes

The GUI is the primary batch interface. Diagnostic and single-file CLI modes remain available:

```powershell
Stream Copy Remuxer.exe --dependency-check --output dependency.json
Stream Copy Remuxer.exe --self-test --output self-test.json
Stream Copy Remuxer.exe --probe input.mkv --output probe.json
Stream Copy Remuxer.exe --remux input.mkv --output output.mp4 --container mp4 --stream-mode av
Stream Copy Remuxer.exe --remux input.mkv --output output.avi --container avi --stream-mode av
Stream Copy Remuxer.exe --remux input.mkv --output output.mov --container mov --video-encoding prores_source_aware
Stream Copy Remuxer.exe --remux input.mkv --output output.mp4 --container mp4 --video-encoding h264_x264_placebo --quality 12
Stream Copy Remuxer.exe --remux input.mkv --output output.mp4 --container mp4 --video-encoding h264_nvenc_p7 --quality 12
```

`--video-encoding` choices are `copy`, `prores_source_aware`, `dnxhr_source_aware`, `h264_x264_placebo`, `h264_nvenc_p7`, `hevc_x265_veryslow`, `hevc_nvenc_p7`, `av1_svt_p0`, and `av1_nvenc_p7`.

The packaged self-test creates real FFV1, audio, and subtitle sources; exercises drag-and-drop dispatch, queue/profile/quality/help behavior, common destinations, stream-copy modes, and 100/150/200% DPI layouts; runs verified ProRes, DNxHR, x264, x265, and SVT-AV1 outputs; and statically verifies every requested H.264 NVENC command option without requiring NVIDIA hardware.

## Current limitations

- The queue is not persisted after the app closes.
- Files run one at a time by design.
- Selected non-video streams are copied, not automatically transcoded; an incompatible audio/subtitle codec can therefore be rejected by the destination preflight.
- Hardware encoder availability depends on the exact FFmpeg build, GPU generation, and installed driver. Encoder presence alone does not guarantee every requested option is supported.
- Alpha is preserved only by the ProRes 4444 XQ path among the supplied compatibility profiles; every affected profile discloses alpha removal.
- Container standards can normalize timestamps, tags, dispositions, or chapter representation.
- Verification avoids a second full-file packet-hash pass, which would double I/O on large files.
- The app-local FFmpeg installer requires internet access and a writable extracted application folder.
- The standalone EXE is not Authenticode-signed unless a signing identity is supplied separately.
