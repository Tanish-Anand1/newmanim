"""Static compliance checks shared by CI and the publish gate."""

from __future__ import annotations

import ast
from pathlib import Path


CONNECTOR_TYPES = {"Line", "Arrow", "DashedLine", "CurvedArrow"}
GEOMETRY_METHODS = {"get_left", "get_right", "get_top", "get_bottom", "get_center"}


def _has_live_geometry_reference(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr in GEOMETRY_METHODS
        for child in ast.walk(node)
    )


class _StaticConnectorVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[str] = []
        self._always_redraw_functions: set[str] = set()
        self._safe_depth = 0

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id == "always_redraw":
            for argument in node.args:
                if isinstance(argument, ast.Lambda):
                    self._safe_depth += 1
                    self.visit(argument)
                    self._safe_depth -= 1
                elif isinstance(argument, ast.Name):
                    self._always_redraw_functions.add(argument.id)
            for keyword in node.keywords:
                self.visit(keyword.value)
            return

        constructor_name = node.func.id if isinstance(node.func, ast.Name) else None
        is_next_to = isinstance(node.func, ast.Attribute) and node.func.attr == "next_to"
        if (
            (constructor_name in CONNECTOR_TYPES or is_next_to)
            and _has_live_geometry_reference(node)
            and self._safe_depth == 0
        ):
            self.violations.append(f"line {node.lineno}: static connector {constructor_name or 'next_to'}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        safe = node.name in self._always_redraw_functions
        if safe:
            self._safe_depth += 1
        self.generic_visit(node)
        if safe:
            self._safe_depth -= 1

    visit_AsyncFunctionDef = visit_FunctionDef


def find_static_connectors(filepath: Path) -> list[str]:
    tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    visitor = _StaticConnectorVisitor()
    # Collect named updater functions before visiting function definitions;
    # generated scenes commonly define the updater before registering it with
    # always_redraw().
    visitor._always_redraw_functions = {
        argument.id
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "always_redraw"
        for argument in call.args
        if isinstance(argument, ast.Name)
    }
    visitor.visit(tree)
    return visitor.violations


def assert_no_static_connectors(filepath: Path) -> None:
    violations = find_static_connectors(filepath)
    if violations:
        raise AssertionError(
            f"{filepath}: static connector(s) found outside always_redraw: {violations}"
        )
