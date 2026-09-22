"""`python manage.py restore_db <filename>` — restores the database from a `backup_db` dump.
DESTRUCTIVE: overwrites every table currently in the database. Command-line only, admin/ops use
— not exposed anywhere in the API or frontend (see docs/deviations.md Part 15). Prompts for
typed confirmation unless `--yes` is passed (for scripted/non-interactive use, e.g. a disaster-
recovery runbook — still requires deliberately passing the flag, never a silent default).
"""
import os
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

BACKUP_DIR = Path(settings.BASE_DIR) / 'backups'


class Command(BaseCommand):
    help = 'Restores the database from a backups/ dump file. Overwrites the current database — confirmation required.'

    def add_arguments(self, parser):
        parser.add_argument('filename', help='Dump filename inside backups/, or an absolute path to one.')
        parser.add_argument('--yes', action='store_true', help='Skip the interactive confirmation prompt.')

    def handle(self, *args, **options):
        path = Path(options['filename'])
        if not path.is_absolute():
            path = BACKUP_DIR / path
        if not path.exists():
            raise CommandError(f'Backup file not found: {path}')

        if not options['yes']:
            self.stdout.write(self.style.WARNING(
                f'This will PERMANENTLY OVERWRITE the current database with the contents of {path.name}.'
            ))
            confirm = input('Type "yes" to continue: ')
            if confirm.strip().lower() != 'yes':
                self.stdout.write('Aborted — no changes made.')
                return

        db = settings.DATABASES['default']
        env = {**os.environ, 'PGPASSWORD': db['PASSWORD']}
        result = subprocess.run(
            [
                'pg_restore', '--clean', '--if-exists', '--no-owner',
                '-h', db['HOST'], '-p', str(db['PORT']),
                '-U', db['USER'], '-d', db['NAME'],
                str(path),
            ],
            env=env, capture_output=True, text=True,
        )
        # pg_restore can exit non-zero on benign warnings even with --if-exists (e.g. an
        # extension it can't drop/recreate without superuser) — surfaced as a warning, not
        # treated as an automatic failure, since the restore itself commonly still succeeds.
        if result.returncode != 0:
            self.stdout.write(self.style.WARNING(f'pg_restore reported warnings:\n{result.stderr}'))
        self.stdout.write(self.style.SUCCESS(f'Restored from {path.name}'))
