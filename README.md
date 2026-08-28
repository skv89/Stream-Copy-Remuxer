# Stream Copy Remuxer 1.6.0

Certain software such as Topaz Video are more or less compatible with different containers. Stream Copy Remuxer changes containers without re-encoding video or audio and also offers optional compatibility-focused video transcoding profiles.

## Download

[Download the portable Windows release](https://github.com/skv89/Stream-Copy-Remuxer/releases/tag/v1.6.0)

Only compiled portable application artifacts are distributed. Application source, tests, requirements, build scripts, and internal development records are not published.

The executable keeps the stable filename `Stream Copy Remuxer.exe` across releases so existing shortcuts continue to work.

SHA-256: `9D1BA3D5299DE7340F6F8772FE56EB380819117AA5798B6598D15730E2B7A581`

## What's new in 1.6.0

- Source-aware FFV1 version 3 output that preserves decoded bit depth, chroma, and alpha when the detected FFmpeg supports the source format.
- Every FFV1 frame is independently seekable with `-g 1`; 16 CRC-protected slices improve corruption localization and parallel decoding.
- Exact FFV1 options: `-level 3 -coder 2 -context 1 -g 1 -slicecrc 1 -slices 16`.
- MKV is the default FFV1 container; MOV, MP4, and AVI are also selectable.
- Updated selection summaries, compatibility guidance, confirmation text, and encoding help while preserving all existing stream-copy and transcoding modes.

## Screenshots

### Batch queue and source-aware ProRes selection

<p align="center">
  <img src="screenshots/stream-copy-remuxer-main-window.png" width="100%" alt="Stream Copy Remuxer batch queue with a source-aware ProRes output selected">
</p>

### Video output choices

<p align="center">
  <img src="screenshots/stream-copy-remuxer-video-output-options.png" width="100%" alt="Stream Copy Remuxer video output menu showing stream copy, ProRes, DNxHR, H.264, HEVC, and AV1 options">
</p>

> These screenshots are permanent project documentation. Keep both files in the public GitHub repository across future updates unless the repository owner explicitly requests their deletion.

## Portable application

Download and run `Stream Copy Remuxer.exe`. FFmpeg is detected from the system or can be installed into the application's own folder when needed. The executable is not Authenticode-signed.
