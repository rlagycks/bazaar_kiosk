# JWT 인증 구현과 운영 전환

상태: 구현 설명. 운영 배포 완료를 의미하지 않는다.
D-035의 공용 ID/비밀번호 계정, D-042/043의 토큰 수명·갱신 구조, D-045의 회수·실패 제한·조회 정책을 다룬다.

## 계정과 요청 흐름

계정 역할은 `ORDER`, `B1_COUNTER`, `KITCHEN`이다. 각 역할의 공용 ID와 비밀번호 해시를
환경변수 `ROLE_ACCOUNTS`에 JSON으로 공급한다. 로그인 화면은 역할 선택이나 PIN 대신
`account_id`, `password`를 받는다. 폐기된 주방 역할은 허용하지 않는다.

1. `POST /orders/login/`은 CSRF 검증 후 ID·비밀번호와 실패 횟수를 검사한다.
2. 성공하면 기존 브라우저의 refresh 디바이스를 폐기하고 Django 세션을 비운다.
   새 `AuthDevice`와 refresh 쿠키를 발급하고 역할 화면으로 이동한다.
3. HTML 화면 이동은 refresh 쿠키를 **읽기 전용으로 검증**한다. 토큰 발급이나
   refresh 회전은 일어나지 않는다. 일반 페이지 이동이 `Authorization` 헤더를
   설정할 수 없기 때문에 쿠키 경로는 `/orders/`이다.
4. 공용 JavaScript 클라이언트가 `POST /orders/auth/refresh/`를 호출하여 access를
   메모리에 받는다. HTML 렌더링 시 스크립트의 data 속성에 결속한 역할·session ID와
   응답의 `role`·`session_id`가 일치해야 부트스트랩과 재시도를 진행한다. 다른 탭에서
   계정을 바꾸거나 재로그인했다면 기존 화면은 API 호출을 중단한다. API 요청의 `Authorization: Bearer <access>`에 넣는다.
5. API는 access 서명과 현재 DB 디바이스 상태를 매번 검사한다. refresh 쿠키나
   예전 Django 세션의 역할 값만으로 API 권한을 얻을 수 없다.

Access는 JavaScript 클로저 메모리에만 보관한다. localStorage/sessionStorage에 넣지
않는다. Refresh는 `bk_refresh` 쿠키에 보관하며 `HttpOnly`, `Secure`, `SameSite=Strict`,
`Path=/orders/`를 사용한다. 운영 설정은 HTTPS를 전제로 한다.

## HTTP 계약

| 경로 | 메서드 | 결과 |
| --- | --- | --- |
| `/orders/login/` | GET | 로그인 화면·CSRF 쿠키 |
| `/orders/login/` | POST | 성공 시 역할 화면 redirect·refresh 쿠키, 잘못된 자격증명은 일반 오류 화면, 차단 시 429·`Retry-After`, 로그인 설정 미완료 시 503 |
| `/orders/auth/refresh/` | POST | 200: `access_token`, `role`, `session_id`, `expires_in` JSON·회전 시 새 refresh 쿠키; 인증 실패 401; 직전 토큰 동시 갱신 409 |
| `/orders/logout/` | POST | 해당 디바이스 폐기·refresh 쿠키 삭제·세션 비우기·로그인 화면 redirect |

로그인·refresh·logout과 API 쓰기 요청에는 CSRF 보호가 적용된다. 인증 API의 401에는
`WWW-Authenticate: Bearer`가 붙는다. 유효한 access라도 허용되지 않은 역할은 403이다.
Refresh의 401/409 응답은 새 쿠키를 쓰거나 기존 쿠키를 삭제하지 않는다. 늦게 도착한
실패 응답이 다른 탭에서 갱신한 쿠키를 덮어쓰지 않도록 한다.

클라이언트는 동일 출처 API만 호출하며 refresh 작업을 탭 내부에서 공유하고, Web Locks가
있으면 탭 간에도 직렬화한다. 409에는 제한된 재시도를 한다. API의 명시적인 401에는
refresh 후 한 번 재요청한다. 네트워크 오류만으로 이미 처리되었을 수 있는 쓰기를 재전송하지 않는다.

## 수명·회전·폐기

- Access 수명은 최대 15분이다. 디바이스의 절대 만료까지 남은 시간이 더 짧으면 그
  시점에 access도 만료된다.
- Refresh와 디바이스 수명은 최초 로그인부터 절대 12시간이다. 회전해도 연장하지 않는다.
- Refresh 회전은 PostgreSQL `select_for_update()`로 해당 디바이스 행을 잠근다.
  같은 토큰에 대한 동시 요청 중 하나만 새 토큰을 발급한다.
- 현재 refresh가 마지막 회전 후 5초 미만에 다시 오면 access만 발급한다. refresh JTI와
  회전 시각은 바꾸지 않고 `Set-Cookie`도 보내지 않는다. 여러 탭의 순차 갱신으로 직전
  토큰이 너무 빨리 밀려나는 것을 방지한다.
- **직전** refresh 토큰이 마지막 회전 후 5초 미만에 다시 오면 `RefreshInProgress`로
  409를 반환한다. 발급·폐기·쿠키 변경은 하지 않는다.
- 5초가 지났거나 더 오래된 유효 서명의 refresh가 재사용되면 해당 디바이스만 폐기한다.
  폐기는 트랜잭션 종료 후 인증 오류를 발생시켜 DB에 유지한다. 다른 디바이스는 유지된다.
- 잘못된 서명·토큰 종류·클레임·만료 토큰은 검증 단계에서 거부한다. 이런 입력으로
  디바이스를 폐기하지 않는다.
- 로그아웃은 아직 유효한 서명의 이전 refresh로도 같은 디바이스를 폐기할 수 있다.
- DB 폐기 상태, 계정 공급 상태, ID 및 자격증명 fingerprint를 access·refresh·HTML
  인증 때마다 확인한다. 현재 구현에서는 계정 제거와 ID/비밀번호 해시 변경이 해당
  계정의 기존 디바이스를 모두 무효화한다. 비밀번호 교체 시 전체 디바이스 종료는
  D-045로 승인된 운영 정책이다.

회전이 서버에서 완료되었지만 응답이 유실되면 브라우저가 새 쿠키를 받지 못할 수 있다.
이전 토큰으로 새 토큰을 복구해 주지 않으므로 재로그인이 필요할 수 있다.

## 서버 저장과 검증

`orders/authentication.py`가 HTTP와 분리된 서비스다.

| 함수 | 책임 |
| --- | --- |
| `authenticate_credentials(account_id, password)` | 일치하는 역할 또는 `None` |
| `issue_tokens(role)` | 새 디바이스와 `TokenPair` 생성 |
| `rotate_refresh(raw)` | 디바이스를 잠그고 회전 또는 재사용 처리 |
| `validate_access(raw)` | access와 현재 디바이스 검증 후 역할 반환 |
| `validate_refresh(raw)` | 현재 refresh를 읽기 전용 검증 후 역할 반환 |
| `revoke_refresh(raw)` | 서명된 refresh의 디바이스 폐기 |

`TokenPair`는 `access_token`, `refresh_token`, `role`, `expires_at`, `session_id`를 가진다.
`session_id`는 디바이스 UUID다. 5초 내 현재 토큰 요청을 합칠 때 `refresh_token`은 `None`이며
HTTP 계층은 refresh 쿠키를 쓰지 않는다.
여기서 `expires_at`은 access 만료가 아니라 디바이스의 절대 만료 시각이다.

Migration `0021_auth_device`는 `AuthDevice`, `LoginAttempt`를 추가한다. 디바이스에는 UUID,
역할, 계정 ID, 자격증명 fingerprint, 현재/직전 refresh JTI의 SHA-256 해시, 마지막
회전 시각, 절대 만료 시각, 폐기 시각을 저장한다. 원본 JWT나 refresh JTI는 저장하지 않는다.

JWT는 `HS256`만 허용하고, issuer `bazaar-kiosk`, audience `bazaar-kiosk-browser`를 고정한다.
`iss`, `aud`, `iat`, `exp`, `sub`, `role`, `device`, `jti`, `type`을 필수로 요구한다.
숫자 날짜는 정수, 식별자·역할·종류는 문자열이어야 하며 UUID 형식과 토큰 종류도 확인한다.
입력이 빈 문자열·비문자열·8192자 초과이면 파싱 전에 거부한다.
허용 알고리즘을 토큰 헤더에서 결정하지 않는 방식은
[PyJWT 공식 API 문서의 알고리즘 검증 지침](https://pyjwt.readthedocs.io/en/latest/api.html#jwt.decode)을 따른다.

민감한 서비스 프레임은 `sensitive_variables()`로 표시한다. HTTP 오류 보고 필터와
설정 마스킹도 함께 사용하며, 토큰·비밀번호를 로그 메시지에 넣지 않는다.

## 설정과 운영 정책

| 설정 | 현재 계약 |
| --- | --- |
| `ROLE_ACCOUNTS` | 알려진 역할 → `{"id": "공용 계정 ID", "password_hash": "Django PBKDF2 인코딩 해시"}` JSON |
| `JWT_SIGNING_KEY` | `SECRET_KEY`와 별도인 충분히 긴 비밀 값; 시작 검사에서 최소 50자 등 검증 |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_HOURS` | 코드 설정 15 / 12 |
| `JWT_REFRESH_COOKIE_NAME` / `JWT_REFRESH_COOKIE_PATH` | `bk_refresh` / `/orders/` |
| `JWT_COOKIE_SECURE` | `True` |
| `LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_SECONDS` / `LOGIN_BLOCK_SECONDS` | 코드 설정 10 / 300 / 300 (D-045). 환경 변수로 바꿀 수 없다 |

ID는 고유해야 하고 앞뒤 공백 없이 최대 128자다. 비밀번호는 평문 환경변수 대신 Django
`pbkdf2_sha256` 인코딩 해시를 공급한다. 샘플·테스트 계정은 합성 fixture이며 운영 자격증명이 아니다.
[D-045](DECISIONS.md)로 비밀번호 교체 시 전체 디바이스 종료, 5분 동안 10회 실패 시 5분 잠금,
메뉴·테이블 조회의 인증된 세 계정 허용이 확정됐다. 테스트 프로필도 같은 실패 제한 값을 쓴다.

비밀번호 해시는 저장소 밖의 안전한 터미널에서 다음처럼 생성할 수 있다. 입력은 화면에
표시하지 않으며, 출력된 해시는 운영 환경 설정의 해당 `password_hash`에 넣는다. 실제
비밀번호·해시·완성된 계정 JSON을 문서나 Git에 저장하지 않는다.

```sh
.venv/bin/python - <<'PYHASH'
from getpass import getpass
from django.contrib.auth.hashers import PBKDF2PasswordHasher

password = getpass("New shared-account password: ")
confirmation = getpass("Confirm password: ")
if not password or password != confirmation:
    raise SystemExit("Passwords must be nonempty and match.")
hasher = PBKDF2PasswordHasher()
print(hasher.encode(password, hasher.salt()))
PYHASH
```

실패 횟수는 계정 ID와 **직접 연결한 peer IP (`REMOTE_ADDR`) 조합**별로 DB에서 공유한다.
키는 HMAC으로 저장한다. 성공하면 해당 조합의 횟수를 초기화한다. `X-Forwarded-For`를
임의로 신뢰하지 않는다. 프록시 뒤에서는 여러 사용자가 같은 peer IP로 묶일 수 있고,
여러 IP나 ID로 분산된 시도를 전역 제한하는 기능은 아니다. 운영 프록시 구성과 정책을
함께 검토해야 한다.

**공개 노출 전 남은 위험(2026-09-17 보안 리뷰):**

- 분산 추측: 공용 계정 ID는 세 개뿐이고 추측될 수 있다. IP마다 5분 10회가 따로 주어지므로
  여러 IP를 가진 공격자에게는 계정당 총 시도 상한이 없다. 앱은 해시만 받으므로 비밀번호
  강도를 검사할 수 없다. **운영 비밀번호는 사람이 고른 단어가 아니라 무작위 생성값(예: 20자 이상)으로
  공급한다.** 전역 제한·WAF 필요 여부는 12A1에서 판단한다.
- 프록시 뒤 IP 뭉침: 역방향 프록시가 앞에 서고 앱 서버가 실제 클라이언트 주소를
  `REMOTE_ADDR`로 받지 못하면 모든 외부 요청이 프록시 IP 하나로 묶인다. 그러면 한 공격자의
  10회 실패가 같은 계정의 정상 기기 로그인까지 5분씩 막는다. 프록시 주소 전달 설정은
  12A1의 필수 인수 항목이며, 설정 없이 `X-Forwarded-For`를 앱에서 신뢰하도록 바꾸지 않는다.

환경변수는 프로세스 시작 시 읽는다. 계정 변경·제거 또는 서명키 변경을 적용할 때에는
모든 worker에 같은 환경을 공급하고 모두 재시작해야 한다. 일부 worker만 교체한 상태는
자격증명·키의 일관된 적용을 보장하지 않는다.

## 배포와 복구 경계

이 문서 작성 작업은 배포를 수행하지 않는다. 배포 시에는 정책과 실제 환경을 확정하고,
DB migration을 적용한 뒤 새 인증 코드와 설정을 모든 worker에 일관되게 적용한다.
기존 Django 세션은 JWT 인증을 대신하지 않으므로 사용자는 다시 로그인한다.

장애 때 이전 세션 인증 앱을 그대로 다시 띄우면 남아 있는 legacy 세션이 다시 권한을
얻을 수 있다. **옛 앱 복원으로 인증 전환을 되돌리지 않는다.** 인증 실패를 닫힌 상태로
유지하는 점검 화면 또는 새 인증 구조의 전진 수정으로 복구한다. migration을 단순히
역적용하는 절차도 권장 복구 절차가 아니다.

## 검증

전용 로컬 PostgreSQL fixture를 시작한 뒤 다음 형태로 실행한다. 운영 DB URL을 쓰지 않는다.

```sh
BK_TEST_DATABASE_URL='postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:<fixture-port>/bk_test_control' \
  .venv/bin/python manage.py test orders.tests.test_jwt_service orders.tests.test_jwt_http \
  --settings=bazaar_kiosk.settings_test_pg
node scripts/test_auth_client.cjs
```

서비스 테스트는 클레임 형식·누락·서명·종류·만료, 절대 수명, 디바이스 격리, 동시 회전,
유예와 재사용 폐기, 계정 변경을 다룬다. HTTP·브라우저 클라이언트 검증과 전체 회귀 결과는
작업 기록에 별도로 남긴다. 이 문서는 최종 테스트 수나 배포 성공을 주장하지 않는다.
