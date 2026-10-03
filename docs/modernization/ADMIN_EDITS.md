# 관리자 주문 편집 (7B)

상태: 로컬 구현과 검증. 결정은 [D-052](DECISIONS.md)(D-011 확정, 권장과 다른 선택). 위험: BK-R008.

## 고친 것

| 이전 | 지금 |
| --- | --- |
| 관리자에서 수량을 바꾸면 저장 합계는 그대로(5000 vs 품목 합계 15000) | 저장 시 `order_edits.apply_line_changes`가 합계·거스름돈을 다시 계산 |
| 단가·합계·번호·수납 금액을 관리자 폼으로 덮어쓸 수 있음 | 전부 읽기 전용. POST에 실어 보내도 무시 |
| 상태를 아무 값으로나 저장(취소 → 준비중 되살림) | 주방과 같은 전이표(D-050), 행 잠금, `STATUS` 이력 |
| 품목 편집이 이력에 남지 않음 | `OrderEvent.kind = ITEMS`(0027, choices만 변경) |
| 관리자에서 주문 생성 가능(번호·결제 없이) | 생성 불가(`has_add_permission = False`) |
| 조리 이력이 있는 품목 삭제 → PROTECT 500 | 폼 오류 문장으로 거부 |

## 규칙 (orders/services/order_edits.py, orders/admin.py)

- `check_lines(order, lines)`: 취소된 주문이면 거부. 삭제하려는 품목에 조리 이력(`OrderEvent.item`)이 있으면 거부.
  수량이 이미 조리한 수량보다 적으면 거부. 품목이 하나도 남지 않으면 거부. 남은 품목의 합계를 수납액과
  정산(7A `payments.settle`)해 부족하면 거부(D-048). 이 검사는 관리자 인라인 formset의 `clean()`에서 먼저 돌아
  오류가 문장으로 보인다.
- `apply_line_changes(order, actor)`: 잠긴 주문 행에서 품목을 다시 읽어 합계·거스름돈을 저장하고 `ITEMS` 이력을 남긴 뒤,
  조리 진행 기준으로 상태를 다시 맞춘다(6B `sync_from_items`, 바뀌면 `STATUS` 이력).
- 새 품목의 단가는 저장 시점의 메뉴 가격이다. 폼의 `unit_price`는 받지 않는다.
- 잠금: 변경 폼 POST는 `get_queryset`에서 주문 행을 `select_for_update`로 읽는다(Django 변경 뷰는 한 트랜잭션).
  검증과 저장이 같은 주문을 보고, 주방(주문을 먼저 잠금)은 차례를 기다린다. 없으면 검증과 저장 사이에 취소·조리가
  끼어들어 500이 났다(PR #70 리뷰 HIGH).
- 상태: 폼 `clean_status`가 전이표로 먼저 거르고, `save_model`이 잠긴 행에서 `status.change`를 지난다.
- 행위자: Django 관리자 사용자는 `Account`가 아니므로 `OrderEvent.actor`는 NULL이다(에이전트 판단).
  누가 했는지는 Django 자체 `django_admin_log`(LogEntry)가 관리자 사용자와 변경 요약을 남기므로 시간·주문 id로 대조한다.
- 관리자도 화면과 같은 경계를 지킨다: 수량 1~99(`payments.MAX_QTY`), 새 품목은 판매 중(`is_active`)이고 주방 메뉴
  (`visible_kitchen`)여야 한다(PR #70 보안 리뷰).

## 검증

```sh
.venv/bin/python scripts/test_postgres.py   # 전용 PG fixture
```

`orders/tests/test_admin_integrity.py`(실제 admin form POST): 수량 변경 → 합계·거스름돈·이력, 추가 → 현재 메뉴 가격
스냅샷, 삭제 → 재계산과 조리 이력 보호, 조리 수량 미만 거부, 수납 부족 거부(아무것도 저장 안 함), 스냅샷·번호·
수납 덮어쓰기 무시, 메모만 저장 시 이력 없음, 상태 전이표(취소 최종), READY에 품목 추가 → PREPARING, 취소 주문 품목
편집 거부, 관리자 주문 생성 403, 권한 없는 staff 403, 익명 → 로그인.

## PR #70 리뷰 결과 (2026-09-20)

코드·보안 리뷰 에이전트 2개. HIGH 1건(검증과 저장 사이 경합 → 500)은 POST 첫 읽기부터 행 잠금으로 닫았다.
MEDIUM 3건: 읽기 전용 집합이 `fields − readonly_fields`에 의존 → 두 튜플의 차가 `{status, note}`임을 고정하는 회귀 추가;
관리자에서 비활성·비주방 메뉴 추가 가능 → 거부; 수량 상한 99 미적용 → 거부. LOW: `ITEMS` 이력의 상태를 편집 후 값으로,
수량 0 거부, LogEntry 참고 경로 문서화.

## 남은 것

- 관리자 사용자를 `Account`와 잇는 것(행위자 기록). 관리자 계정 체계는 별도 결정.
- 브라우저에서 실제 admin 폼 제출(자동완성 위젯 포함)은 돌리지 않았다.
