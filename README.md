# Bazaar Kiosk

단일 층에서 운영되는 바자회를 위한 Django 기반 주문, 결제, 주방 진행 상황 및 매출
대시보드 시스템입니다. 이 저장소는 점진적인 현대화를 준비하고 있습니다. 현재 동작은
테스트와 운영자의 결정으로 확인되기 전까지 레거시 동작으로 간주해야 합니다.

## 로컬 설정

기존 CI 워크플로에 맞춰 Python 3.12를 사용합니다.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

애플리케이션은 환경 변수에서 설정을 읽으며 `.env`를 자동으로 불러오지 않습니다.
데이터베이스 명령을 실행하기 전에 로컬 설정을 구성하고 확인하세요. 다음 명령은 기존
`.env`를 보존합니다.

```bash
test -e .env || cp .env.example .env
# 불러오기 전에 .env를 검토하세요. 로컬 SQLite를 사용하려면 DATABASE_URL을 비워 둡니다.
set -a
source .env
set +a
```

명시적으로 로컬 SQLite 데이터베이스를 사용하려면 데이터베이스에 영향을 주는 각 명령에서
상속된 데이터베이스 URL을 제거합니다.

```bash
env -u DATABASE_URL python manage.py migrate
env -u DATABASE_URL python manage.py runserver
```

`DATABASE_URL`이 검증되지 않은 데이터베이스를 가리키는 동안에는 마이그레이션을 실행하지
마세요. `DATABASE_URL`이 비어 있거나 설정되지 않으면 로컬 SQLite가 선택됩니다.
PostgreSQL은 운영 환경용으로 예정된 백엔드이며, 시퀀스, 잠금, 마이그레이션 및 동시성
검증에는 폐기 가능한 환경에서 PostgreSQL을 사용해야 합니다.

이 예시는 `DEBUG=1`을 설정합니다. 현재 레거시 설정에서는 이 값 때문에
`ALLOWED_HOSTS`가 `['*']`가 됩니다. `.env.example`의 허용 목록은 디버그를 비활성화해야만
적용됩니다. 이를 안전한 배포 설정이 아닌 로컬 개발 동작으로 간주하세요.

유용한 로컬 URL은 다음과 같습니다.

- `http://127.0.0.1:8000/orders/` — 역할 로그인
- `http://127.0.0.1:8000/admin/` — Django 관리자 페이지

## 기준 검사

```bash
env -u DATABASE_URL .venv/bin/python manage.py check
env -u DATABASE_URL .venv/bin/python manage.py makemigrations --check --dry-run
env -u DATABASE_URL .venv/bin/python manage.py test
```

준비 단계의 기준 상태에서는 Django 검사와 SQLite 마이그레이션이 통과하지만 프로젝트에 자동화
테스트가 없습니다. 따라서 위 명령을 통과하는 것만으로는 주문, 결제, 인가, PostgreSQL 번호
부여 또는 실시간 동작이 올바르다는 근거가 되지 않습니다.

## 현대화 워크플로

[현대화 가이드](docs/modernization/README.md)부터 시작하세요. 이 가이드에는 다음 내용이
있습니다.

- 저장소별 기준 상태 및 위험 목록
- 권장 GPT-6 Astra 세션 설정
- 안전한 Git 복구 전략
- 여러 세션에 걸친 구축 블루프린트
- 분석, 계획 검토, 구현 및 최종 감사를 위해 바로 붙여 넣을 수 있는 프롬프트
- 원활한 인수인계를 위한 결정 사항 및 작업 로그 템플릿

에이전트는 코드를 변경하기 전에 [AGENTS.md](AGENTS.md)를 읽어야 합니다.
