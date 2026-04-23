from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ResolutionError
from .models import ModuleInfo
from .resolver import ResolvedModule, resolve_import_request, resolve_module
from .scanner import (
    detect_unsupported_dynamic_imports,
    extract_imports,
    extract_top_level_defined_names,
    parse_source,
)


@dataclass
class ModuleGraph:
    modules: dict[str, ModuleInfo]
    skipped_imports: list[tuple[str, int, str, str]]

    def sorted_module_names(self) -> list[str]:
        return sorted(self.modules.keys())


def build_graph(
    root_dir: Path,
    entry_module: str,
    logger: Callable[[str], None] | None = None,
) -> ModuleGraph:
    modules: dict[str, ModuleInfo] = {}
    skipped_imports: list[tuple[str, int, str, str]] = []

    entry_resolved = resolve_module(root_dir, entry_module)
    if entry_resolved is None:
        raise ResolutionError(f"entry module '{entry_module}' was not found under root {root_dir}")

    _visit_module(
        root_dir,
        entry_resolved,
        modules,
        skipped_imports,
        defined_names_cache={},
        logger=logger,
    )
    return ModuleGraph(modules=modules, skipped_imports=skipped_imports)


def _visit_module(
    root_dir: Path,
    resolved: ResolvedModule,
    modules: dict[str, ModuleInfo],
    skipped_imports: list[tuple[str, int, str, str]],
    defined_names_cache: dict[str, set[str]],
    logger: Callable[[str], None] | None = None,
) -> None:
    if resolved.name in modules:
        return
    if logger is not None:
        logger(f"visit module: {resolved.name} ({resolved.path})")

    source = resolved.path.read_text(encoding="utf-8")
    tree = parse_source(resolved.path)
    detect_unsupported_dynamic_imports(tree, resolved.path)
    imports = extract_imports(tree)

    info = ModuleInfo(
        name=resolved.name,
        path=resolved.path,
        is_package=resolved.is_package,
        source=source,
        imports=imports,
        dependencies=set(),
    )
    modules[resolved.name] = info

    def is_name_defined_in_module(module_name: str, name: str) -> bool:
        if module_name not in defined_names_cache:
            dep_resolved = resolve_module(root_dir, module_name)
            if dep_resolved is None:
                defined_names_cache[module_name] = set()
            else:
                dep_tree = parse_source(dep_resolved.path)
                defined_names_cache[module_name] = extract_top_level_defined_names(dep_tree)
        return name in defined_names_cache[module_name]

    for req in imports:
        try:
            resolved_import = resolve_import_request(
                root_dir=root_dir,
                current_module=resolved.name,
                current_is_package=resolved.is_package,
                req_module=req.module,
                req_names=req.names,
                req_level=req.level,
                is_name_defined_in_module=is_name_defined_in_module,
            )
        except ResolutionError as exc:
            raise ResolutionError(exc.message, file=resolved.path, lineno=req.lineno) from exc

        deps = resolved_import.local_deps
        for dep in deps:
            info.dependencies.add(dep)
        if logger is not None and deps:
            logger(f"  deps from line {req.lineno}: {sorted(deps)}")
        for skipped in resolved_import.skipped:
            skipped_imports.append((resolved.name, req.lineno, skipped.module, skipped.reason))
            if logger is not None:
                logger(
                    f"  skipped from line {req.lineno}: {skipped.module} ({skipped.reason})"
                )

        for dep in sorted(deps):
            dep_resolved = resolve_module(root_dir, dep)
            if dep_resolved is not None:
                _visit_module(
                    root_dir,
                    dep_resolved,
                    modules,
                    skipped_imports,
                    defined_names_cache,
                    logger=logger,
                )
