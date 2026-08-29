from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# PostgreSQL connection string using asyncpg
DATABASE_URL = "postgresql+asyncpg://ntro_admin:securepassword@localhost:5432/ntro_auth"

# Create the async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# Create a configured "Session" class
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for the SQLAlchemy models
Base = declarative_base()

# Dependency to get the database session in FastAPI routes
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session