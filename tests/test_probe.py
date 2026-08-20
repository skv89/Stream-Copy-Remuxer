from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from stream_copy_remuxer.probe import INPUT_ANALYZE_DURATION_MICROSECONDS, probe_media


class ProbeTests(unittest.TestCase):
    def test_probe_uses_bounded_analysis_and_parses_recovered_ffv1_pixel_format(self) -> None:
        payload = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "ffv1",
                    "width": 1424,
                    "height": 1080,
                    "pix_fmt": "yuv420p",
                    "avg_frame_rate": "25/1",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "48000",
                    "channels": 2,
                    "channel_layout": "stereo",
                },
            ],
            "format": {
                "format_name": "matroska,webm",
                "format_long_name": "Matroska / WebM",
                "duration": "2770.8",
            },
            "chapters": [],
        }
        with tempfile.TemporaryDirectory(prefix="remux-probe-analysis-test-") as folder:
            source = Path(folder) / "FFV1 source & 输入.mkv"
            source.write_bytes(b"source")
            completed = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=json.dumps(payload),
                stderr="",
            )
            with patch("stream_copy_remuxer.probe.subprocess.run", return_value=completed) as run:
                media = probe_media(Path("ffprobe.exe"), source)

        command = run.call_args.args[0]
        analysis_position = command.index("-analyzeduration")
        self.assertEqual(
            command[analysis_position + 1],
            str(INPUT_ANALYZE_DURATION_MICROSECONDS),
        )
        self.assertLess(analysis_position, command.index(str(source.resolve())))
        self.assertEqual(media.video_streams[0].pixel_format, "yuv420p")
        self.assertEqual(media.audio_streams[0].channel_layout, "stereo")
        self.assertEqual(run.call_args.kwargs["timeout"], 120.0)


if __name__ == "__main__":
    unittest.main()
