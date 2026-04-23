from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pyfuse.errors import UnsupportedFeatureError
from pyfuse.graph import build_graph


class GraphTests(unittest.TestCase):
    def test_build_graph_collects_local_dependencies(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("import helper\nprint(helper.value())\n", encoding="utf-8")
            (root / "helper.py").write_text("def value():\n    return 42\n", encoding="utf-8")

            graph = build_graph(root, "main")
            self.assertIn("main", graph.modules)
            self.assertIn("helper", graph.modules)
            self.assertIn("helper", graph.modules["main"].dependencies)

    def test_build_graph_rejects_dynamic_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("name='helper'\n__import__(name)\n", encoding="utf-8")
            (root / "helper.py").write_text("x=1\n", encoding="utf-8")

            with self.assertRaises(UnsupportedFeatureError):
                build_graph(root, "main")

    def test_build_graph_accepts_constant_dynamic_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("__import__('helper')\n", encoding="utf-8")
            (root / "helper.py").write_text("x=1\n", encoding="utf-8")
            graph = build_graph(root, "main")
            self.assertIn("helper", graph.modules)

    def test_from_import_prefers_defined_symbol_over_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("value = 123\n", encoding="utf-8")
            (pkg / "value.py").write_text("raise RuntimeError('should not load')\n", encoding="utf-8")
            (root / "main.py").write_text("from pkg import value\nprint(value)\n", encoding="utf-8")

            graph = build_graph(root, "main")
            self.assertIn("pkg", graph.modules)
            self.assertNotIn("pkg.value", graph.modules)


if __name__ == "__main__":
    unittest.main()
