import json
from pathlib import Path

from younique.api.factory import create_app

app = create_app()
target = Path(__file__).resolve().parents[4] / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2) + "\n")
print(target)
