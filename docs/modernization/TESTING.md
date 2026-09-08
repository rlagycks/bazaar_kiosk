# 2A — 격리된 로컬 특성화 테스트

첫 구현 이슈: [#35](https://github.com/rlagycks/bazaar_kiosk/issues/35).
후속1A의 전용 Compose PG 환경과 migration 경로 재현은 [PG 테스트 안내](POSTGRES_TESTING.md)를 따른다.
현재 SQLite 전체 수집은24개 중12개 실행·12개 PG skip이며 PG 인수는 별도 명령으로 확인한다.
이 테스트는 현재 정상 로그인·주문·주방 흐름을 변경 없이 관찰하는 안전망이다.
업무 계약 변경, 보안 수정, PostgreSQL 검증과 배포 검증은 포함하지 않는다.

## 실행

저장소 루트에서 기존 가상환경을 사용한다. 검증 환경은 Python3.12.11/Django5.2.17이다.
requirements의 버전 고정과 CI에서 테스트 실행 강제는2B에서 진행한다.

```bash
.venv/bin/python manage.py check --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py test orders.tests.test_baseline --settings=bazaar_kiosk.settings_test --verbosity 2
.venv/bin/python manage.py test orders.tests --settings=bazaar_kiosk.settings_test --verbosity 2
```

마지막 명령은 환경 격리 검사까지 수집한다. 수집된 테스트가0개면 이 단계의 성공이 아니다.
새 환경에서는 Python3.12 가상환경과 requirements 설치가 먼저 필요하며, 설치 버전을 결과에 기록한다.
운영 환경용 명령이나 기본 settings로 바꾸어 실행하지 않는다.

## 격리와 유지하는 구성

[settings_test.py](../../bazaar_kiosk/settings_test.py)는 배포 환경 값을 비운 상태에서
기본 설정을 가져온 뒤 DB·비밀값·외부 설정을 덮어쓴다. 호출자의 환경 변수는 복원한다.
DB NAME과 TEST NAME 모두 메모리 SQLite다. 기존 db.sqlite3와 운영 DB를 읽거나 쓰지 않는다.
캐시·파일·메일 저장소는 프로세스 메모리를 사용하며 Supabase URL/키는 비워 둔다.
역할 PIN과 SECRET_KEY는 공개 가능한 합성 테스트 값이다. 이 설정으로 서버를 배포하지 않는다.

실제 앱·middleware·URL·template·migration 체인은 유지한다. 정적 파일 URL 렌더를 위해
manifest 저장소만 일반 staticfiles 저장소로 바꾸며 collectstatic 배포 검증을 대신하지 않는다.
fixture는 테스트 안에서 합성 메뉴/테이블을 만들고 캐시와 테이블 LRU를 전후 정리한다.

[환경 격리 테스트](../../orders/tests/test_settings_isolation.py)는 새 Python 프로세스에
잘못된 DB URL과 합성 배포 자격증명을 주입한다. 네트워크 접속과 파일 DB 연결을 거부한 상태로
설정 로딩·Django check·실제 메모리 SQL을 실행해 격리 여부를 확인한다.

## 보존하는 정상 경로

- 역할5개의 로그인 리다이렉트·현재 페이지와 주방 범위, 잘못된 PIN의 세션 미생성,
  익명 사용자의 화면 접근 시 로그인 이동.
- 로그인한 주문 담당의 홀/포장 생성과 상세·목록 조회, 합성 메뉴에 기반한 서버 합계.
- 현금·티켓·혼합 결제를 주문 합계에 정확히 맞춰 지급한 정상 사례의 저장·응답 분할 금액.
- 클라이언트가 낮은 가격을 보내도 서버 단가 사용, 메뉴 가격 변경 뒤 기존 주문 단가 유지.
- 실제 주문·항목·번호 할당 쓰기 뒤 실패하면 전체 주문 작업 롤백과 다음 요청 정상 처리.
  이 검사는 TransactionTestCase로 실행해 TestCase의 바깥 transaction이 결함을 숨기지 않게 한다.
- 주방 담당의 부분 준비→품목 완료→전체 완료, 남은 수량·요약·상태 일치.

번호가 날짜별로 초기화되어야 한다거나 PostgreSQL sequence가 롤백된다는 계약은 단정하지 않는다.
휴대폰/PC HTML 경로를 렌더하지만 JS 실행·터치·레이아웃·실제 브라우저 인수 증거는 아니다.

## 알려진 결함은 정상 계약과 분리

익명 API 변경(BK-R001), 부족 결제(BK-R014/030), 중복 생성(BK-R012), 통계500(BK-R016),
캐시·조회 누락 등은 [분석 재현 기록](ANALYSIS_REPORT.md)과 [위험 등록부](RISK_REGISTER.md)를 따른다.
이 동작을 정상으로 주장하는 통과 테스트나 광범위한 expectedFailure로 안전망에 넣지 않는다.
해당 수정 단계에서 위험 ID에 연결된 실패 회귀 테스트를 먼저 추가한다.
잘못된 PIN은 오류 context가 있어도 현재 템플릿에 안내가 표시되지 않는 것으로 확인했다.
이 단계에서는 로그인 실패 시 인증이 성립하지 않는 경로만 검증하고 화면 오류 안내는 후속11에 인계한다.

## 의도적 회귀 감지와 한계

가격 단가를1로 만드는 변이와 주문 생성의 바깥 atomic을 제거하는 변이를 별도 임시 복사본에
각각 적용해 관련 테스트가 실패하는지 확인한다. 원본 앱 파일은 변경하지 않는다.
실제 실행 결과와 임시 산출물 위치는 [WORKLOG](WORKLOG.md)의2A 기록을 따른다.

SQLite migration 통과는 PostgreSQL 신규/기존 설치, 잠금, sequence, 동시성 증거가 아니다.
1A에서 PG 실패 fixture,1B에서 승인된 복구,2B에서 PG CI를 이어간다.
2A만으로 BK-R004를 닫지 않으며 운영 테스트나 실제 데이터 이전은 실행하지 않는다.
롤백은 테스트/테스트 설정을 제거하는 것으로 충분하며 앱 스키마·데이터 변화는 없다.
