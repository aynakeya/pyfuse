from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable

from .generator import generate_bundled_script, write_bundled_script
from .graph import ModuleGraph, build_graph
from .resolver import compute_entry_context


@dataclass
class BundleResult:
    entry_path: Path
    root_dir: Path
    module_roots: list[Path]
    includes: list[str]
    entry_module: str
    graph: ModuleGraph
    output_path: Path
    report: dict[str, object]


def bundle_project(
    entry_file: Path,
    output_path: Path,
    report_path: Path | None = None,
    module_roots: list[Path] | None = None,
    includes: list[str] | None = None,
    logger: Callable[[str], None] | None = None,
) -> BundleResult:
    entry_file = entry_file.resolve()
    output_path = output_path.resolve()
    extra_module_roots = [root.resolve() for root in (module_roots or [])]
    include_names = includes or []

    if logger is not None:
        logger(f"entry file: {entry_file}")

    root_dir, entry_module = compute_entry_context(entry_file)
    if logger is not None:
        logger(f"root dir:   {root_dir}")
        for module_root in extra_module_roots:
            logger(f"module root: {module_root}")
        for include in include_names:
            logger(f"include:   {include}")
        logger(f"entry mod:  {entry_module}")

    graph = build_graph(
        root_dir,
        entry_module,
        module_roots=extra_module_roots,
        includes=include_names,
        logger=logger,
    )
    if logger is not None:
        logger(f"graph size: {len(graph.modules)} modules")

    bundled = generate_bundled_script(graph, entry_module)
    write_bundled_script(bundled, output_path)
    if logger is not None:
        logger(f"wrote bundle: {output_path}")

    report = _build_report(
        entry_path=entry_file,
        root_dir=root_dir,
        module_roots=extra_module_roots,
        includes=include_names,
        entry_module=entry_module,
        output_path=output_path,
        graph=graph,
    )
    if report_path is not None:
        report_path = report_path.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if logger is not None:
            logger(f"wrote report: {report_path}")

    return BundleResult(
        entry_path=entry_file,
        root_dir=root_dir,
        module_roots=extra_module_roots,
        includes=include_names,
        entry_module=entry_module,
        graph=graph,
        output_path=output_path,
        report=report,
    )


def _build_report(
    *,
    entry_path: Path,
    root_dir: Path,
    module_roots: list[Path],
    includes: list[str],
    entry_module: str,
    output_path: Path,
    graph: ModuleGraph,
) -> dict[str, object]:
    dependency_edges = sum(len(info.dependencies) for info in graph.modules.values())
    module_dependencies = {
        name: sorted(graph.modules[name].dependencies) for name in sorted(graph.modules.keys())
    }
    all_roots = [root_dir, *module_roots]
    module_origins = {
        name: _find_module_origin(graph.modules[name].path, all_roots)
        for name in sorted(graph.modules.keys())
    }
    skipped = [
        {
            "importer": importer,
            "lineno": lineno,
            "module": module,
            "reason": reason,
        }
        for importer, lineno, module, reason in graph.skipped_imports
    ]
    return {
        "entry_path": str(entry_path),
        "entry_module": entry_module,
        "root_dir": str(root_dir),
        "module_roots": [str(root) for root in module_roots],
        "includes": includes,
        "output_path": str(output_path),
        "bundled_modules": sorted(graph.modules.keys()),
        "bundled_module_count": len(graph.modules),
        "skipped_imports": skipped,
        "skipped_import_count": len(skipped),
        "dependency_edges": dependency_edges,
        "module_dependencies": module_dependencies,
        "module_origins": module_origins,
    }


def _find_module_origin(path: Path, roots: list[Path]) -> str:
    resolved_path = path.resolve()
    for root in roots:
        resolved_root = root.resolve()
        try:
            resolved_path.relative_to(resolved_root)
        except ValueError:
            continue
        return str(resolved_root)
    return ""
