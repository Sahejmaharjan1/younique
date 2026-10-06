import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "backend" / "migrations"
text = "\n".join(path.read_text() for path in ROOT.rglob("*.py"))
sql = "\n".join(path.read_text() for path in ROOT.rglob("*.sql"))
combined = text + sql
failures: list[str] = []
if "langgraph" in combined.lower():
    failures.append("migration references langgraph schema")
if "lock_timeout" not in text:
    failures.append("migration does not set lock_timeout")
if "DROP COLUMN" in combined or "DROP TABLE" in text:
    failures.append("destructive drop found in the baseline migration")
heads = list((ROOT / "versions").glob("*.py"))
if len(heads) != 1:
    failures.append(f"expected one alembic head file, found {len(heads)}")
if failures:
    print("\n".join(failures))
    sys.exit(1)
