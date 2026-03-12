"""Print a summary of all public tables and their row counts."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text


async def show_tables():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("    ERROR: DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(url)
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' ORDER BY tablename"
        ))
        tables = [row[0] for row in result.fetchall()]
        if not tables:
            print("    (no tables found)")
        else:
            for table in tables:
                count_result = await conn.execute(
                    text(f'SELECT COUNT(*) FROM "{table}"')
                )
                count = count_result.scalar()
                print(f"    {table}: {count} rows")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(show_tables())
