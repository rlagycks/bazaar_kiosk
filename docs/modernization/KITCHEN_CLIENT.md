# 10D2 — 주방 SSE 클라이언트·재접속·응답 순서 (D-019, D-061)

브랜치 `phase-10d2-kitchen-client`, 기준 `develop` affc842. 상태: 구현 완료.

## 문제

10D1이 서버가 화면에 먼저 말하게 했다. 이제 화면이 들어야 하는데, 4B2 이후 주방 보드는
새로고침 버튼과 탭 복귀에만 읽는 수동 화면이었다. 붙이는 것 자체보다 어려운 것은 카드가
적은 대로 **"연결 성공만으로 복구 완료가 아니다"**라는 점이다. 연결이 CONNECTING에 걸려 있거나,
허브가 죽은 채 heartbeat만 오거나, 늦은 응답이 최신 화면을 덮거나, 로그아웃된 탭이 계속 읽는
경로가 전부 열려 있다. 그것이 BK-R020과 BK-R033이다.

## 사용자가 고른 것 (D-019의 마지막 관문)

> **"5초 후퇴 폴링"**, **"보이는 탭만 연결"**

## 설계 — 스케줄러 하나

`orders/static/orders/ui/kitchen_live.js`. 보드의 **읽는 시점**을 정하는 곳은 이 파일 하나이고,
페이지의 다른 어떤 코드도 읽지 않는다. 주문 데이터는 10C snapshot에서만 온다(스트림에는
payload가 없다, D-058).

```
poll while NOT (stream open AND hub_ok AND complete snapshot applied AND last read succeeded)
```

D-019 그대로다. heartbeat는 증거가 아니다 — 프레임마다 실린 `hub_ok`가 거짓이면 죽은 연결과
똑같이 폴링한다.

| 상황 | 동작 | 상태 줄 |
| --- | --- | --- |
| 페이지 열림 | 스트림 열고 snapshot 한 번 읽음. `ready`가 오면 한 번 더(연결 중 바뀐 것) | 연결 중 · 5초마다 다시 읽음 |
| `ready` + `hub_ok` + 완전한 snapshot | 폴링 멈춤 | **실시간 연결** |
| `change` | `since=` 커서로 읽기. 읽는 중 온 것은 하나로 합침 | 실시간 연결 |
| `heartbeat` `hub_ok:false` | 폴링 시작 | 서버 감지 지연 · 5초마다 다시 읽음 |
| snapshot `complete:false` (500건 상한) | 스트림이 건강해도 폴링 | 5초마다 다시 읽음 · 서버에 N건 대기 |
| 읽기 실패 | 카드 유지, 폴링 | 읽기 실패 · 화면은 hh:mm:ss 목록입니다 |
| `EventSource` CONNECTING | 브라우저 재시도에 맡김. 폴링 | 연결 중 · 5초마다 다시 읽음 |
| `EventSource` CLOSED (비 200·503·거절) | 2초→4초→…→30초 상한으로 직접 다시 엶. 폴링 | 연결 중 |
| `closed: unverified` | 같은 백오프로 재접속. 폴링 | 연결 중 |
| `closed: revoked` / `reauthenticate` | **전부 끝냄** — 스트림·타이머·읽기. 로그인으로 | 로그인 화면으로 이동합니다 |
| 읽기 중 `AuthenticationLost` | 위와 같음 (auth.js가 이미 로그인으로 보냄) | — |
| heartbeat 두 주기 침묵 | 죽은 연결로 보고 닫고 다시 엶 | 연결 중 |
| 탭 숨김 / `pagehide` | 스트림 닫고 폴링 멈춤. 진행 중 읽기는 늦은 것으로 | — |
| 탭 보임 / `pageshow` | 새 스트림 + 읽기 한 번 | 연결 중 → 실시간 연결 |
| `EventSource` 없는 브라우저 | 폴링만. 실시간이라 말하지 않음 | 연결 중 · 5초마다 다시 읽음 |

### 응답 역전은 버전이 아니라 epoch으로 막는다

카드는 "같은 세대 43→42 역전 방어"를 `appliedRevision`으로 요구했다. 그런데 D-059의
버전은 **비교하는 것이지 순서를 재는 것이 아니다** — generation이 돌면 숫자가 어디로든
떨어진다. 그래서 순서는 서버 버전이 아니라 클라이언트의 두 숫자로 정한다.

- **읽기는 한 번에 하나.** 읽는 중 온 요청은 "끝나면 한 번 더"로 합쳐진다. 같은 epoch 안에서는
  역전이 생길 **수 없다** — 두 번째 읽기는 첫 번째가 적용된 뒤에야 나간다.
- **일시정지가 epoch을 올린다.** 탭을 숨긴 채 응답이 오는 중이고, 다시 보여 새 읽기가 먼저
  적용되면, 옛 응답은 epoch이 달라 버려진다. 테스트가 이 순서를 정확히 재현한다.

### 쓰기 응답은 그리지 않는다

BK-R033의 경합은 목록 읽기와 단건 읽기라는 **두 경로**가 있어서 생겼다. 이제 PATCH 뒤에는
응답을 그리지 않고 같은 스케줄러에 읽기를 요청한다. 거절(409)을 받아도 마찬가지다 — 다른
사람이 이미 바꿨을 수 있다. 경로가 하나라 늦은 목록이 덮을 최신 단건이 없다. 왕복 하나가
늘지만 `since=`가 있어 대개 `unchanged`(4왕복·1ms)다.

### 보이는 탭만 연결한다

TLS 전(12A1)이라 HTTP/1.1이고 브라우저는 출처당 연결을 약 6개로 제한한다. 주방 탭 6개면
snapshot 요청 자체가 막힌다. 서버도 워커당 24개가 상한이다(10D1). 숨겨진 탭은 낡은 보드를
가장 안 보는 곳이기도 하다. `pagehide`에 닫는 것은 BFCache 때문이다 — 열린 연결을 쥔
페이지는 캐시되지 않고, 캐시에서 돌아온 페이지는 그동안을 전부 놓쳤다.

## 구현

| 조각 | 파일 |
| --- | --- |
| 스케줄러 | `orders/static/orders/ui/kitchen_live.js` (`window.BazaarLive.create`) |
| 보드 | `orders/templates/orders/kitchen_supervisor.html` — 목록·단건 fetch 제거, snapshot만 |
| 인증 상실 이름 | `orders/static/orders/ui/auth.js` — 던지는 오류에 `name = 'AuthenticationLost'` |
| 스케줄러 테스트 | `scripts/test_kitchen_live.cjs` (CI의 `node --test`에 추가) |
| 서버 왕복·배선 테스트 | `orders/tests/test_realtime.py` |
| 4B2 울타리 | `orders/tests/test_external_realtime.py` — 타이머는 스케줄러에만, 스트림은 같은 출처만 |
| 실제 브라우저 | `scripts/kitchen_board_browser.mjs` (headless Chrome, CDP) |

`test_external_realtime.py`의 타이머 울타리는 4B2가 "10D2에서 만료된다"고 적어 둔 것이다. 없애지
않고 **어디에 타이머가 살아도 되는지**로 바꿨다: `kitchen_live.js`에만, 단발(`setInterval` 금지),
그리고 스트림이 건강하면 멈춘다(노드 테스트). 템플릿에는 `setTimeout`도 `visibilitychange`도
없다.

## 검증

- **스케줄러 20건** (`node --test scripts/test_kitchen_live.cjs`): 가짜 시계·스트림·fetch로
  CONNECTING/CLOSED, `unverified` 백오프 2·4·8·16·30·30, `revoked`/`reauthenticate` 종료,
  읽기 중 인증 상실, 읽기 실패 후 카드 유지, 침묵 감지, 숨김/`pagehide`/`pageshow`, 늦은 응답
  폐기, 버스트 합치기, `complete:false`, `EventSource` 없음.
  **변이 3종이 각각 하나를 실패시킨다:** `hub_ok`를 무시 → heartbeat 테스트, epoch 검사만 제거 →
  "숨긴 채 도착한 응답" 테스트(리뷰 반영으로 추가, 아래), `revoked`를 재접속으로 → 종료 테스트.
- **격리 PostgreSQL: 마이그레이션 26건 + 애플리케이션 528건 통과** (10D2 신규 11건 + 울타리
  7건 재작성). 신규 왕복 테스트는 실제 스트림을 열고 이 연결에서 PATCH해 `change`가 오고
  `ready`의 버전으로 읽은 snapshot이 새 상태를 답하는 것을 확인한다.
- `manage.py check` 이상 없음, `makemigrations --check` 변경 없음. **스키마 변경 없음.**
- **실제 브라우저 (V-BROWSER, 17건 통과).** Chrome 확장·Playwright 브리지가 모두 연결되지
  않아(4B2와 같음) 로컬 Chrome을 headless로 띄우고 DevTools 프로토콜로 직접 구동했다. 격리
  PostgreSQL 위의 일회용 DB에 uvicorn(ASGI) 1워커, 정적 파일만 개발용 래퍼로 서빙.

| 확인 | 결과 |
| --- | --- |
| 로그인 뒤 보드가 스스로 `실시간 연결` | 열자마자. 스트림 1개, snapshot 읽기 2회(초기 + `ready`), 목록·단건 API 호출 0 |
| 다른 연결에서 커밋한 주문 | **0.6~1.7초** 뒤 카드 표시(허브 폴 1초 + snapshot). 새로고침 없음 |
| `+1` | PATCH → snapshot 읽기 순서 확인, 152ms 뒤 `완료 1 / 2` |
| 탭 숨김 | 스트림 닫힘, `running:false`, 타이머 없음 |
| 탭 보임 | 새 스트림, 154ms 뒤 다시 실시간 |
| 취소 | snapshot을 통해 카드 사라짐 |
| 서버를 SIGKILL | 154ms 뒤 `연결 중 · 5초마다 다시 읽음` |
| 서버 복구 | **3.1초** 뒤 새로고침 없이 `실시간 연결`(백오프 2초 + 연결). 그 뒤 변경도 1.1초에 도착 |
| 다른 곳에서 계정 비활성화 | **0.5~0.6초** 뒤 로그인 화면으로 (허브가 다음 이벤트 전 재인가) |
| 페이지 오류 | 0 |

**우연히 본 것 하나.** 처음에는 SIGTERM으로 서버를 죽였는데 보드가 40초 동안 "끊김"을
감지하지 못했다. uvicorn이 정상 종료(graceful) 중 열린 스트림을 끝까지 기다리기 때문에 —
`--timeout-graceful-shutdown` 없이 — **스트림은 살아 있고 새 요청만 거절**되는 상태였다. 보드는
그걸 "읽기 실패 → 폴링"으로 맞게 처리했고, 운영 스택은 10A가 그 플래그를 두어 재시작을 묶는다.
스크립트는 케이블이 뽑힌 경우를 재현하도록 SIGKILL을 쓴다.

## 리뷰 반영

- 코드 리뷰 HIGH 1: **epoch 검사에 자기만의 테스트가 없었다.** 제가 "epoch 검사를 빼면 실패한다"고
  적은 변이는 seq 검사까지 같이 뺀 것이었다. epoch만 빼면 18건이 전부 통과했다 — "숨김 → 보임 →
  새 응답 먼저 → 옛 응답" 시나리오는 요청 순번(seq)만으로도 막히기 때문이다. epoch이 진짜로
  하중을 받는 것은 **숨긴 채로 옛 응답이 도착하는** 경우(새 읽기가 아직 없어 seq가 도울 수 없다)고,
  거기엔 테스트가 없었다. 추가했고, 이제 epoch만 빼면 그 테스트가 실패한다.
- 코드 리뷰 MEDIUM: 읽기가 계속 실패하는 동안 `change`마다 같은 오류를 두 번씩 로그했다(읽기 시작·
  실패 보고 각각). 오류가 바뀔 때만 로그하고 복구도 한 줄 남기도록 바꿨다.
- 코드 리뷰 LOW: 탭을 다시 보일 때 백오프 지연을 초기화하지 않았다. 새 탭은 옛 스트림의 실패로
  벌받지 않도록 2초부터 다시 시작한다(테스트 추가).
- 보안: CRITICAL/HIGH/MEDIUM 없음. LOW 하나 — 브라우저 스크립트가 대상 DB가 일회용인지
  확인하지 않았다. 모든 쓰기 전에 DB 이름이 `bk_dev*`/`bk_test*`가 아니면 거부하도록 넣었다.
  확인하고 문제없다고 한 것: 같은 출처 검사(스케줄러·auth.js 양쪽), `since=` 커서가 서버 응답에서만
  오는 점, 상태 줄이 `textContent`만 쓰는 점, 읽기 하나·백오프 상한으로 증폭 경로가 없는 점,
  회수 뒤 stale 탭이 `resume`으로 되살아나지 않는 점.

## 이 단계가 하지 않은 것

- **렌더링은 여전히 문자열 조립 + `escapeHtml`이다.** 11단계가 DOM 헬퍼로 옮긴다.
- **다중 워커 전달 미측정**(10D1과 같음). 브라우저 검증은 uvicorn 1워커였다.
- **실제 프록시 경유 없음.** nginx의 비버퍼링 위치는 10A가 probe로 확인했고 이 경로는 같은 위치
  아래에 있지만, 이 화면으로 실제 nginx를 통과시키지는 않았다(BK-R039, 12A).
- **요청 제한 없음.** 12A1.
- **모바일·실기기 없음.** headless Chrome 데스크톱 한 종류다.

## 다음

- 10E: 부하 검증. 변경당 비용은 10D1의 `W × (1 + 7K)`에 화면당 후퇴 폴링(장애 시에만)이 더해진다.
- 11: 보드 렌더링을 `BazaarDom`으로, `selectors`를 `services/`로.
