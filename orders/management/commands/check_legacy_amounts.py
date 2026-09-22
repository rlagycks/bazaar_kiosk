"""Report the old money shapes a database holds (7C, D-054). Read-only."""

import json

from django.core.management.base import BaseCommand

from orders.services import legacy_audit


class Command(BaseCommand):
    help = "분할 수납 기록이 없는 주문을 세어 보고합니다. 데이터는 바꾸지 않습니다."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true", dest="as_json",
            help="사람이 읽는 문장 대신 JSON으로 출력합니다.",
        )

    def handle(self, *args, **options):
        figures = legacy_audit.survey()
        if options["as_json"]:
            self.stdout.write(json.dumps(figures, ensure_ascii=False, indent=2))
            return
        self.stdout.write(legacy_audit.render(figures))
