# Stream Copy Remuxer 1.4.0 — Transcoding Requirements

Authoritative baseline: commit `4e687835a968cb02a551f3e8822c29c96a0b34d9` on branch `codex/transcoding-v1.4.0`.

## User requirements

- Preserve the existing batch stream-copy workflow as the default.
- Add ProRes and DNxHR transcoding for applications that cannot import FFV1, even after remuxing.
- Choose the closest supported ProRes/DNxHR class automatically from each source video stream's detected bit depth, chroma family, RGB family, and alpha presence.
- Add HEVC and AV1 software and NVIDIA NVENC choices.
- Add H.264 software and NVIDIA NVENC choices for maximum compatibility.
- H.264 software must use 8-bit 4:2:0, `libx264`, and preset `placebo`.
- H.264 NVENC must use preset `p7`, tune `hq`, VBR plus user CQ, full-resolution multipass, four B-frames, middle B-reference mode, 27-frame rate-control lookahead, lookahead level 3, spatial AQ off, and temporal AQ on.
- Let users enter CRF or CQ for applicable lossy profiles, validate the encoder-specific range, and explain that lower values increase quality and file size.
- Add a reusable high-contrast encoding/stream help popup modeled on Video Crop Tool's help window.
- Clearly disclose that transcoding profiles are lossy, while stream copy still does not re-encode selected streams.

## Resolved behavior

- Release version: `1.4.0` because this is a substantial, backward-compatible feature release.
- Output modes:
  - Stream copy — selected MP4/MOV/MKV container.
  - ProRes — source-aware MOV.
  - DNxHR — source-aware MOV.
  - H.264 x264 — software placebo/CRF MP4, always 8-bit 4:2:0.
  - H.264 NVENC — P7/HQ VBR-CQ MP4, always 8-bit 4:2:0.
  - HEVC x265 — software veryslow/CRF MP4 with a closest supported decoded pixel-format path.
  - HEVC NVENC — P7/UHQ VBR-CQ MP4 with a closest supported decoded pixel-format path.
  - AV1 SVT-AV1 — preset 0/CRF MP4, 4:2:0 at 8 or 10 bit.
  - AV1 NVENC — P7/UHQ VBR-CQ MP4 with a closest supported decoded pixel-format path.
- Default CRF/CQ: 12. Valid ranges: x264/x265/NVENC H.264/HEVC 0–51; SVT-AV1/AV1 NVENC 0–63. NVENC value 0 means automatic quality selection, not lossless.
- `b_ref_mode=middle` is used because the user requested B-reference mode without a value and FFmpeg 9.0.1 exposes `disabled`, `each`, and `middle`; middle is the high-quality hierarchical choice used by the reference tool.
- ProRes resolution:
  - RGB, 4:4:4, or alpha → ProRes 4444 XQ, 10-bit; alpha is preserved.
  - Other source chroma → ProRes 422 HQ, 10-bit.
- DNxHR resolution:
  - RGB, 4:4:4, or alpha → DNxHR 444, 10-bit. DNxHR cannot retain alpha, so alpha loss is explicitly disclosed and ProRes 4444 XQ is recommended when alpha is required.
  - Other source video above 8-bit → DNxHR HQX, 4:2:2 10-bit.
  - Other 8-bit source video → DNxHR HQ, 4:2:2 8-bit.
- Every selected video stream is encoded independently with its resolved path. Selected non-video streams remain stream-copied according to the existing stream mode and container-compatibility policy.
- Remux outputs keep `_remux`; transcoding outputs receive a codec-specific suffix. Existing files and reports are never overwritten.
- Audit reports record the exact resolved encoder, pixel format, options, quality, lossy disclosure, command, probes, and verification checks.

## Acceptance criteria

- Existing stream-copy unit and real-FFmpeg tests still pass unchanged.
- Static command tests assert every requested H.264 software/NVENC option and quality validation boundary.
- Profile tests cover 8/10/12-bit, 4:2:0/4:2:2/4:4:4, RGB, and alpha source resolution.
- Real-FFmpeg tests verify ProRes, DNxHR, x264, x265, and SVT-AV1 output codecs, pixel formats, dimensions, timelines, and copied non-video streams.
- NVENC commands pass a disposable hardware preflight when a compatible NVIDIA encoder is usable; absence of compatible hardware is reported without affecting software modes.
- GUI tests cover per-row profile application, fixed-container behavior, CRF/CQ validation, capability disclosure, and help content.
- Packaged executable self-test, TkDND registration, DPI layout audit, and release-manifest checks pass.
- The exact release folder and ZIP are rebuilt after the final material change and inspected before handoff.
