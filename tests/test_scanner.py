from __future__ import annotations

import ast
import unittest
from pathlib import Path

from pyfuse.errors import UnsupportedFeatureError
from pyfuse.scanner import (
    detect_unsupported_dynamic_imports,
    extract_imports,
    extract_top_level_defined_names,
)


class ScannerTests(unittest.TestCase):
    def test_extract_imports_supports_required_forms(self) -> None:
        src = """
import x
import x as y
from x import y
from . import z
from .sub import y
"""
        tree = ast.parse(src)
        imports = extract_imports(tree)
        got = [(i.module, i.names, i.level) for i in imports]

        self.assertIn(("x", (), 0), got)
        self.assertIn(("x", ("y",), 0), got)
        self.assertIn((None, ("z",), 1), got)
        self.assertIn(("sub", ("y",), 1), got)

    def test_detect_dynamic_import_with_non_constant_module_raises(self) -> None:
        tree = ast.parse("name = 'x'\n__import__(name)")
        with self.assertRaises(UnsupportedFeatureError):
            detect_unsupported_dynamic_imports(tree, Path("main.py"))

    def test_detect_constant_dynamic_import_is_supported(self) -> None:
        tree = ast.parse("import importlib\nimportlib.import_module('x.y')")
        detect_unsupported_dynamic_imports(tree, Path("main.py"))

    def test_extract_top_level_defined_names(self) -> None:
        tree = ast.parse(
            "import pkg.sub\n"
            "from x import y as yy\n"
            "A = 1\n"
            "def fn():\n"
            "    return 1\n"
            "class C:\n"
            "    pass\n"
        )
        names = extract_top_level_defined_names(tree)
        self.assertIn("pkg", names)
        self.assertIn("yy", names)
        self.assertIn("A", names)
        self.assertIn("fn", names)
        self.assertIn("C", names)


if __name__ == "__main__":
    unittest.main()
