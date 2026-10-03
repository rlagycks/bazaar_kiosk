# 매출 보고: 기간과 금액의 의미 (8C)

상태: 로컬 구현과 검증. 결정은 [D-053](DECISIONS.md)(D-013 확정). 위험: BK-R006(해결), BK-R026·BK-R034(부분).
레거시 수납 필드 정합(D-012)은 열려 있고 7C가 맡는다.

## 고친 것

| 이전 | 지금 |
| --- | --- |
| 무엇을 물어도 기간이 `2025-10-18`로 고정(BK-R006) | 기본은 **가장 최근 행사일**(미래 제외), 등록된 행사일이 없으면 **오늘**. `start_date`/`end_date`로 지정 가능 |
| 잘못된 날짜를 조용히 무시 | 형식 오류·역전 범위는 400과 문장 |
| 메뉴를 **이름**으로 묶어 동명이 메뉴가 한 줄(BK-R034) | 메뉴 **ID**로 묶는다. 표시 이름은 현재 이름(이름 스냅샷은 D-008 미결) |
| 취소 주문이 집계에서 빠지는지 화면에 드러나지 않음 | 빠지고, **취소 n건 제외**로 표시 |
| 현금은 받은 금액만 보여 거스름돈이 반영되지 않음 | 받은 현금·식권에 더해 **거스름돈**과 **순현금(현금 − 거스름돈)** |
| 시간별 집계가 UTC 기준으로 잘림 | `Asia/Seoul` 기준으로 자른다 |
| 화면에서 기간을 고를 수 없음 | 카운터 화면에 시작·끝 입력과 “기본 기간” 단추 |

## 규칙 (orders/services/reporting.py)

- `resolve_period(params, today=)`: `start_date`/`end_date` 중 하나라도 있으면 **명시 기간**(한쪽만 주면 그 하루,
  양 끝 포함). 없으면 오늘 이하의 가장 최근 `EventDay`, 그것도 없으면 오늘. 형식은 `YYYY-MM-DD`만.
- 날짜 기준은 주문의 `order_date`다. 번호를 매길 때 `Asia/Seoul`로 정한 날짜이므로(D-047) 00:10에 받은 주문은
  그 태그의 날짜에 속한다. `created_at`은 시간별 표에만 쓰고 역시 서울 기준으로 자른다.
- 매출 대상은 **행사 계열**의 `PREPARING`·`READY` 주문이다. 연습 주문과 취소 주문은 매출이 아니다(D-047/D-048).
  취소 건수는 `summary.cancelled_orders`로 따로 보여 준다.
- 금액: `cash`·`ticket`은 받은 금액, `change`는 돌려준 금액(7A 이후 저장, 이전 행은 같은 식으로 유도),
  `net_cash = cash − change`가 금고에 남는 현금이다.
- 분할 필드가 없는 옛 행은 주문 상세와 **같은 방식**으로 읽는다(현금 결제면 현금, 식권 결제면 식권). 고쳐 쓰지 않고
  `summary.legacy_unsplit_orders`로 몇 건을 해석했는지 알린다.
- 그중 **혼합 결제**는 한 값을 현금과 식권으로 나눌 수 없어 어느 쪽에도 더하지 않는다. 대신 `unattributed_orders`와
  `unattributed_amount`로 건수와 금액을 드러내 `cash + ticket`이 매출보다 적은 이유를 말한다(PR #71 DB 리뷰).
- 단가가 없는 옛 품목 줄은 수량에만 들어가고 금액에는 0으로 들어간다.
- 메뉴 줄은 `menu_item_id`로 묶고 판매 시점 단가로 금액을 낸다. 응답에 `menu_item_id`를 포함한다.

## 응답 (`GET /orders/api/stats/dashboard/`)

```
period  : start_date, end_date, floor, basis("event_day"|"today"|"explicit"), label(행사일 메모)
summary : orders, items, revenue, cancelled_orders, legacy_unsplit_orders,
          unattributed_orders, unattributed_amount
payment : cash, ticket, change, net_cash, cash_ratio, ticket_ratio
menu    : [{menu_item_id, name, qty, amount}]
hourly  : [{date("YYYY-MM-DD", 서울), hour("HH:MM", 서울), orders, revenue}]
```

## 검증

```sh
.venv/bin/python scripts/test_postgres.py   # 전용 PG fixture
```

- `orders/tests/test_reporting_dates.py`: 기본 기간(최근 행사일·미래 제외·오늘), 명시 단일일·범위·양 끝 포함,
  잘못된 형식·역전 범위 400, 서울 기준 오늘, 자정 전후 주문일 귀속과 시간 표시, 연습 주문 제외.
- `orders/tests/test_reporting.py`: 합계 산술, 취소 제외와 별도 집계, 메뉴 ID 그룹(동명이 메뉴 2줄), 이름 변경 후
  표시, 옛 수납 기록 해석과 건수, 빈 기간 0, floor 검증, 통계 권한 외 403.

## PR #71 리뷰 결과 (2026-09-20)

코드·DB 리뷰 에이전트 2개. CRITICAL/HIGH 없음.

- 코드 MEDIUM 1건: 고정 날짜 시절의 죽은 헬퍼(`_parse_date`·`_date_limits`)가 제거된 import를 참조 → 삭제.
  LOW 3건(기간 파서 흐름, `today` 인자 가림, 중복 시간대 변환) 반영.
- DB MEDIUM 4건: 취소 집계와 매출 집계를 한 번의 스캔으로, 품목 수는 메뉴 집계에서 계산해 **쿼리 5개 → 3개**.
  옛 혼합 결제의 구분 불가 금액을 드러내고, NULL 단가를 명시적으로 0으로 처리.
- DB 측정(20만~30만 행 합성): 기간 필터는 기존 `order_date` 인덱스를 탄다. `(number_series, order_date, status)`
  복합 인덱스를 만들어 비교했으나 플래너가 선택하지 않아 **추가하지 않았다**. 시간별 집계는
  `DATE_TRUNC(... AT TIME ZONE ...)`이라 `created_at` 인덱스를 못 쓰지만 기간으로 이미 좁혀져 수십 ms다.
  `order_date`가 NULL인 행이 매출에서 빠지는 것은 `orders_number_needs_date` 제약이 보장하는 안전한 동작이다.

## 남은 것

- 메뉴 **이름 스냅샷**(D-008). 지금은 과거 주문도 현재 이름으로 보인다. 금액과 줄 구분은 영향받지 않는다.
- 옛 수납 기록의 실제 정합(D-012)은 7C. 보고는 해석만 하고 원본을 바꾸지 않는다.
- 환불 기록(D-048 미결). 취소는 매출에서 빠지지만 돌려준 현금 기록은 없다.

UI-05C/D-064에서 `hourly.date`를 추가했다. 기존 날짜별 시간대 그룹과 합계는 유지한다.
[새 화면·조회 실패 복구 계약](UI_STATS.md)을 따른다.
