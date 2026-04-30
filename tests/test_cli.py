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

    def test_build_parser_supports_module_root_and_include(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "build",
                "scripts/s1/main.py",
                "-o",
                "dist/s1.py",
                "--module-root",
                "src",
                "--include-module",
                "package_a.plugin",
                "--include-package",
                "package_a",
            ]
        )
        self.assertEqual([str(root) for root in args.module_root], ["src"])
        self.assertEqual(args.include_module, ["package_a.plugin"])
        self.assertEqual(args.include_package, ["package_a"])

    def test_build_parser_keeps_legacy_include_alias(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["build", "main.py", "-o", "out.py", "--include", "package_a"])
        self.assertEqual(args.include, ["package_a"])


if __name__ == "__main__":
    unittest.main()
