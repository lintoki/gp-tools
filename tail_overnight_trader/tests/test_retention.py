import tempfile
import unittest
from pathlib import Path

from tail_trader.retention import prepare_output_file, trim_jsonl_file


class RetentionTest(unittest.TestCase):
    def test_prepare_output_file_keeps_room_for_new_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir) / "reports"
            directory.mkdir()
            for index in range(12):
                path = directory / f"20260623-14{index:02d}00.html"
                path.write_text(str(index), encoding="utf-8")

            pending = directory / "20260623-150000.html"
            prepare_output_file(pending, "*.html", keep=10)
            pending.write_text("new", encoding="utf-8")

            names = sorted(path.name for path in directory.glob("*.html"))

        self.assertEqual(len(names), 10)
        self.assertNotIn("20260623-140000.html", names)
        self.assertNotIn("20260623-140100.html", names)
        self.assertNotIn("20260623-140200.html", names)
        self.assertIn("20260623-150000.html", names)

    def test_trim_jsonl_file_keeps_latest_non_empty_lines(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "trades.jsonl"
            path.write_text("\n".join(f"line-{index}" for index in range(12)) + "\n", encoding="utf-8")

            trim_jsonl_file(path, keep=10)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(lines, [f"line-{index}" for index in range(2, 12)])


if __name__ == "__main__":
    unittest.main()
