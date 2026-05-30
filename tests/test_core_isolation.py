"""Belt-and-suspenders for the dependency rule (import-linter enforces it in CI).

The neutral core must not import ``discord`` or any frontend. This guards the
invariant even for contributors who don't run ``lint-imports`` locally.
"""

from __future__ import annotations

import ast
from pathlib import Path

import petbot.core

CORE_ROOT = Path(petbot.core.__file__).parent
FORBIDDEN_PREFIXES = ("discord", "petbot.frontends")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_core_never_imports_discord_or_frontends() -> None:
    offenders: list[str] = []
    for path in CORE_ROOT.rglob("*.py"):
        for module in _imported_modules(path.read_text(encoding="utf-8")):
            if any(module == p or module.startswith(p + ".") for p in FORBIDDEN_PREFIXES):
                offenders.append(f"{path.relative_to(CORE_ROOT.parent)} imports {module}")
    assert not offenders, "Core must stay platform-neutral:\n" + "\n".join(offenders)
