from __future__ import annotations

import ast
import unittest
from pathlib import Path

from pyfuse.errors import UnsupportedFeatureError
from pyfuse.scanner import (
    detect_unsupported_dynamic_imports,
    extract_imports,
    extract_top_level_all_names,
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
        tree = ast.parse("name = ''.join(['x'])\n__import__(name)")
        with self.assertRaises(UnsupportedFeatureError):
            detect_unsupported_dynamic_imports(tree, Path("main.py"))

    def test_detect_constant_dynamic_import_is_supported(self) -> None:
        tree = ast.parse("import importlib\nimportlib.import_module('x.y')")
        detect_unsupported_dynamic_imports(tree, Path("main.py"))

    def test_detect_top_level_constant_dynamic_import_is_supported(self) -> None:
        tree = ast.parse("import importlib\nPLUGIN = 'x.y'\nimportlib.import_module(PLUGIN)")
        detect_unsupported_dynamic_imports(tree, Path("main.py"))
        imports = extract_imports(tree)
        self.assertIn(("x.y", (), 0), [(i.module, i.names, i.level) for i in imports])

    def test_reassigned_constant_dynamic_import_raises(self) -> None:
        tree = ast.parse("import importlib\nPLUGIN = 'x.y'\nPLUGIN = 'z'\nimportlib.import_module(PLUGIN)")
        with self.assertRaises(UnsupportedFeatureError):
            detect_unsupported_dynamic_imports(tree, Path("main.py"))

    def test_detect_concatenated_literal_dynamic_import_is_supported(self) -> None:
        tree = ast.parse("import importlib\nimportlib.import_module('x.' + 'y')")
        detect_unsupported_dynamic_imports(tree, Path("main.py"))
        imports = extract_imports(tree)
        self.assertIn(("x.y", (), 0), [(i.module, i.names, i.level) for i in imports])

    def test_detect_concatenated_constant_dynamic_import_is_supported(self) -> None:
        tree = ast.parse("import importlib\nPREFIX = 'x.'\nimportlib.import_module(PREFIX + 'y')")
        detect_unsupported_dynamic_imports(tree, Path("main.py"))
        imports = extract_imports(tree)
        self.assertIn(("x.y", (), 0), [(i.module, i.names, i.level) for i in imports])

    def test_detect_alias_importlib_dynamic_import_raises(self) -> None:
        tree = ast.parse("import importlib as il\nil.import_module('x.y')")
        with self.assertRaises(UnsupportedFeatureError) as ctx:
            detect_unsupported_dynamic_imports(tree, Path("main.py"))
        self.assertIn("aliased importlib.import_module", str(ctx.exception))

    def test_detect_from_importlib_import_module_raises(self) -> None:
        tree = ast.parse("from importlib import import_module\nimport_module('x.y')")
        with self.assertRaises(UnsupportedFeatureError) as ctx:
            detect_unsupported_dynamic_imports(tree, Path("main.py"))
        self.assertIn("aliased importlib.import_module", str(ctx.exception))

    def test_detect_alias_dunder_dynamic_import_raises(self) -> None:
        tree = ast.parse("_import = __import__\n_import('x')")
        with self.assertRaises(UnsupportedFeatureError) as ctx:
            detect_unsupported_dynamic_imports(tree, Path("main.py"))
        self.assertIn("aliased __import__", str(ctx.exception))

    def test_extract_top_level_defined_names(self) -> None:
        # fmt: off
        tree = ast.parse(
            "import pkg.sub\n"
            "from x import y as yy\n"
            "A = 1\n"
            "B: int = 2\n"
            "C: int\n"
            "def fn():\n"
            "    return 1\n"
            "class Klass:\n"
            "    pass\n"
        )
        # fmt: on
        names = extract_top_level_defined_names(tree)
        self.assertIn("pkg", names)
        self.assertIn("yy", names)
        self.assertIn("A", names)
        self.assertIn("B", names)
        self.assertNotIn("C", names)
        self.assertIn("fn", names)
        self.assertIn("Klass", names)

    def test_extract_top_level_all_names(self) -> None:
        tree = ast.parse("__all__ = ['a', 'b']\n__all__ = ('c',)\nx = 1\n")
        names = extract_top_level_all_names(tree)
        self.assertIn("a", names)
        self.assertIn("b", names)
        self.assertIn("c", names)

    def test_extract_top_level_all_names_from_sequence_constant_and_concat(self) -> None:
        tree = ast.parse("BASE = ['a', 'b']\n__all__ = BASE + ['c']\n")
        names = extract_top_level_all_names(tree)
        self.assertEqual(names, {"a", "b", "c"})

    def test_extract_top_level_all_names_with_augassign(self) -> None:
        tree = ast.parse("__all__ = ['a']\n__all__ += ['b']\n")
        names = extract_top_level_all_names(tree)
        self.assertEqual(names, {"a", "b"})

    def test_extract_top_level_all_names_with_append_extend(self) -> None:
        tree = ast.parse("__all__ = ['a']\n__all__.append('b')\nMORE = ['c']\n__all__.extend(MORE)\n")
        names = extract_top_level_all_names(tree)
        self.assertEqual(names, {"a", "b", "c"})

    def test_extract_top_level_all_names_with_list_constructor(self) -> None:
        tree = ast.parse("BASE = ['a', 'b']\n__all__ = list(BASE)\n__all__ += tuple(['c'])\n")
        names = extract_top_level_all_names(tree)
        self.assertEqual(names, {"a", "b", "c"})


if __name__ == "__main__":
    unittest.main()
