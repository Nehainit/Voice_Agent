import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from api.db.models import Base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://nehadubey:@localhost:5433/dograh_rebuild",
)

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def init_db():
    Base.metadata.create_all(bind=engine)
    run_bootstrap_migrations()


def run_bootstrap_migrations():
    # ponytail: simple bootstrap migration; switch to Alembic when schema history matters.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                ALTER TABLE workflows
                ADD COLUMN IF NOT EXISTS agent_id INTEGER REFERENCES agents(id)
                """
            )
        )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
