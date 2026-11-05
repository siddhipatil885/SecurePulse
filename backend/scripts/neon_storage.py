"""Read-only database usage check against the configured 1 GB budget."""
from pathlib import Path
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.core.config import Settings


def main():
    settings = Settings(_env_file=None, **{k: v for k, v in dotenv_values(ROOT / 'backend/.env', interpolate=False).items() if v is not None})
    engine = create_engine(make_url(settings.database_url_unpooled or settings.database_url).set(drivername='postgresql+psycopg2'),
                           connect_args={'connect_timeout': 20})
    try:
        with engine.connect() as connection:
            used = connection.scalar(text('SELECT pg_database_size(current_database())'))
            rows = connection.execute(text('SELECT schemaname,relname,pg_total_relation_size(relid) AS bytes '
                'FROM pg_catalog.pg_statio_user_tables ORDER BY bytes DESC LIMIT 8')).all()
        budget = settings.database_storage_budget_bytes
        ratio = used / budget
        status = 'critical' if ratio >= .9 else 'warning' if ratio >= .8 else 'ok'
        print(f'Database storage: {used:,} bytes / {budget:,} bytes ({ratio:.2%}); status={status}')
        for row in rows:
            print(f'  {row.schemaname}.{row.relname}: {row.bytes:,} bytes including indexes')
        print('Media stays on the host. This is live database size, not total provider billing/history/branch usage.')
        if status != 'ok':
            print('Archive/review growth before reaching the plan limit. No data was deleted.')
        return 1 if status == 'critical' else 0
    except Exception as error:
        print('Storage check failed (' + type(error).__name__ + '); connection details omitted.', file=sys.stderr)
        return 1
    finally:
        engine.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
