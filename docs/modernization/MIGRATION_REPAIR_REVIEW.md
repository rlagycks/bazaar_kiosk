# 1B — 검증된 복구 후보와 적용 승인 관문

2026-09-08 · 기준 develop `3604ccad7add5c760c3b1cecfaa7032706ddc01c` · [이슈 #39](https://github.com/rlagycks/bazaar_kiosk/issues/39).
**상태: 후보 검증 완료, 원본 적용 승인 대기. 전체1B는 미완료다.**
원본 앱·migration20개·운영 데이터는 변경하지 않았다. 검증은1A 전용 PostgreSQL 환경과
별도 소스 복사본에서 진행했다. 이 문서를 머지하는 것만으로 과거 파일 변경 승인이 생기지 않는다.

## 적용 승인을 요청할 정확한 범위

대상은 `orders/migrations/0020_create_floor_sequences.py` 하나다.
검토할 전체 diff는 [0020 패치](proposals/0020-empty-sequence.patch)다.

- 최대 번호가 NULL/0이면 sequence를1·미호출 상태로 초기화해 첫 nextval이1이 되게 한다.
- 최대 양수 번호가40이면 기존과 같이40·호출 상태로 초기화해 다음 번호41을 사용한다.
- 이미 원본0020을 적용한 DB에서는 migration을 재실행하지 않아 진행한 sequence를 유지한다.
- 적용 이력이 없는데 같은 이름의 sequence가 있으면 덮어쓰거나 뒤로 돌리지 않고 중단한다.
  이를 위해 `CREATE SEQUENCE IF NOT EXISTS`를 `CREATE SEQUENCE`로 바꾼다.
- schema state·업무 앱·역할·일일 번호 정책·과거 주문의 번호/날짜·reverse 동작은 바꾸지 않는다.
  동시 운영 writer가 있는 상태에서 적용하지 않는다.1B 최종 런북에는 writer 동결·이력/sequence 사전 대조가 필요하다.

이 패치는 신규/미적용0020만 고친다. 이미 적용된 DB의 sequence 누락·소유권·드리프트를
자동으로 복구하지 않는다. 해당 문제가 확인되면 별도의 전진 복구안을 만든다.
새 sequence 생성은 실패 transaction에서 사라지며, 기존 sequence가 발견되면 값 변경 전에 실패한다.
기존 행의 숫자0을 새 번호로 덮어쓰거나 NULL 번호를 일괄 배정하지 않는다.

## 확인한 PostgreSQL 증거

Python3.12.11/Django5.2.17/psycopg3.3.5, PostgreSQL15.18/aarch64.
임시 복사본의 후보 suite12개와 기존 정상 특성화8개가 각각 실제 PG에서 통과했다.

| 경로 | 결과 |
| --- | --- |
| 빈 DB 전체 Django migration | 성공, 주문0행, sequence(1,false), 첫 nextval1 |
|0019 번호NULL 행→후보0020 | 성공, 행 보존, 첫 nextval1 |
|0019 번호0 행→후보0020 | 성공, 기존0 보존, 첫 nextval1 |
|0019 양수40→후보0020 | 성공, 행 보존, nextval41 |
| 후보0020 재적용 | plan 비어 있음, 행·이력·sequence 무변경 |
| 원본0020 적용 뒤 sequence100인 DB에 후보 로딩 | no-op, 다음값101 |
|0020 미적용·동명sequence100 있음 |42P07로 중단, 이력0019·행·sequence(100,false) 보존 |
| 새 sequence 생성·초기화 후 실패 주입 | 새 sequence/0020 이력 없음, 행 보존, 이후 재시도 성공 |
| 원본0019의 과거 포장NULL/F1/BOOTH 및 포장 역이행 | 기존23514 실패와 행·이력·제약 보존 유지 |
| NOT VALID 제약 후보 | 과거행은 남지만 상태 API의 UPDATE가23514, VALIDATE도 실패 |
| 실제 Django PG test DB 생성+기존8개 특성화 | 로그인·주문·결제·가격·원자성·주방 경로 통과 |

12개에는 원본0019 실패를 유지하는4개 사례와 NOT VALID 배제용 탐색1개가 포함된다.
따라서12개 통과를 전체 migration 경로가 모두 성공한다는 뜻으로 해석하지 않는다.
기존 재현 이름을 override한 빈/NULL 사례는 후보에서는 성공을 검사한다.
NOT VALID는0018 합성 DB에서 직접 SQL을 실행한 탐색이며 실제0019 후보 migration의
정·역방향 호환 검증이 아니다. 이력 없는 기존 sequence는 자동 DROP·재설정·fake 적용하지 않고
적용 기록과 실제 객체를 대조해 별도 복구안을 마련해야 한다.

## 0019에서 아직 정할 내용

과거 포장/table NULL과 F1/BOOTH 행을 현재 제약에 맞추는 방법은 데이터 의미를 바꿀 수 있다.
현재 사용자는 지상/부스 정리 요구사항을 확정하지 않았으며 D-008/017/024는 미정이다.

| 후보 | 판단 |
| --- | --- |
|0021만 추가 | 앞선0019/0020 실패에 도달하므로 신규 설치 해결 불가 |
| 주문 삭제·임의 테이블 배정 | 데이터 의미 변경. 승인 없는 자동 복구로 사용하지 않음 |
| PG ADD CONSTRAINT NOT VALID | 과거행은 유지하지만 상태 수정·준비 완료에서 실패. 현행 앱 호환안으로 채택하지 않음 |
| 별도 과거 데이터 보관·조회 전용 처리 | 조회·정산·참조 보존과 운영 수정 가능 여부를 먼저 결정해야 함 |
| 과거행을 구분해 제한적으로 허용 | 신규/과거 쓰기·상태 변경·SQLite/PG 제약 계약과 구앱 호환 설계가 필요 |
| 정책 확정 전 원본0019 유지 | 현재 권고. 위반 데이터가 있으면 migration을 중단하고 행을 보존 |

독립 검토와 실제 테스트 모두 NOT VALID의 UPDATE 문제를 확인했다. 읽기 가능만으로
과거 주문의 운영 수정·통계 호환성을 보장할 수 없다. 위반 행을 영구 유지하면서 나중에
VALIDATE가 자동 성공한다고 약속할 수도 없다. PostgreSQL만 제약을 미검증으로 두면
SQLite와의 계약 차이도 명시해야 한다.

우선0020 패치만 별도 승인·적용하고0019는 안전하게 중단하는 경로를 유지할 수 있다.
이 경우에도1B 전체 완료와 BK-R017 해결은 아니다. 이후 결정할 핵심은 **과거 주문이
조회·통계 보존만 필요한지, 취소·완료 같은 수정도 계속 필요한지**다.

## 후보 검증 재현

원본 파일에 패치를 직접 적용하지 않는다. 준비 도구는 무시되는 `.venv/phase-1b/` 아래에
새 복사본을 만들고 그 안에서만 patch를 실행한다. Python·시스템 patch·Docker Compose가 필요하다.

```bash
BK_REPO="$PWD"
BK_PY="$BK_REPO/.venv/bin/python"
BK_CANDIDATE=$("$BK_PY" docs/modernization/proposals/prepare_0020_candidate.py)
BK_TEST_PROJECT="bk1b-$(date +%s)-$$"
export BK_TEST_PG_PORT=55437
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml up -d --wait postgres
export BK_TEST_DATABASE_URL="postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:${BK_TEST_PG_PORT}/bk_test_control"
cd "$BK_CANDIDATE"
"$BK_PY" manage.py test orders.tests.test_candidate.SequenceCandidateTests --settings=bazaar_kiosk.settings_test_pg --verbosity 2
"$BK_PY" manage.py test orders.tests.test_baseline --settings=bazaar_kiosk.settings_test_pg --verbosity 2
cd "$BK_REPO"
docker volume inspect "${BK_TEST_PROJECT}_pg_test_data" --format '{{json .Labels}}'
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml down --volumes
unset BK_TEST_DATABASE_URL BK_TEST_PG_PORT BK_TEST_PROJECT BK_CANDIDATE BK_PY BK_REPO
```

중간 실패 시에도 이번 프로젝트 label을 확인하고 같은 프로젝트만 정리한다.
다른 개발/운영 컨테이너는 사용하지 않는다. [1A 대상 guard와 정리 규칙](POSTGRES_TESTING.md)을 따른다.
검증 코드는 [후보 suite](proposals/test_0020_candidate.py), 복사 도구는
[prepare_0020_candidate.py](proposals/prepare_0020_candidate.py)에 보관한다.

## 승인과 다음 적용

[AGENTS.md](../../AGENTS.md)의 “사용자가 마이그레이션 기록 복구 전략을 명시적으로 승인하지
않은 한 … 과거 마이그레이션 파일을 수정하지 마세요”와 [1B 관문](BLUEPRINT.md#phase-1b)에 따라,
정확한 이0020 diff의 적용 승인이 필요하다. 승인 뒤 원본에 해당 패치만 적용하고
기존 실패 재현 테스트를 성공 회귀로 전환해 PG/SQLite·이미 적용된 경로를 다시 검증한다.
그 전에는 이 PR을 원본 복구 구현 완료나 운영 배포 승인으로 취급하지 않는다.
