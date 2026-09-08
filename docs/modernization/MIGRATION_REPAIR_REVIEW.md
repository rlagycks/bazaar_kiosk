# 1B — 0020 복구 적용 기록과 남은 관문

2026-09-08 · 기준 develop `3604ccad7add5c760c3b1cecfaa7032706ddc01c` · [이슈 #39](https://github.com/rlagycks/bazaar_kiosk/issues/39).
**상태: 사용자 승인(D-P07)으로0020을 적용 완료. 0019 정책은 미정이므로 전체1B는 여전히 미완료다.**
운영 데이터는 변경하지 않았다. 저장소 migration20개 중0020 하나만 아래 diff대로 바뀌었고
나머지19개는 기준 커밋과 바이트 동일하다. 검증은1A 전용 PostgreSQL 환경에서 진행했다.
이 기록은 운영 DB 적용·배포 승인이 아니다. 운영 적용은 별도 런북과 승인을 따른다.

## 승인·적용한 정확한 범위

대상은 `orders/migrations/0020_create_floor_sequences.py` 하나이며 적용한 전체 diff는
[0020 패치](proposals/0020-empty-sequence.patch)다. 적용 후 파일 해시는
`dbde0d9cc2843a33f69c47ba02491d6bf4c457e0297cfb7fa456ca0ba1c79d33`이고,
적용 전 사본은 [orders/tests/original_0020.py](../../orders/tests/original_0020.py)에 보존한다.

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

신규 PG 설치 성공 뒤에도 **날짜가 바뀌어도 번호가 이어지는 기존 BK-R003 동작은 남는다.**
다른 번호 소비가 없는 예에서는 첫날1→2, 다음 날3이다. SQLite는 날짜별 counter를 사용해
다음 날1부터 시작한다. 이 차이를 목표 업무 정책이나 운영 위험 수용으로 승인하는 것이 아니며,
일일 초기화 여부와 번호 계약은 D-004/단계5에서 별도 결정·검증한다.

역이행은 원본처럼 sequence를 삭제한다. 이후 정방향 적용은 남은 주문의 MAX에서 다시 초기화하므로,
주문 삭제나 미사용 번호 소비 이력이 있으면 이전 번호 위치를 잃고 번호가 재사용될 수 있다.
따라서 역이행→재적용을 안전한 번호 복원 절차로 사용하지 않는다.

## 확인한 PostgreSQL 증거

Python3.12.11/Django5.2.17/psycopg3.3.5, PostgreSQL15.18/aarch64.
승인 전에는 임시 복사본의 후보 suite12개와 기존 정상 특성화8개가 실제 PG에서 통과했다.
승인 후 원본 적용본에서 같은 경로를 다시 실행해 아래 표를 재확인했다.

| 경로 | 결과 |
| --- | --- |
| 빈 DB 전체 Django migration | 성공, 주문0행, sequence(1,false), 첫 nextval1 |
| 같은 빈 DB에 수정 전 SQL | 여전히22003 실패,0019 head·sequence 없음(패치가 원인임을 고정) |
|0019 번호NULL 행→수정0020 | 성공, 행 보존, 첫 nextval1 |
|0019 번호0 행→수정0020 | 성공, 기존0 보존, 첫 nextval1 |
|0019 양수40→수정0020 | 성공, 행 보존, nextval41 |
| 수정0020 재적용 | plan 비어 있음, 행·이력·sequence 무변경 |
| 원본0020으로 적용된 뒤 sequence100인 DB | plan 비어 있음, no-op, 다음값101 |
|0020 미적용·동명sequence100 있음 |42P07로 중단, 이력0019·행·sequence(100,false) 보존 |
| 새 sequence 생성·초기화 후 실패 주입 | 새 sequence/0020 이력 없음, 행 보존, 이후 재시도 성공 |
| 원본0019의 과거 포장NULL/F1/BOOTH 및 포장 역이행 | 기존23514 실패와 행·이력·제약 보존 유지 |
| NOT VALID 제약 탐색(승인 전, 저장소 미포함) | 과거행은 남지만 상태 API의 UPDATE가23514, VALIDATE도 실패 |
| runner의 빈 PG 테스트 DB 생성+앱12개 | **처음으로 성공.** 로그인·주문·결제·가격·원자성·주방·guard·격리 통과 |

적용 후 `orders/tests/test_migration_paths.py`는 PG12개다. 그중4개는0019 제약 실패를
그대로 유지하는 사례이고1개는 수정 전 SQL이 여전히22003으로 실패함을 고정한다.
따라서12개 통과를 전체 migration 경로가 모두 성공한다는 뜻으로 해석하지 않는다.
1A의 기대 실패2개는 `test_empty_database_installs_and_starts_at_one`과
`test_null_order_number_is_preserved_and_sequence_starts_at_one`으로 대체했고,
0/이미적용/동명sequence/생성 후 실패 사례를 추가했다.
NOT VALID 탐색은0018 합성 DB에서 직접 SQL을 실행한 검토였으며 저장소 suite에는 넣지 않았다.
이력 없는 기존 sequence는 자동 DROP·재설정·fake 적용하지 않고
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

사용자는0020 패치만 승인·적용하고0019는 안전하게 중단하는 경로를 선택했다.
따라서1B 전체 완료와 BK-R017 해결은 아직 아니다. 이후 결정할 핵심은 **과거 주문이
조회·통계 보존만 필요한지, 취소·완료 같은 수정도 계속 필요한지**다.

## 승인 후 재현

적용 이후에는 저장소 원본에서 바로 실행한다. [PG 안내](POSTGRES_TESTING.md)의 전용 Compose를
띄운 뒤 아래를 실행하고, 종료·실패 후에는 같은 안내의 정리 절차를 수행한다.

```bash
.venv/bin/python manage.py test orders.tests.test_migration_paths --settings=bazaar_kiosk.settings_test_pg --verbosity 2
.venv/bin/python manage.py test orders.tests.test_baseline orders.tests.test_pg_guard orders.tests.test_settings_isolation --settings=bazaar_kiosk.settings_test_pg --verbosity 2
```

앞은 PG12개, 뒤는 앱12개다. `test orders.tests`를 PG 프로필로 한 번에 실행하면 runner가
`default`를 자신의 테스트 DB로 바꾸므로1A의 fixture guard가 의도대로 거부한다.
이는0020 실패가 아니며 migration 경로는 위와 같이 전용 모듈로 실행한다.

## 승인 전 후보 검증 재현(과거 절차)

아래는 승인 전에 원본을 보존한 채 후보를 검증한 절차다. 준비 도구는 무시되는 `.venv/phase-1b/`
아래에 새 복사본을 만들고 그 안에서만 patch를 실행했다. 지금은 원본에 이미 패치가 적용돼 있어
같은 도구를 그대로 다시 실행할 수 없으며, 기록 재현이 필요하면 적용 이전 커밋에서 실행한다.

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

임시 소스 복사본은 검증 결과 확인을 위해 자동 삭제하지 않는다. 결과를 보관한 뒤 준비 도구가
출력한 이번 실행의 정확한 `.venv/phase-1b/0020-candidate-*` 경로만 확인해 삭제한다.
다른 실행의 복사본·증거·가상환경을 포함하는 상위 디렉터리나 wildcard로 일괄 삭제하지 않는다.

## 승인 이후 남은 관문

[AGENTS.md](../../AGENTS.md)의 “사용자가 마이그레이션 기록 복구 전략을 명시적으로 승인하지
않은 한 … 과거 마이그레이션 파일을 수정하지 마세요”와 [1B 관문](BLUEPRINT.md#phase-1b)에 따라
정확한0020 diff의 적용 승인을 받은 뒤에만 원본을 바꿨다. 남은 관문은 다음과 같다.

- 0019 정책(D-008/017/024): 과거 주문이 조회·통계 보존만 필요한지, 취소·완료 같은 운영 수정도
  계속 필요한지. 결정 전에는 위반 데이터에서 migration을 중단하고 행을 보존한다.
- 번호 정책(D-004/단계5): BK-R003의 PG 다음 날 번호 연속은 이번 승인으로 수용되지 않았다.
- 운영 적용 런북: writer 동결, 적용 이력·실제 sequence 사전 대조, 백업·롤백 리허설.
  이 문서와 이 PR은 운영 DB 적용·배포 승인이 아니다.
