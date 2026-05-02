from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .errors import ResolutionError
from .generator import generate_bundled_script, write_bundled_script
from .graph import ModuleGraph, build_graph
from .resolver import compute_entry_context


@dataclass
class BundleResult:
    entry_path: Path
    root_dir: Path
    module_roots: list[Path]
    include_modules: list[str]
    include_packages: list[str]
    vendor_packages: list[str]
    vendor_modules: list[str]
    entry_module: str
    graph: ModuleGraph
    output_path: Path
    report: dict[str, object]


def bundle_project(
    entry_file: Path,
    output_path: Path,
    report_path: Path | None = None,
    module_roots: list[Path] | None = None,
    include_modules: list[str] | None = None,
    include_packages: list[str] | None = None,
    vendor_packages: list[str] | None = None,
    vendor_modules: list[str] | None = None,
    logger: Callable[[str], None] | None = None,
) -> BundleResult:
    entry_file = entry_file.resolve()
    output_path = output_path.resolve()
    extra_module_roots = [root.resolve() for root in (module_roots or [])]
    include_module_names = include_modules or []
    include_package_names = include_packages or []
    vendor_package_names = vendor_packages or []
    vendor_module_names = vendor_modules or []
    vendor_roots = _resolve_vendor_roots(vendor_package_names)
    vendor_module_roots = _resolve_vendor_module_roots(vendor_module_names)
    extra_module_roots.extend(vendor_roots)
    extra_module_roots.extend(vendor_module_roots)
    graph_include_module_names = [*include_module_names, *vendor_module_names]
    graph_include_package_names = [*include_package_names, *vendor_package_names]

    if logger is not None:
        logger(f"entry file: {entry_file}")

    root_dir, entry_module = compute_entry_context(entry_file)
    if logger is not None:
        logger(f"root dir:   {root_dir}")
        for module_root in extra_module_roots:
            logger(f"module root: {module_root}")
        for include in include_module_names:
            logger(f"include module: {include}")
        for include in include_package_names:
            logger(f"include package: {include}")
        for vendor in vendor_package_names:
            logger(f"vendor package: {vendor}")
        for vendor_module in vendor_module_names:
            logger(f"vendor module: {vendor_module}")
        logger(f"entry mod:  {entry_module}")

    graph = build_graph(
        root_dir,
        entry_module,
        module_roots=extra_module_roots,
        include_modules=graph_include_module_names,
        include_packages=graph_include_package_names,
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
        include_modules=include_module_names,
        include_packages=include_package_names,
        vendor_packages=vendor_package_names,
        vendor_modules=vendor_module_names,
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
        include_modules=include_module_names,
        include_packages=include_package_names,
        vendor_packages=vendor_package_names,
        vendor_modules=vendor_module_names,
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
    include_modules: list[str],
    include_packages: list[str],
    vendor_packages: list[str],
    vendor_modules: list[str],
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
    risk_level, risk_reasons = _compute_risk(
        include_modules,
        include_packages,
        vendor_packages,
        vendor_modules,
        skipped,
    )
    return {
        "entry_path": str(entry_path),
        "entry_module": entry_module,
        "root_dir": str(root_dir),
        "module_roots": [str(root) for root in module_roots],
        "included_modules_exact": include_modules,
        "included_packages_tree": include_packages,
        "vendor_packages": vendor_packages,
        "vendor_modules": vendor_modules,
        "output_path": str(output_path),
        "bundled_modules": sorted(graph.modules.keys()),
        "bundled_module_count": len(graph.modules),
        "skipped_imports": skipped,
        "skipped_import_count": len(skipped),
        "dependency_edges": dependency_edges,
        "module_dependencies": module_dependencies,
        "module_origins": module_origins,
        "uncertain_imports": skipped,
        "risk_level": risk_level,
        "risk_reasons": risk_reasons,
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


def _compute_risk(
    include_modules: list[str],
    include_packages: list[str],
    vendor_packages: list[str],
    vendor_modules: list[str],
    skipped: list[dict[str, object]],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if include_packages:
        reasons.append("package-tree includes may bundle modules not statically imported")
    if include_modules:
        reasons.append("exact module includes were supplied by user")
    if vendor_packages:
        reasons.append("vendor packages were supplied from current Python environment")
    if vendor_modules:
        reasons.append("vendor modules were supplied from current Python environment")

    if include_packages or vendor_packages or vendor_modules:
        return "medium", reasons
    return "low", reasons


def _resolve_vendor_roots(vendor_packages: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for package_name in vendor_packages:
        root = _resolve_vendor_root(package_name)
        if root not in seen:
            roots.append(root)
            seen.add(root)
    return roots


def _resolve_vendor_root(package_name: str) -> Path:
    spec = importlib.util.find_spec(package_name)
    if spec is None:
        raise ResolutionError(f"vendor package '{package_name}' was not found in current Python environment")

    if spec.submodule_search_locations is None:
        raise ResolutionError(f"vendor package '{package_name}' is not a package")

    if spec.origin is None:
        raise ResolutionError(f"namespace vendor package '{package_name}' is not supported")

    package_init = Path(spec.origin)
    if package_init.name != "__init__.py":
        raise ResolutionError(f"vendor package '{package_name}' is not a regular package with __init__.py")

    package_dir = package_init.parent
    root_dir = package_dir
    for _ in package_name.split("."):
        root_dir = root_dir.parent
    return root_dir.resolve()


def _resolve_vendor_module_roots(vendor_modules: list[str]) -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for module_name in vendor_modules:
        root = _resolve_vendor_module_root(module_name)
        if root not in seen:
            roots.append(root)
            seen.add(root)
    return roots


def _resolve_vendor_module_root(module_name: str) -> Path:
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        raise ResolutionError(f"vendor module '{module_name}' was not found in current Python environment")

    if spec.submodule_search_locations is not None:
        raise ResolutionError(f"vendor module '{module_name}' is a package; use --vendor-package")

    if spec.origin is None:
        raise ResolutionError(f"vendor module '{module_name}' has no file origin")

    module_path = Path(spec.origin)
    if module_path.suffix != ".py":
        raise ResolutionError(f"vendor module '{module_name}' is not a pure Python .py module")

    root_dir = module_path.parent
    for _ in module_name.split(".")[:-1]:
        root_dir = root_dir.parent
    return root_dir.resolve()
