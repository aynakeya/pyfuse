from __future__ import annotations

import unittest

from pyfuse.cli import build_parser


class CliTests(unittest.TestCase):
    def test_build_parser_supports_verbose(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["build", "main.py", "-o", "out.py", "--verbose"])
        self.assertTrue(args.verbose)

    def test_build_parser_supports_report(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["build", "main.py", "-o", "out.py", "--report", "report.json"])
        self.assertEqual(str(args.report), "report.json")


if __name__ == "__main__":
    unittest.main()
