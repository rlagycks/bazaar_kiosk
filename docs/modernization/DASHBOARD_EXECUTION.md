# 8A — 통계 API 실행성 복구

현재 실행 안내(2026-09-09, D-029): [PostgreSQL 전용 전환](POSTGRES_ONLY.md)과
[공통 검증 명령](POSTGRES_TESTING.md)을 따른다. 아래 SQLite 관찰·이전 수치·명령은 당시 증거다.
PR40·PR42는 머지됐고8A는2B 이후 최종 인수 대기다. 현재44개(15+29)를 PG에서 검증한다.

2026-09-09 · [이슈41](https://github.com/rlagycks/bazaar_kiosk/issues/41) ·
[PR42](https://github.com/rlagycks/bazaar_kiosk/pull/42), 브랜치 `phase-8a-dashboard-execution`.
기준 develop `f9b562c349a2a6318bcfa0b68fa45af800d3926e` (PR40 머지), 리뷰 기준 head `8531e18`.
코드 수정·로컬 검증은 완료했고 BLUEPRINT의2B 이후 PG 최종 인수는 대기 중이다.

## 원인과 수정

[stats_dashboard](../../orders/views/api.py)의 `.values("menu_item__name")` 뒤에서
`qty=Sum("qty")`가 먼저 annotation으로 등록된다. 뒤따르는 금액 식의 `F("qty")`는
모델 컬럼 대신 이 annotation으로 해석돼 중첩 집계로 거부된다. SQL 실행 전 `.annotate()`
호출에서 FieldError가 발생하므로 빈 DB에서도500이었다. 단순 모델 필드 충돌 ValueError와 구분한다.

내부 이름을 `qty_sum`으로 바꾸고 정렬·JSON 매핑을 같은 이름으로 맞췄다. 외부 JSON은
`name`, `qty`, `amount` 그대로다. 인수 순서만 뒤집는 방법은 별칭 모호성을 남긴다.
정렬에 `-qty`를 남기면 모델 컬럼이 GROUP BY에 들어가 같은 메뉴가 행별 수량에 따라 분리된다.
여러 주문의 같은 메뉴를 다른 수량으로 만드는 테스트는 이 실제 응답 오류를 검출하기 위해 유지한다.

## 회귀 범위와 리뷰 반영

[회귀 테스트](../../orders/tests/test_dashboard_execution.py)는7개다.

- 빈 DB의200·0 합계·빈 그룹.
- 한 품목의 수량×주문 당시 단가. 현재 메뉴 가격은 집계에 섞이지 않음.
- 여러 주문/단가의 행별 곱셈 합산, 수량·금액·시간대 그룹과 응답 키 유지.
- 현행 취소/기간 제외 조건이 요약·품목·결제·시간대 집계에 유지됨.
- 삽입순·이름 오름/내림차순과 구별되는 수량 내림차순, 동률의 이름 오름차순.
- 지원하지 않는 F1·BOOTH·unknown 입력은400.
- 전 단가 NULL인 그룹은 수량을 세고 금액0, 혼합 그룹은 알려진 단가의 금액만 합산.

`qty`는 NOT NULL이어서 존재하는 그룹의 합은 NULL이 아니지만 `unit_price`는 nullable이므로
금액의 `or 0`은 필요하다. NULL fixture는 저장 당시 가격 보완 로직을 거치지 않도록 UPDATE로 만든다.
이는 기존 NULL 응답을 관찰하는 테스트이며 누락 금액을0으로 정산하겠다는 목표 정책 승인이 아니다.
기본 기간2025-10-18 단언도 임시 특성화이며8C의 승인된 기간 정책에 맞춰 교체한다.
fixture의 created_at은 요청한 order_date의 서울12:30으로 맞춘다.
B1_COUNTER 세션은 현행 역할을 사용하는 준비일 뿐이며 현재 API가 세션을 검사한다는 증거가 아니다.

0019의 DB 제약은 유효한 층을 B1로 제한한다. 층 필터 제거를 검출하려고 제약을 우회한
가짜 활성 층 데이터를 만들지 않는다. 여러 시간대·기간 라벨, 순매출/혼합 결제의 보고 계약,
동명 메뉴 정책(D-012/013·BK-R034)은 후속 범위다. 전체 변이 검출 비율을 품질 점수로 쓰지 않는다.
정렬 검사는 이 PG fixture의 응답을 보장하며 모든 collation이나 쿼리 실행 계획을 검증하지 않는다.

## 실행과 결과

현재 전체 검증은 [PG 안내](POSTGRES_TESTING.md)의 새 전용 Compose 생성·URL 설정 뒤 실행한다.

```bash
.venv/bin/python scripts/test_postgres.py
```

PR42 리뷰 보완은 새 Compose `bk-pr42-review-20260909`에서 migration15개·앱19개(통계7개 포함),
skip0이었다. 정렬 fixture 확장 후 집중7개도 통과했다. PR42 수정 head `2acfd4a`의 CI를 확인하고
2026-09-09 develop에 squash merge했다(`c8c11b5`). 그 CI는 당시 check/drift만 수행했다.

PR44는 PostgreSQL 전용 설정과 위 회귀를 통합해 전체40개(migration15개·앱25개), skip0을 검증한다.
Docker PostgreSQL15.18/Django5.2.17/Python3.12.11이며 CI도 같은 전체 실행기를 사용한다.
실제 실행 결과와 정리 기록은 [작업 로그](WORKLOG.md)에 기록한다.

최초 실패 회귀는 수정 전 SQLite에서4개 모두 FieldError였고, 최초 수정 후 SQLite/PG에서4개가 통과했다.
이는 과거 증거다. 현재 SQLite 런타임·테스트 설정은 제거됐고 PG로만 실행한다.
PR42 브랜치의 push 필터 누락은 PR44에서 `phase-*` 추가로 보완됐다.
전체2B 종료 전까지8A 최종 인수 관문은 유지한다.

## 범위와 복구

앱 변경은 집계3줄이다. 이번 리뷰 보완은 테스트·문서만 변경한다.
schema·migration·UI·권한·기본 기간·결제 계약을 변경하지 않았다.
BK-R016은 Repo-fixed/Open(2B 이후 인수 대기)이며 BK-R006/007/030/034는 미해결이다.
같은 함수의 naive 시간 분기에 있는 `timezone.utc`는 설치 Django5.2.17에 없어 도달 시 오류가 난다.
현재 USE_TZ=True의 TruncHour 결과는 aware다. 시간 처리 개선 시 naive 경로와 다중 버킷을 함께 검증한다.
기존 통계 페이지는 backend200을 받게 되지만 실제 PC 브라우저 인수·운영 데이터/성능 검증은 하지 않았다.
문제가 발생하면 새 실패 사례를 확보해 별칭 충돌 없이 정방향으로 수정한다. 실패하던 코드를 되돌려
500을 복구하는 것을 정상 롤백으로 보지 않는다. 운영 배포·통계 조회 불가 UI 변경은 이번 범위 밖이다.
