# 8A — 통계 API 실행성 복구

2026-09-09 · [이슈41](https://github.com/rlagycks/bazaar_kiosk/issues/41) ·
기준 develop `f9b562c349a2a6318bcfa0b68fa45af800d3926e` (PR40 머지).
코드 수정·로컬 검증은 완료했고 BLUEPRINT의2B 이후 PG 최종 인수는 대기 중이다.

## 원인과 수정

[stats_dashboard](../../orders/views/api.py)의 `qty=Sum("qty")`가 뒤따르는 금액 식의
`F("qty")`를 집계 별칭으로 해석하게 만들어 FieldError를 발생시켰다. 빈 DB에서도500이었다.
내부 이름을 `qty_sum`으로 바꾸고 정렬·JSON 매핑을 같은 이름으로 맞췄다. 외부 JSON은
`name`, `qty`, `amount` 그대로다. SQL 집계 별칭 외 앱 변경은 없다.

[회귀 테스트](../../orders/tests/test_dashboard_execution.py)는 다음4개다.

- 빈 DB의200·0 합계·빈 그룹.
- 한 품목의 수량×주문 당시 단가. 현재 메뉴 가격은 집계에 섞이지 않음.
- 여러 주문/단가의 행별 곱셈 합산, 수량·금액·시간대 그룹과 응답 키 유지.
- 현행 취소/기간 제외 조건이 요약·품목·결제·시간대 집계에 유지됨.

수정 전에4개 모두 같은 FieldError로 실패했고 수정 후 SQLite/PG에서 통과했다.
이는 기존 표현식 산술의 회귀이며 기본 기간2025-10-18, 동명 메뉴 병합, 레거시 NULL 금액,
거스름돈·순매출·취소 환불의 목표 정책을 승인하는 테스트가 아니다. 해당 결정과 위험은 남아 있다.
테스트는 기존 B1_COUNTER 세션을 사용하며 익명 API 접근을 정상 계약으로 고정하지 않는다.

## 실행과 결과

```bash
.venv/bin/python manage.py check --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py makemigrations --check --dry-run --settings=bazaar_kiosk.settings_test
.venv/bin/python manage.py test orders.tests --settings=bazaar_kiosk.settings_test --verbosity 2
```

check 문제0·drift 없음. SQLite31개 수집,16개 통과, migration15개 skip.
[PG 안내](POSTGRES_TESTING.md)의 준비·identity 검사 뒤 아래 앱 명령을 실행하고 소유 자원을 정리한다.

```bash
.venv/bin/python manage.py test orders.tests.test_dashboard_execution orders.tests.test_baseline orders.tests.test_pg_guard orders.tests.test_settings_isolation --settings=bazaar_kiosk.settings_test_pg --verbosity 2
```

PostgreSQL15.18에서16개 통과·skip0. 동일 세션의 PR40 검증에서 migration15개를 별도 실행해
통과했으며 이후 migration은 변경하지 않아 반복하지 않았다. Django5.2.17/Python3.12.11 환경이다.
현재 CI는 check/drift만 실행한다. 2B의 재현 가능한 환경·PG CI 연결 이후 이 검사를 재실행하고
8A 최종 인수를 판정한다. 지금 PG 성공을2B 완료나8A 관문 면제로 해석하지 않는다.

## 범위와 복구

앱 변경은 집계3줄이다. schema·migration·UI·권한·기본 기간·결제 계약을 변경하지 않았다.
BK-R016은 Repo-fixed/Open(2B 이후 인수 대기)이며 BK-R006/007/030/034는 미해결이다.
기존 통계 페이지는 backend200을 받게 되지만 실제 PC 브라우저 인수·운영 데이터/성능 검증은 하지 않았다.
문제가 발생하면 새 실패 사례를 확보해 별칭 충돌 없이 정방향으로 수정한다. 실패하던 코드를 되돌려
500을 복구하는 것을 정상 롤백으로 보지 않는다. 운영 배포·통계 조회 불가 UI 변경은 이번 범위 밖이다.
