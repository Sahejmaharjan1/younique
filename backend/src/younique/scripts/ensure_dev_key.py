import base64
import os
from pathlib import Path

root = Path(__file__).resolve().parents[4]
env_path = root / ".env"
if not env_path.exists():
    env_path.write_text((root / ".env.example").read_text())
text = env_path.read_text()
if "MASTER_KEY=\n" in text or "MASTER_KEY=" not in text or text.split("MASTER_KEY=", 1)[1].splitlines()[0] == "":
    key = base64.b64encode(os.urandom(32)).decode()
    if "MASTER_KEY=" in text:
        lines = []
        for line in text.splitlines():
            if line.startswith("MASTER_KEY="):
                lines.append(f"MASTER_KEY={key}")
            else:
                lines.append(line)
        env_path.write_text("\n".join(lines) + "\n")
    else:
        env_path.write_text(text + f"\nMASTER_KEY={key}\n")
print("dev key ready")
