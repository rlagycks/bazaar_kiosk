"""Serve the real UI against a disposable, verified PostgreSQL fixture.

Run with BK_TEST_DATABASE_URL pointing at compose.test.yaml. Only localhost is
bound. Ctrl-C removes this invocation's UUID database; no existing data is used.
"""
import argparse
import multiprocessing
import os
import signal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def serve(database, port):
    """Own all HTTP/SSE connections in a child that exits before DB removal."""
    import django
    from django.conf import settings
    settings.DATABASES = {'default': database}
    settings.DEBUG = True
    django.setup()
    from django.core.asgi import get_asgi_application
    from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
    from orders.tests.auth_support import AUTH_SETTINGS
    import uvicorn

    for key, value in AUTH_SETTINGS.items():
        setattr(settings, key, value)
    uvicorn.run(ASGIStaticFilesHandler(get_asgi_application()),
                host='127.0.0.1', port=port, log_level='warning',
                timeout_graceful_shutdown=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8018)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'bazaar_kiosk.settings_test_pg'
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.utils import timezone
    from orders.models import EventDay, MenuItem, Table
    from orders.roles import HALL_MONITOR, TAKEOUT_MONITOR, SERVING, STATS
    from orders.tests.auth_support import AUTH_SETTINGS, EVENT_PASSWORD, make_account
    from orders.tests.pg_support import migration_database

    previous_sigint = signal.getsignal(signal.SIGINT)
    try:
        with migration_database() as connection:
            settings.DEBUG = True
            for key, value in AUTH_SETTINGS.items():
                setattr(settings, key, value)
            call_command('migrate', verbosity=0)
            accounts = {
                'ui-all': (SERVING, HALL_MONITOR, TAKEOUT_MONITOR, STATS),
                'ui-serving': (SERVING,), 'ui-hall': (HALL_MONITOR,),
                'ui-takeout': (TAKEOUT_MONITOR,), 'ui-stats': (STATS,),
            }
            for name, permissions in accounts.items():
                make_account(name, *permissions)
            EventDay.objects.update_or_create(date=timezone.localdate(), defaults={'label': 'UI 합성 검증 행사'})
            MenuItem.objects.all().update(is_active=False)
            names = ['김밥', '잔치국수', '<img src=x onerror=alert(1)>', '떡볶이', '어묵',
                     '부침개', '잡채', '만두', '음료', '길이가 아주 긴 메뉴 이름 · 포장과 홀 구분 검증']
            for index, name in enumerate(names, start=1):
                MenuItem.objects.create(name=name, price=index * 1000, sort_index=index)
            for number in [1, 12, *range(101, 121)]:
                Table.objects.update_or_create(number=number, defaults={'is_active': True})
            print(f'Local synthetic UI: http://127.0.0.1:{args.port}/orders/login/', flush=True)
            print(f'Accounts: {", ".join(accounts)}; synthetic password: {EVENT_PASSWORD}', flush=True)
            # Spawn (not fork) so no parent PostgreSQL socket is inherited. Keeping
            # the owner in this process lets normal fixture cleanup run after every
            # child connection, including an interrupted SSE worker, has gone away.
            database = connection.settings_dict.copy()
            connection.close()
            server = multiprocessing.get_context('spawn').Process(target=serve, args=(database, args.port))
            server.start()
            try:
                server.join()
            except KeyboardInterrupt:
                pass  # The terminal also delivers Ctrl-C to the child server.
            finally:
                # Keep repeated Ctrl-C from racing child exit and fixture DROP.
                signal.signal(signal.SIGINT, signal.SIG_IGN)
                server.join(timeout=8)
                if server.is_alive():
                    server.terminate()
                    server.join(timeout=3)
                if server.is_alive():
                    server.kill()
                    server.join()
            if server.exitcode not in (0, -2, -15):
                raise RuntimeError(f'Preview server exited with code {server.exitcode}')
    finally:
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == '__main__':
    main()
