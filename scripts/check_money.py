import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend" / "src" / "younique" / "usage"
failures: list[str] = []
for path in ROOT.glob("*.py"):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float":
            failures.append(f"{path}:{node.lineno} uses float()")
if failures:
    print("\n".join(failures))
    sys.exit(1)
