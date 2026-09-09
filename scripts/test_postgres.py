"""Run project discovery on verified PostgreSQL targets in two sequential processes."""

import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def partition_suite(suite):
    def cases(node):
        if isinstance(node, unittest.TestSuite):
            for child in node:
                yield from cases(child)
        else:
            yield node

    migration, application = [], []
    for case in cases(suite):
        if isinstance(case, unittest.loader._FailedTest):
            raise RuntimeError('Project test discovery contains an import error')
        label = case.id()
        target = migration if label.startswith('orders.tests.test_migration_paths.') else application
        target.append(label)
    if not migration or not application:
        raise RuntimeError('Both migration and application test partitions must be nonempty')
    if len(set(migration + application)) != len(migration + application):
        raise RuntimeError('Duplicate test IDs in project discovery')
    return migration, application


def verify_target(cfg):
    import psycopg
    from orders.tests.pg_support import verify_control_database

    with psycopg.connect(dbname=cfg['NAME'], user=cfg['USER'], password=cfg['PASSWORD'],
                         host=cfg['HOST'], port=cfg['PORT'], **cfg['OPTIONS']) as control:
        verify_control_database(control)
        if control.execute('SELECT 1 FROM pg_database WHERE datname = %s',
                           (cfg['TEST']['NAME'],)).fetchone():
            raise RuntimeError('Application test database already exists; refusing to reuse or delete it')


def main():
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bazaar_kiosk.settings_test_pg'
    os.environ.setdefault('BK_TEST_APP_DATABASE', 'bk_test_app_' + uuid.uuid4().hex)
    import django
    django.setup()
    from django.conf import settings
    from django.test.runner import DiscoverRunner

    cfg = settings.DATABASES['default']
    verify_target(cfg)
    migration, application = partition_suite(DiscoverRunner(verbosity=0).build_suite([str(ROOT)]))
    print(f'Complete discovery: {len(migration)} migration + {len(application)} application tests', flush=True)

    def manage(*args):
        # EOF on collision, never Django's --noinput automatic DROP behavior.
        subprocess.run([sys.executable, str(ROOT / 'manage.py'), *args,
                        '--settings=bazaar_kiosk.settings_test_pg'], cwd=ROOT,
                       stdin=subprocess.DEVNULL, check=True)

    manage('check')
    manage('makemigrations', '--check', '--dry-run')
    manage('test', *migration, '--verbosity', '2')
    verify_target(cfg)
    manage('test', *application, '--verbosity', '2')


if __name__ == '__main__':
    main()
