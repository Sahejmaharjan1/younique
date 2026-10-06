import sys
from pathlib import Path

name = sys.argv[1] if len(sys.argv) > 1 else ""
if not name:
    raise SystemExit("usage: python3 scripts/new_connector.py <key>")
root = Path(__file__).resolve().parents[1] / "connectors" / name
root.mkdir(parents=True)
(root / "tools").mkdir()
(root / "manifest.py").write_text(
    "from younique_sdk import ConnectorManifest, PermissionBundle\n\n"
    f"MANIFEST = ConnectorManifest(key={name!r}, display_name={name!r}, description='', auth='oauth', limitations=[], bundles=[])\n"
    "TOOLS = []\n"
)
print(root)
