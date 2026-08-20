# Stream Copy Remuxer 1.3.2

Certain software such as Topaz Video are more or less compatible with different containers. This app allows changing containers without re-encoding the video or audio.

Stream Copy Remuxer is a Windows batch front end for FFmpeg stream copy. It changes the container around already-encoded streams; it does not decode, re-encode, resize, or otherwise alter encoded video/audio packets.

Version 1.3.2 adds loss-safe handling for extra streams that MP4 or MOV cannot copy. **All compatible streams** maps exact stream indexes, keeps video/audio and supported extras, and names every intentionally omitted track in the table, Details log, confirmation workflow, and audit report. **Video only** removes audio and every other non-video stream for maximum compatibility while still copying the encoded video unchanged. **All source streams (strict)** remains available when nothing may be omitted. The Details log is also five rows taller (10 visible rows). The bounded FFV1 input analysis added in 1.3.1 remains unchanged.

## Batch workflow

1. Extract the release ZIP and open `Stream Copy Remuxer.exe`.
2. Drag multiple media files from File Explorer onto the window, or choose **Add files** and select several files.
3. Wait while FFprobe fills each row's detected input container, video encoding, audio encoding, and compatibility guidance.
4. Select one or more rows and choose **MP4**, **MOV**, or **MKV**. New rows default to MP4.
5. Choose the stream mode:
   - **Video + audio** copies all video and audio streams. It excludes subtitle, attachment, and data streams. Container metadata and chapters are still mapped separately and retained where the destination supports them.
   - **Video only** copies every video stream and excludes audio, subtitle, attachment, and data streams for maximum compatibility. Exact omissions are disclosed before the batch and recorded in its audit report.
   - **All compatible streams** keeps every stream covered by the destination's conservative stream-copy rules. MP4/MOV retain video, audio, and existing `mov_text` subtitles; incompatible extras such as SubRip are explicitly named and omitted without conversion. MKV keeps every source stream.
   - **All source streams (strict)** omits nothing. If MP4/MOV cannot copy a known extra stream, the app blocks the batch before FFmpeg starts and recommends compatible mode, video+audio mode, video-only mode, or MKV.
6. Optionally choose a common **Destination folder** for the batch. Leave it blank to put each output beside its own source. **Clear** restores the blank/default behavior.
7. Select **Start batch**, review the destination summary, and confirm.

With a blank Destination folder, each GUI output is written beside its source as `<source name>_remux.<selected extension>`. With a common destination, all uncompleted rows are written there. If a proposed path or audit report already exists—or same-stem inputs would collide—the app safely uses `_remux_2`, `_remux_3`, and so on. Existing files are never overwritten. Changing the setting never moves or deletes completed outputs.

Rows run sequentially to avoid competing for disk bandwidth on large lossless intermediates. A per-file compatibility or remux failure is recorded in that row and does not stop later files. Completed rows remain visible and their verified outputs remain available.

Select queue rows and press **Delete** (or choose **Remove selected**) to remove those rows. This never deletes source files, completed outputs, or reports. Queue editing is locked while a batch is active so the UI and worker cannot diverge.

After completion, **Show output** opens the actual folder containing the selected verified output. If no completed row is selected, it opens the most recently verified output folder.

## Input and output formats

The file picker includes MKV, MP4, MOV, AVI, RM/RMVB, TS/MTS/M2TS, WebM, FLV/F4V, WMV/ASF, MPG/MPEG/VOB, OGV/Ogg, 3GP/3G2, MXF, DV, NUT, Y4M, and M4V. **All files** and drag-and-drop also accept any other file that the detected FFprobe can inspect.

Input recognition is not the same as output compatibility. For example, an older RealVideo stream may be readable from RMVB but impossible to copy into MP4. Each row therefore receives a short destination-container preflight before the full copy. Known incompatible extra streams are handled before launch according to the selected stream mode; other incompatible combinations fail safely without publishing an output.

The only GUI output choices are:

| Destination | Typical use | Important limitation |
|---|---|---|
| MP4 | Default; common H.264/H.265/AV1 media; finalized FFV1 intermediate for Topaz | Some legacy codecs and subtitle/data/attachment streams are unsupported; FFV1/MP4 is not supported by every player/editor |
| MOV | ProRes and QuickTime-oriented workflows | FFV1/MOV is unusual; some copied codecs are not valid in MOV |
| MKV | Broadest codec and stream preservation | FFV1 frame count can remain unavailable to some software |

## Verification and file safety

For every row, the app:

- uses `-c copy` and passes paths as explicit process arguments, never through a shell;
- runs a short compatibility preflight before a potentially very large copy;
- writes to a unique application-owned partial file in the selected output folder;
- never overwrites a source, existing output, existing report, or destination that appears during processing;
- verifies selected stream codecs and core properties, duration, chapters, and source identity;
- requires FFV1 in MP4/MOV to expose a positive indexed frame count;
- promotes the partial file atomically only after verification passes; and
- writes an adjacent `<output>.remux.json` report containing the exact command, probes, and checks.

Before starting, aggregate free space is checked per destination volume for the complete ready batch. Plan for approximately one additional source-sized allocation per output plus a reserve. Stream copy is usually limited by source/destination disk speed and does not make a lossless source substantially smaller.

Cancel stops the active FFmpeg process and removes its partial/preflight files. Already completed outputs remain intact, while unstarted rows return to a retryable state.

## Stream selection details

**Video + audio** uses:

```text
-map 0:v? -map 0:a? -map_metadata 0 -map_chapters 0
```

It omits subtitle, attachment, and data streams, while separately mapping container metadata and chapters.

**Video only** uses:

```text
-map 0:v? -map_metadata 0 -map_chapters 0
```

It copies every encoded video stream unchanged and intentionally excludes audio and every non-video stream. The exact omitted tracks are shown in the table, confirmation, Details log, and JSON audit report.

**All compatible streams** uses explicit input-stream indexes. For an FFV1/AAC/SubRip source going to MP4, for example, it uses:

```text
-map 0:0 -map 0:1 -map_metadata 0 -map_chapters 0
```

The SubRip stream is omitted because copying it into MP4/MOV is unsupported, and the exact omitted index, type, codec, language, and title are disclosed. Existing `mov_text` subtitle streams are retained. For MKV, compatible mode selects every source stream. All selected streams still use `-c copy`.

**All source streams (strict)** uses:

```text
-map 0 -map_metadata 0 -map_chapters 0
```

It attempts every FFprobe stream and never drops one. A known SubRip/attachment/data incompatibility with MP4/MOV is reported before FFmpeg starts; use MKV if every such stream must be retained without re-encoding.

## FFmpeg detection and installation

At startup, the app automatically detects a paired `ffmpeg.exe` and `ffprobe.exe` in this order:

1. explicit command-line or environment paths;
2. the highest versioned `ffmpeg\<version>\bin` installation beside the app;
3. a legacy app-local `tools\ffmpeg\bin` folder;
4. FFmpeg on `PATH` and common standalone installation folders; and
5. known application-bundled copies as a last-resort system fallback.

The GUI displays only the detected FFmpeg version, generic source class, and path. It does not advertise the application that may have installed a system copy.

The app checks current stable-release metadata in the background. If FFmpeg is missing or older, **Install FFmpeg `<version>`** appears. Installation requires explicit confirmation and then:

1. downloads the current release-essentials ZIP from gyan.dev, a Windows-build provider linked by FFmpeg.org;
2. fetches the provider's current version and SHA-256 metadata over HTTPS;
3. restricts redirects to the expected provider host;
4. verifies the complete archive checksum before extraction;
5. rejects unsafe or incomplete ZIP content;
6. stages and validates `ffmpeg.exe` plus `ffprobe.exe`; and
7. promotes the validated files into a versioned `ffmpeg` subfolder beside the app.

As of August 17, 2026, the official current stable release is FFmpeg 9.0.1. The app queries current metadata rather than permanently assuming 9.0.1 will remain current. The release ZIP does not bundle FFmpeg; downloading it remains optional and user initiated.

If the app folder is not writable, extract or move the release folder to a location you can write to, then retry installation.

## Drag-and-drop

Native File Explorer drag-and-drop uses TkinterDnD2/TkDND's Windows OLE2 integration. Multi-file payloads are parsed as Tcl lists so spaces, braces, ampersands, and Unicode paths remain intact. The former custom Python/ctypes Windows window-procedure hook is not used.

Windows normally blocks a non-elevated Explorer process from dropping into an application deliberately launched as administrator. This app does not request elevation; run Explorer and the app at the same integrity level or use **Add files**.

## FFV1/MKV to finalized MP4

For an FFV1/MKV intermediate, add the source, leave its output set to MP4, and run the batch. The equivalent direct command is:

```powershell
& 'C:\path\to\ffmpeg.exe' `
  -hide_banner -nostdin -n `
  -i 'D:\path\input.mkv' `
  -map '0:v?' -map '0:a?' `
  -map_metadata 0 -map_chapters 0 `
  -c copy -tag:v:0 FFV1 `
  -f mp4 'D:\path\input_remux.mp4'
```

`-tag:v:0 FFV1` is appropriate only when the first copied video stream is FFV1. MP4/MOV outputs are ordinary finalized files, not fragmented files. The app does not use `faststart`, which would require an avoidable second rewrite of a very large local output.

## Current limitations

- The queue is not persisted after the application closes.
- Files run one at a time by design.
- Container compatibility is determined by the detected FFmpeg build and actual streams, not by filename extension alone.
- Stream copy can normalize container-level timestamps, tags, or dispositions where container standards differ.
- Verification avoids a second full-file packet-hash pass, which would double I/O on very large files.
- The app-local FFmpeg installer requires internet access and a writable extracted application folder.
- The standalone EXE is not Authenticode-signed unless a signing identity is provided separately.

## Command-line modes

The existing diagnostic and single-file remux modes remain available. GUI outputs default beside sources and can optionally share one destination folder; command-line remuxes retain an explicit `--output` path:

```powershell
Stream Copy Remuxer.exe --dependency-check --output dependency.json
Stream Copy Remuxer.exe --self-test --output self-test.json
Stream Copy Remuxer.exe --probe input.mkv --output probe.json
Stream Copy Remuxer.exe --remux input.mkv --output output.mp4 --container mp4 --stream-mode av
Stream Copy Remuxer.exe --remux input.mkv --output video-only.mp4 --container mp4 --stream-mode video
Stream Copy Remuxer.exe --remux input.mkv --output output.mp4 --container mp4 --stream-mode compatible
Stream Copy Remuxer.exe --ffmpeg C:\ffmpeg\bin\ffmpeg.exe --dependency-check
```

The self-test creates FFV1/MKV, MPEG-4/AVI, and FFV1/AAC/SubRip MKV sources. It exercises repeated multi-file TkDND/Tcl-list dispatch, verifies blank and common-destination planning, Status-column sizing, the 10-row Details log, `_remux` collision handling, and Delete-row behavior, and audits layout at 100%, 150%, and 200% scaling. It then stream-copies four plans through a Unicode common destination, verifies compatible-mode SubRip omission and video-only audio/subtitle omission disclosures, and verifies all outputs.
