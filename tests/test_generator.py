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


if __name__ == "__main__":
    unittest.main()
