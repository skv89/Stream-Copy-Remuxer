from __future__ import annotations

import unittest
from pathlib import Path

from stream_copy_remuxer.drop_support import parse_drop_paths


class DropSupportTests(unittest.TestCase):
    def test_normalized_tcl_list_values_preserve_unicode_spaced_paths(self) -> None:
        expected = (
            Path(r"D:\Media files\first & one.mkv"),
            Path(r"D:\中文\{episode 02}.avi"),
            Path(r"D:\plain.ts"),
        )

        class Root:
            class Tcl:
                @staticmethod
                def splitlist(_data: str) -> tuple[str, ...]:
                    raise AssertionError("Tuple input should already be a normalized Tcl list.")

            tk = Tcl()

        self.assertEqual(parse_drop_paths(Root(), tuple(str(path) for path in expected)), expected)  # type: ignore[arg-type]

    def test_unsafe_python_wndproc_hook_is_not_present(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "stream_copy_remuxer"
        combined = "\n".join(path.read_text(encoding="utf-8") for path in source_root.glob("*.py"))
        self.assertNotIn("SetWindowLongPtrW", combined)
        self.assertNotIn("GWLP_WNDPROC", combined)


if __name__ == "__main__":
    unittest.main()
