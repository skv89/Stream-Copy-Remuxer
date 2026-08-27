# Stream Copy Remuxer 1.5.0

Certain software such as Topaz Video are more or less compatible with different containers. Stream Copy Remuxer changes containers without re-encoding video or audio and also offers optional compatibility-focused video transcoding profiles.

## Download

[Download the portable Windows release](https://github.com/skv89/Stream-Copy-Remuxer/releases/tag/v1.5.0)

Only compiled portable application artifacts are distributed. Application source, tests, requirements, build scripts, and internal development records are not published.

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

The release is a self-contained Windows application package. Extract it and run `Stream Copy Remuxer.exe`. FFmpeg is detected from the system or can be installed into the application's own folder when needed.
