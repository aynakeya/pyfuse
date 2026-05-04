from __future__ import annotations

import marshal
from pathlib import Path
from pprint import pformat
from typing import Literal

from .graph import ModuleGraph
from .runtime import build_runtime_source

CodeFormat = Literal["source", "marshal"]


def generate_bundled_script(graph: ModuleGraph, entry_module: str, code_format: CodeFormat = "source") -> str:
    modules_data: dict[str, dict[str, object]] = {}
    for name in graph.sorted_module_names():
        info = graph.modules[name]
        module_data: dict[str, object] = {
            "is_package": info.is_package,
            "filename": str(info.path),
        }
        if code_format == "source":
            module_data["code"] = info.source
        elif code_format == "marshal":
            code = compile(info.source, str(info.path), "exec")
            module_data["code_bytes"] = marshal.dumps(code)
        else:
            raise ValueError(f"unsupported code format: {code_format}")
        modules_data[name] = module_data

    modules_literal = pformat(modules_data, width=100, sort_dicts=True)
    return build_runtime_source(modules_literal=modules_literal, entry_module=entry_module)


def write_bundled_script(content: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
