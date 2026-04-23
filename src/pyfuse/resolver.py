from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ResolutionError


@dataclass(frozen=True)
class ResolvedModule:
    name: str
    path: Path
    is_package: bool


@dataclass(frozen=True)
class SkippedImport:
    module: str
    reason: str


@dataclass
class ImportResolution:
    local_deps: set[str]
    skipped: list[SkippedImport]


def compute_entry_context(entry_path: Path) -> tuple[Path, str]:
    entry = entry_path.resolve()
    module_parts = [entry.stem]
    current = entry.parent

    while (current / "__init__.py").exists():
        module_parts.append(current.name)
        current = current.parent

    root_dir = current
    module_name = ".".join(reversed(module_parts))
    return root_dir, module_name


def _module_name_to_paths(root_dir: Path, module_name: str) -> tuple[Path, Path]:
    rel = Path(*module_name.split("."))
    return root_dir / rel.with_suffix(".py"), root_dir / rel / "__init__.py"


def resolve_module(root_dir: Path, module_name: str) -> ResolvedModule | None:
    file_path, package_init = _module_name_to_paths(root_dir, module_name)
    if file_path.exists():
        return ResolvedModule(module_name, file_path, False)
    if package_init.exists():
        return ResolvedModule(module_name, package_init, True)
    return None


def parent_packages(module_name: str) -> list[str]:
    parts = module_name.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def ensure_no_namespace_parents(root_dir: Path, module_name: str) -> None:
    for pkg in parent_packages(module_name):
        pkg_dir = root_dir / Path(*pkg.split("."))
        if pkg_dir.is_dir() and not (pkg_dir / "__init__.py").exists():
            raise ResolutionError(
                f"namespace package '{pkg}' is not supported (missing __init__.py)"
            )


def resolve_relative_base(current_module: str, current_is_package: bool, level: int) -> str:
    if current_is_package:
        package = current_module
    else:
        package = current_module.rsplit(".", 1)[0] if "." in current_module else ""
    parts = [p for p in package.split(".") if p]

    if level <= 0:
        return package

    if level > len(parts) + 1:
        raise ResolutionError(
            f"relative import level {level} is beyond top-level package for module '{current_module}'"
        )

    if level == 1:
        return package

    up = level - 1
    return ".".join(parts[:-up])


def _join_module(base: str, suffix: str | None) -> str:
    if base and suffix:
        return f"{base}.{suffix}"
    if suffix:
        return suffix
    return base


def resolve_local_dependencies(
    *,
    root_dir: Path,
    current_module: str,
    current_is_package: bool,
    req_module: str | None,
    req_names: tuple[str, ...],
    req_level: int,
    is_name_defined_in_module: Callable[[str, str], bool] | None = None,
) -> set[str]:
    return resolve_import_request(
        root_dir=root_dir,
        current_module=current_module,
        current_is_package=current_is_package,
        req_module=req_module,
        req_names=req_names,
        req_level=req_level,
        is_name_defined_in_module=is_name_defined_in_module,
    ).local_deps


def resolve_import_request(
    *,
    root_dir: Path,
    current_module: str,
    current_is_package: bool,
    req_module: str | None,
    req_names: tuple[str, ...],
    req_level: int,
    is_name_defined_in_module: Callable[[str, str], bool] | None = None,
) -> ImportResolution:
    local_deps: set[str] = set()
    skipped: list[SkippedImport] = []

    if req_level > 0:
        base = resolve_relative_base(current_module, current_is_package, req_level)
        abs_module = _join_module(base, req_module)
    else:
        abs_module = req_module or ""

    abs_module_is_local = False
    if abs_module:
        resolved = resolve_module(root_dir, abs_module)
        if resolved is not None:
            abs_module_is_local = True
            ensure_no_namespace_parents(root_dir, abs_module)
            local_deps.add(abs_module)
            for pkg in parent_packages(abs_module):
                if resolve_module(root_dir, pkg) is not None:
                    local_deps.add(pkg)
        else:
            skipped.append(SkippedImport(module=abs_module, reason="not-local-or-missing"))

    for name in req_names:
        if name == "*":
            continue
        if abs_module and abs_module_is_local and is_name_defined_in_module is not None:
            if is_name_defined_in_module(abs_module, name):
                skipped.append(
                    SkippedImport(
                        module=f"{abs_module}.{name}",
                        reason="name-defined-in-module",
                    )
                )
                continue
        candidate = _join_module(abs_module, name)
        if candidate and resolve_module(root_dir, candidate) is not None:
            ensure_no_namespace_parents(root_dir, candidate)
            local_deps.add(candidate)
            for pkg in parent_packages(candidate):
                if resolve_module(root_dir, pkg) is not None:
                    local_deps.add(pkg)
        elif candidate:
            skipped.append(SkippedImport(module=candidate, reason="not-local-or-missing"))

    return ImportResolution(local_deps=local_deps, skipped=skipped)
