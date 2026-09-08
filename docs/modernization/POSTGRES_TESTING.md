# 1A — 로컬 PostgreSQL migration 경로 재현

[이슈 #37](https://github.com/rlagycks/bazaar_kiosk/issues/37), 기준 develop의2A 머지 커밋 ff013b4.
이 환경은 합성 데이터만 사용하는 일회용 테스트 클러스터다. **테스트 통과는 운영 DB의 상태나
운영 적용 성공을 뜻하지 않는다.** 앱 업무 코드는 변경하지 않는다.
2026-09-08 D-P07 승인으로0020만 수정됐다. 아래 표는 그 이후의 기대 결과다.
수정 전 기대 결과는 [적용 기록](MIGRATION_REPAIR_REVIEW.md)과 이 문서의 git 이력에 남아 있다.

## 전용 환경 시작

Python3.12 가상환경과 requirements, Docker Compose가 필요하다. 검증한 버전은
Python3.12.11/Django5.2.17/psycopg3.3.5, Docker29.4.1/Compose5.1.3,
PostgreSQL15.18/aarch64다. Compose는 검증 당시 로컬 이미지 digest를 고정했다.
이 선택은 D-006 운영 지원 버전·EC2 구성 승인이 아니다. 다른 CPU의 이미지 가용성은 별도 확인한다.

아래 명령은 저장소 루트와 같은 셸에서 실행한다. 프로젝트 이름은 매번 새로 생성한다.
포트가 이미 사용 중이면 다른 비특권 포트를 지정하고 URL에도 같은 포트를 사용한다.
libpq의 PGHOSTADDR/PGSERVICE 등 비어 있지 않은 `PG*` 환경 변수가 있으면 먼저 별도 테스트 셸에서 제거한다.

```bash
BK_TEST_PROJECT="bk1a-$(date +%s)-$$"
export BK_TEST_PG_PORT=55437
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml config --quiet
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml up -d --wait postgres
export BK_TEST_DATABASE_URL="postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:${BK_TEST_PG_PORT}/bk_test_control"
.venv/bin/python manage.py check --settings=bazaar_kiosk.settings_test_pg
.venv/bin/python manage.py test orders.tests.test_migration_paths --settings=bazaar_kiosk.settings_test_pg --verbosity 2
.venv/bin/python manage.py test orders.tests.test_baseline orders.tests.test_pg_guard orders.tests.test_settings_isolation --settings=bazaar_kiosk.settings_test_pg --verbosity 2
```

컨테이너의 pg_isready 성공만으로 인수하지 않는다. fixture helper가 연결 후 실제 DB 이름,
사용자·DB 소유자·전용 marker·PG major15·비superuser/CREATEDB와 제한된 역할 권한을 검사한다.
검증된 대상에서만 UUID 이름의 새 DB를 만들며 원본 control DB에는 앱 schema를 설치하지 않는다.
오류 로그에는 실제 비밀값을 넣지 않는다. 파일에 있는 암호는 이 로컬 환경만의 공개 합성 값이다.

일반 DATABASE_URL·DATABASE_URL_FILE은 읽지 않는다. 테스트 URL은 loopback IP·전용 DB/역할/
합성 암호·명시적 포트만 허용하며 query·fragment·libpq 환경의 우회는 거부한다.
테스트 전용 sslmode=disable을 외부 DB나 운영 TLS 설정으로 복사하지 않는다.

## 격리와 경로

각 사례는 별도의 빈 UUID DB에서 시작한다. 과거 RunPython0014는 DB alias를 지정하지 않아
테스트 동안 `default` 연결 자체를 그 UUID DB로 교체하고 종료 시 복원한다.
이는 과거 migration의 내용을 패치하거나 건너뛰는 방식이 아니다. helper는 순차 실행용이며
다른 스레드의 DB 작업과 같은 프로세스에서 겹쳐 실행하지 않는다.

테스트는 Django TestCase의 자동 최신 DB 설치를 사용하지 않는 unittest 사례다.
원본 MigrationExecutor와 historical model state로 아래 경로를 실제 실행한다.
`--keepdb`, fake, MIGRATION_MODULES 비활성화는 사용하지 않는다. 테스트를 통과시키려고
migration을 바꾸지 않으며,0020 수정은 D-P07의 별도 사용자 승인으로만 이뤄졌다.

| 사례 | 기대하는 결과 | 보존 확인 |
| --- | --- | --- |
| 빈 DB→0020 | 성공·sequence(1,false)·첫 nextval1 | 주문0행 |
| 빈 DB→수정 전0020 SQL | SQLSTATE22003, setval(0) 실패 |0019까지 적용·새 sequence DDL rollback |
|0019 번호NULL 주문→0020 | 성공·첫 nextval1 | NULL 번호와 모든 합성 행 보존 |
|0019 번호0 주문→0020 | 성공·첫 nextval1 | 기존0을 덮어쓰지 않음 |
|0019 번호40→0020 | 성공·다음값41 | 기존 행 보존 |
| 이미0020인 위 DB 재적용 | migration plan 비어 있음 | 이력·행·sequence값 무변경 |
| 수정 전0020으로 적용된 DB | migration plan 비어 있음 | sequence100→다음값101 유지 |
| 이력 없는 동명 sequence100 | SQLSTATE42P07로 중단 | 이력0019·행·sequence(100,false) 보존 |
| sequence 초기화 직후 실패 주입 | 예외 전파 | 새 sequence·0020 이력 없음, 재시도 성공 |
|0018 B1 포장/table NULL→0019 | SQLSTATE23514, orders_table_rule | 행·이력·제약 원복 |
|0018 과거 F1/BOOTH→0019 | 각각 SQLSTATE23514 | 역사적 값·행·이력·제약 원복 |
|0019 table 있는 포장→0018 | SQLSTATE23514 | 역이행 실패 후 행·이력·제약 보존 |

양수 번호 seed는 별도 사례이며 빈 DB 성공을 위장하지 않는다. choices 변경은 과거 값을
DB에서 자동 삭제하지 않는다는 점을 합성 데이터로 확인한다. 실제 운영에 F1/BOOTH 행이 있는지는 미확인이다.
전체 application/auth/admin migration의 운영 설치 성공을 주장하지 않는다. 이 suite는 orders의 의존 체인을 검증한다.

## 로컬 회귀와 정리

```bash
.venv/bin/python manage.py test orders.tests --settings=bazaar_kiosk.settings_test --verbosity 2
.venv/bin/python manage.py makemigrations --check --dry-run --settings=bazaar_kiosk.settings_test
```

SQLite 프로필에서는 PG12개가 명시적으로 skip된다. 기존9개와 대상/정리 guard3개를 실행하며,
PG 인수에는 앞의 명시적 PG 명령에서 migration12개·앱12개가 skip0으로 실행된 결과가 별도로 있어야 한다.
0020 적용 이후 runner의 빈 PG 테스트 DB 생성이 성공하므로 앱 테스트를 PG에서 실행할 수 있다.
다만 `test orders.tests`를 PG 프로필로 한 번에 실행하면 runner가 `default`를 자기 테스트 DB로
바꾸므로 migration fixture guard가 의도대로 거부한다. 그래서 두 명령을 나눠 실행한다.
이는0020 실패가 아니며, 어떤 실패도 fake migration이나 runner 우회로 숨기지 않는다.

helper는 자신이 CREATE한 UUID DB만 DROP한다. 소유자 변경이나 외부 연결로 cleanup이 실패하면
강제 세션 종료·FORCE DROP을 하지 않고 오류를 보고한다. 프로세스 강제 종료 시 남는 전용 DB는
이 작업이 만든 Compose 프로젝트/볼륨을 확인한 뒤 아래 정리로 제거한다.

```bash
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml ps
docker volume inspect "${BK_TEST_PROJECT}_pg_test_data" --format '{{json .Labels}}'
docker compose -p "$BK_TEST_PROJECT" -f compose.test.yaml down --volumes
unset BK_TEST_DATABASE_URL BK_TEST_PG_PORT BK_TEST_PROJECT
```

볼륨의 프로젝트 label과 `org.bazaar-kiosk.purpose=phase-1a-local-test`가 이번 작업과 일치해야 한다.
다른 개발/운영 프로젝트나 공유 볼륨에 위 정리 명령을 적용하지 않는다.
테스트 대상 볼륨·컨테이너를 없애는 것이 이 단계의 롤백이며 앱 데이터 migration은 없다.

## 남은 결정

[이력 인벤토리](MIGRATION_INVENTORY.md)는 저장소 파일 해시와 적용 경로다.
운영의 실제 적용 기록, DB 버전, 실제 sequence 값·소유권, 과거 포장/F1/BOOTH 행 분포,
원본·백업 호환성은 아직 확인하지 않았다.
0020은 D-P07 승인으로 수정했고,0019 수정은 여전히 승인 대상이 아니다.
임의 테이블 배정·데이터 삭제로 제약 실패를 없애지 않는다.
