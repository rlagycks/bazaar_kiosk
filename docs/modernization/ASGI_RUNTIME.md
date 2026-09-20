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

## 1. 동기 미들웨어 하나가 요청 경로를 스레드로 끌어내리고 있었다

Django는 동기 전용 미들웨어를 만나면 **그 안쪽 전체**를 `async_to_sync`로 감싼다. 목록을
그대로 두고 체인을 만들어 보면 이렇게 나왔다.

```
BRIDGE sync_to_async  around None
BRIDGE async_to_sync  around middleware whitenoise.middleware.WhiteNoiseMiddleware
BRIDGE sync_to_async  around None
```

미들웨어 8개 중 `async_capable=False`는 `WhiteNoiseMiddleware` 하나뿐이었다. 그 하나 때문에
**정적 파일과 무관한 모든 요청**이 스레드를 두 번 건넌다.

### 그 대가를 재 봤다 — 처음 적은 것보다 작고, 원인도 달랐다

**이 문서의 초안은 "async 뷰가 본문을 읽는 루프와 다른 이벤트 루프에서 실행되고, 10D1의 허브
큐처럼 루프에 묶이는 객체는 거기서 끝난다"고 적었다. 그 주장을 증명하려고 쓴 테스트가 실패했다.**
asgiref의 `AsyncToSync`는 자신이 `SyncToAsync` 스레드 안에서 호출됐으면 코루틴을 **원래 루프로
되돌려** 실행한다(`main_event_loop`을 `call_soon_threadsafe`로). 그래서 루프는 같다. probe가 모든
프레임에 `same_loop`을 적는 이유가 이것이고, 동기 미들웨어를 끼운 채 확인해도 `true`다.

실제 대가는 스레드 왕복이고, 크기는 이렇다. 동기 전용 미들웨어 하나를 끼우고 뺀 채 실제
`ASGIHandler`로 32 동시 요청 × 4회(128건)를 돌렸다.

| 구성 | 전체 시간 | 요청당 중앙값 | p90 |
| --- | --- | --- | --- |
| 전부 async-capable | 144~152 ms | 34~35 ms | 36~39 ms |
| 동기 전용 1개 | 154~180 ms | 35~41 ms | **44~50 ms** |

4회 반복에서 꼬리는 일관되게 나빠졌고 처리량은 몇 퍼센트 차이였다. **정확성 문제가 아니다.**
직렬 요청 하나만 재면 차이가 없다(중앙값 1.43 vs 1.41 ms).

그래서 이 변경의 근거는 두 가지이고, 무게 순서는 이렇다. (1) 애플리케이션 서버가 정적 자산을
나르는 것이 이 문제를 지금까지 가려 왔다 — 프록시는 이미 있고 그 일을 더 잘한다. (2) 그 미들웨어가
체인에서 유일한 동기 전용 항목이라, 빼면 요청 경로가 실제로 async가 되고 그 상태를 검사로 고정할 수
있다. WhiteNoise는 최신 릴리스(6.12)까지도 async 경로가 없다(이 저장소는 저장 백엔드용으로 6.10을
고정한다).

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
종류의 사실이 아니다. 어기면 **아무것도 실패하지 않고 아무 테스트도 빨개지지 않으며**, 남는 흔적은
부하가 걸릴 때의 느린 꼬리뿐이다.

uvicorn은 Django 검사를 돌리지 않으므로, 컨테이너 시작 명령이 `manage.py check`를 먼저 실행한 뒤
서버를 `exec`한다. 이게 없으면 이 검사는 CI에서만 도는 것이고, CI를 건너뛴 수정 하나가 요청 경로가
더 이상 async가 아닌 워커를 조용히 띄운다.

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

그래서 [probe 뷰](../../orders/views/stream_probe.py)는 프레임을 내보내기 전에 그 요청의
스레드에서 연결을 닫고, 닫혔는지를 같은 스레드에서 다시 물어 프레임에 적는다. `connections`는
스레드별 저장소라서, 다른 곳에서 물으면 편한 대답(`False`)이 그냥 나온다.

**이건 런타임의 성질이 아니라 이 뷰의 성질이다.** probe는 연결을 한 번 놓고 그 뒤로 DB를 건드리지
않는다. 10D1의 허브는 이벤트마다 revision·snapshot·세션을 읽으므로, 매번 다시 놓지 않으면 연결 수가
다시 화면 수를 따라간다. 아래 측정표의 "DB 연결 1"을 그 뜻으로 읽으면 안 된다.

`CONN_MAX_AGE`는 `0`으로 **명시했다.** 기본값이라 적지 않아도 같지만, 지금 구조에서는 0이 안전한
값이고 나중에 바꾸려는 사람이 이 주석과 먼저 부딪히는 편이 낫다. 다만 놓고-다시-여는 비용은 10D1이
이벤트마다 DB를 건드릴 때 처음 드러난다. 연결 재사용이나 pooler는 **10E에서 다시 볼 항목**이고,
이 결정이 그것을 닫지 않는다.

## 측정 (2026-09-20)

실제 `compose.prod.yaml` 스택을 전용 프로젝트 `bk10a-stream`, 합성 비밀값,
`127.0.0.1:8080`에서 띄우고 `curl -N`으로 측정했다. 운영 자격증명·실제 호스트는 쓰지 않았고
측정 후 컨테이너·볼륨·비밀 파일을 제거했다. 프로세스는 uvicorn 워커 3개였다.

측정은 산문이 아니라 [`scripts/stream_smoke.py`](../../scripts/stream_smoke.py)로 돌린다. 이
저장소가 `scripts/test_postgres.py`로 검증을 재현 가능하게 만들어 온 것과 같은 이유다 — 아무도 다시
뽑을 수 없는 숫자는 증거가 아니라 주장이다. 아래는 그 출력이다.

### 프레임이 끝나기 전에, 하나씩 도착한다

`frames=5&interval_ms=500`:

```
t+   75 ms  event: probe   {"db_open":false,"elapsed_ms":0,   "pid":10,"same_loop":true,"seq":0}
t+  578 ms  event: probe   {"db_open":false,"elapsed_ms":501, "pid":10,"same_loop":true,"seq":1}
t+ 1080 ms  event: probe   {"db_open":false,"elapsed_ms":1004,"pid":10,"same_loop":true,"seq":2}
t+ 1581 ms  event: probe   {"db_open":false,"elapsed_ms":1505,"pid":10,"same_loop":true,"seq":3}
t+ 2085 ms  event: probe   {"db_open":false,"elapsed_ms":2009,"pid":10,"same_loop":true,"seq":4}
t+ 2587 ms  event: done    {"frames":5}
```

프레임 간격 `[503, 502, 501, 504, 502] ms`. 첫 프레임은 요청 75ms 뒤에 도착했고 응답은
그로부터 2.5초 뒤에 끝났다. WSGI였다면 여섯 덩어리가 2587ms에 한꺼번에 왔다.

### 열린 스트림이 일반 API를 굶기지 않는다

| 열린 스트림 | 워커 스레드 합 | FD | DB 연결 | `GET /orders/menus/` (8회) |
| --- | --- | --- | --- | --- |
| 0 | 9 | 63 | 1 | 중앙값 20ms, 최대 33ms |
| 6 | 15 | 69 | 1 | 중앙값 21ms, 최대 25ms |
| 24 | 33 | 87 | 1 | 중앙값 22ms, 최대 31ms |
| 48 | 57 | 111 | 1 | 중앙값 19ms, 최대 21ms |
| 전부 종료 후 | 9 | 63 | 1 | — |

**이 probe를 48개 열어 두어도 DB 연결은 1이다**(유휴 기준선과 같다). 일반 API 지연도 변하지 않았다.
앞서 적었듯 연결이 늘지 않는 것은 이 뷰가 한 번 놓고 다시 읽지 않기 때문이고, 10D1에는 그대로
넘어가지 않는다.

**nginx 쪽 자원은 세지 않았다.** `proxy_read_timeout 1h`인 upstream 연결이 화면 수만큼 프록시에도
상주한다. 위 FD는 앱 컨테이너만의 숫자다.

### 스트림 하나는 스레드 하나를 차지한다 — 10D가 알아야 할 숫자

표에서 스레드 수는 정확히 열린 스트림 수만큼 늘어난다(9 → 15 → 33 → 57).

**원인은 인증이 아니다.** 이 문서의 초안은 "인증이 DB를 읽기 위해 만든 스레드"라고 적었는데, 계측해
보니 순서가 이렇다.

```
0: Signal.asend.<locals>.sync_send        thread_sensitive=True  live_threads=1
1: SecurityMiddleware.process_request     thread_sensitive=True  live_threads=2
...
8: login_view                             thread_sensitive=True  live_threads=2
```

`ASGIHandler`는 요청 하나 전체를 `ThreadSensitiveContext`로 감싸고, 그 안에서 제일 먼저
`request_started` 시그널을 보낸다. 거기 붙은 `reset_queries`·`close_old_connections`가 동기
리시버라 `sync_to_async`로 감싸지고, **그 순간 요청 전용 스레드가 만들어진다.** 요청 객체가 생기기도
전이고 미들웨어·인증보다 먼저다. 게다가 `MiddlewareMixin`의 `process_request`/`process_response`도
전부 그 스레드에서 돈다.

**왜 중요한가:** "인증 때문"이라고 읽으면 10D1이 자연스럽게 "인증을 async ORM으로 바꾸자"는 완화책을
꺼내는데, 그것으로는 스레드가 **하나도** 줄지 않는다. Django 5.2에서 요청당 1개는 구조적이고,
CSRF·인증 미들웨어를 체인에 남겨 두는 한(카드가 요구한다) 피할 수 없다. D-007에 넘길 문장은
"제거할 수 없으니 동시 화면 수가 곧 스레드 수"다.

블록된 스레드라 probe에서는 CPU를 쓰지 않았고 RSS 증가도 스트림당 약 90kB였다(48개에 +3.7MB).
**다만 10D1에서는 이 스레드가 놀지 않는다.** D-010/D-019가 요구하는 주기적 세션·권한 재확인과
snapshot 읽기가 그 스레드에서 실행되므로, 스트림 하나의 동기 작업이 전부 거기서 직렬화된다.

### 연결이 끊기면 정리된다

클라이언트를 죽이면 스레드 57 → 9, FD 111 → 63으로 **기준선까지 돌아왔다.** 제너레이터의
`finally`가 실행된다는 뜻이고, 10D1의 허브가 구독을 해제할 자리가 거기다.

다만 여기서 증명된 것은 `finally`에서 **정수 증가 하나와 슬롯 반납**이 실행된다는 것뿐이다. 허브
해제는 취소(`CancelledError`/`GeneratorExit`) 중에 실행되며 그 안에서 `await`(큐 해제, 연결 반납)를
해야 하는 경우가 실제로 새는 경로인데, probe는 그 경로를 만들지 않는다. 10D1이 직접 재야 한다.

### 재시작이 스트림에 걸려 멈추지 않는다

스트림을 연 채 `docker compose stop -t 30 app`은 **10.7초**에 돌아왔다.

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
| 보안 헤더 | `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `Cross-Origin-Opener-Policy: same-origin` |
| `/static/staticfiles.json` | **404** |
| 앱이 본 `/static/` 요청 수 | **0** |

보안 헤더는 그냥 따라온 것이 아니다. WhiteNoise가 미들웨어 체인 **안에서** 응답할 때는 모든 자산이
`SecurityMiddleware.process_response`를 거쳐 저 셋을 달고 나갔다. 프록시로 옮기면 체인 밖이 되므로
말없이 사라진다 — 미들웨어를 빼서 생기는 부작용 중 유일하게 보상이 필요했던 항목이고,
[`scripts/nginx_static_headers.conf`](../../scripts/nginx_static_headers.conf)가 그 자리를 메운다.
`X-Frame-Options`는 일부러 넣지 않았다. WhiteNoise는 `XFrameOptionsMiddleware`보다 먼저 응답했으므로
정적 응답은 원래도 그 헤더를 달지 않았다.

manifest(`staticfiles.json`)는 거부한다. Django가 앱 컨테이너에서 디스크로 읽으므로 HTTP로
내보낼 이유가 없다.

## 측정이 잡은 결함 하나

스트리밍 location에 `proxy_set_header Connection "";`을 넣자 프록시 경유 요청이 **400**으로
떨어졌다. nginx는 **자기 레벨에 `proxy_set_header`가 하나라도 있으면 상위의 것을 전부 상속하지
않는다.** 헤더 하나를 더한 것이 `Host`, `X-Forwarded-Proto`, `X-Forwarded-For`를 통째로 떨어뜨린
것이다. `Host`가 없어 `ALLOWED_HOSTS`가 거부해서 눈에 띄었지만, 눈에 띄지 않는 쪽이 더 나쁘다.
그 location의 로그인 실패는 전부 프록시 주소로 집계됐을 것이다(이슈 #61 상태로 복귀).

그래서 공통 헤더를 [`scripts/nginx_proxy_headers.conf`](../../scripts/nginx_proxy_headers.conf)로
빼고 **프록시하는 모든 location이 `include`한다.** server 레벨에는 `proxy_set_header`를 두지
않는다. 어디에나 적용되는 것처럼 읽히기 때문이다. 회귀 테스트가 이 둘을 같이 묶어 둔다.
`add_header`도 같은 규칙이라 정적 보안 헤더 역시 include 파일로 뒀다.

## 10D1이 빠질 함정 하나 (테스트로 막아 뒀다)

스트리밍 설정은 **URL prefix `/orders/api/stream/`에 붙어 있지, 그게 필요한 뷰에 붙어 있지 않다.**
10D1이 SSE 엔드포인트를 예컨대 `/orders/api/kitchen/events`에 두면 `location /`로 떨어져
`proxy_buffering on`과 60초 read timeout을 받는다. 프레임은 모였다가 한 번에 나가고 조용한 2분마다
연결이 끊긴다 — 10A가 존재하는 이유인 그 무증상 실패가 그대로 복귀한다.

그래서 스트리밍 뷰는 `streams = True`를 단다. 테스트가 URLconf에서 그 표시가 붙은 경로를 모아
nginx에서 `proxy_buffering off`인 location prefix와 대조한다. 표시가 하나도 없으면 그 테스트도
실패하므로, probe를 지우면서 조용히 무력해지지 않는다.

## probe는 기능이 아니다

[`orders/views/stream_probe.py`](../../orders/views/stream_probe.py)는 계측기다. 주문 데이터를 내보내지
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
- **워커당 동시 32개**를 넘으면 503과 `Retry-After`다. 프레임 상한은 스트림 하나의 길이를 묶지
  개수를 묶지 않는데, 스트림 하나가 스레드 하나이므로 그것만으로는 계정 하나가 워커의 스레드 수를
  마음대로 키울 수 있다(PR #76 보안 리뷰). 32는 튜닝값이 아니라 위 측정에 대고 고른 값이다 —
  워커 3개에 48개를 열어도 일반 API가 느려지지 않았으므로, 워커당 32는 편안하다고 확인된 선 위이고
  아프다고 볼 선보다 한참 아래다. 주방 화면의 진짜 상한은 D-007을 가진 10D1이 정한다.

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
없음, 인증·CSRF 미들웨어 잔존, 검사가 동기 전용 미들웨어를 이름으로 거부함, 설정 없이는 404,
404 판단이 자격증명보다 먼저, 인증 없으면 JSON 401, 인증되면 `text/event-stream`과
`X-Accel-Buffering: no`, 프레임 번호와 순서, 종료 이벤트, 상한 200, 읽을 수 없는 인자의 기본값
복귀, 제너레이터 종료, **트랜잭션 밖에서 DB 연결 해제**(`TransactionTestCase`),
**동시 개수 상한과 슬롯 반납**(읽히지 않은 응답 포함), **뷰와 제너레이터가 같은 루프**(동기
미들웨어를 끼운 채로도).

`orders/tests/test_runtime_config.py`: ASGI 진입점, **서버보다 먼저 도는 시스템 검사**,
`--no-proxy-headers`와 `--forwarded-allow-ips` 부재, graceful shutdown 상한, 스트리밍 location의
`proxy_buffering off`, **스트리밍 라우트가 그 location 안에 있음**, 정적 파일의 프록시 제공과 볼륨
없음, **프록시하는 모든 location의 공통 헤더 include**.

## 이 단계가 하지 않은 것

- **실제 SSE는 없다.** 이벤트 발생(10B), snapshot 정합(10C), 인증된 SSE 서버·허브(10D1),
  주방 클라이언트와 재접속(10D2)은 그대로 열려 있다.
- **브라우저로 확인하지 않았다.** HTTP/2·여러 탭·BFCache·백그라운드 복귀는 BK-R039로 12A1에
  남는다. 여기서 닫은 것은 프록시 buffering과 idle timeout뿐이다.
- **실제 호스트가 아니다.** EC2·TLS·백업·관측은 12A1/12A2다. 평문 HTTP에서는
  `JWT_COOKIE_SECURE=True` 때문에 브라우저 로그인이 되지 않는다는 4A3의 정정이 그대로 유효하다.
- **화면 수 상한을 정하지 않았다.** 스트림당 스레드 1개라는 숫자와 probe의 워커당 32라는 안전선만
  넘긴다. 목표 부하와 동시 접속 수는 D-007이다.
- **재시작의 thundering herd를 재지 않았다.** `--timeout-graceful-shutdown 10`은 배포마다 열린 화면을
  전부 동시에 끊으므로, 10D2가 붙으면 전원이 동시에 재접속하고 동시에 snapshot을 요청한다.
  10E/D-007의 부하 항목이다.
- **로컬 개발은 여전히 WSGI다.** `runserver`는 WSGI 전용이고 이 저장소에 daphne는 없다. 즉 10D1·10D2를
  쓰는 사람은 스트리밍이 한 덩어리로 모이는 런타임에서 SSE를 작성하게 된다. 10A가 운영에서 찾아낸
  함정이 개발 환경에는 그대로 남아 있으니, SSE 작업은 이 문서의 compose 절차로 확인해야 한다.
- 지원 PostgreSQL 버전·토폴로지·실제 호스트 사양은 계속 D-006/12A1에 남는다.
