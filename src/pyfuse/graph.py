from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ResolutionError
from .models import ModuleInfo
from .resolver import (
    ResolvedModule,
    parent_packages,
    resolve_import_request,
    resolve_module,
    resolve_module_in_roots,
)
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
    module_roots: list[Path] | None = None,
    includes: list[str] | None = None,
    logger: Callable[[str], None] | None = None,
) -> ModuleGraph:
    modules: dict[str, ModuleInfo] = {}
    skipped_imports: list[tuple[str, int, str, str]] = []
    search_roots = _dedupe_roots([root_dir, *(module_roots or [])])
    include_names = includes or []

    entry_resolved = resolve_module(root_dir, entry_module)
    if entry_resolved is None:
        raise ResolutionError(f"entry module '{entry_module}' was not found under root {root_dir}")

    _visit_module(
        root_dir,
        search_roots,
        entry_resolved,
        modules,
        skipped_imports,
        defined_names_cache={},
        allow_unresolved_dynamic_imports=bool(include_names),
        logger=logger,
    )
    for include in include_names:
        _include_module_tree(
            root_dir,
            search_roots,
            include,
            modules,
            skipped_imports,
            defined_names_cache={},
            allow_unresolved_dynamic_imports=True,
            logger=logger,
        )
    return ModuleGraph(modules=modules, skipped_imports=skipped_imports)


def _visit_module(
    root_dir: Path,
    search_roots: list[Path],
    resolved: ResolvedModule,
    modules: dict[str, ModuleInfo],
    skipped_imports: list[tuple[str, int, str, str]],
    defined_names_cache: dict[str, set[str]],
    allow_unresolved_dynamic_imports: bool = False,
    logger: Callable[[str], None] | None = None,
) -> None:
    if resolved.name in modules:
        return
    if logger is not None:
        logger(f"visit module: {resolved.name} ({resolved.path})")

    source = resolved.path.read_text(encoding="utf-8")
    tree = parse_source(resolved.path)
    detect_unsupported_dynamic_imports(
        tree,
        resolved.path,
        allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
    )
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
            dep_resolved = resolve_module_in_roots(search_roots, module_name)
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
                search_roots=search_roots,
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
            dep_resolved = resolve_module_in_roots(search_roots, dep)
            if dep_resolved is not None:
                _visit_module(
                    root_dir,
                    search_roots,
                    dep_resolved,
                    modules,
                    skipped_imports,
                    defined_names_cache,
                    allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
                    logger=logger,
                )


def _include_module_tree(
    root_dir: Path,
    search_roots: list[Path],
    module_name: str,
    modules: dict[str, ModuleInfo],
    skipped_imports: list[tuple[str, int, str, str]],
    defined_names_cache: dict[str, set[str]],
    allow_unresolved_dynamic_imports: bool,
    logger: Callable[[str], None] | None,
) -> None:
    resolved = resolve_module_in_roots(search_roots, module_name)
    if resolved is None:
        raise ResolutionError(f"included module '{module_name}' was not found in local module roots")

    if resolved.is_package:
        package_dir = resolved.path.parent
        for path in sorted(package_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            rel = path.relative_to(resolved.root_dir)
            parts = list(rel.with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            child_name = ".".join(parts)
            child_resolved = resolve_module(resolved.root_dir, child_name)
            if child_resolved is not None:
                _visit_module(
                    root_dir,
                    search_roots,
                    child_resolved,
                    modules,
                    skipped_imports,
                    defined_names_cache,
                    allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
                    logger=logger,
                )
        return

    for package_name in parent_packages(module_name):
        package_resolved = resolve_module_in_roots(search_roots, package_name)
        if package_resolved is not None:
            _visit_module(
                root_dir,
                search_roots,
                package_resolved,
                modules,
                skipped_imports,
                defined_names_cache,
                allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
                logger=logger,
            )

    _visit_module(
        root_dir,
        search_roots,
        resolved,
        modules,
        skipped_imports,
        defined_names_cache,
        allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
        logger=logger,
    )


def _dedupe_roots(roots: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve()
        if resolved not in seen:
            result.append(resolved)
            seen.add(resolved)
    return result
