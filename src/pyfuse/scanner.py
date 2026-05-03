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
    constants = _collect_top_level_string_constants(tree)
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
            dyn_req = _extract_static_dynamic_import(node, constants=constants)
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


def extract_top_level_all_names(tree: ast.Module) -> set[str]:
    sequence_constants = _collect_top_level_string_sequences(tree)
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if not any(isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets):
                continue
            names.update(_extract_string_sequence(node.value, sequence_constants))
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.target.id != "__all__":
                continue
            names.update(_extract_string_sequence(node.value, sequence_constants))
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name) or node.target.id != "__all__":
                continue
            if not isinstance(node.op, ast.Add):
                continue
            names.update(_extract_string_sequence(node.value, sequence_constants))
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            names.update(_extract_all_mutation_names(node.value, sequence_constants))
    return names


def detect_unsupported_dynamic_imports(
    tree: ast.AST,
    path: Path,
    allow_unresolved_dynamic_imports: bool = False,
) -> None:
    importlib_aliases, dunder_import_aliases = _collect_dynamic_import_aliases(tree)
    constants = _collect_top_level_string_constants(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        lineno = getattr(node, "lineno", None)
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "import_module"
            and isinstance(func.value, ast.Name)
            and func.value.id in importlib_aliases
            and func.value.id != "importlib"
        ):
            raise UnsupportedFeatureError(
                "dynamic import via aliased importlib.import_module is not supported",
                file=path,
                lineno=lineno,
            )

        if isinstance(func, ast.Name) and func.id in dunder_import_aliases and func.id != "__import__":
            raise UnsupportedFeatureError(
                "dynamic import via aliased __import__ is not supported",
                file=path,
                lineno=lineno,
            )

        _ = _extract_static_dynamic_import(
            node,
            path=path,
            allow_unresolved_dynamic_imports=allow_unresolved_dynamic_imports,
            constants=constants,
        )


def _extract_constant_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _resolve_static_string(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    literal = _extract_constant_str(node)
    if literal is not None:
        return literal

    if isinstance(node, ast.Name):
        return constants.get(node.id)

    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _resolve_static_string(node.left, constants)
        right = _resolve_static_string(node.right, constants)
        if left is None or right is None:
            return None
        return left + right

    return None


def _extract_static_module_name(node: ast.AST | None, constants: dict[str, str]) -> str | None:
    return _resolve_static_string(node, constants)


def _collect_top_level_string_constants(tree: ast.AST) -> dict[str, str]:
    if not isinstance(tree, ast.Module):
        return {}

    values: dict[str, str] = {}
    invalid: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            value = _resolve_static_string(node.value, values)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = _resolve_static_string(node.value, values)
        else:
            continue

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in values or value is None:
                values.pop(target.id, None)
                invalid.add(target.id)
            elif target.id not in invalid:
                values[target.id] = value
    return values


def _collect_dynamic_import_aliases(tree: ast.AST) -> tuple[set[str], set[str]]:
    importlib_aliases: set[str] = {"importlib"}
    dunder_import_aliases: set[str] = {"__import__"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                continue
            target_name = node.targets[0].id
            if isinstance(node.value, ast.Name):
                if node.value.id in dunder_import_aliases:
                    dunder_import_aliases.add(target_name)
                if node.value.id in importlib_aliases:
                    importlib_aliases.add(target_name)
        elif isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or not isinstance(node.value, ast.Name):
                continue
            if node.value.id in dunder_import_aliases:
                dunder_import_aliases.add(node.target.id)
            if node.value.id in importlib_aliases:
                importlib_aliases.add(node.target.id)

    return importlib_aliases, dunder_import_aliases


def _assignment_targets(node: ast.Assign | ast.AnnAssign) -> list[ast.expr]:
    if isinstance(node, ast.Assign):
        return list(node.targets)
    if isinstance(node.target, ast.expr):
        return [node.target]
    return []


def _extract_string_sequence(node: ast.AST | None, constants: dict[str, tuple[str, ...]] | None = None) -> set[str]:
    constants = constants or {}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        result: set[str] = set()
        for elt in node.elts:
            value = _extract_constant_str(elt)
            if value is not None:
                result.add(value)
        return result
    if isinstance(node, ast.Name):
        return set(constants.get(node.id, ()))
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _extract_string_sequence(node.left, constants) | _extract_string_sequence(node.right, constants)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id in {"list", "tuple", "set"} and len(node.args) == 1:
            return _extract_string_sequence(node.args[0], constants)
    return set()


def _collect_top_level_string_sequences(tree: ast.Module) -> dict[str, tuple[str, ...]]:
    values: dict[str, tuple[str, ...]] = {}
    invalid: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = node.targets
            raw_values = _extract_string_sequence(node.value, values)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            raw_values = _extract_string_sequence(node.value, values)
        elif isinstance(node, ast.AugAssign):
            if not isinstance(node.target, ast.Name) or not isinstance(node.op, ast.Add):
                continue
            current = set(values.get(node.target.id, ()))
            current.update(_extract_string_sequence(node.value, values))
            raw_values = current
            targets = [node.target]
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            mut_names = _extract_all_mutation_names(node.value, values)
            if not mut_names:
                continue
            current = set(values.get("__all__", ()))
            current.update(mut_names)
            values["__all__"] = tuple(sorted(current))
            continue
        else:
            continue

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in values or not raw_values:
                values.pop(target.id, None)
                invalid.add(target.id)
            elif target.id not in invalid:
                values[target.id] = tuple(sorted(raw_values))
    return values


def _extract_all_mutation_names(call: ast.Call, constants: dict[str, tuple[str, ...]]) -> set[str]:
    func = call.func
    if not isinstance(func, ast.Attribute):
        return set()
    if not isinstance(func.value, ast.Name) or func.value.id != "__all__":
        return set()
    if func.attr == "append":
        if len(call.args) != 1:
            return set()
        value = _extract_constant_str(call.args[0])
        return {value} if value is not None else set()
    if func.attr == "extend":
        if len(call.args) != 1:
            return set()
        return _extract_string_sequence(call.args[0], constants)
    return set()


def _extract_static_dynamic_import(
    node: ast.Call,
    path: Path | None = None,
    allow_unresolved_dynamic_imports: bool = False,
    constants: dict[str, str] | None = None,
) -> ImportRequest | None:
    lineno = getattr(node, "lineno", 0)
    func = node.func
    constants = constants or {}

    if isinstance(func, ast.Name) and func.id == "__import__":
        if not node.args:
            if path is None:
                return None
            raise UnsupportedFeatureError(
                "dynamic import via __import__ without module argument is not supported",
                file=path,
                lineno=lineno,
            )
        module_name = _extract_static_module_name(node.args[0], constants)
        if module_name is None:
            if path is None or allow_unresolved_dynamic_imports:
                return None
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
            isinstance(func.value, ast.Name) and func.value.id == "importlib" and func.attr == "import_module"
        )
        if not is_import_module_call:
            return None

        if not node.args:
            if path is None:
                return None
            raise UnsupportedFeatureError(
                "dynamic import via importlib.import_module without module argument is not supported",
                file=path,
                lineno=lineno,
            )

        module_name = _extract_static_module_name(node.args[0], constants)
        if module_name is None:
            if path is None or allow_unresolved_dynamic_imports:
                return None
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
