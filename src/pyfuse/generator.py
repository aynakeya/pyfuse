from __future__ import annotations

from pathlib import Path
from pprint import pformat

from .graph import ModuleGraph
from .runtime import build_runtime_source


def generate_bundled_script(graph: ModuleGraph, entry_module: str) -> str:
    modules_data: dict[str, dict[str, object]] = {}
    for name in graph.sorted_module_names():
        info = graph.modules[name]
        modules_data[name] = {
            "code": info.source,
            "is_package": info.is_package,
            "filename": str(info.path),
        }

    modules_literal = pformat(modules_data, width=100, sort_dicts=True)
    return build_runtime_source(modules_literal=modules_literal, entry_module=entry_module)


def write_bundled_script(content: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
