import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from younique.connectors.registry import manifests

for manifest in manifests():
    assert manifest.key
    assert manifest.bundles
print(f"{len(manifests())} connectors valid")
