from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pyfuse.errors import ResolutionError
from pyfuse.resolver import (
    compute_entry_context,
    resolve_local_dependencies,
    resolve_module,
    resolve_relative_base,
)


class ResolverTests(unittest.TestCase):
    def test_compute_entry_context_for_package_module(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "pkg"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            entry = pkg / "main.py"
            entry.write_text("print('ok')\n", encoding="utf-8")

            root_dir, module_name = compute_entry_context(entry)
            self.assertEqual(root_dir, root)
            self.assertEqual(module_name, "pkg.main")

    def test_resolve_relative_base(self) -> None:
        self.assertEqual(resolve_relative_base("a.b.c", False, 1), "a.b")
        self.assertEqual(resolve_relative_base("a.b.c", False, 2), "a")
        self.assertEqual(resolve_relative_base("a.b", True, 1), "a.b")
        with self.assertRaises(ResolutionError):
            resolve_relative_base("a.b", False, 5)

    def test_resolve_local_dependencies_from_relative_import(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pkg = root / "app"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("", encoding="utf-8")
            (pkg / "util.py").write_text("x = 1\n", encoding="utf-8")
            self.assertIsNotNone(resolve_module(root, "app.util"))

            deps = resolve_local_dependencies(
                root_dir=root,
                current_module="app.main",
                current_is_package=False,
                req_module=None,
                req_names=("util",),
                req_level=1,
            )
            self.assertIn("app.util", deps)


if __name__ == "__main__":
    unittest.main()
