# ASGI 실행과 프록시 최소 증명 (10A)

상태: 구현과 로컬 합성 검증. 결정은 [D-057](DECISIONS.md). 위험: BK-R035, BK-R039(일부).
**스키마 변경과 마이그레이션이 없다.** 실제 EC2·TLS·관측은 12A1이다.

## 무엇이 사실이 아니었나

저장소에는 `bazaar_kiosk/asgi.py`가 프로젝트 생성 때부터 있었다. 그런데 배포 후보는
`gunicorn bazaar_kiosk.wsgi:application`을 실행하고 있었다. WSGI 워커는 스트리밍 응답을
**전부 모은 뒤 한 번에** 보낸다. 즉 이 구성에서 SSE는 느리게 도착하는 것이 아니라 **아예
스트리밍되지 않는다.** 파일이 있다는 것과 그 파일이 실행된다는 것은 다른 말이고, 10D가
기대는 것은 후자다.

여기서 확인한 것은 세 가지다. 셋 다 파일을 읽어서는 알 수 없다.

## 1. 동기 미들웨어 하나가 ASGI를 무효로 만들고 있었다

Django는 동기 전용 미들웨어를 만나면 **그 안쪽 전체**를 `async_to_sync`로 감싼다. 목록을
그대로 두고 체인을 만들어 보면 이렇게 나왔다.

```
BRIDGE sync_to_async  around None
BRIDGE async_to_sync  around middleware whitenoise.middleware.WhiteNoiseMiddleware
BRIDGE sync_to_async  around None
```

미들웨어 8개 중 `async_capable=False`는 `WhiteNoiseMiddleware` 하나뿐이었다. 그 하나 때문에
**정적 파일과 무관한 모든 요청**이 스레드를 왕복하고, async 뷰와 그 뷰가 돌려준 제너레이터가
본문을 읽는 루프와 **다른 이벤트 루프**에서 실행된다. 스트림 자체는 운 좋게 동작할 수 있지만,
10D1의 허브 큐처럼 루프에 묶이는 객체를 들고 있으면 거기서 끝난다.

WhiteNoise는 최신 릴리스(6.12)까지도 async 경로가 없다. 그래서 정적 파일을 앱 밖으로 옮겼다.

| 이전 | 지금 |
| --- | --- |
| 앱이 `WhiteNoiseMiddleware`로 `/static/`을 제공 | **프록시가 디스크에서 직접 제공.** 앱은 정적 요청을 한 건도 보지 않는다 |
| 자산이 앱 이미지 안에만 있음 | 같은 빌드의 `collectstatic` 결과를 프록시 이미지가 함께 담는다(Dockerfile `proxy` 타깃) |
| 미들웨어가 파일마다 캐시 수명을 판단 | 해시 이름은 `max-age=31536000, immutable`, 원래 이름은 `max-age=60`. nginx location 두 개 |

**볼륨으로 공유하지 않았다.** 이름 있는 볼륨은 처음 한 번만 이미지에서 채워지므로, 다시 빌드한
뒤에도 지난주 번들을 이번 주 manifest에 대고 계속 내보낸다. 이미 `pg_data` 초기화에서 같은
성질의 함정을 문서화한 적이 있다([배포 후보](DEPLOYMENT_CANDIDATE.md)). 그래서 자산과 그것을
가리키는 템플릿이 **같은 빌드에서 나오도록** 이미지에 넣었다.

되돌아오는 것을 막기 위해 [시스템 검사](../../orders/checks.py)를 뒀다. 동기 전용 미들웨어가
목록에 들어오면 `manage.py check`가 `orders.E001`로 거부한다. 이건 주석으로 적어 둘 수 있는
종류의 사실이 아니다. 어기면 아무것도 실패하지 않기 때문이다.

**알아 둘 결과:** `DEBUG=0`이고 앞에 프록시가 없으면 `/static/`은 아예 제공되지 않는다.
의도한 것이다. 애플리케이션 서버가 조용히 자산을 날라 주던 것이 이 문제를 지금까지 가려 왔다.

## 2. 워커를 uvicorn 단독으로 바꿨다 (D-057)

`uvicorn.workers`는 공식적으로 deprecated이고 제거 예정이다. 대체 패키지 `uvicorn-worker`는
Development Status가 Alpha이고 마지막 릴리스가 2025-09-20으로 1년째 멈춰 있다. gunicorn을
앞에 두면 **가장 관리가 덜 되는 조각**에 의존하게 되므로, uvicorn 자체의 프로세스 관리자를 쓴다.

```
python -m uvicorn bazaar_kiosk.asgi:application
  --host 0.0.0.0 --port 8000
  --workers 3
  --no-proxy-headers
  --timeout-graceful-shutdown 10
  --log-level info
```

**`--no-proxy-headers`가 이 명령에서 가장 중요한 한 줄이다.** uvicorn의 프록시 헤더 처리는
기본이 **켜짐**이고, gunicorn과 달리 `X-Forwarded-For`를 읽어 **클라이언트 주소 자체를 바꾼다.**
켜 둔 채 전환하면 이슈 #61의 판단 주체가 `TRUSTED_PROXY_IPS`에서 이 명령줄로 조용히 옮겨 간다.
결과는 우연히 같지만, 경계가 어디에 있는지 아무도 말해 주지 않는 상태가 된다.
같은 이유로 `--forwarded-allow-ips`도 넣지 않았다. 집행하지 않는 경계처럼 읽힌다.

전달된 **스킴**은 영향받지 않는다. Django는 `SECURE_PROXY_SSL_HEADER`로 `X-Forwarded-Proto`를
직접 읽으며, 서버가 `wsgi.url_scheme`에 무엇을 넣든 보지 않는다.
*(정정: `compose.prod.yaml`의 이전 주석은 gunicorn의 `--forwarded-allow-ips`가 앱에 HTTPS 여부를
알려 준다고 읽혔다. `DEBUG=0`에서는 그 옵션이 Django의 판단에 관여한 적이 없다.)*

`--timeout-graceful-shutdown`은 재시작을 유한하게 만든다. graceful shutdown은 열린 연결이
닫히기를 기다리는데, 스트림은 닫힐 이유가 없는 연결이다.

## 3. DB 연결은 스트림이 시작하기 전에 놓는다

인증은 DB를 읽는다. 스트리밍 응답에서 Django가 보는 "요청의 끝"은 **마지막 프레임을 보낸
시점**이므로, 그대로 두면 주방 화면 하나가 켜져 있는 내내 연결 하나를 붙들게 된다. 연결 수가
작업량이 아니라 **열려 있는 화면 수**를 따라가는 상태다.

그래서 [probe 뷰](../../orders/views/stream.py)는 프레임을 내보내기 전에 그 요청의 스레드에서
연결을 닫고, 닫혔는지를 같은 스레드에서 다시 물어 프레임에 적는다. `connections`는 스레드별
저장소라서, 다른 곳에서 물으면 편한 대답(`False`)이 그냥 나온다.

`CONN_MAX_AGE`는 `0`으로 **명시했다.** 기본값이라 적지 않아도 같지만, ASGI에서는 0이 유일하게
안전한 값이고 나중에 바꾸려는 사람이 이 주석과 먼저 부딪히는 편이 낫다.

## 측정 (2026-09-20)

실제 `compose.prod.yaml` 스택을 전용 프로젝트 `bk10a-stream`, 합성 비밀값,
`127.0.0.1:8080`에서 띄우고 `curl -N`으로 측정했다. 운영 자격증명·실제 호스트는 쓰지 않았고
측정 후 컨테이너·볼륨·비밀 파일을 제거했다. 프로세스는 uvicorn 워커 3개였다.

### 프레임이 끝나기 전에, 하나씩 도착한다

`frames=5&interval_ms=500`:

```
t+   32 ms  event: probe   {"db_open":false,"elapsed_ms":0,   "pid":10,"seq":0}
t+  538 ms  event: probe   {"db_open":false,"elapsed_ms":504, "pid":10,"seq":1}
t+ 1040 ms  event: probe   {"db_open":false,"elapsed_ms":1006,"pid":10,"seq":2}
t+ 1541 ms  event: probe   {"db_open":false,"elapsed_ms":1508,"pid":10,"seq":3}
t+ 2043 ms  event: probe   {"db_open":false,"elapsed_ms":2009,"pid":10,"seq":4}
t+ 2545 ms  event: done    {"frames":5}
```

프레임 간격 `[506, 502, 501, 502, 502] ms`. 첫 프레임은 요청 32ms 뒤에 도착했고 응답은
그로부터 2.5초 뒤에 끝났다. WSGI였다면 여섯 덩어리가 2545ms에 한꺼번에 왔다.

### 열린 스트림이 일반 API를 굶기지 않는다

| 열린 스트림 | 워커 스레드 합 | DB 연결 | `GET /orders/menus/` (8회) |
| --- | --- | --- | --- |
| 0 | 9 | 1 | 중앙값 28ms |
| 6 | 15 | 1 | 중앙값 19ms, 최대 21ms |
| 24 | 33 | 1 | 중앙값 19ms, 최대 23ms |
| 48 | 57 | 1 | 중앙값 20ms, 최대 28ms |
| 전부 종료 후 | 9 | 1 | — |

**DB 연결은 열린 스트림 수와 무관하게 1이다**(유휴 기준선과 같다). 48개를 열어 두고도 일반
API 지연이 변하지 않았다.

### 스트림 하나는 스레드 하나를 차지한다 — 10D가 알아야 할 숫자

표에서 스레드 수는 정확히 열린 스트림 수만큼 늘어난다(9 → 15 → 33 → 57). 인증이 DB를 읽기
위해 만든 요청별 스레드가, 응답이 끝날 때까지 놀면서 남아 있기 때문이다. 블록된 스레드라 CPU는
쓰지 않고 RSS 증가도 스트림당 약 90kB였지만(48개에 +3.7MB), **화면 수만큼 스레드가 생긴다**는
사실은 그대로다. 행사 규모에서는 문제가 아니고, 화면 수 상한과 목표는 D-007에 남아 있다.

### 연결이 끊기면 정리된다

클라이언트를 죽이면 스레드 57 → 9, FD 70 → 64로 **기준선까지 돌아왔다.** 제너레이터의
`finally`가 실행된다는 뜻이고, 10D1의 허브가 구독을 해제할 자리가 거기다.

### 재시작이 스트림에 걸려 멈추지 않는다

스트림을 연 채 `docker compose stop -t 30 app`은 **10.5초**에 돌아왔다.

```
INFO:     Waiting for connections to close. (CTRL+C to force quit)
ERROR:    Cancel 1 running task(s), timeout graceful shutdown exceeded
INFO:     Finished server process [9]
```

`--timeout-graceful-shutdown 10`이 없으면 docker의 30초를 다 기다린 뒤 SIGKILL로 끝난다.

### 이슈 #61 경계가 서버를 바꾼 뒤에도 그대로다

프록시 경유로 틀린 비밀번호 11회: `200 ×9, 429, 429`. 그다음 요청에
`X-Forwarded-For: 203.0.113.99`를 붙여도 **429**. nginx가 헤더를 덮어쓰고 uvicorn이
`REMOTE_ADDR`을 건드리지 않으므로, 판단하는 것은 여전히 `TRUSTED_PROXY_IPS`뿐이다.

### 정적 파일은 프록시가 낸다

| 요청 | 결과 |
| --- | --- |
| `/static/admin/js/SelectBox.js` | 200, `Cache-Control: public, max-age=60` |
| `/static/admin/js/SelectBox.7d3ce5a98007.js` | 200, `Cache-Control: public, max-age=31536000, immutable` |
| 같은 파일에 `Accept-Encoding: gzip` | `Content-Encoding: gzip` (`gzip_static`이 `.gz` 형제를 낸다) |
| 앱이 본 `/static/` 요청 수 | **0** |

## 측정이 잡은 결함 하나

스트리밍 location에 `proxy_set_header Connection "";`을 넣자 프록시 경유 요청이 **400**으로
떨어졌다. nginx는 **자기 레벨에 `proxy_set_header`가 하나라도 있으면 상위의 것을 전부 상속하지
않는다.** 헤더 하나를 더한 것이 `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`를 통째로 떨어뜨린
것이다. `Host`가 없어 `ALLOWED_HOSTS`가 거부해서 눈에 띄었지만, 눈에 띄지 않는 쪽이 더 나쁘다.
그 location의 로그인 실패는 전부 프록시 주소로 집계됐을 것이다(이슈 #61 상태로 복귀).

그래서 공통 헤더를 [`scripts/nginx_proxy_headers.conf`](../../scripts/nginx_proxy_headers.conf)로
빼고 **프록시하는 모든 location이 `include`한다.** server 레벨에는 `proxy_set_header`를 두지
않는다. 어디에나 적용되는 것처럼 읽히기 때문이다. 회귀 테스트가 이 둘을 같이 묶어 둔다.

## probe는 기능이 아니다

[`orders/views/stream.py`](../../orders/views/stream.py)는 계측기다. 주문 데이터를 내보내지
않고 어떤 화면도 부르지 않는다. 주방의 실제 SSE는 10D1이고 이 코드를 공유하지 않는다.
공유하는 것은 여기서 측정한 런타임이다.

- 기본값은 **꺼짐**이다. `BK_STREAM_PROBE=1`일 때만 응답하고, 아니면 404다.
- 그 판단을 **자격증명보다 먼저** 한다. 401을 먼저 주면 인증 없는 호출자에게 "경로는 있고 꺼져
  있을 뿐"이라고 알려 주는 셈이다.
- 켜져 있어도 인증된 계정만 닿는다. 미들웨어를 빼서 async를 통과시킨 것이 아니라는 뜻이고,
  테스트가 인증·CSRF 미들웨어가 체인에 남아 있는지 확인한다.
- `frames`는 최대 200, `interval_ms`는 최대 2000으로 제한한다. 호출자가 워커 점유 시간을
  고르게 두지 않는다. 읽을 수 없는 값은 오류가 아니라 기본값이다. 측정 도구가 오타 하나로 실행을
  날리는 것은 잘못된 교환이다.

재현 절차:

```sh
export BK_ALLOWED_HOSTS=127.0.0.1,localhost
export BK_CSRF_TRUSTED_ORIGINS=http://127.0.0.1:8080
export BK_STREAM_PROBE=1
docker compose -p bk10a-stream -f compose.prod.yaml up -d --build
docker compose -p bk10a-stream -f compose.prod.yaml exec app python manage.py migrate
curl -sN -H "Authorization: Bearer $TOKEN" \
  'http://127.0.0.1:8080/orders/api/stream/probe?frames=5&interval_ms=500'
```

비밀값 생성은 `compose.prod.yaml` 상단 주석을 따른다. 끝나면 `down -v`와 `secrets/` 삭제.

## 검증

```sh
.venv/bin/python scripts/test_postgres.py
```

`orders/tests/test_asgi_stream.py`: 동기 전용 미들웨어 없음, 체인 생성에 `async_to_sync` 삽입
없음, 인증·CSRF 미들웨어 잔존, 설정 없이는 404, 404 판단이 자격증명보다 먼저, 인증 없으면
JSON 401, 인증되면 `text/event-stream`과 `X-Accel-Buffering: no`, 프레임 번호와 순서, 종료
이벤트, 상한 200, 읽을 수 없는 인자의 기본값 복귀, 제너레이터 종료, **트랜잭션 밖에서 DB 연결
해제**(`TransactionTestCase`).

`orders/tests/test_runtime_config.py`: ASGI 진입점, `--no-proxy-headers`와
`--forwarded-allow-ips` 부재, graceful shutdown 상한, 스트리밍 location의 `proxy_buffering off`,
정적 파일의 프록시 제공과 볼륨 없음, **프록시하는 모든 location의 공통 헤더 include**.

## 이 단계가 하지 않은 것

- **실제 SSE는 없다.** 이벤트 발생(10B), snapshot 정합(10C), 인증된 SSE 서버·허브(10D1),
  주방 클라이언트와 재접속(10D2)은 그대로 열려 있다.
- **브라우저로 확인하지 않았다.** HTTP/2·여러 탭·BFCache·백그라운드 복귀는 BK-R039로 12A1에
  남는다. 여기서 닫은 것은 프록시 buffering과 idle timeout뿐이다.
- **실제 호스트가 아니다.** EC2·TLS·백업·관측은 12A1/12A2다. 평문 HTTP에서는
  `JWT_COOKIE_SECURE=True` 때문에 브라우저 로그인이 되지 않는다는 4A3의 정정이 그대로 유효하다.
- **화면 수 상한을 정하지 않았다.** 스트림당 스레드 1개라는 숫자만 넘긴다. 목표 부하와 동시
  접속 수는 D-007이다.
- 지원 PostgreSQL 버전·토폴로지·실제 호스트 사양은 계속 D-006/12A1에 남는다.
