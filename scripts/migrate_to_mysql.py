"""Copy a stopped application's SQLite database to a NEW local MySQL database.

Never overwrites an existing target. Keeps a consistent SQLite backup and
checks every value before committing. Stop the app until .env is switched.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from sqlalchemy import select, text, inspect
from sqlalchemy.engine import make_url
from app.db import Base, build_engine


def digest(rows):
    encoded = json.dumps([dict(row) for row in rows], ensure_ascii=False,
                         sort_keys=True, default=str, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def migrate(source, target_url):
    source = source.resolve(strict=True)
    url = make_url(target_url)
    database = url.database or ''
    if (url.drivername != 'mysql+pymysql' or url.host not in ('localhost', '127.0.0.1')
            or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', database)):
        raise ValueError('Target must be a local mysql+pymysql URL with a valid database name.')
    admin = build_engine(url.set(database=''))
    with admin.connect() as connection:
        exists = connection.execute(text('SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=:name'), {'name': database}).first()
        if exists:
            raise RuntimeError('Target database already exists; no data modified. Choose a new database.')

    backup_dir = ROOT / 'data' / 'backups'
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = backup_dir / f'before-mysql-{stamp}.db'
    with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as src:
        with sqlite3.connect(backup) as dest:
            src.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('SQLite backup integrity check failed.')
            if dest.execute('PRAGMA foreign_key_check').fetchall():
                raise RuntimeError('SQLite source has invalid foreign keys.')

    with admin.begin() as connection:
        connection.execute(text(f'CREATE DATABASE `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin'))
    admin.dispose()
    target = build_engine(url)
    for table in Base.metadata.tables.values():
        table.dialect_options['mysql'].update(engine='InnoDB', charset='utf8mb4', collate='utf8mb4_bin')
    Base.metadata.create_all(target)
    snapshot = build_engine('sqlite:///' + backup.as_posix())
    report = {'database': database, 'backup': str(backup), 'tables': {}}
    try:
        with snapshot.connect() as src, target.begin() as dest:
            source_tables = set(inspect(src).get_table_names())
            for table in Base.metadata.sorted_tables:
                # 旧 SQLite 版本尚无删除标记表；其他表缺失仍视为错误。
                rows = [] if table.name == 'deleted_job' and table.name not in source_tables else src.execute(select(table).order_by(table.c.id)).mappings().all()
                for offset in range(0, len(rows), 500):
                    dest.execute(table.insert(), [dict(row) for row in rows[offset:offset + 500]])
                copied = dest.execute(select(table).order_by(table.c.id)).mappings().all()
                if len(copied) != len(rows) or digest(copied) != digest(rows):
                    raise RuntimeError(f'Validation failed for {table.name}; insert transaction rolled back.')
                report['tables'][table.name] = {'rows': len(rows), 'sha256': digest(rows)}
        report['verified'] = True
        report_path = backup_dir / f'mysql-migration-{stamp}.json'
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        snapshot.dispose()
        target.dispose()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data' / 'jobs.db')
    parser.add_argument('--target-url', default=os.getenv('MYSQL_TARGET_URL', 'mysql+pymysql://root@127.0.0.1:3306/ai_jobs_intelligence?charset=utf8mb4'))
    args = parser.parse_args()
    migrate(args.source, args.target_url)
