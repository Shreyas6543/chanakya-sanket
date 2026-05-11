from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.env == "development",
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add source column to existing installations that predate this column
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE signals ADD COLUMN IF NOT EXISTS source VARCHAR(10) NOT NULL DEFAULT 'live'"
            )
        )
        # Add signal_context JSON column for market condition snapshots at signal time
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE signals ADD COLUMN IF NOT EXISTS signal_context JSONB"
            )
        )
