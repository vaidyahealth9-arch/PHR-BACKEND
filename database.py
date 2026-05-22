import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

load_dotenv()

raw_database_url = os.getenv("DATABASE_URL")

if not raw_database_url:
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_name = os.getenv("POSTGRES_DB")
    db_host = os.getenv("POSTGRES_HOST")
    
    if db_user and db_pass and db_name and db_host:
        db_pass = db_pass.strip()
        if db_host.startswith("/"): # Unix socket (Cloud SQL)
            raw_database_url = f"postgresql://{db_user}:{db_pass}@/{db_name}?host={db_host}"
        else:
            raw_database_url = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"
    else:
        raw_database_url = "sqlite+aiosqlite:///./phr.db"

if raw_database_url.startswith("postgresql://"):
    DATABASE_URL = raw_database_url.replace("postgresql://", "postgresql+asyncpg://")
else:
    DATABASE_URL = raw_database_url

# Log for debugging (mask password)
log_url = DATABASE_URL
if ":" in log_url and "@" in log_url:
    try:
        user_pass_part = log_url.split("@")[0].split("//")[-1]
        if ":" in user_pass_part:
            mask_user_pass = user_pass_part.split(":")[0] + ":****"
            log_url = log_url.replace(user_pass_part, mask_user_pass)
    except Exception:
        pass
print(f"DATABASE_URL: {log_url}")

SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO, pool_pre_ping=True)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine, class_=AsyncSession, expire_on_commit=False
)
