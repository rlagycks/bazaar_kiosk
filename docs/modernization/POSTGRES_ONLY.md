# PostgreSQL 전용 실행 전환

2026-09-09 · D-029 사용자 지시: SQLite를 지원 경로에서 제거하고 Docker로 PostgreSQL 관리.
시작 기준은 PR42 HEAD `8531e181ed23acb17d32b2363d47d7061ebcd8ca`, 후속 브랜치는 `postgres-only-runtime`이다.
PR42는 리뷰 보완 후 머지됐다. develop `c8c11b5`를 병합했고 PR44 base를 develop으로 전환한다.
통계7개를 포함한 최신 회귀를 PG 전용 설정으로 검증한다.

## 변경 범위

- 기본 설정에서 DATABASE_URL이 필수다. 미설정·비PostgreSQL·불완전 URL은 설정 오류로 종료한다.
  접속 실패도 SQLite로 우회하지 않는다. 오류에 URL 암호를 포함하지 않는다.
- SQLite settings_test를 제거하고 settings_test_pg에 합성 자격증명·메모리 캐시/파일·빈 외부 설정을 통합한다.
  호출 환경을 복원하고 일반 DATABASE_URL을 테스트 대상으로 읽지 않는다. PostgreSQL만 실제 DB로 사용한다.
- 주문 번호의 SQLite/기타 DB counter fallback을 제거한다. PostgreSQL sequence 경로는 그대로다.
- [개발 Compose](../../compose.dev.yaml)는 localhost55436·전용 영속 볼륨·비superuser 앱 역할을 사용한다.
  [테스트 Compose](../../compose.test.yaml)는 localhost55437·전용 프로젝트·폐기 DB를 사용한다.
- CI는 현재 검증된 패키지 스냅샷 [requirements-ci.txt](../../requirements-ci.txt)를 설치하고
  고정 PG 이미지와 [공통 실행기](../../scripts/test_postgres.py)로 check/drift/전체 회귀를 실행한다.
  이번 변경에서 Django/PG 주 버전을 올리지 않았다. 이미지 index의 AMD64/ARM64 제공을 확인했다.

## 검증과 격리

전체 발견된 테스트를 migration/app 두 묶음으로 나눠 각각 별도 프로세스에서 실행한다.
현재40개(15+25)이며 skip0이다. 중첩 패키지·다른 앱의 테스트도 전체 discovery에서 포함한다.
DB 실제 identity·소유자·marker·권한·버전을 실행 전과 앱 실행 직전에 확인한다.
앱 테스트 DB도 실행마다 UUID 이름을 쓰고 기존 DB가 있으면 삭제/재사용하지 않고 거부한다.
자동 DROP을 유발하는 --noinput은 테스트 runner에 주지 않으며 자식 입력은 EOF로 닫는다.
앱 DB 생명주기 자체는 Django runner가 관리하고 migration helper와 동일한 매 SQL guard를 제공하지는 않는다.
따라서 항상 새 전용 Compose 프로젝트에서 실행한다. [전체 실행·정리](POSTGRES_TESTING.md).

새로운 설정 거부 회귀는 수정 전 실패를 확인했다. 새 가상환경 설치·pip check와 PG 전체 회귀,
개발용 비superuser 앱 역할의 빈 DB migrate, 잘못된 대상·DB 충돌 거부를 검증한다.
DB 중단 시 fallback하지 않으며 기존 로컬/운영 DB는 검증 대상으로 사용하지 않는다.

## 보존과 남은 결정

기존 db.sqlite3 파일을 지우거나 자동 변환하지 않는다. 과거 migration20개와 frozen 원본은 바이트를 보존한다.
FloorOrderCounter 모델/테이블은 과거 데이터와 schema 호환성 때문에 남지만 번호 발급에서는 사용하지 않는다.
테이블 제거가 필요하면 별도 정방향 migration과 데이터 보존 계획으로 처리한다.
기존 분석·WORKLOG의 SQLite 관찰은 역사적 증거다. 실행 안내가 아니며 현재 테스트는 PostgreSQL만 사용한다.

이번 지시로 PostgreSQL 실행 기반과 CI 준비를 선행했지만0019 정책·D-006 운영 지원 기준·복원/원본 이전은
해결하지 않았다.1B/2B 전체와8A 최종 운영 인수를 자동 완료로 처리하지 않는다.
PG 일일 번호 연속(BK-R003)은 남고 일일 초기화 정책은 D-004/단계5에서 결정한다.
EC2 배포·Supabase 제거/SSE 구현·비밀 교체·운영 DB 적용은 별도 단계다.
