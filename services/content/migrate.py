"""Forward-only migration runner, called by create_app() at every startup.

The files in migrations/ (001_init.sql, 002_..., ...) are applied in name order, each one once.
Applied versions are recorded in the schema_migrations table. A file runs in one transaction
together with its schema_migrations row, so a file that fails leaves nothing behind and is
tried again on the next start. Applied files are never edited; a fix is a new file.

The scheduler service has its own copy of this file on purpose: the services share no code.
"""

import logging
import re
from pathlib import Path
from typing import Any

log = logging.getLogger("migrate")

# A line that holds only GO ends a batch, as in sqlcmd. Some statements, e.g. adding a column
# and then updating it, must be in separate batches because SQL Server compiles a whole batch first.
GO_LINE = re.compile(r"^[ \t]*GO[ \t]*$", re.IGNORECASE | re.MULTILINE)

CREATE_TABLE = (
    "IF OBJECT_ID(N'schema_migrations', N'U') IS NULL "
    "CREATE TABLE schema_migrations (version NVARCHAR(100) NOT NULL PRIMARY KEY, applied_at DATETIME2(0) NOT NULL)"
)


def split_batches(script: str) -> list[str]:
    """Split a script on GO lines and drop empty batches."""
    return [batch.strip() for batch in GO_LINE.split(script) if batch.strip()]


def pending(migrations_dir: Path, applied: set[str]) -> list[Path]:
    """The migration files not applied yet, in name order (the version is the name without .sql)."""
    return [path for path in sorted(migrations_dir.glob("*.sql")) if path.stem not in applied]


def migrate(conn: Any, migrations_dir: Path) -> list[str]:
    """Apply every pending migration and return their versions, in the order applied.

    `conn` is an open connection with autocommit off whose rows are dicts.
    """
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE)
    conn.commit()
    cursor.execute("SELECT version FROM schema_migrations")
    applied = {row["version"] for row in cursor.fetchall()}

    done = []
    for path in pending(migrations_dir, applied):
        try:
            for batch in split_batches(path.read_text(encoding="utf-8")):
                cursor.execute(batch)
            cursor.execute("INSERT INTO schema_migrations (version, applied_at) VALUES (%s, SYSUTCDATETIME())",
                           (path.stem,))
            conn.commit()
        except Exception:
            conn.rollback()
            log.error("migration failed: %s (rolled back)", path.stem)
            raise
        log.info("migration applied: %s", path.stem)
        done.append(path.stem)

    if not done:
        log.info("migrations: nothing to apply")
    return done
