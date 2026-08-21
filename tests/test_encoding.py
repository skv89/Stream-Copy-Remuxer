from __future__ import annotations

import unittest
from pathlib import Path

from stream_copy_remuxer.encoding import (
    AV1_NVENC_PROFILE_KEY,
    AV1_SOFTWARE_PROFILE_KEY,
    DNXHR_PROFILE_KEY,
    H264_NVENC_PROFILE_KEY,
    H264_SOFTWARE_PROFILE_KEY,
    HEVC_SOFTWARE_PROFILE_KEY,
    PRORES_PROFILE_KEY,
    EncodingError,
    encoder_availability,
    resolve_quality,
    resolve_video_encoding,
)
from stream_copy_remuxer.models import StreamInfo, Toolchain


def source_video(pixel_format: str, *, bits: int | None = None) -> StreamInfo:
    return StreamInfo(
        index=0,
        codec_type="video",
        codec_name="ffv1",
        width=1920,
        height=1080,
        pixel_format=pixel_format,
        bits_per_raw_sample=bits,
        frame_rate="25/1",
    )


class EncodingProfileTests(unittest.TestCase):
    def test_prores_selects_422_hq_for_420_and_4444_xq_for_444_rgb_or_alpha(self) -> None:
        hq = resolve_video_encoding(source_video("yuv420p"), PRORES_PROFILE_KEY)
        self.assertEqual((hq.label, hq.pixel_format, hq.expected_profile), (
            "ProRes 422 HQ — source-aware MOV", "yuv422p10le", "HQ"
        ))
        for pixel_format, expected_pixel_format in (
            ("yuv444p12le", "yuv444p10le"),
            ("gbrp10le", "yuv444p10le"),
            ("rgba", "yuva444p10le"),
        ):
            with self.subTest(pixel_format=pixel_format):
                resolved = resolve_video_encoding(source_video(pixel_format), PRORES_PROFILE_KEY)
                self.assertIn("ProRes 4444 XQ", resolved.label)
                self.assertEqual(resolved.pixel_format, expected_pixel_format)
                self.assertEqual(
                    resolved.expected_pixel_format,
                    "yuva444p12le" if pixel_format == "rgba" else "yuv444p12le",
                )
                self.assertEqual(resolved.expected_profile, "XQ")
                self.assertIn(("profile", "5"), resolved.encoder_options)

    def test_dnxhr_selects_hq_hqx_and_444_from_source_depth_and_chroma(self) -> None:
        hq = resolve_video_encoding(source_video("yuv420p"), DNXHR_PROFILE_KEY)
        hqx = resolve_video_encoding(source_video("yuv422p12le"), DNXHR_PROFILE_KEY)
        rgb = resolve_video_encoding(source_video("gbrp12le"), DNXHR_PROFILE_KEY)
        self.assertEqual((hq.pixel_format, hq.expected_profile), ("yuv422p", "DNXHR HQ"))
        self.assertEqual((hqx.pixel_format, hqx.expected_profile), ("yuv422p10le", "DNXHR HQX"))
        self.assertEqual((rgb.pixel_format, rgb.expected_profile), ("gbrp10le", "DNXHR 444"))

    def test_dnxhr_uses_444_and_explicitly_discloses_alpha_loss(self) -> None:
        resolved = resolve_video_encoding(source_video("yuva444p10le"), DNXHR_PROFILE_KEY)
        self.assertEqual((resolved.pixel_format, resolved.expected_profile), ("yuv444p10le", "DNXHR 444"))
        self.assertIn("alpha channel is discarded", resolved.precision_notice)
        self.assertIn("ProRes 4444 XQ", resolved.precision_notice)

    def test_common_packed_semiplanar_and_legacy_formats_are_classified(self) -> None:
        cases = (
            ("pal8", "ProRes 4444 XQ", "yuv444p10le"),
            ("nv24", "ProRes 4444 XQ", "yuv444p10le"),
            ("p410le", "ProRes 4444 XQ", "yuv444p10le"),
            ("yuv440p10le", "ProRes 422 HQ", "yuv422p10le"),
            ("yuv411p", "ProRes 422 HQ", "yuv422p10le"),
            ("ya16le", "ProRes 4444 XQ", "yuva444p10le"),
            ("x2rgb10le", "ProRes 4444 XQ", "yuv444p10le"),
        )
        for pixel_format, label, encoder_format in cases:
            with self.subTest(pixel_format=pixel_format):
                resolved = resolve_video_encoding(source_video(pixel_format), PRORES_PROFILE_KEY)
                self.assertIn(label, resolved.label)
                self.assertEqual(resolved.pixel_format, encoder_format)

    def test_h264_software_is_placebo_crf_and_forces_8_bit_420(self) -> None:
        resolved = resolve_video_encoding(
            source_video("yuv444p12le"), H264_SOFTWARE_PROFILE_KEY, 7
        )
        self.assertEqual(resolved.pixel_format, "yuv420p")
        self.assertEqual(
            resolved.encoder_options,
            (("preset", "placebo"), ("crf", "7"), ("profile", "high")),
        )

    def test_h264_nvenc_uses_every_requested_ultra_quality_option(self) -> None:
        resolved = resolve_video_encoding(source_video("yuv444p12le"), H264_NVENC_PROFILE_KEY, 9)
        self.assertEqual(resolved.pixel_format, "yuv420p")
        self.assertEqual(
            dict(resolved.encoder_options),
            {
                "preset": "p7",
                "tune": "hq",
                "rc": "vbr",
                "cq": "9",
                "b": "0",
                "multipass": "fullres",
                "bf": "4",
                "b_ref_mode": "middle",
                "rc-lookahead": "27",
                "lookahead_level": "3",
                "spatial-aq": "0",
                "temporal-aq": "1",
                "profile": "high",
            },
        )

    def test_hevc_and_av1_choose_supported_precision_paths(self) -> None:
        hevc = resolve_video_encoding(source_video("yuv422p12le"), HEVC_SOFTWARE_PROFILE_KEY)
        av1_software = resolve_video_encoding(source_video("yuv444p12le"), AV1_SOFTWARE_PROFILE_KEY)
        av1_nvenc = resolve_video_encoding(source_video("yuv422p12le"), AV1_NVENC_PROFILE_KEY)
        self.assertEqual(hevc.pixel_format, "yuv422p12le")
        self.assertEqual(av1_software.pixel_format, "yuv420p10le")
        self.assertEqual((av1_nvenc.pixel_format, av1_nvenc.expected_pixel_format), (
            "p212le", "yuv422p12le"
        ))

    def test_quality_defaults_and_boundaries_are_encoder_specific(self) -> None:
        self.assertEqual(resolve_quality(H264_SOFTWARE_PROFILE_KEY, None), 12)
        self.assertEqual(resolve_quality(H264_NVENC_PROFILE_KEY, "0"), 0)
        self.assertEqual(resolve_quality(AV1_SOFTWARE_PROFILE_KEY, "63"), 63)
        with self.assertRaisesRegex(EncodingError, "between 0 and 51"):
            resolve_quality(H264_SOFTWARE_PROFILE_KEY, 52)
        with self.assertRaisesRegex(EncodingError, "whole number"):
            resolve_quality(AV1_SOFTWARE_PROFILE_KEY, "12.5")

    def test_unknown_pixel_format_is_blocked_for_source_aware_planning(self) -> None:
        with self.assertRaisesRegex(EncodingError, "no detected pixel format"):
            resolve_video_encoding(source_video(""), PRORES_PROFILE_KEY)

    def test_encoder_capability_disclosure_uses_exact_detected_build(self) -> None:
        toolchain = Toolchain(
            Path("ffmpeg.exe"),
            Path("ffprobe.exe"),
            "test",
            video_encoders=frozenset({"libx264"}),
        )
        self.assertTrue(encoder_availability(toolchain, H264_SOFTWARE_PROFILE_KEY)[0])
        available, detail = encoder_availability(toolchain, H264_NVENC_PROFILE_KEY)
        self.assertFalse(available)
        self.assertIn("h264_nvenc", detail)


if __name__ == "__main__":
    unittest.main()
