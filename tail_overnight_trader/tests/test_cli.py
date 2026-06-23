import unittest

from tail_trader.cli import DEFAULT_DATA_DIR, default_scan_args


class CliTest(unittest.TestCase):
    def test_default_scan_args_are_enough_for_one_command_report(self):
        args = default_scan_args()

        self.assertEqual(args.data_dir, str(DEFAULT_DATA_DIR))
        self.assertEqual(args.market_change_pct, 0.0)
        self.assertEqual(args.top, 20)
        self.assertEqual(args.max_prefilter, 80)
        self.assertFalse(args.record)


if __name__ == "__main__":
    unittest.main()
