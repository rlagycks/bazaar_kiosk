# GPT-6 Astra 세션 설정

마지막 검증: 2026-09-06

## 모델 및 추론

이번 현대화를 위해 명시적으로 선택한 `gpt-6-astra`를 사용합니다.

- 분석, 아키텍처, 마이그레이션 및 적대적 검토는 `xhigh`로 시작합니다.
- 범위가 명확한 구현 단계는 `high`로 시작합니다.
- 동시성 증명, 데이터 마이그레이션 설계 또는 상충하는 아키텍처 제약 조건처럼 구체적이고
  어려운 문제가 있을 때만 `max`로 높입니다.
- 어려운 결정 사항이 안정된 뒤에만 일상적인 문서 작업이나 기계적인 후속 작업의 추론
  수준을 낮춥니다.

GPT-6 Astra는 `none` 추론 수준을 지원하지 않습니다. API 연동에서는 도구 호출 작업에
Responses API를 사용하고, 현재의 모든 요청 매개변수를 공식 모델 가이드와
대조해 검증합니다. 이 저장소 설정에는 OpenAI API 코드나 자격 증명을 추가하지 않습니다.

## 이후 세션을 위해 준비된 저장소 상태

- 클론: 전체 이력을 포함한 로컬 저장소를 사용할 수 있습니다.
- 준비 브랜치: `chore/astra-modernization-setup`
- 확인 당시 업스트림 기본 브랜치: `origin/develop`
- 로컬 환경: `.venv`, Python 3.12.11, Django 5.2.17
- 스모크 테스트용 로컬 데이터베이스: 모든 마이그레이션이 적용되고 무시 대상으로 설정된
  `db.sqlite3`
- GitHub CLI: 설치되어 있지만 확인 당시 저장된 `rlagycks` 토큰이 유효하지 않았습니다.
  PR 또는 원격 관리 작업 전에 다시 인증해야 합니다.

사용자가 준비 브랜치를 push하기로 선택하기 전까지는 해당 브랜치가 원격에 존재한다고
가정하지 마세요. 자동 설정 단계로 `main`으로 전환하거나 기록을 재작성하지 마세요.

새 워크트리를 생성하기 전에 준비 문서가 기준이 되는 로컬 체크포인트 커밋에 존재해야
합니다. 의도한 ref를 대상으로 다음 두 명령을 검증합니다.

```bash
git cat-file -e <intended-ref>:AGENTS.md
git cat-file -e <intended-ref>:docs/modernization/BLUEPRINT.md
```

명령 중 하나라도 실패하면 해당 ref에서 워크트리를 시작하지 마세요. 먼저 로컬 준비
브랜치 팁을 사용하거나, 검토를 거친 Git 작업으로 해당 체크포인트를 통합합니다.
체크포인트를 공개하거나 merge하는 작업은 계속해서 별도 승인이 필요합니다.

## 새 작업을 시작할 때마다 수행할 절차

1. 저장소를 열고 `AGENTS.md`와 이 디렉터리의 제어 파일을 읽습니다.
2. 현재 브랜치, 상태 및 기존 diff를 확인합니다.
3. 선택한 기준에 준비 제어 파일이 포함되어 있는지 검증한 다음, 승인된 블루프린트 단계
   하나에 전용 브랜치나 워크트리를 사용합니다.
4. 편집하기 전에 해당 단계의 기준 검사를 실행합니다.
5. 승인된 작업을 자율적으로 진행합니다. 누락된 답변이 비즈니스 동작, 영속 데이터,
   보안 또는 되돌릴 수 없는 작업을 변경하는 경우에만 질문합니다.
6. 인수인계하기 전에 `WORKLOG.md`를 업데이트합니다.

권장 브랜치 이름은 다음과 같습니다.

```text
modernize/01-postgres-bootstrap
modernize/02-test-ci-foundation
modernize/03-api-access-control
modernize/04a-identity-security
modernize/04b-content-realtime-security
modernize/05-numbering
modernize/06-order-commands
modernize/07-financial-integrity
modernize/08-reporting-retrieval
modernize/09-api-boundaries
modernize/10-performance-realtime
modernize/11-frontend-resilience
modernize/12a-operations
```

기존의 merge가 많은 그래프가 계속 커지지 않도록 검토 후 squash merge를 우선합니다. 원격
브랜치 삭제, 기본 브랜치 변경 및 보호 규칙 설정은 각각 별도의 사용자 승인이 필요한
작업입니다.

## 로컬 명령

```bash
env -u DATABASE_URL .venv/bin/python manage.py check
env -u DATABASE_URL .venv/bin/python manage.py makemigrations --check --dry-run
env -u DATABASE_URL .venv/bin/python manage.py test
```

보안에 민감하거나 배포와 관련된 작업에서는 현실적이면서 비밀 정보가 아닌 설정으로 운영
환경 방식의 Django 배포 검사도 실행합니다. 영속성, 번호 부여 또는 동시성 작업에서는 폐기
가능한 PostgreSQL 환경을 추가하고 그 환경에서 집중 통합 테스트 스위트를 실행합니다.

## Astra 출력 방식

결과를 먼저 제시합니다. 비교나 순서를 더 명확하게 할 때만 간결한 문단과 목록을
사용합니다. 모든 발견 사항에서 근거, 추론 및 미확인 사항을 구분해야 합니다. 모든 구현
인수인계에는 변경된 파일, 실행한 검사, 남은 위험 및 다음 블루프린트 관문을 나열해야
합니다.
