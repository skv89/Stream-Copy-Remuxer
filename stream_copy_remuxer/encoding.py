from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ResolvedVideoEncoding, StreamInfo, Toolchain


COPY_PROFILE_KEY = "copy"
PRORES_PROFILE_KEY = "prores_source_aware"
DNXHR_PROFILE_KEY = "dnxhr_source_aware"
H264_SOFTWARE_PROFILE_KEY = "h264_x264_placebo"
H264_NVENC_PROFILE_KEY = "h264_nvenc_p7"
HEVC_SOFTWARE_PROFILE_KEY = "hevc_x265_veryslow"
HEVC_NVENC_PROFILE_KEY = "hevc_nvenc_p7"
AV1_SOFTWARE_PROFILE_KEY = "av1_svt_p0"
AV1_NVENC_PROFILE_KEY = "av1_nvenc_p7"


class EncodingError(RuntimeError):
    pass


@dataclass(frozen=True)
class QualitySpec:
    name: str
    minimum: int
    maximum: int
    default: int = 12
    zero_is_automatic: bool = False


@dataclass(frozen=True)
class EncodingProfile:
    key: str
    label: str
    fixed_container_key: str | None
    encoder_name: str | None
    codec_name: str | None
    lossy: bool
    hardware: bool = False
    quality: QualitySpec | None = None


ENCODING_PROFILES: dict[str, EncodingProfile] = {
    COPY_PROFILE_KEY: EncodingProfile(
        COPY_PROFILE_KEY,
        "Stream copy — no re-encoding",
        None,
        None,
        None,
        False,
    ),
    PRORES_PROFILE_KEY: EncodingProfile(
        PRORES_PROFILE_KEY,
        "ProRes — source-aware MOV",
        "mov",
        "prores_ks",
        "prores",
        True,
    ),
    DNXHR_PROFILE_KEY: EncodingProfile(
        DNXHR_PROFILE_KEY,
        "DNxHR — source-aware MOV",
        "mov",
        "dnxhd",
        "dnxhd",
        True,
    ),
    H264_SOFTWARE_PROFILE_KEY: EncodingProfile(
        H264_SOFTWARE_PROFILE_KEY,
        "H.264 x264 — software placebo/CRF MP4",
        "mp4",
        "libx264",
        "h264",
        True,
        quality=QualitySpec("CRF", 0, 51),
    ),
    H264_NVENC_PROFILE_KEY: EncodingProfile(
        H264_NVENC_PROFILE_KEY,
        "H.264 NVENC — P7/HQ VBR-CQ MP4",
        "mp4",
        "h264_nvenc",
        "h264",
        True,
        hardware=True,
        quality=QualitySpec("CQ", 0, 51, zero_is_automatic=True),
    ),
    HEVC_SOFTWARE_PROFILE_KEY: EncodingProfile(
        HEVC_SOFTWARE_PROFILE_KEY,
        "HEVC x265 — software veryslow/CRF MP4",
        "mp4",
        "libx265",
        "hevc",
        True,
        quality=QualitySpec("CRF", 0, 51),
    ),
    HEVC_NVENC_PROFILE_KEY: EncodingProfile(
        HEVC_NVENC_PROFILE_KEY,
        "HEVC NVENC — P7/UHQ VBR-CQ MP4",
        "mp4",
        "hevc_nvenc",
        "hevc",
        True,
        hardware=True,
        quality=QualitySpec("CQ", 0, 51, zero_is_automatic=True),
    ),
    AV1_SOFTWARE_PROFILE_KEY: EncodingProfile(
        AV1_SOFTWARE_PROFILE_KEY,
        "AV1 SVT-AV1 — preset 0/CRF MP4",
        "mp4",
        "libsvtav1",
        "av1",
        True,
        quality=QualitySpec("CRF", 0, 63),
    ),
    AV1_NVENC_PROFILE_KEY: EncodingProfile(
        AV1_NVENC_PROFILE_KEY,
        "AV1 NVENC — P7/UHQ VBR-CQ MP4",
        "mp4",
        "av1_nvenc",
        "av1",
        True,
        hardware=True,
        quality=QualitySpec("CQ", 0, 63, zero_is_automatic=True),
    ),
}

ENCODING_PROFILE_CHOICES: tuple[tuple[str, str], ...] = tuple(
    (profile.label, profile.key) for profile in ENCODING_PROFILES.values()
)
ENCODING_LABELS: dict[str, str] = dict(ENCODING_PROFILE_CHOICES)
ENCODING_LABEL_BY_KEY: dict[str, str] = {
    key: label for label, key in ENCODING_PROFILE_CHOICES
}


def profile_for(profile_key: str) -> EncodingProfile:
    try:
        return ENCODING_PROFILES[profile_key]
    except KeyError as exc:
        raise EncodingError(f"Unknown video output mode: {profile_key}") from exc


def quality_spec(profile_key: str) -> QualitySpec | None:
    return profile_for(profile_key).quality


def resolve_quality(profile_key: str, value: int | str | None = None) -> int | None:
    spec = quality_spec(profile_key)
    if spec is None:
        return None
    if value is None or (isinstance(value, str) and not value.strip()):
        return spec.default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EncodingError(f"{spec.name} must be a whole number.") from exc
    if not spec.minimum <= parsed <= spec.maximum:
        raise EncodingError(
            f"{spec.name} must be between {spec.minimum} and {spec.maximum}; received {parsed}."
        )
    return parsed


def effective_container_key(profile_key: str, copy_container_key: str) -> str:
    profile = profile_for(profile_key)
    return profile.fixed_container_key or copy_container_key


def output_name_suffix(profile_key: str) -> str:
    return {
        COPY_PROFILE_KEY: "remux",
        PRORES_PROFILE_KEY: "prores",
        DNXHR_PROFILE_KEY: "dnxhr",
        H264_SOFTWARE_PROFILE_KEY: "h264_x264",
        H264_NVENC_PROFILE_KEY: "h264_nvenc",
        HEVC_SOFTWARE_PROFILE_KEY: "hevc_x265",
        HEVC_NVENC_PROFILE_KEY: "hevc_nvenc",
        AV1_SOFTWARE_PROFILE_KEY: "av1_svt",
        AV1_NVENC_PROFILE_KEY: "av1_nvenc",
    }[profile_for(profile_key).key]


def report_suffix(profile_key: str) -> str:
    return ".remux.json" if profile_key == COPY_PROFILE_KEY else ".transcode.json"


def _source_bit_depth(stream: StreamInfo) -> int:
    if stream.bits_per_raw_sample and stream.bits_per_raw_sample > 0:
        return stream.bits_per_raw_sample
    name = stream.pixel_format.lower()
    packed_depths = {
        "rgb48le": 16,
        "rgb48be": 16,
        "bgr48le": 16,
        "bgr48be": 16,
        "rgba64le": 16,
        "rgba64be": 16,
        "p010le": 10,
        "p012le": 12,
        "p016le": 16,
        "p210le": 10,
        "p212le": 12,
        "p216le": 16,
        "p410le": 10,
        "p412le": 12,
        "p416le": 16,
        "x2rgb10le": 10,
        "x2bgr10le": 10,
        "ya16le": 16,
        "ya16be": 16,
        "ayuv64le": 16,
        "ayuv64be": 16,
    }
    if name in packed_depths:
        return packed_depths[name]
    match = re.search(r"(?:p|rgb|bgr|gray|gbr)(9|10|12|14|16)(?:msb)?(?:le|be)?$", name)
    return int(match.group(1)) if match else 8


def source_characteristics(stream: StreamInfo) -> tuple[bool, str, int]:
    name = stream.pixel_format.lower().strip()
    if not name or name in {"none", "unknown"}:
        raise EncodingError(
            f"Source video stream #{stream.index} has no detected pixel format. "
            "It cannot be source-matched safely; inspect the file with a current FFprobe build."
        )
    has_alpha = name.startswith(("yuva", "gbra", "ya")) or name in {
        "rgba",
        "bgra",
        "argb",
        "abgr",
        "rgba64le",
        "rgba64be",
        "ayuv64le",
        "ayuv64be",
        "uyva",
        "vuya",
    }
    if name.startswith(("gbr", "rgb", "bgr", "rgba", "bgra", "argb", "abgr")) or name in {
        "0rgb",
        "0bgr",
        "pal8",
    } or name.startswith(("x2rgb", "x2bgr", "xyz")):
        family = "rgb"
    elif "444" in name or name.startswith(("nv24", "nv42", "p41", "ayuv", "uyva", "vuya", "vuyx")):
        family = "444"
    elif "422" in name or "440" in name or name.startswith(("nv16", "p21")):
        family = "422"
    elif "420" in name or "411" in name or "410" in name or name.startswith(("nv12", "p01")):
        family = "420"
    elif name.startswith(("gray", "mono", "ya")):
        family = "gray"
    else:
        raise EncodingError(
            f"Source video stream #{stream.index} uses pixel format {stream.pixel_format}, "
            "whose chroma family cannot be classified safely."
        )
    return has_alpha, family, _source_bit_depth(stream)


def _normalized_depth(depth: int, *, maximum: int = 12) -> int:
    if depth <= 8:
        return 8
    if depth <= 10:
        return 10
    return min(12, maximum)


def _planar_pixel_format(family: str, depth: int) -> str:
    suffix = "" if depth == 8 else f"{depth}le"
    if family == "rgb":
        return f"gbrp{suffix}"
    if family == "gray":
        return f"gray{suffix}"
    return f"yuv{family}p{suffix}"


def _nvenc_pixel_formats(family: str, depth: int) -> tuple[str, str]:
    if family in {"rgb", "444"}:
        expected = _planar_pixel_format("444", depth)
        return expected, expected
    if family == "gray":
        family = "420"
    if family == "422":
        if depth == 8:
            return "nv16", "yuv422p"
        return f"p2{depth}le", f"yuv422p{depth}le"
    if depth == 8:
        return "nv12", "yuv420p"
    return f"p0{depth}le", f"yuv420p{depth}le"


def resolve_video_encoding(
    stream: StreamInfo,
    profile_key: str,
    quality: int | str | None = None,
    *,
    output_video_index: int = 0,
) -> ResolvedVideoEncoding:
    profile = profile_for(profile_key)
    if profile.key == COPY_PROFILE_KEY:
        raise EncodingError("Stream-copy mode does not create a video encoder configuration.")
    selected_quality = resolve_quality(profile_key, quality)
    assert profile.fixed_container_key and profile.encoder_name and profile.codec_name
    has_alpha, family, source_depth = source_characteristics(stream)
    quality_name = profile.quality.name if profile.quality else ""
    expected_pixel_format = ""

    if profile_key == PRORES_PROFILE_KEY:
        if has_alpha or family in {"rgb", "444"}:
            pixel_format = "yuva444p10le" if has_alpha else "yuv444p10le"
            expected_pixel_format = "yuva444p12le" if has_alpha else "yuv444p12le"
            variant, expected_profile, tag = "ProRes 4444 XQ", "XQ", "ap4x"
            options = (("profile", "5"), ("vendor", "apl0"), ("tag", tag))
        else:
            pixel_format = "yuv422p10le"
            variant, expected_profile, tag = "ProRes 422 HQ", "HQ", "apch"
            options = (("profile", "3"), ("vendor", "apl0"), ("tag", tag))
        if source_depth < 10:
            precision = f"{source_depth}-bit source samples are represented in a 10-bit path without gaining precision."
        elif source_depth == 10:
            precision = "The source and encoder paths are both 10-bit."
        else:
            precision = f"{source_depth}-bit source samples are quantized to ProRes's 10-bit path."
        label = f"{variant} — source-aware MOV"
    elif profile_key == DNXHR_PROFILE_KEY:
        if has_alpha or family in {"rgb", "444"}:
            pixel_format = "gbrp10le" if family == "rgb" else "yuv444p10le"
            variant, expected_profile = "DNxHR 444", "DNXHR 444"
            options = (("profile", "dnxhr_444"),)
        elif source_depth > 8:
            pixel_format = "yuv422p10le"
            variant, expected_profile = "DNxHR HQX", "DNXHR HQX"
            options = (("profile", "dnxhr_hqx"),)
        else:
            pixel_format = "yuv422p"
            variant, expected_profile = "DNxHR HQ", "DNXHR HQ"
            options = (("profile", "dnxhr_hq"),)
        tag = ""
        precision = (
            f"DNxHR selected {pixel_format}, the closest supported class for source format "
            f"{stream.pixel_format}; DNxHR is high-quality lossy encoding."
        )
        if has_alpha:
            precision += " DNxHR cannot retain alpha; the alpha channel is discarded. Use ProRes 4444 XQ when alpha is required."
        label = f"{variant} — source-aware MOV"
    elif profile_key in {H264_SOFTWARE_PROFILE_KEY, H264_NVENC_PROFILE_KEY}:
        pixel_format = "yuv420p"
        expected_profile = "High"
        tag = ""
        if profile_key == H264_SOFTWARE_PROFILE_KEY:
            options = (
                ("preset", "placebo"),
                ("crf", str(selected_quality)),
                ("profile", "high"),
            )
            label = "H.264 x264 placebo"
        else:
            options = (
                ("preset", "p7"),
                ("tune", "hq"),
                ("rc", "vbr"),
                ("cq", str(selected_quality)),
                ("b", "0"),
                ("multipass", "fullres"),
                ("bf", "4"),
                ("b_ref_mode", "middle"),
                ("rc-lookahead", "27"),
                ("lookahead_level", "3"),
                ("spatial-aq", "0"),
                ("temporal-aq", "1"),
                ("profile", "high"),
            )
            label = "H.264 NVENC P7/HQ"
        precision = (
            f"For maximum compatibility, source format {stream.pixel_format} is converted to 8-bit 4:2:0."
            + (" The alpha channel is discarded." if has_alpha else "")
        )
    elif profile_key == HEVC_SOFTWARE_PROFILE_KEY:
        if has_alpha:
            family = "444" if family in {"rgb", "444"} else family
        depth = _normalized_depth(source_depth)
        pixel_format = _planar_pixel_format(family, depth)
        expected_profile = ""
        tag = "hvc1"
        options = (
            ("preset", "veryslow"),
            ("crf", str(selected_quality)),
            ("tag", "hvc1"),
        )
        label = "HEVC x265 veryslow"
        precision = f"HEVC uses the closest supported {pixel_format} path for {stream.pixel_format}."
        if has_alpha:
            precision += " The alpha channel is discarded."
    elif profile_key in {HEVC_NVENC_PROFILE_KEY, AV1_NVENC_PROFILE_KEY}:
        if has_alpha:
            family = "444" if family in {"rgb", "444"} else family
        depth = _normalized_depth(source_depth)
        encoder_pixel_format, expected_pixel_format = _nvenc_pixel_formats(family, depth)
        pixel_format = encoder_pixel_format
        expected_profile = ""
        tag = "hvc1" if profile_key == HEVC_NVENC_PROFILE_KEY else "av01"
        options = (
            ("preset", "p7"),
            ("tune", "uhq"),
            ("rc", "vbr"),
            ("cq", str(selected_quality)),
            ("b", "0"),
            ("multipass", "fullres"),
            ("temporal-aq", "1"),
            ("spatial-aq", "1"),
            ("b_ref_mode", "middle"),
            ("lookahead_level", "auto"),
            ("tf_level", "4"),
            ("tag", tag),
        )
        label = "HEVC NVENC P7/UHQ" if profile_key == HEVC_NVENC_PROFILE_KEY else "AV1 NVENC P7/UHQ"
        precision = f"NVENC uses the closest supported {expected_pixel_format} path for {stream.pixel_format}."
        if has_alpha:
            precision += " The alpha channel is discarded."
        return ResolvedVideoEncoding(
            source_stream_index=stream.index,
            output_video_index=output_video_index,
            profile_key=profile_key,
            label=label,
            container_key=profile.fixed_container_key,
            encoder_name=profile.encoder_name,
            codec_name=profile.codec_name,
            pixel_format=pixel_format,
            expected_pixel_format=expected_pixel_format,
            expected_profile=expected_profile,
            expected_codec_tag=tag,
            encoder_options=options,
            lossy=profile.lossy,
            quality_name=quality_name,
            quality_value=selected_quality,
            precision_notice=precision,
        )
    elif profile_key == AV1_SOFTWARE_PROFILE_KEY:
        depth = 8 if source_depth <= 8 else 10
        pixel_format = _planar_pixel_format("420", depth)
        expected_profile = "Main"
        tag = "av01"
        options = (
            ("preset", "0"),
            ("crf", str(selected_quality)),
            ("tag", "av01"),
        )
        label = "AV1 SVT-AV1 preset 0"
        precision = (
            f"SVT-AV1 accepts 4:2:0 at 8 or 10 bit; source format {stream.pixel_format} uses {pixel_format}."
        )
        if has_alpha:
            precision += " The alpha channel is discarded."
    else:
        raise EncodingError(f"Unknown video output mode: {profile_key}")

    return ResolvedVideoEncoding(
        source_stream_index=stream.index,
        output_video_index=output_video_index,
        profile_key=profile_key,
        label=label,
        container_key=profile.fixed_container_key,
        encoder_name=profile.encoder_name,
        codec_name=profile.codec_name,
        pixel_format=pixel_format,
        expected_pixel_format=expected_pixel_format or pixel_format,
        expected_profile=expected_profile,
        expected_codec_tag=tag,
        encoder_options=options,
        lossy=profile.lossy,
        quality_name=quality_name,
        quality_value=selected_quality,
        precision_notice=precision,
    )


def required_encoder(profile_key: str) -> str | None:
    return profile_for(profile_key).encoder_name


def encoder_availability(toolchain: Toolchain, profile_key: str) -> tuple[bool, str]:
    encoder = required_encoder(profile_key)
    if encoder is None:
        return True, "No encoder is needed; selected packets are copied."
    if not toolchain.video_encoders:
        return True, "Encoder list was unavailable; the disposable preflight will verify support."
    if encoder in toolchain.video_encoders:
        hardware_note = " A compatible NVIDIA GPU and driver are also required." if profile_for(profile_key).hardware else ""
        return True, f"Detected FFmpeg exposes {encoder}.{hardware_note}"
    return False, f"The detected FFmpeg build does not expose the required {encoder} encoder."


def profile_description(
    profile_key: str,
    stream: StreamInfo | None = None,
    quality: int | str | None = None,
) -> str:
    profile = profile_for(profile_key)
    selected_quality = resolve_quality(profile_key, quality)
    if profile_key == COPY_PROFILE_KEY:
        return "Copies selected encoded packets into MP4, MOV, MKV, or AVI without decoding or re-encoding."
    if stream is not None:
        resolved = resolve_video_encoding(stream, profile_key, selected_quality)
        quality_text = (
            f" {resolved.quality_name} {resolved.quality_value}; lower values increase quality and file size."
            if resolved.quality_name
            else ""
        )
        options = " ".join(f"-{name} {value}" for name, value in resolved.encoder_options)
        return (
            f"Resolves this source to {resolved.label}; encoder input {resolved.pixel_format}; expected decoded "
            f"output {resolved.expected_pixel_format}; encoder {resolved.encoder_name}.{quality_text} "
            f"Encoder options: {options}. {resolved.precision_notice} This is lossy encoding."
        )
    if profile_key == PRORES_PROFILE_KEY:
        return (
            "MOV interchange output. RGB, 4:4:4, or alpha sources use the ProRes 4444 XQ class "
            "through prores_ks's 10-bit input path (FFprobe commonly reports the decoded XQ output as 12-bit); "
            "other sources use ProRes 422 HQ at 10-bit. High-quality lossy encoding."
        )
    if profile_key == DNXHR_PROFILE_KEY:
        return (
            "MOV interchange output. RGB/4:4:4 uses DNxHR 444 10-bit; other sources above 8-bit use "
            "DNxHR HQX 4:2:2 10-bit; 8-bit sources use DNxHR HQ 4:2:2 8-bit. DNxHR cannot retain "
            "alpha, so alpha is disclosed and discarded. High-quality lossy encoding."
        )
    if profile_key == H264_SOFTWARE_PROFILE_KEY:
        return (
            f"MP4 compatibility output. libx264 always uses 8-bit 4:2:0, -preset placebo, -profile high, "
            f"and user CRF {selected_quality} (0–51; lower is higher quality). Placebo can be extremely slow. "
            "Potentially lossy encoding."
        )
    if profile_key == H264_NVENC_PROFILE_KEY:
        return (
            f"MP4 compatibility output. h264_nvenc always uses 8-bit 4:2:0 with -preset p7 -tune hq -rc vbr "
            f"-cq {selected_quality} -b 0 -multipass fullres -bf 4 -b_ref_mode middle -rc-lookahead 27 "
            "-lookahead_level 3 -spatial-aq 0 -temporal-aq 1 -profile high. CQ 0 means automatic, not lossless. "
            "A disposable preflight checks whether the NVIDIA GPU/driver accepts every option. Lossy encoding."
        )
    if profile_key == HEVC_SOFTWARE_PROFILE_KEY:
        return (
            f"MP4 output using libx265 -preset veryslow and user CRF {selected_quality} (0–51), with the closest "
            "supported planar chroma/bit-depth path and hvc1 tag. Alpha is discarded. Lossy encoding."
        )
    if profile_key == HEVC_NVENC_PROFILE_KEY:
        return (
            f"MP4 output using hevc_nvenc P7/UHQ, VBR-CQ {selected_quality}, zero target bitrate, full-resolution "
            "multipass, temporal/spatial AQ, middle B-reference mode, automatic lookahead level, temporal filter "
            "level 4, and hvc1 tag. CQ 0 means automatic. Alpha is discarded. Lossy encoding."
        )
    if profile_key == AV1_SOFTWARE_PROFILE_KEY:
        return (
            f"MP4 output using libsvtav1 -preset 0 and user CRF {selected_quality} (0–63), at 4:2:0 8- or 10-bit "
            "with av01 tag. Preset 0 can be extremely slow; alpha is discarded. Lossy encoding."
        )
    if profile_key == AV1_NVENC_PROFILE_KEY:
        return (
            f"MP4 output using av1_nvenc P7/UHQ, VBR-CQ {selected_quality}, zero target bitrate, full-resolution "
            "multipass, temporal/spatial AQ, middle B-reference mode, automatic lookahead level, temporal filter "
            "level 4, and av01 tag. CQ 0 means automatic. Alpha is discarded. Lossy encoding."
        )
    spec = profile.quality
    assert spec is not None
    automatic = " Value 0 asks NVENC to choose automatically." if spec.zero_is_automatic else ""
    return (
        f"{profile.label}. User-adjustable {spec.name} {selected_quality} ({spec.minimum}–{spec.maximum}); "
        f"lower is higher quality and usually larger.{automatic} This is lossy encoding."
    )


def encoding_help_text(toolchain: Toolchain, stream: StreamInfo | None = None) -> str:
    sections = ["VIDEO OUTPUT MODES"]
    for label, key in ENCODING_PROFILE_CHOICES:
        available, availability = encoder_availability(toolchain, key)
        state = "Available" if available else "Unavailable"
        sections.append(
            f"\n{label}\n{profile_description(key, stream)}\n{state}: {availability}"
        )
    sections.append(
        "\n\nCRF / CQ GUIDE\nCRF is software encoder quality; CQ is NVIDIA constant-quality targeting. "
        "Lower numbers retain more detail and usually create larger files. 12 is the Ultra HQ default and "
        "can be very large; 16–18 is still very high quality, 20–23 is a more typical delivery range. "
        "Results depend on content. Software value 0 is accepted, but pixel-format conversion and codec behavior "
        "mean the app still treats every transcode as potentially lossy. For NVENC, 0 means automatic quality "
        "selection, not lossless."
    )
    return "\n".join(sections)
