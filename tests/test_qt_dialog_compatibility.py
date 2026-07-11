from __future__ import annotations

import ast
from pathlib import Path


def test_dialog_result_checks_use_qdialog_dialogcode():
    source_root = Path(__file__).parents[1] / "src" / "dockflow"
    violations = []
    for path in source_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Attribute) or node.attr not in {"Accepted", "Rejected"}:
                continue
            expression = ast.get_source_segment(source, node) or ""
            if expression not in {
                "QDialog.DialogCode.Accepted",
                "QDialog.DialogCode.Rejected",
            }:
                violations.append(f"{path.name}:{node.lineno}: {expression}")
    assert not violations, "Use QDialog.DialogCode for dialog results:\n" + "\n".join(violations)
