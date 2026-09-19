# 개인 계정·권한 4종·행위자 기록 (4A4, D-051)

상태: 로컬 구현과 검증. 운영 배포·실제 행사 비밀번호 공급은 하지 않았다.
[D-051](DECISIONS.md)의 제품 결정을 코드로 옮긴 기록이며, JWT 발급·갱신·회수 구조는
[JWT 인증](JWT_AUTHENTICATION.md)을 그대로 쓴다.

## 무엇이 바뀌었나

| 항목 | 4A2까지 | 4A4 |
| --- | --- | --- |
| 주체 | 역할별 공용 계정 3개(`ROLE_ACCOUNTS` 환경변수) | 개인 계정(`orders_account` 표), 관리자 화면에서 등록 |
| 로그인 | 계정 ID + 계정별 비밀번호 | **이름 + 행사 공용 비밀번호**(`EVENT_PASSWORD_HASH`) |
| 권한 | 역할 문자열 1개 | 권한 집합: 서빙·식당 모니터링·포장 모니터링·누적·통계 |
| 권한 판정 시점 | 토큰의 역할 클레임 + 기기 상태 | 매 요청 계정 행(활성 여부·권한 4개 불리언) |
| 홀/포장 | 화면 필터 | **서버 데이터 경계**(`orders/services/scope.py`) |
| 행위자 | 없음(6A의 요청 ID에 역할만) | `Order.created_by` + `orders_orderevent` 이력 |

## 로그인과 계정

- 관리자가 Django 관리자 화면 **계정**에서 이름과 권한 4개 체크박스, 활성 여부를 등록한다.
  자가 등록은 없다. 계정 삭제는 주문·이력이 걸려 있으면 거부되며 **비활성화**로 대체한다.
- 로그인 화면은 `name`과 `password`를 받는다. 이름은 앞뒤 공백을 제거하고 최대 50자, 대소문자를
  구분한다. 비밀번호는 모두가 같은 행사 비밀번호다.
- 등록되지 않은 이름, 비활성 계정, 권한이 하나도 없는 계정, 틀린 비밀번호는 **같은 문장·같은
  상태(200)**로 거부되고 기기를 발급하지 않는다. 응답으로 등록 여부를 알 수 없다.
  네 경우 모두 D-045의 실패 제한(이름 + 직접 peer IP, 5분 10회 → 5분 잠금)에 센다.
- 성공하면 권한에 따라 착륙 화면으로 보낸다. 서빙 → 주문 화면, 식당+포장 → 주방 전체,
  식당 → 홀, 포장 → 포장, 누적·통계 → 카운터 통계. 우선순위는 `orders/roles.py`의 `landing_urlname`.
- `EVENT_PASSWORD_HASH`가 비어 있으면 503이다. 운영(DEBUG=0)은 시작을 거부한다(D-039).

## 권한 매트릭스 (구현 값)

| 동작 | 서빙 | 식당 모니터링 | 포장 모니터링 | 누적·통계 |
| --- | --- | --- | --- | --- |
| `/orders/order/` | 허용 | 불가 | 불가 | 불가 |
| `/orders/kitchen/hall/` | 불가 | 허용 | 불가 | 불가 |
| `/orders/kitchen/takeout/` | 불가 | 불가 | 허용 | 불가 |
| `/orders/kitchen/` (전체) | 불가 | 둘 다 가진 계정만 | 둘 다 가진 계정만 | 불가 |
| `/orders/b1-counter/` | 불가 | 불가 | 불가 | 허용 |
| `menus`·`tables` | 인증된 전원 | | | |
| `orders-collection` POST | 인증된 전원 (현행 유지, D-051 판단 5) | | | |
| `orders-collection` GET·`order-detail` | 불가 | 식당 분류만 | 포장 분류만 | 전체 |
| `order-status`·`order-item-progress` | 불가 | 식당 분류만 | 포장 분류만 | 불가 |
| `stats-dashboard`·`stats-menu-counts` | 불가 | 불가 | 불가 | 허용 |

분류 규칙: 항목 중 매장(`DINE_IN`)이 하나라도 있으면 **식당**, 전부 포장이면 **포장**. 혼합 주문은
식당이다. 주방 화면이 쓰던 필터와 같은 규칙이며 이제 서버가 `Exists` 서브쿼리로 목록을 거르고,
단건 조회·상태·조리 진행은 주문 행을 잠근 뒤 분류를 읽어 범위 밖이면 403이다.

거부 응답은 4A2와 같다. 미인증 401 + `WWW-Authenticate: Bearer`, 권한 부족·범위 밖 403
`{"detail": "권한이 없습니다."}`. 화면은 로그인으로 redirect. 주방 화면의 전체/홀/포장 링크는
계정이 열 수 있는 것만 렌더링한다.

## 토큰과 기기

- access·refresh 클레임에서 `role`이 빠지고 `sub`가 계정 UUID다. 기기 행은 계정 FK와
  행사 비밀번호 해시의 fingerprint를 가진다.
- 매 요청 기기 행과 계정 행을 함께 읽는다. 계정 비활성화·권한 변경은 **다음 요청부터** 적용된다.
  access 만료를 기다리지 않는다. 행사 비밀번호 교체는 전 기기 로그아웃이다(D-045 확장).
- refresh 응답은 `access_token`, `account_id`, `account_name`, `permissions`, `session_id`,
  `expires_in`이다. 화면은 `data-auth-account`와 `data-auth-session`으로 결속하고, 다른 탭에서
  다른 계정으로 바꾸면 이전 화면은 API 호출을 멈춘다.
- 0025 적용 시 기존 기기 행은 모두 `revoked_at`이 찍힌다. 전원이 다시 로그인한다.

## 행위자 기록

- `Order.created_by`: 주문을 만든 계정(FK, PROTECT). 0025 이전 주문은 null.
- `OrderEvent`(주문 이력, append-only): `CREATED`(생성), `STATUS`(from→to), `PROGRESS`(품목·수량).
  변경과 같은 트랜잭션에서 쓴다. 상태가 실제로 바뀌지 않으면 이력도 없다. 거부된 요청은 이력을
  남기지 않는다. 관리자 화면 **주문 이력**은 읽기 전용이다.
- 6A의 `OrderRequest.role`은 `actor`(계정 UUID 문자열)로 바뀌었다. 같은 요청 ID를 다른 계정이
  보내면 409다.
- 한계: 행사 비밀번호를 아는 사람은 등록된 다른 이름으로 로그인할 수 있다. 이력의 행위자는
  "그 이름으로 로그인한 세션"이지 신원 증명이 아니다(D-051이 명시한 사용자 선택).

## 설정과 마이그레이션

| 설정 | 계약 |
| --- | --- |
| `EVENT_PASSWORD_HASH` | Django PBKDF2 인코딩 해시. 평문·다른 알고리즘·손상된 digest는 시작 거부. `_FILE` 전달 가능 |
| `ROLE_ACCOUNTS` | **제거.** compose secret은 `event_password_hash` |

해시 생성은 [JWT 인증](JWT_AUTHENTICATION.md#설정과-운영-정책)의 절차와 같다(프롬프트 문구만 다르다).

0025 `account_permissions_audit`: `Account`·`OrderEvent` 생성, `Order.created_by`, `AuthDevice.account`
FK 추가, `AuthDevice.role`·`account_id` 제거(제거 전 빈 기본값을 주어 테스트 DB의 역적용이 가능),
`OrderRequest.role`→`actor`. 데이터 변환은 기존 기기 전부 회수뿐이다. 운영에서는 정방향 전용이며
옛 앱을 이 스키마 위에 되돌리지 않는다(4A2와 같은 정책).

## 검증

```sh
# 전용 PG fixture (docs/modernization/POSTGRES_TESTING.md)
.venv/bin/python scripts/test_postgres.py
node --test scripts/test_auth_client.cjs
```

새 회귀: `test_accounts`(로그인·착륙·거부 동일성·비활성화·권한 즉시 반영·비밀번호 교체·삭제 보호·
개인별 제한), `test_scope`(분류·목록 필터·단건 403·상태/진행 403·전체 화면·내비게이션),
`test_audit`(생성자·이력·no-op·거부·비활성 후 보존), `test_permissions`(권한 4종 매트릭스 재작성),
`test_migration_paths`의 0025 사례. 2026-09-20 실행: 마이그레이션 23 + 앱 242 통과, Node 12 통과
([작업 기록](WORKLOG.md)).

## 남은 것

- 주문 생성 POST를 서빙 권한으로 한정할지(D-051 판단 5). 현행은 인증된 전원이다.
- 계정 관리를 Django 관리자 밖의 화면으로 옮길지는 UI 단계의 문제다.
- 10C 권한 snapshot·10D1 SSE 인가는 `Identity.permissions`를 전제로 한다.
