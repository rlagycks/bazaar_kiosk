# 4A3 — 배포 후보 구성과 노출 경계

상태: 구현과 로컬 합성 검증. **운영 배포·실제 호스트 인수를 뜻하지 않는다.**
D-046이 정한 형태(Compose 한 스택, 파일 비밀값, 내부 네트워크 전용 DB, 단일 DB 역할)를
저장소에 구현한 기록이다. 실제 EC2·TLS 인증서·백업·관측은 12A1/12A2다.

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `Dockerfile` | 두 타깃. `app`은 앱 이미지(빌드 시 `collectstatic`, 비루트 uid 10001, 컴파일러 미포함), `proxy`는 그 빌드의 정적 파일을 담은 nginx(10A) |
| `compose.prod.yaml` | 배포 후보 스택. 프록시만 포트를 발행한다 |
| `scripts/pg_prod_init.sql` | 앱 DB 역할 생성과 권한 축소. 빈 데이터 디렉터리에서 1회 실행 |
| `scripts/nginx_prod.conf` | 프록시. 정적 파일, 스트리밍 location, 프록시 대상 |
| `scripts/nginx_proxy_headers.conf` | 프록시하는 모든 location이 include하는 공통 헤더(10A). 클라이언트 주소를 실제 peer로 덮어쓴다 |

## 노출 경계

- `proxy`만 호스트 포트를 발행한다(후보에서는 `127.0.0.1:8080`). `app`·`postgres`는
  발행하지 않는다. 확인: `docker compose ps`의 PORTS에 호스트 매핑이 없다.
- `internal` 네트워크는 `internal: true`라 외부로 나가는 경로가 없다. `proxy`만
  `edge`와 `internal` 양쪽에 붙는다.
- DB 연결은 같은 호스트 내부 네트워크 안에서만 일어나므로 TLS를 쓰지 않는다(D-046).
  따라서 `DATABASE_URL`에 `sslmode=disable`을 명시한다. 이 값을 외부 DB나 다른 호스트로
  옮기면서 그대로 복사하지 않는다. DB를 다른 서버로 분리하면 TLS 결정을 다시 해야 한다.

## 비밀값 전달 (D-046)

운영 비밀값은 환경 변수가 아니라 **파일**로 전달한다. 설정은 `<NAME>_FILE` 환경 변수가
가리키는 파일을 읽는다. 대상은 `SECRET_KEY`, `JWT_SIGNING_KEY`, `EVENT_PASSWORD_HASH`
(2026-09-20 D-051로 `ROLE_ACCOUNTS`를 대체), `DATABASE_URL`이다.

- 환경 변수와 `_FILE`을 **둘 다** 설정하면 시작을 거부한다. 하나를 조용히 무시하면
  교체한 쪽이 반영되지 않았는지 알 수 없다.
- `_FILE`이 읽히지 않으면 시작을 거부한다. "설정되지 않음"으로 떨어지면 기본값으로
  뜨거나, 운영자가 설정한 변수를 누락으로 지목하는 메시지가 나온다.
- 파일 끝의 줄바꿈은 값에서 제거한다. 서명 키나 비밀번호가 줄바꿈을 달고 있으면
  "자격증명이 틀림"처럼 보이는 실패가 된다.
- 거부 메시지에는 변수 이름만 들어가고 파일 내용은 들어가지 않는다.

`secrets/` 디렉터리는 `.gitignore` 대상이다. 생성 절차는 `compose.prod.yaml` 상단 주석과
[JWT_AUTHENTICATION](JWT_AUTHENTICATION.md)의 해시 생성 절차를 따른다.

## 실행 형태 (10A, D-057)

**2026-09-20 갱신:** 앱은 이제 ASGI로 실행한다.
`python -m uvicorn bazaar_kiosk.asgi:application --workers 3 --no-proxy-headers
--timeout-graceful-shutdown 10`. 이전의 `gunicorn ...wsgi:application`에서는 스트리밍 응답이
모여서 한 번에 나갔으므로 SSE가 아예 동작하지 않았다. 정적 파일은 `WhiteNoiseMiddleware`
대신 프록시가 디스크에서 낸다. 측정과 이유는 [ASGI 실행과 프록시](ASGI_RUNTIME.md).

`--no-proxy-headers`는 아래 경계와 직접 연결된다. uvicorn의 프록시 헤더 처리는 기본이 켜짐이고
gunicorn과 달리 `REMOTE_ADDR` 자체를 `X-Forwarded-For`로 덮어쓴다. 끄지 않으면 아래 경계를
앱이 아니라 명령줄이 집행하게 된다.

## 프록시 뒤 클라이언트 주소 ([이슈 #61](https://github.com/rlagycks/bazaar_kiosk/issues/61))

**정정:** 이전 기록은 gunicorn `--forwarded-allow-ips`가 클라이언트 주소를 복원한다고
읽힐 수 있었다. 실제로 gunicorn은 `REMOTE_ADDR`을 **소켓 peer로만** 채운다. 그 옵션은
`X-Forwarded-Proto` 같은 헤더의 신뢰 여부만 정한다. 따라서 프록시를 앞에 두면 앱이 보는
주소는 항상 프록시가 되고, 계정 ID+IP별 실패 제한이 사실상 계정 단위 전역 잠금이 된다.

**추가 정정(10A):** `DEBUG=0`에서 그 옵션은 Django의 HTTPS 판단에도 관여하지 않았다. Django는
`SECURE_PROXY_SSL_HEADER`로 `X-Forwarded-Proto`를 직접 읽으며 서버가 채운 스킴을 보지 않는다.
uvicorn으로 옮기면서 그 옵션은 사라졌고, 경계는 앱의 `TRUSTED_PROXY_IPS` 하나로 남았다.

경계는 앱에 구현했다(`orders/client_ip.py`).

- `TRUSTED_PROXY_IPS`에 적힌 주소·대역에서 온 요청일 때만 `X-Forwarded-For`를 읽는다.
- 체인은 오른쪽부터 읽고 신뢰된 홉을 건너뛴다. 클라이언트가 앞에 덧붙인 값은 쓰지 않는다.
- 비어 있으면 peer 주소를 그대로 쓴다. 프록시 없는 배포의 올바른 값이다.
- 값이 없거나 형식이 틀리면 peer 주소로 되돌아간다. 이 경로는 공격자가 헤더를 조종하는 순간이다.
- 프록시는 인바운드 `X-Forwarded-For`를 **덮어쓴다**(`$remote_addr`). 이어 붙이지 않는다.
- `TRUSTED_PROXY_IPS`에 IP·CIDR이 아닌 값이 있으면 **시작을 거부한다.** 이 값은 로그인 경로에서
  읽으므로, 요청 중에 터지면 오타 하나가 로그인 전면 장애가 된다. 요청 처리 중에는 예외를
  올리지 않고 그 항목을 건너뛴다.

이 두 가지가 같이 있어야 이슈 #61이 닫힌다. 한쪽만 있으면 전역 잠금(설정 누락) 또는
누구나 자기 버킷 선택(지나치게 넓은 신뢰)이 된다.

## DB 역할

D-046으로 역할은 **하나**다(`bazaar_app`). 스키마를 소유하므로 migration을 직접 적용할 수 있다.

- 막은 것: `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOREPLICATION`, `NOBYPASSRLS`.
  `PUBLIC`의 스키마 생성 권한과 DB 접속 권한도 회수했다.
- 비밀번호 파일이 비어 있으면 역할을 만들지 않고 초기화를 중단한다. 암호 없는 역할이
  조용히 생기는 것을 막는다.
- **초기화는 빈 볼륨에서 한 번만 실행된다.** 중단된 뒤 컨테이너가 재시작하면 데이터
  디렉터리는 이미 초기화된 상태이므로 스크립트가 다시 돌지 않는다. 그 DB에는 앱 역할이
  없어 앱이 접속하지 못한다(닫힌 실패). 비밀값을 고친 뒤에는 **볼륨을 지우고 다시 시작**해야 한다.
- **남는 위험:** 앱이 장악되면 자기 테이블을 변경·삭제할 수 있다. 역할을 migration용과
  런타임용으로 나누면 줄어들지만, 사용자가 단일 역할을 선택했다. 백업 역할은 12A2에서 다룬다.
  이 선택을 바꾸려면 D-046을 개정한다.

## 로컬 합성 검증 (2026-09-18)

전용 프로젝트 `bk4a3-candidate`, 합성 비밀값, 호스트 `127.0.0.1:8080`에서 확인했다.
운영 자격증명·실제 호스트는 사용하지 않았고 검증 후 컨테이너·볼륨·비밀 파일을 제거했다.

| 확인 | 결과 |
| --- | --- |
| `docker compose config --quiet` | 통과 |
| 앱 이미지 빌드와 기동 | 통과(비루트 uid 10001) |
| 앱 역할로 `migrate` | `0021`까지 적용 |
| 프록시 경유 `/orders/login/` | 200 |
| `docker compose ps` 포트 | `proxy`만 호스트 매핑, `app`·`postgres` 없음 |
| 컨테이너 내부 `client_ip` | 프록시 peer면 전달 주소, 아니면 peer 주소 |
| 프록시 경유 로그인 실패 | 9회 200, 10회째 429 |
| 빈 비밀번호 파일로 첫 부팅 | 초기화 중단, `bazaar_app` 미생성(0개) |
| `check --deploy` | 경고 2건(아래) |

**정정(2026-09-18): 이 구성으로는 브라우저에서 로그인할 수 없다.**
`JWT_COOKIE_SECURE = True`라 refresh 쿠키 `bk_refresh`가 `Secure`로 나가고, 평문 HTTP에서는
브라우저가 그 쿠키를 저장하지 않는다. 그래서 로그인 POST가 302로 성공해도 다음 화면이 다시
로그인으로 돌아온다. 6A 작업 중 LAN 주소(`http://192.168.x.x`)로 열어 재현했고, 남는 쿠키는
`csrftoken`뿐이었다. 4A3 검증은 curl로 했는데 curl은 `Secure`를 강제하지 않아 드러나지 않았다.
따라서 **12A1의 TLS는 선택이 아니라 이 앱이 동작하기 위한 조건**이다. 이 후보를 실제 접속
경로로 쓰려면 TLS를 먼저 끝내야 한다. 자세한 경위는 [중복 요청 경계](IDEMPOTENCY.md).

`check --deploy`의 `security.W004`(HSTS)와 `security.W008`(HTTPS 리다이렉트)은 남겼다.
둘 다 실제 TLS 종단·도메인이 정해진 뒤 결정할 항목이라 12A1에서 함께 처리한다.
HSTS는 잘못 켜면 되돌리기 어렵다.

## 12A1로 넘긴 보안 리뷰 항목

2026-09-18 독립 보안 리뷰가 머지 차단 없음으로 판정하면서 아래를 다음 단계 몫으로 남겼다.

- 프록시 하드닝: `server_tokens off`, 요청·연결 제한(`limit_req`/`limit_conn`),
  응답 보안 헤더. 지금 파일은 헤더 신뢰 경계만 담은 후보다.
- IPv4-mapped IPv6: 내부 네트워크에 IPv6를 켜면 프록시 peer가 `::ffff:` 형태로 보일 수 있고,
  그러면 신뢰 판정이 조용히 실패해 이슈 #61 상태로 돌아간다(스푸핑은 아니다). 현재 내부
  네트워크는 IPv4 전용이며 [회귀 테스트](../../orders/tests/test_client_ip.py)로 닫힌 실패를 고정했다.
  IPv6를 켤 때 `.ipv4_mapped` 정규화를 함께 넣는다.

## 이 단계가 하지 않은 것

- 실제 EC2 생성·배포·도메인·인증서·방화벽(SG)·IAM 구성
- 백업과 복원, 새 호스트 복원 리허설(12A2), 데이터 이전(12A3)
- 헬스/레디니스 엔드포인트와 로그·메트릭 수집(12A1)
- 부하·SLO 측정(10E)

BK-R043/BK-R044는 저장소 쪽 구성이 갖춰졌을 뿐 **운영 대상 검증 전까지 Open**이다.

## 2026-09-20 재검증 (10A)

같은 방식(전용 프로젝트 `bk10a-stream`, 합성 비밀값, `127.0.0.1:8080`)으로 ASGI 전환 뒤를
다시 확인했다. 검증 후 컨테이너·볼륨·비밀 파일을 제거했다.

| 확인 | 결과 |
| --- | --- |
| 앱·프록시 이미지 빌드와 기동 | 통과(uvicorn 워커 3개, 비루트 uid 10001) |
| 앱 역할로 `migrate` | `0027`까지 적용 |
| `docker compose ps` 포트 | `proxy`만 호스트 매핑, `app`·`postgres` 없음 |
| 프록시 경유 로그인 실패 | 9회 200, 10회째 429 |
| 스푸핑한 `X-Forwarded-For`로 한 번 더 | 429(새 버킷을 얻지 못함) |
| 프록시 경유 `/static/` 두 가지 | 200, 해시 이름은 `immutable`, `gzip_static` 동작, 앱이 본 정적 요청 0건 |
| 정적 응답의 보안 헤더 | `nosniff`·`Referrer-Policy: same-origin`·COOP 모두 존재 |
| `/static/staticfiles.json` | 404(manifest를 밖으로 내보내지 않는다) |
| 스트림을 연 채 `stop -t 30 app` | 10.7초에 종료 |
| 시작 시 `manage.py check` | 컨테이너 로그에서 `System check identified no issues` 확인 |

**주의:** 4A3의 정정은 그대로다. 평문 HTTP에서는 `JWT_COOKIE_SECURE=True` 때문에 브라우저가
`bk_refresh` 쿠키를 저장하지 않아 로그인이 유지되지 않는다. 위 검증은 curl로 했다.
