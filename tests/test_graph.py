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
            (root / "main.py").write_text("name='helper'\nname='other'\n__import__(name)\n", encoding="utf-8")
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

    def test_from_import_prefers_all_export_over_submodule(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text(
                "__all__ = ['value']\n"
                "value = 123\n",
                encoding="utf-8",
            )
            (pkg / "value.py").write_text("raise RuntimeError('should not load')\n", encoding="utf-8")
            (root / "main.py").write_text("from pkg import value\nprint(value)\n", encoding="utf-8")

            graph = build_graph(root, "main")
            self.assertIn("pkg", graph.modules)
            self.assertNotIn("pkg.value", graph.modules)

    def test_include_package_prefers_package_over_same_named_module(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scripts = root / "scripts"
            src = root / "src"
            pkg = src / "pkg"
            scripts.mkdir(parents=True)
            pkg.mkdir(parents=True)
            (scripts / "main.py").write_text("print('entry')\n", encoding="utf-8")
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "deep.py").write_text("KIND = 'module'\n", encoding="utf-8")
            deep_pkg = pkg / "deep"
            deep_pkg.mkdir()
            (deep_pkg / "__init__.py").write_text("KIND = 'package'\n", encoding="utf-8")

            graph = build_graph(root / "scripts", "main", module_roots=[src], include_packages=["pkg"])

            self.assertIn("pkg.deep", graph.modules)
            self.assertTrue(graph.modules["pkg.deep"].is_package)
            self.assertEqual(graph.modules["pkg.deep"].source.strip(), "KIND = 'package'")

    def test_star_import_uses_package_all_for_local_submodule_deps(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pkg"
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("__all__ = ['sub']\n", encoding="utf-8")
            (pkg / "sub.py").write_text("VALUE = 7\n", encoding="utf-8")
            (root / "main.py").write_text("from pkg import *\nprint(sub.VALUE)\n", encoding="utf-8")

            graph = build_graph(root, "main")
            self.assertIn("pkg", graph.modules)
            self.assertIn("pkg.sub", graph.modules)
            self.assertIn("pkg.sub", graph.modules["main"].dependencies)


if __name__ == "__main__":
    unittest.main()
