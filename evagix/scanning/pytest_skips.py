"""Extract a small, syntactic subset of pytest declarations without importing code."""

from __future__ import annotations

import ast
from dataclasses import dataclass

_NODE_LIMIT = 50_000


@dataclass(frozen=True)
class SkipDeclaration:
    line: int
    column: int
    scope: str


@dataclass(frozen=True)
class TestDeclaration:
    line: int
    skip: SkipDeclaration | None


def _attribute(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _attribute(node.value) + "." + node.attr
    return ""


def _skip(node: ast.expr, source: list[str], scope: str) -> SkipDeclaration | None:
    target = node.func if isinstance(node, ast.Call) else node
    if _attribute(target) != "pytest.mark.skip":
        return None
    if isinstance(node, ast.Call):
        # Do not interpret expressions, splats, or arbitrary decorator arguments.
        if len(node.args) > 1 or any(key.arg != "reason" for key in node.keywords):
            raise ValueError("skip marker arguments are outside the supported literal syntax")
        values = [*node.args, *(key.value for key in node.keywords)]
        if len(values) > 1 or any(
            not isinstance(value, ast.Constant) or not isinstance(value.value, str) for value in values
        ):
            raise ValueError("skip marker arguments are outside the supported literal syntax")
    prefix = source[node.lineno - 1].encode("utf-8")[: node.col_offset]
    return SkipDeclaration(node.lineno, len(prefix.decode("utf-8")) + 1, scope)


def _scope_skip(body: list[ast.stmt], source: list[str], scope: str) -> SkipDeclaration | None:
    assignments = []
    direct_targets: set[ast.AST] = set()
    for statement in body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in statement.targets
        ):
            assignments.append(statement.value)
            direct_targets.update(statement.targets)
        elif (
            isinstance(statement, ast.AnnAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "pytestmark"
        ):
            direct_targets.add(statement.target)
            if statement.value is not None:
                assignments.append(statement.value)
    if len(assignments) > 1:
        raise ValueError("multiple pytestmark assignments are not supported")
    if not assignments or assignments[0] is None:
        return None
    value = assignments[0]
    markers = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
    skip = next((skip for marker in markers if (skip := _skip(marker, source, scope))), None)
    if skip is not None:
        pending: list[ast.AST] = list(body)
        while pending:
            node = pending.pop()
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == "pytestmark":
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, ast.alias) and (node.asname or node.name.split(".")[0]) in {"pytestmark", "*"}:
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, ast.ExceptHandler) and node.name == "pytestmark":
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "pytestmark":
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, ast.MatchMapping) and node.rest == "pytestmark":
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if (
                isinstance(node, ast.Name)
                and node.id == "pytestmark"
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and node not in direct_targets
            ):
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if (
                isinstance(node, ast.Subscript)
                and isinstance(node.ctx, (ast.Store, ast.Del))
                and _attribute(node.value) == "pytestmark"
            ):
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            if isinstance(node, ast.Call) and _attribute(node.func).startswith("pytestmark."):
                raise ValueError("pytestmark has an unsupported rebinding or mutation")
            pending.extend(ast.iter_child_nodes(node))
    return skip


def _direct_pytest_binding(tree: ast.Module, nodes: list[ast.AST]) -> bool:
    imports = [
        alias
        for statement in tree.body
        if isinstance(statement, ast.Import)
        for alias in statement.names
        if alias.name == "pytest" and alias.asname in (None, "pytest")
    ]
    if len(imports) != 1:
        return False
    allowed = imports[0]
    for node in nodes:
        if (
            isinstance(node, ast.alias)
            and node is not allowed
            and (node.asname or node.name.split(".")[0]) in {"pytest", "*"}
        ):
            return False
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == "pytest":
            return False
        if isinstance(node, ast.arg) and node.arg == "pytest":
            return False
        if isinstance(node, ast.Name) and node.id == "pytest" and isinstance(node.ctx, (ast.Store, ast.Del)):
            return False
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, (ast.Store, ast.Del))
            and _attribute(node).startswith("pytest.")
        ):
            return False
        if isinstance(node, ast.ExceptHandler) and node.name == "pytest":
            return False
        if isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == "pytest":
            return False
        if isinstance(node, ast.MatchMapping) and node.rest == "pytest":
            return False
    return True


def extract_test_declarations(text: str) -> dict[str, TestDeclaration]:
    """Named top-level tests / direct Test* methods and literal skip markers only.

    These are candidate declarations, not a pytest collection or execution result.
    Aliases, conditional definitions, skipif, runtime calls and custom discovery
    are outside scope. Ambiguous direct bindings/definitions fail conservatively.
    """
    try:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        tree = ast.parse(text)
        nodes = []
        for node in ast.walk(tree):
            nodes.append(node)
            if len(nodes) > _NODE_LIMIT:
                raise ValueError("Python syntax tree exceeds the inspection limit")
        direct = _direct_pytest_binding(tree, nodes)
        if not direct and any(
            isinstance(node, ast.Attribute) and _attribute(node) == "pytest.mark.skip" for node in nodes
        ):
            raise ValueError("literal skip marker has an unsupported or ambiguous pytest binding")
        source = text.split("\n")
        module_skip = _scope_skip(tree.body, source, "module") if direct else None
        result: dict[str, TestDeclaration] = {}
        seen: set[str] = set()

        def collect(body: list[ast.stmt], prefix: str, inherited: SkipDeclaration | None) -> None:
            for statement in body:
                if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                name = prefix + statement.name
                if name in seen:
                    raise ValueError("duplicate Python declarations prevent an unambiguous comparison")
                seen.add(name)
                if isinstance(statement, ast.ClassDef):
                    if prefix or not statement.name.startswith("Test"):
                        continue
                    skip = inherited
                    if direct:
                        skip = skip or next(
                            (
                                item
                                for decorator in statement.decorator_list
                                if (item := _skip(decorator, source, "class"))
                            ),
                            None,
                        )
                        skip = skip or _scope_skip(statement.body, source, "class")
                    collect(statement.body, name + ".", skip)
                elif statement.name.startswith("test_"):
                    skip = inherited
                    if direct:
                        skip = skip or next(
                            (
                                item
                                for decorator in statement.decorator_list
                                if (item := _skip(decorator, source, "test"))
                            ),
                            None,
                        )
                    result[name] = TestDeclaration(statement.lineno, skip)

        collect(tree.body, "", module_skip)
        return result
    except (SyntaxError, RecursionError, MemoryError) as exc:
        raise ValueError("Python source cannot be safely parsed by this interpreter") from exc
