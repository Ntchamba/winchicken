"""`python manage.py backup_db` — runs pg_dump against the configured PostgreSQL connection and
writes a timestamped, compressed custom-format dump to `backups/`, then prunes dumps beyond the
retention count (default 7, `BACKUP_RETENTION_COUNT` env var). See docs/deviations.md Part 15
and the root README's "Backups" section for the full picture: how this is scheduled (a
dedicated `backup` docker-compose service, not cron inside this container — see that file),
and `restore_db` (this command's companion, apps/core/management/commands/restore_db.py).
"""
import os
import subprocess
from datetime import datetime
from pathlib import Path

from decouple import config
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

BACKUP_DIR = Path(settings.BASE_DIR) / 'backups'
DUMP_GLOB = 'winchicken-*.dump'


class Command(BaseCommand):
    help = 'Dumps the database to backups/ (pg_dump, custom format) and prunes old dumps beyond the retention count.'

    def handle(self, *args, **options):
        BACKUP_DIR.mkdir(exist_ok=True)
        db = settings.DATABASES['default']
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        dump_path = BACKUP_DIR / f'winchicken-{timestamp}.dump'

        env = {**os.environ, 'PGPASSWORD': db['PASSWORD']}
        result = subprocess.run(
            [
                'pg_dump', '-Fc',  # custom format: compressed, and the only format pg_restore --clean can target
                '-h', db['HOST'], '-p', str(db['PORT']),
                '-U', db['USER'], '-d', db['NAME'],
                '-f', str(dump_path),
            ],
            env=env, capture_output=True, text=True,
        )
        if result.returncode != 0:
            dump_path.unlink(missing_ok=True)  # don't leave a truncated/empty file counted by retention
            raise CommandError(f'pg_dump failed:\n{result.stderr}')

        self.stdout.write(self.style.SUCCESS(f'Backup written: {dump_path}'))

        retention = config('BACKUP_RETENTION_COUNT', default=7, cast=int)
        dumps = sorted(BACKUP_DIR.glob(DUMP_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dumps[retention:]:
            old.unlink()
            self.stdout.write(f'Deleted old backup (beyond retention of {retention}): {old.name}')
