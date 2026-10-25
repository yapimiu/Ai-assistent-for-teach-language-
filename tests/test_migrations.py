import os
import subprocess
import sys
import uuid
from sqlalchemy import text, create_engine, inspect


def test_frozen_migration_upgrade_and_downgrade(sessions):
    schema = "migration_" + uuid.uuid4().hex
    engine = sessions.kw["bind"]
    with engine.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    env = {**os.environ, "DATABASE_URL": url}
    private_engine = create_engine(url)
    try:
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        names = inspect(private_engine).get_table_names()
        assert {"users", "tasks", "attempts", "task_dependencies", "message_receipts"} <= set(names)
        result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "base"], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert inspect(private_engine).get_table_names() == ["alembic_version"]
    finally:
        private_engine.dispose()
        with engine.begin() as db:
            db.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
