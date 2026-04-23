from __future__ import annotations

import ast
from pathlib import Path

from .errors import UnsupportedFeatureError
from .models import ImportRequest


def parse_source(path: Path) -> ast.Module:
    source = path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(path))


def extract_imports(tree: ast.AST) -> list[ImportRequest]:
    imports: list[ImportRequest] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(
                    ImportRequest(
                        module=alias.name,
                        names=(),
                        level=0,
                        lineno=getattr(node, "lineno", 0),
                    )
                )
        elif isinstance(node, ast.ImportFrom):
                imports.append(
                    ImportRequest(
                        module=node.module,
                        names=tuple(alias.name for alias in node.names),
                        level=node.level,
                        lineno=getattr(node, "lineno", 0),
                    )
                )
        elif isinstance(node, ast.Call):
            dyn_req = _extract_static_dynamic_import(node)
            if dyn_req is not None:
                imports.append(dyn_req)
    return imports


def extract_top_level_defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            for target in _assignment_targets(node):
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                names.add(alias.asname or alias.name)
    return names


def detect_unsupported_dynamic_imports(tree: ast.AST, path: Path) -> None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        _ = _extract_static_dynamic_import(node, path=path)


def _extract_constant_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node.target, ast.expr):
        return [node.target]
    return []


def _extract_static_dynamic_import(
    node: ast.Call,
    path: Path | None = None,
) -> ImportRequest | None:
    lineno = getattr(node, "lineno", 0)
    func = node.func

    if isinstance(func, ast.Name) and func.id == "__import__":
        if not node.args:
            raise UnsupportedFeatureError(
                "dynamic import via __import__ without module argument is not supported",
                file=path,
                lineno=lineno,
            )
        module_name = _extract_constant_str(node.args[0])
        if module_name is None:
            raise UnsupportedFeatureError(
                "dynamic import via __import__ requires a constant string module name",
                file=path,
                lineno=lineno,
            )
        if module_name.startswith("."):
            raise UnsupportedFeatureError(
                "relative dynamic import via __import__ is not supported",
                file=path,
                lineno=lineno,
            )
        return ImportRequest(module=module_name, names=(), level=0, lineno=lineno)

    if isinstance(func, ast.Attribute):
        is_import_module_call = (
            isinstance(func.value, ast.Name)
            and func.value.id == "importlib"
            and func.attr == "import_module"
        )
        if not is_import_module_call:
            return None

        if not node.args:
            raise UnsupportedFeatureError(
                "dynamic import via importlib.import_module without module argument is not supported",
                file=path,
                lineno=lineno,
            )

        module_name = _extract_constant_str(node.args[0])
        if module_name is None:
            raise UnsupportedFeatureError(
                "dynamic import via importlib.import_module requires a constant string module name",
                file=path,
                lineno=lineno,
            )
        if module_name.startswith("."):
            raise UnsupportedFeatureError(
                "relative dynamic import via importlib.import_module is not supported",
                file=path,
                lineno=lineno,
            )
        return ImportRequest(module=module_name, names=(), level=0, lineno=lineno)

    return None
