from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pyfuse.generator import generate_bundled_script
from pyfuse.graph import build_graph


class GeneratorTests(unittest.TestCase):
    def test_generated_script_is_valid_python(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("print('ok')\n", encoding="utf-8")
            graph = build_graph(root, "main")
            script = generate_bundled_script(graph, "main")
            compile(script, "bundled.py", "exec")

    def test_marshal_script_does_not_embed_module_source_text(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "main.py").write_text("import helper\nprint(helper.msg())\n", encoding="utf-8")
            (root / "helper.py").write_text(
                "def msg():\n    return 'hello-from-helper'\n",
                encoding="utf-8",
            )
            graph = build_graph(root, "main")
            script = generate_bundled_script(graph, "main", code_format="marshal")
            compile(script, "bundled.py", "exec")
            self.assertIn("code_bytes", script)
            self.assertNotIn("def msg():", script)


if __name__ == "__main__":
    unittest.main()
