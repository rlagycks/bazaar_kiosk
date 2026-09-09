# 현대화 세션 시작과 인수인계

마지막 상태 정리: 2026-09-09. 이 문서는 모델에 공통인 작업 계약이다.

## 현재 단계와 기준

- 2A·1A와 PR40(0020 복구)은 머지됐다.1B는0019 정책·운영 확인이 남아 미완료다.
- PR42의8A 집계 수정은 코드/로컬 검증 완료, 리뷰 보완과 최종 인수 대기다.
- D-029로 개발·테스트·CI·운영 DB를 PostgreSQL로 통일한다. 현재 브랜치는 `postgres-only-runtime`,
  기준은 PR42 HEAD `8531e181ed23acb17d32b2363d47d7061ebcd8ca`다.
- 2B의 PostgreSQL CI 기반은 선행 구현했지만1B와 지원/운영 관문이 남아 전체 완료가 아니다.

```bash
git status --short
git branch --show-current
git rev-parse HEAD
gh pr list --state open --json number,title,headRefName,baseRefName,isDraft,url
```

새 세션마다 실제 ref·사용자 변경·열린 PR을 확인한다. 현재 문서가 없는 기준으로 자동 전환하지 않는다.

## 승인과 범위

D-029는 SQLite 실행/테스트 지원 제거, PostgreSQL 전용 설정·번호 경로·개발 Compose·필수 CI 전환 지시다.
이슈·브랜치·PR 작업 방식은 유지한다. PR42 자체의 리뷰 보완/머지는 별도이며 변경은 후속 PR로 인계한다.
D-P07의0020 적용은 완료됐다.0019 정책·번호 정책·운영 DB 적용·EC2 배포는 여전히 미정 또는 별도 승인이다.
기존 데이터 파일·과거 migration·counter 테이블을 삭제하지 않는다.
[결정 기록](DECISIONS.md), [현재 전환 범위](POSTGRES_ONLY.md), [작업 로그](WORKLOG.md)를 함께 읽는다.

## 현재 검증 명령

[POSTGRES_TESTING](POSTGRES_TESTING.md)의 새 전용 Compose 생성·명시적 테스트 URL 설정 후 실행한다.

```bash
.venv/bin/python scripts/test_postgres.py
```

실제 대상 검증 후 check/drift와 프로젝트 전체 테스트를 migration/app 별도 프로세스로 실행한다.
현재37개(15+22), 모두 PostgreSQL·skip0이다. DB 충돌은 자동 삭제하지 않고 오류로 종료한다.
일반 DATABASE_URL·기존 SQLite 파일·개발용 DB를 테스트 대상으로 사용하지 않는다.
테스트가 끝나거나 실패하면 안내의 소유 label 검증·정리 절차를 따른다.
CI도 같은 명령을 사용한다. PG 성공을0019 정책이나 운영 배포 승인으로 확대하지 않는다.

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
   0020은 적용됐으나0019·번호 정책·운영 적용을 자동 시작하지 않는다.
5. 결과·실행 검사·미실행 이유·남은 관문을 WORKLOG에 기록하고 인계한다.
