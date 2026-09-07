# 현대화 세션 시작과 인수인계

마지막 상태 정리: 2026-09-08. 이 문서는 모델에 공통인 작업 계약이다.

## 현재 단계와 기준

| 단계 | 현재 상태 | 근거·다음 조건 |
| --- | --- | --- |
| 2A | 완료, PR36 머지 | [격리 SQLite 테스트](TESTING.md) |
| 1A | 완료, PR38 머지 | [전용 PostgreSQL fixture](POSTGRES_TESTING.md) |
| 1B | 후보 검증·검토 중, 미완료 | [Draft PR40](https://github.com/rlagycks/bazaar_kiosk/pull/40), [정확한 복구 후보](MIGRATION_REPAIR_REVIEW.md). D-P07은 proposed |
| 2B | 미착수 | 1B 종료 후 의존성 재현성과 PG CI 연결 |

확인된 develop 기준은 `3604ccad7add5c760c3b1cecfaa7032706ddc01c`다.
이번 문서 정리 시작점은 `review/phase-1b-migration-repair`의
`262f3d544b36f55160c68b4a41e449be14f38ea0`다. 고정된 최신 HEAD로 간주하지 말고
새 세션마다 로컬 상태와 PR 상태를 다시 조회한다. develop만으로는 PR40의 후보 산출물이 포함되지 않는다.

```bash
git status --short
git branch --show-current
git rev-parse HEAD
git diff --stat
gh pr view 40 --json state,isDraft,headRefName,headRefOid,baseRefName,url
```

조회 실패는 미확인으로 기록한다. 과거 인증 실패를 현재 인증 상태로 간주하지 않는다.
새 worktree는 검증된 ref와 필요한 최신 문서·후보를 포함해야 한다. 사용자 변경을 보존하며
main/develop에 직접 구현하거나 문서 확보를 위해 자동 merge하지 않는다.

## 적용 승인 상태

| 작업 | 상태·범위 |
| --- | --- |
| 문서 정리 및 PR40 반영 | 사용자 승인됨. 현재 요청의 범위 |
| 원본을 보존한 임시 복사본 후보 검증 | 기존 검토 범위에서 허용. 격리 DB와 소유 자원만 사용 |
| 원본0020 수정 | **승인 대기**. D-P07은 proposed이며 정확한 패치와 신규·기존·이미 적용 경로에 대한 명시적 승인 필요 |
| 0019 과거 주문 처리 | 정책 미정. 삭제·테이블 재배정·제약 완화를 임의로 적용하지 않음 |
| 번호 정책·운영 위험 수용 | 미정. BK-R003의 PG 다음 날 번호 연속은0020 패치 승인으로 수용되지 않음 |
| 실제 모델 위임·운영 이전·배포·merge | 이번 문서 정리 범위 밖. 별도 작업 지시와 해당 승인 확인 |

근거는 [AGENTS](../../AGENTS.md), [결정 기록](DECISIONS.md), [작업 로그](WORKLOG.md)다.
문서·리뷰 권고 자체를 사용자 승인으로 해석하지 않는다. 이미 받은 승인은 같은 범위에서 유지하되
새 세션에 승인 근거·제외 범위를 전달한다. 이 표가 기존 사용자 승인을 취소하거나 확장하지 않는다.

## 격리 테스트 명령

저장소 루트에서 실행한다. 기존 검증 환경은 Python3.12.11/Django5.2.17이며 새 환경에서는
설치 버전과 접근 권한을 확인한다. 기본 settings나 기존 db.sqlite3로 대체하지 않는다.

```bash
.venv/bin/python manage.py check --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py test orders.tests --settings=bazaar_kiosk.settings_test --verbosity 2
```

원본 SQLite의 기존 결과는19개 수집·12개 실행·PG7개 skip이다. 이번 문서 검증에서 재실행한
결과가 아니며 SQLite 통과는 PG 설치 성공을 뜻하지 않는다.

원본 PG는 [POSTGRES_TESTING](POSTGRES_TESTING.md)의 전용 Compose 생성·URL 설정·실제
identity 검사를 완료한 뒤 다음 모듈을 실행한다. 테스트 종료 또는 실패 후에는 같은 안내의
소유 자원 정리 절차를 수행한다. 순서는 준비 → 검사 → 정리다.

```bash
.venv/bin/python manage.py test orders.tests.test_migration_paths --settings=bazaar_kiosk.settings_test_pg --verbosity 2
```

이7개는 원본0019/0020의 예상 실패6개와 양수40 업그레이드·재적용 no-op 성공1개를 검증한다. 원본 PG 전체 suite의 성공을
기대하거나 fake migration으로 우회하지 않는다.
[후보 검증 절차](MIGRATION_REPAIR_REVIEW.md)는 준비 도구가 생성한 임시 복사본에서 후보 클래스12개와
정상 흐름8개를 구분해 실행한다. 원본 수정 승인을 대신하지 않는다. 후보 성공과0019 미해결을 함께 보고한다.
승인 후 구현에서는 성공 회귀 전환과 신규·기존·이미 적용 경로를 검증하고 전체 PG suite의 실행 가능성을
다시 판정한다. 현재 CI는 check/drift만 수행하므로 녹색 CI를 PG 인수로 보고하지 않는다.

## 모델 설정과 과거 기록

현재 모델은 사용자가 선택한 실행 환경의 설정을 따른다. 문서는 특정 모델 선택을 강제하지 않는다.
대상 모델의 정확한 식별자·도구 지원·파일/명령/DB 접근은 실제 위임 전에 확인한다.
다른 제공자에게 동일한 API 인수나 추론 수준 이름을 추정해 전달하지 않는다.
이 정리는 모델 설정 변경이나 Opus 5 호출·품질 검증이 아니다.

2026-09-06 초기 준비 기록에서는 GPT-6 Astra, 분석 xhigh·구현 high·어려운 문제 max,
Responses API 사용을 안내했다. 당시 준비 브랜치는 chore/astra-modernization-setup이었다.
이는 **과거 세션 설정 기록**이며 현재 모델/API 요구사항이나 시작 브랜치 지시가 아니다.
당시 db.sqlite3 준비와 GitHub 인증 실패도 현재 실행 전제로 사용하지 않는다.

## 작업 절차

1. AGENTS와 README·BASELINE·BLUEPRINT·DECISIONS·WORKLOG를 읽고 과거 관찰과 최신 상태를 구분한다.
2. 승인된 하위 작업 하나의 기준 ref, 소유 파일, 승인 근거, 제외 범위, 인수 기준을 정한다.
3. 변경 규모에 맞게 검증한다. 문서만 변경하면 링크·명령 구문·자리 표시자·렌더·diff를 검사한다.
4. [구현 프롬프트](prompts/03_IMPLEMENT_PHASE.md)는 실제 작업 지시 시 모든 항목을 채운다.
   현재 승인 대기인 원본0020 적용을 자동 시작하지 않는다.
5. 결과·실행 검사·미실행 이유·남은 관문을 WORKLOG에 기록하고 인계한다.
