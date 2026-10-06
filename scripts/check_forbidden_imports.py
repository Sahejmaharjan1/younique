import ast
import sys
from pathlib import Path

BANNED = {"httpx", "requests", "socket", "subprocess"}
ROOT = Path(__file__).resolve().parents[1] / "connectors"
failures: list[str] = []
for path in ROOT.glob("*/**/*.py"):
    if "_sdk" in path.parts:
        continue
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".")[0]]
        for name in names:
            if name in BANNED:
                failures.append(f"{path}:{node.lineno} imports {name}")
if failures:
    print("\n".join(failures))
    sys.exit(1)
