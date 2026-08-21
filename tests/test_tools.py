from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from stream_copy_remuxer.tools import video_encoders


class ToolCapabilityTests(unittest.TestCase):
    def test_video_encoder_parser_ignores_legend_and_keeps_video_encoder_names(self) -> None:
        output = """Encoders:
 V..... = Video
 A..... = Audio
 ------
 V....D prores_ks            Apple ProRes
 V..... libx264              libx264 H.264
 A..... aac                  AAC
"""
        completed = subprocess.CompletedProcess(["ffmpeg", "-encoders"], 0, output, "")
        with patch("stream_copy_remuxer.tools.subprocess.run", return_value=completed):
            result = video_encoders(Path("ffmpeg.exe"))
        self.assertEqual(result, frozenset({"prores_ks", "libx264"}))


if __name__ == "__main__":
    unittest.main()
