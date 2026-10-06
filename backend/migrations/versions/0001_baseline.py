from __future__ import annotations

from pathlib import Path

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _split_sql(script: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    index = 0
    dollar: str | None = None
    while index < len(script):
        if dollar is not None:
            if script.startswith(dollar, index):
                buf.append(dollar)
                index += len(dollar)
                dollar = None
                continue
            buf.append(script[index])
            index += 1
            continue
        if script[index] == "$":
            end = script.find("$", index + 1)
            if end == -1:
                buf.append(script[index])
                index += 1
                continue
            tag = script[index : end + 1]
            dollar = tag
            buf.append(tag)
            index = end + 1
            continue
        if script[index] == ";":
            statement = "".join(buf).strip()
            if statement:
                parts.append(statement)
            buf = []
            index += 1
            continue
        buf.append(script[index])
        index += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def upgrade() -> None:
    op.execute("SET lock_timeout = '3s'")
    op.execute("SET statement_timeout = '30s'")
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    bind = op.get_bind()
    from younique.models import Base

    Base.metadata.create_all(bind)
    sql = Path(__file__).resolve().parents[1].joinpath("sql", "rls.sql").read_text()
    for statement in _split_sql(sql):
        op.execute(statement)


def downgrade() -> None:
    op.execute("SET lock_timeout = '3s'")
    bind = op.get_bind()
    from younique.models import Base

    Base.metadata.drop_all(bind)
    op.execute("DROP SCHEMA IF EXISTS audit CASCADE")
    op.execute("DROP SCHEMA IF EXISTS app CASCADE")
