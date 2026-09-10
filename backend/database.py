import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# DATABASE_URL can be overridden via env (e.g. in docker-compose to point at a
# named volume like sqlite:////app/data/assessment.db). Default keeps the
# original local-dev path.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./assessment.db")

# For sqlite:/// URLs, ensure the parent directory exists so SQLite can create
# the file on first run (otherwise we'd get "unable to open database file").
if SQLALCHEMY_DATABASE_URL.startswith("sqlite:///"):
    _db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "", 1)
    _db_dir = os.path.dirname(_db_path)
    if _db_dir:
        os.makedirs(_db_dir, exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Dependency to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
