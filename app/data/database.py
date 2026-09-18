from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import Config
from app.core.logging.manager import LogManager

Base = declarative_base()
logger = LogManager.get_logger("backend")

class Database:
    """
    Manages the SQLite database connection using SQLAlchemy.
    Provides session factories for interacting with data.
    """
    def __init__(self):
        # check_same_thread=False is needed for SQLite because the GUI runs in a separate thread 
        # from the background worker that might access the DB.
        self.engine = create_engine(
            Config.DATABASE_URL, 
            connect_args={"check_same_thread": False} 
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_session(self):
        return self.SessionLocal()
        
    def create_tables(self):
        """Create tables if they don't exist, then bring existing tables up
        to date with the current models."""
        # Import models to ensure they are registered with Base.metadata before
        # create_all runs -- without this, create_all is a silent no-op unless
        # something else already imported app.data.models first (previously
        # harmless because the DB file shipped pre-populated with these tables
        # already; now that it's created fresh at first launch, this import is
        # load-bearing). Done inside the method, not at module level, to avoid
        # a circular import if models.py ever imports this file.
        from app.data import models  # noqa: F401
        Base.metadata.create_all(bind=self.engine)
        self._sync_schema()

    def _sync_schema(self):
        """Adds any column present in the SQLAlchemy models but missing from
        an already-existing table.

        `create_all()` only creates whole tables that don't exist yet -- it
        never alters a table that's already there. So a column added to a
        model after someone already has a populated database (a dev's local
        checkout, or a packaged build a user has already run once, since
        `app_data.db` sits beside the executable and survives an app
        upgrade) would otherwise raise "no such column" instead of the new
        field just being picked up. This is a lightweight stand-in for a full
        migration framework (e.g. Alembic), proportionate to this app's
        handful of small reference tables; only ADD COLUMN is supported
        (additive schema changes), which covers every change this app has
        needed so far. New columns must be nullable (or have a server-side
        default), since SQLite can't add a NOT-NULL column with no default to
        a table that already has rows.
        """
        inspector = inspect(self.engine)
        try:
            with self.engine.begin() as conn:
                for table in Base.metadata.sorted_tables:
                    if not inspector.has_table(table.name):
                        continue  # brand-new table -- create_all() just made it
                    existing_cols = {col["name"] for col in inspector.get_columns(table.name)}
                    for column in table.columns:
                        if column.name in existing_cols:
                            continue
                        col_type = column.type.compile(dialect=self.engine.dialect)
                        logger.info(f"Schema migration: adding column {table.name}.{column.name} ({col_type})")
                        conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
        except Exception as e:
            # A failed migration leaves the schema out of date with the models
            # every query assumes -- the app can't run correctly from here, so
            # this re-raises after logging rather than swallowing it. Without
            # this, the only trace would be whatever unrelated "no such
            # column" error surfaces later, far from the actual cause.
            logger.error(f"Schema migration failed: {e}", exc_info=True)
            raise

# Create a global instance
db_manager = Database()
