from __future__ import annotations

import unittest

from remux_main import build_parser
from stream_copy_remuxer.encoding import COPY_PROFILE_KEY, H264_NVENC_PROFILE_KEY


class CommandLineTests(unittest.TestCase):
    def test_stream_copy_remains_the_cli_default(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.video_encoding, COPY_PROFILE_KEY)
        self.assertIsNone(args.quality)
        self.assertEqual(args.container, "mp4")

    def test_cli_accepts_transcode_profile_and_quality(self) -> None:
        args = build_parser().parse_args(
            [
                "--remux",
                "source.mkv",
                "--output",
                "output.mp4",
                "--video-encoding",
                H264_NVENC_PROFILE_KEY,
                "--quality",
                "12",
            ]
        )
        self.assertEqual(args.video_encoding, H264_NVENC_PROFILE_KEY)
        self.assertEqual(args.quality, 12)

    def test_cli_accepts_avi_for_stream_copy(self) -> None:
        args = build_parser().parse_args(["--container", "avi"])
        self.assertEqual(args.container, "avi")


if __name__ == "__main__":
    unittest.main()
