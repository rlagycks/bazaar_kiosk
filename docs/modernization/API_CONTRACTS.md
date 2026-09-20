# API 경계와 입력 계약 (9)

상태: 로컬 구현과 검증. 결정 관문은 [D-008](DECISIONS.md) 호환성. 위험: BK-R015, BK-R024.
**스키마 변경과 마이그레이션이 없다. 기존 URL·역할·응답을 바꾸지 않았다.**

## 두 가지 문제

### 1. 잘못된 입력이 500으로 나왔다 (BK-R015)

쓰기 엔드포인트 셋이 모두 한 헬퍼로 본문을 읽고 그 결과를 매핑처럼 다뤘다. `[]`, `"text"`, `5`,
`null`은 전부 유효한 JSON이고 매핑이 아니므로, 다음 `.get`에서 `AttributeError`가 나고 Django가
500을 냈다. 한 단계 아래에서도 같은 일이 일어났다. 문자열이어야 할 `floor`가 숫자로 오면
`.upper()`에서 요청이 끝났다.

**500은 서버가 자기가 망가졌다고 말하는 것이다.** 잘못된 입력은 호출자의 것이고 문장과 4xx로
답해야 한다.

구현 전 측정: 적대적 본문·필드 타입 조합에서 **500이 36건**. 구현 후 **0건**.

### 2. 한 뷰 파일에 전송·조회·금액·명령이 몰려 있었다 (BK-R024)

`orders/views/api.py`가 573줄이고 그중 `orders_collection` 하나가 228줄이었다. 주방 보드가
무엇을 묻는지 알려면 HTTP 분기 사이를 읽어야 했다.

## 무엇을 옮겼나

**동작을 바꾸지 않고** 경계만 꺼냈다.

| 모듈 | 책임 |
| --- | --- |
| [`views/validators.py`](../../orders/views/validators.py) | 본문이 무엇일 수 있는지. 위반은 `InvalidInput`과 문장 |
| [`views/serializers.py`](../../orders/views/serializers.py) | 주문을 API가 돌려주는 모양으로. 응답 계약이 사는 곳 |
| [`views/selectors.py`](../../orders/views/selectors.py) | API가 수행하는 읽기. 범위 좁히기(D-051)가 필터·자르기보다 먼저 |
| `views/api.py` | 남은 것: HTTP 번역과 명령 순서 |

`api.py`는 573줄에서 515줄로 줄었다. 큰 감소가 아니다. **이 단계는 성능 개선도 대폭 정리도
아니다.** 후속 카드가 손댈 자리를 드러내는 것이 목적이다.

## 입력 계약

| 입력 | 규칙 | 위반 시 |
| --- | --- | --- |
| 본문 | UTF-8, JSON, **객체**. 빈 본문은 `{}` | 400 + 문장 |
| 문자열 필드 | 문자열만. 없거나 `""`이면 기본값 | 400 + 어느 필드인지 |
| `floor`/`order_type` | 대문자로 비교. **공백을 다듬지 않는다** | 400 |
| `note`/`table_number` | 공백을 다듬는다(기존 동작) | 400 |
| `items` | 비어 있지 않은 객체 배열 | 400 |
| 금액·수량 | [payments](PAYMENTS.md)가 검사(7A) | 400 |
| `request_id` | [idempotency](IDEMPOTENCY.md)가 검사(6A) | 400 |

`floor`와 `order_type`에서 공백을 다듬지 않는 것은 의도적이다. 기존 뷰가 다듬지 않았고,
받아들이는 범위를 넓히는 것도 동작 변경이다.

`is_takeout`은 예전대로 `bool()`로 강제한다. 이 경로는 500을 내지 않았으므로 건드리지 않았다.
받는 값을 좁히는 것 역시 동작 변경이다.

## 쿼리 기준선 (인계)

카드가 요구하는 "설명 없는 SQL 증가 없음"을 테스트로 고정했다. 목표치가 아니라 **오늘의
사실**이며, 숫자가 바뀌면 같은 커밋에서 설명해야 한다.

| 경로 | 기준선 |
| --- | --- |
| 주방 보드(`status=PREPARING`) | 6쿼리 이하. 주문 2건과 20건이 **같다**(N+1 없음) |
| 주문 상세 | 8쿼리 이하 |

주방 보드는 8B에서 개수 쿼리를 없앴다. 인증, 슬라이스, 프리페치 둘이다.

## writer 책임표 (10B 인계)

10B는 "모든 writer의 영속 변경 감지"다. 지금 주문 데이터를 쓰는 곳은 다음이 전부다.

| writer | 무엇을 쓰나 | 트랜잭션 |
| --- | --- | --- |
| `views/api.py` 주문 생성 | `Order`, `OrderItem`, `OrderRequest`, `OrderEvent` | 하나의 atomic |
| `views/api.py` 상태 변경 | `Order.status`, `OrderEvent` | 행 잠금 + atomic(6B) |
| `views/api.py` 항목 진행 | `OrderItem.prepared_qty`, `Order.status`, `OrderEvent` | 주문 먼저, 항목 다음(고정 순서) |
| `services/status.py` | 상태 전이 판정과 쓰기 | 호출자의 atomic 안 |
| `services/order_edits.py` | 관리자 품목·합계·상태(7B, D-052) | `select_for_update` |
| `admin.py` | 위 서비스 경유 | 변경 폼 POST에서 행 잠금 |
| `services/numbering.py` | `Order.order_no` 발번 | 생성 트랜잭션 안 |
| `services/totals.py` | 합계 계산 도우미 | 쓰기 없음 |

`authentication.py`와 `login_security.py`도 쓰지만 주문 도메인이 아니다(세션·로그인 실패 기록).

**10B가 답해야 할 것:** 이 여덟 중 어디에 revision을 붙이나. 서비스 통합인가 DB trigger인가.
전역 revision인가 범위별인가. D-019가 pending이다.

## 검증

```sh
.venv/bin/python scripts/test_postgres.py
```

`orders/tests/test_api_contracts.py`: 객체가 아닌 본문 7종 × 엔드포인트 3개, UTF-8 아닌 본문,
JSON 아닌 본문, 빈 본문, 거절이 빈 문장이 아님, 필드 타입 오류 20여 종, 항목 항목의 누락 필드,
적대적 쿼리 파라미터, 그리고 정상 요청이 여전히 201.

전체 401건 통과. `manage.py check` 이상 없음, `makemigrations --check` 변경 없음.

## 남은 것

- `orders_collection`은 아직 한 함수 안에 GET과 POST를 모두 담고 있다. 쪼개는 것은 URL 계약을
  건드리므로 이 카드의 "동작 변경 없음"을 넘는다.
- 명령(생성·상태·진행)의 서비스 추출은 10B가 revision을 붙일 때 같이 보는 편이 낫다.
- API 버전 표기는 아직 없다. 비호환 변경이 필요해지면 그때 계약으로 정한다(D-008).
