from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from younique.core.config import get_settings


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url_migrator)
    async with engine.begin() as conn:
        count = (await conn.execute(text("SELECT count(*) FROM app.model_providers"))).scalar_one()
    await engine.dispose()
    print(f"seed complete: {count} model providers")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
