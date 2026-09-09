# Bazaar Kiosk

단일 층에서 운영되는 바자회를 위한 Django 기반 주문, 결제, 주방 진행 상황 및 매출
대시보드 시스템입니다. 이 저장소는 점진적인 현대화를 준비하고 있습니다. 현재 동작은
테스트와 운영자의 결정으로 확인되기 전까지 레거시 동작으로 간주해야 합니다.

## 로컬 설정

개발·테스트·CI·운영에서 PostgreSQL만 지원합니다. Python3.12와 Docker Compose가 필요합니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-ci.txt
docker compose -p bazaar-dev -f compose.dev.yaml up -d --wait postgres
```

[.env.example](.env.example)의 개발 URL은 위 Compose의 loopback55436 DB를 가리킵니다.
Django는 .env를 자동으로 읽지 않습니다. 기존 파일을 덮어쓰지 않고 검토한 뒤 적용합니다.

```bash
test -e .env || cp .env.example .env
set -a
source .env
set +a
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

위 migrate는 새 로컬 개발 DB용입니다. 기존/운영 DB 이전은 별도 승인된 절차를 따릅니다.
DATABASE_URL이 누락되거나 PostgreSQL URL이 아니면 시작이 실패합니다. SQLite 자동 전환은 없습니다.
개발 데이터는 Compose 볼륨에 보존되며 일반 종료에는 `docker compose -p bazaar-dev -f compose.dev.yaml down`을 사용합니다.
개발 볼륨에 `--volumes`를 붙이지 마세요. 공개 합성 암호·DEBUG 설정은 로컬 개발 전용입니다.

## 검사

[전용 테스트 DB 준비·정리](docs/modernization/POSTGRES_TESTING.md)를 따른 뒤 실행합니다.

```bash
.venv/bin/python scripts/test_postgres.py
```

전체 테스트를 발견해 migration15개와 앱/guard22개를 별도 프로세스에서 실행합니다.
모두 PostgreSQL에서 실행하며 SQLite skip 경로는 없습니다. CI도 같은 명령을 사용합니다.
[전환 범위·남은 결정](docs/modernization/POSTGRES_ONLY.md)에 기존 DB 파일과 마이그레이션 보존,
영속 개발 DB·일회용 테스트 DB 구분, 운영 인수 한계를 기록했습니다.

## 현대화 워크플로

[현대화 가이드](docs/modernization/README.md)부터 시작하세요. 이 가이드에는 다음 내용이
있습니다.

- 저장소별 기준 상태 및 위험 목록
- 모델 공통 세션 안내와 과거 설정 기록
- 안전한 Git 복구 전략
- 여러 세션에 걸친 구축 블루프린트
- 분석, 계획 검토, 구현 및 최종 감사를 위해 바로 붙여 넣을 수 있는 프롬프트
- 원활한 인수인계를 위한 결정 사항 및 작업 로그 템플릿

에이전트는 코드를 변경하기 전에 [AGENTS.md](AGENTS.md)를 읽어야 합니다.
