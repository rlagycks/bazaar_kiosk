# 현대화 작업 로그

각 항목은 새 세션에서도 이해할 수 있도록 짧되 충분하게 작성합니다. 최신
항목이 위에 오도록 합니다.

## 2026-09-22 — PR82 머지 확인·UI-05C 다음 PR 준비

- 사용자: “해당 pr 머지했고 다음 작업 진행하자 남은거 뭐뭐 있는지는 텍스트로 보고하고
  피그마 5안 대로 가는거지?” 기존 PR 단위 작업 흐름에 따라 UI-05C를 다음 PR로 준비한다.
- GitHub에서 PR82 MERGED, develop `e61d6ab`, 머지 시각 2026-09-22 07:06:15 UTC를 확인했다.
  이전 검증 기준 `37b8473`과 develop의 전체 tree는 `44c07d25`로 동일하다.
  미공개 통계 커밋만 develop 위로 재배치했고 이전 `a865f17`과 전체 diff가 없음을 확인했다.
  이미 공개한 브랜치 이력은 재작성하지 않았다.
- 기존 검증(격리 PG 622·Node 98·PC 브라우저·독립 리뷰)을 유지한다. 기준 정리 후 집중 Node
  13개와 diff 검사를 통과했다. 코드가 동일하므로 로컬 전체 검사를 불필요하게 반복하지 않았다.
- 05안이 계속 구현 기준임을 재확인했다. 관리자 Django 화면의 새 디자인이나 CSV·실시간 통계 등
  추가 기능은 채택 범위에 자동 포함하지 않는다. 남은 구현·운영 인수는 텍스트로 보고한다.
- merge·배포·운영 데이터 변경은 하지 않는다. UI-05C의 최종 PR 링크·CI는 실제 제출 결과를 따른다.

## 2026-09-22 — UI-05C: 누적·통계 PC와 조회 실패 복구

- 사용자 승인: PR 제출·리뷰와 다음 UI 작업 병행. 별도 worktree
  `/Users/gimhyochan/system/bazaar_kiosk-ui05c`, 브랜치 `ui/05-stats-dashboard`를 만들었다.
  PR82의 수량 원복 충돌 보완까지 기반 `37b8473`에 포함했다. PR82에 UI-05C를 넣지 않았으며
  통계 변경은 로컬이다. merge·운영 마이그레이션·배포를 하지 않았다.
- Figma `2135:1187` 누적·통계 PC의 design context와 스크린샷을 확인했다. 공통 05안 색·글꼴·
  버튼·내 메뉴, 4개 요약 카드, 수납 내역, 시간대 차트/접근 가능한 수치 표, 메뉴별 표를 적용했다.
  기존 인라인 통계 코드를 `stats.js`/`stats_state.js`로 분리했다. 외부 차트·폰트 의존성은 없다.
- D-064: 서버 집계/기간/권한 의미 유지, `hourly.date` 추가. 실패 시 기존 결과와 실제 적용 기간
  유지, 미제출 날짜 입력 보존, 응답 역전 방지, 확인된 0건과 실패 구분, 명시적 재시도를 구현했다.
  API 문자열은 안전한 DOM 텍스트로 렌더링한다. 새 쓰기 경로나 DB 마이그레이션은 없다.
- 백엔드 날짜 필드·회귀/페이지 검사를 별도 에이전트에 위임했다. 독립 code-reviewer가
  통계 프런트/백엔드를 검토했고 신규 결함을 발견하지 못했다.
- 검증: 집중 PostgreSQL 45개 통과. Node 전체 CI 명령에 `scripts/test_stats_ui.cjs`를 포함해
  **98개** 통과(통계 13개). API/일반 텍스트 오류, malformed 200, 초기 실패, 요청 역전,
  재시도, 빈 결과, 음수 순현금, 날짜별 차트, 저장 문자열을 검증했다.
- 통계만 추가한 최초 PostgreSQL 전체 **615개(27+588)** 통과. 리뷰 보완 통합 후 최종 **622개(27+595), skip 0** 통과.
  Django check·migration drift·`git diff --check`·변경 문서의 로컬 링크 검사도 통과했다. 실행 명령: `BK_TEST_DATABASE_URL=<전용 fixture URL> /Users/gimhyochan/system/bazaar_kiosk/.venv/bin/python scripts/test_postgres.py`.
  전용 Compose는 `bk-ui05c-0922`, 포트 55463이며 테스트·브라우저용 UUID DB만 사용했다.
  로그는 `.venv/ui05c-node.log`, `.venv/ui05c-integrated-pg.log`에 미추적으로 보관한다.
- 브라우저: 합성 계정/날짜별 주문으로 1440×1000/1024×768을 확인했다. 기본일 4건·매출
  18,000원·현금 6,000원·거스름돈 1,000원·순현금 5,000원·식권 8,000원과 일치했다.
  과거 혼합 1건 5,000원은 별도 경고, 매출 포함·수납 제외를 확인했다. 취소 1건·연습 제외,
  두 날짜 같은 10시 구분·수치 표, 0건의 0%/0%, 역전 기간 오류/재시도 후 이전 결과 보존,
  정상 기간 재조회·기본일 복귀, 통계 권한만의 내 메뉴·Escape 초점 복귀·POST 로그아웃을 검증했다.
  HTML 형태 메뉴명은 글자로만 나왔고 페이지 가로 넘침은 없었다. 검증 탭·viewport를 정리했다.
- 첫 preview의 테이블 필수 제약 누락과 잘못된 합성 혼합 결제 코드를 fixture에서 바로잡았다.
  애플리케이션 제약·집계 규칙은 바꾸지 않았고 올바른 CASH_TICKET 데이터로 경고를 재확인했다.
- 문서: UI_STATS·UI_IMPLEMENTATION·REPORTING·DECISIONS·README·BLUEPRINT·SESSION_SETUP 갱신.
  남은 범위: PR82 합병 후 통계 PR 비교 기준 정리, 실기기/음성 스크린리더 인수, 10E 부하·12 운영 인수.
  Django 관리자 재디자인, 새 정산 규칙, 실시간 통계는 이번에 추가하지 않았다.

## 2026-09-22 — PR82 독립 리뷰: 수량 원복 후 오래된 요청 재전송 차단

- UI-05B를 develop 대상 [PR82](https://github.com/rlagycks/bazaar_kiosk/pull/82)로 제출했다.
  최초 제출 `cd82dbb`의 GitHub CI가 통과했다. merge·운영 적용·배포는 하지 않았다.
- 독립 리뷰 HIGH 1건: PREPARING 중 수량을 0→1→0으로 바꾸면 주문 시각은 그대로여서 원래
  `monitor_version`이 다시 유효해질 수 있었다. 원래 요청 재전송이 다른 직원의 정정을 덮을 수 있다.
- 실제 수량 변경은 모니터링·기존 품목 API 모두 주문 잠금/트랜잭션 안에서 `updated_at`을 갱신한다.
  관리자 품목 변경도 기존 서비스를 통해 갱신하며 무변경 관리자 저장은 버전·revision을 보존한다.
  수량 원복 재전송 409, 무변경, 동시 수량 저장 한 번만 성공, 실패 시 시각/수량 롤백 회귀를 추가했다.
- 검증: 집중 PostgreSQL 95개, 전체 `BK_TEST_DATABASE_URL=<전용 fixture URL> .venv/bin/python scripts/test_postgres.py`
  **612개(27+585), skip 0** 통과. Django check·migration drift·`git diff --check` 통과.
  변경은 Python/문서이며 기존 Node 85개·브라우저 검증은 앞선 UI-05B 기록을 따른다.
  독립 재리뷰에서 원래 HIGH 해결·추가 지적 없음. 결과 로그 `.venv/ui05b-review-pg.log`는 미추적이다.
- 다음 UI-05C는 별도 `ui/05-stats-dashboard` 브랜치/worktree에서 병행한다. PR82에 포함하지 않는다.

## 2026-09-22 — UI-05B PR 제출·독립 리뷰와 UI-05C 병행 승인

- 사용자 지시: “pr 올리고 서브에이전트로 리뷰 돌리자 동시에 다음 ui 쪽 작업 시작하자”.
  UI-05B commit/push 및 develop 대상 PR 제출을 승인했다. merge·배포는 포함하지 않는다.
- UI-05B 검증 완료 변경만 제출하며, 다음 UI-05C는 별도 worktree/브랜치에서 진행한다.
  리뷰 결과와 후속 수정·UI-05C 검증은 각 브랜치의 이후 기록을 따른다.

## 2026-09-22 — UI-05B: PC 모니터링·준비 수량·명시적 서빙 출발

- 사용자: PR81 머지 후 “다음 부분 ui 랑 로직 구현작업 진행”. 실제 PR81 MERGED 및 clean
  develop `ea1c77e`를 확인하고 `ui/05-monitoring-workflow` 브랜치를 만들었다. 로컬 구현·검증 범위이며
  이번 브랜치 commit/push/PR/merge·운영 마이그레이션·배포는 하지 않았다.
- Figma 05안 `2135:1037`(모니터링), `2202:2203`(상세)의 design context를 읽었다.
  식당·포장·전체 화면에 미완료 가로 목록, 50건씩 전체 내역, 준비 수량 상세, 내 메뉴를 적용했다.
  화면 인라인 코드를 `monitor.js`/`monitor_state.js`로 추출하고 안전한 DOM 생성으로 통일했다.
- D-063: 수량 충족만으로 READY가 되지 않는다. 명시적인 출발 확인이 모든 품목 준비·READY·
  출발 시각을 함께 기록한다. 재개는 수량 유지·출발 시각 제거, 취소는 최종·이력 조회만 가능.
  기존 READY·일반 상태 API 완료에 출발 시각을 추정하지 않는다. nullable 0030만 추가했다.
- 주문 잠금 후 버전 비교, 전체 품목 검증, 변경·감사 이벤트·revision의 원자성을 구현했다.
  조회는 같은 REPEATABLE READ에서 미완료+페이지 내역을 직렬화한다. 커서를 권한·범위·페이지·
  표현 버전·DB 세대에 결속하고 기존 SSE 스케줄러만 사용한다. 새 writer도 변경 감지 목록에 등록했다.
- 읽기/쓰기 구현을 분리 위임하고 통합했다. 독립 code-reviewer가 찾은 HTML data 키 불일치,
  미저장 수량의 재개/목록 이탈 시 유실, 탭 복귀 직후 오래된 값으로 버튼이 활성화되는 문제를
  수정하고 회귀를 추가했다. 최종 재검토에서 actionable finding 없음.
- 첫 전체 검증에서 최신 migration 기대값·기존 인라인 템플릿 검사·writer 분류 누락을 발견했다.
  검사 대상을 추출 controller/새 schema에 맞췄고, 동작 검증은 실제 이벤트 기반 Node 테스트로 보강했다.
  권한 없는 계정의 최초 로그인은 원래 금지이므로 권한 16조합 검사는 로그인 후 권한을 변경하는
  기존 인증 계약에 맞춰 수정했다. 비즈니스 규칙을 테스트 편의상 바꾸지 않았다.
- 주요 파일: models/core·migration0030; services/status·monitoring_actions·monitoring_snapshot;
  views/monitoring·monitoring_actions·serializers·pages·urls; kitchen_supervisor·monitor CSS/JS/state;
  새 monitoring PG/Node 테스트와 기존 상태/감사/관리자/보안/SSE/마이그레이션 회귀; CI.
  문서 UI_MONITORING(신규), UI_IMPLEMENTATION, DECISIONS, ORDER_STATE, KITCHEN_CLIENT,
  README, SESSION_SETUP, BLUEPRINT를 현재 단계로 갱신했다.

### 검증 결과

전용 Compose `bk-ui05b-0922`, PostgreSQL 15, 포트 `55462`와 UUID fixture DB만 사용했다.
실제 운영 DB/자격증명은 사용하지 않았다. 테스트·preview 종료 후 해당 프로젝트를 정리했다.

```sh
BK_TEST_PG_PORT=55462 docker compose -p bk-ui05b-0922 -f compose.test.yaml up -d --wait postgres
BK_TEST_DATABASE_URL=postgresql://bk_test_runner:synthetic-local-runner-only@127.0.0.1:55462/bk_test_control .venv/bin/python scripts/test_postgres.py
node --test scripts/test_auth_client.cjs scripts/test_dom_helpers.cjs scripts/test_request_id.cjs scripts/test_kitchen_live.cjs scripts/test_order_state.cjs scripts/test_order_controller.cjs scripts/test_monitor_state.cjs scripts/test_monitor_controller.cjs
BK_TEST_PG_PORT=55462 docker compose -p bk-ui05b-0922 -f compose.test.yaml down --volumes
```

- Django system check 정상, migration drift 없음. 전체 **27 migration + 578 application = 605건** 통과,
  skip 0. PostgreSQL 실제 동시 쓰기·rollback·16조합 권한·CSRF·stale·500건·페이지·동시 snapshot 포함.
- 최종 Node **85건** 통과. 이후 변경한 controller 관련 Python 정적 연결 검사 23건도 통과.
  `git diff --check`, 수정 문서 상대 링크·코드 구문 검사 정상.
- 실제 브라우저: 격리 ASGI preview, 합성 주문 55건/페이지 2개/메뉴 악성 문자열로 검사했다.
  전체→식당→포장 업무 이동, 상세 +/- 및 부분 수량 저장, 출발 확인/일괄 수량 완료/시각 기록,
  이력 유지·재개·취소 확인·취소 내역 조회 전용·빈 미완료 목록을 확인했다.
- PC 1440×1000과 1024×768에서 확인했다. 작은 PC에서 문서 너비 1024px, 모달 top16/bottom752,
  버튼 영역 bottom751로 화면 안에 있고 본문만 스크롤한다. 상세 제목/입력 label/확인 초기 초점과
  안전한 텍스트 출력을 확인했다(`img`/`script` 노드 생성 0).
- 두 탭 검증: 한 탭에서 #002 수량 1을 입력하고 다른 탭에서 출발 처리했다. 원래 탭 복귀 후
  입력 1 유지, “주문이 변경되었습니다” 안내, 저장 비활성화를 확인했다. 새 탭은 종료했다.
- preview 종료 정상·fixture DB 제거, 생성한 브라우저 탭 정리 및 viewport 복원.
  로컬 로그/preview는 무시되는 `.venv/ui05b-*`에만 남고 커밋 대상이 아니다.

### 남은 범위와 다음 단계

UI-05B 로컬 구현·검증 완료. PR 제출은 다음 사용자 지시에서 진행한다. 다음 독립 UI 구현은
**UI-05C 누적·통계 PC**다. 운영 적용에는 0030이 필요하다. 이전 앱은 schema를 읽을 수 있어도
자동 READY 의미로 되돌아가므로 안전한 복구는 쓰기 중지 후 정방향 수정이다(UI_MONITORING).
운영 부하 10E, 실기기·음성 스크린리더 및 운영 인수 12는 완료하지 않았다.

## 2026-09-21 — 10D2 주방 SSE 클라이언트·재접속·응답 순서 (D-061)

- 브랜치 `phase-10d2-kitchen-client`, 기준 `develop` affc842(PR #79 병합 직후). 관문 둘을 물었고
  사용자가 **"5초 후퇴 폴링"**과 **"보이는 탭만 연결"**을 골랐다(D-061). 이로써 D-019는 전부 확정됐다.
- **읽는 시점을 정하는 곳을 하나로 줄였다.** `orders/static/orders/ui/kitchen_live.js`가 스트림·폴링·
  재접속·탭 수명을 전부 맡고, 보드는 10C snapshot만 읽는다. 목록 fetch와 단건 fetch를 없앴다 —
  BK-R033의 "늦은 목록이 최신 단건을 덮는" 경합은 경로가 둘이라 생겼고, 하나가 되면 막을 것이
  없다. 쓰기 응답도 그리지 않고 같은 스케줄러에 읽기를 요청한다.
- **폴링 규칙은 D-019 문장 그대로다:** 스트림 open + `hub_ok` + 완전한 snapshot + 마지막 읽기 성공이
  아니면 5초마다 `since=` 커서로 읽는다. heartbeat 수신은 조건이 아니다.
- **응답 역전은 버전이 아니라 epoch으로 막았다.** 카드가 요구한 "같은 세대 43→42 방어"를 버전
  대소로는 할 수 없다(D-059의 버전은 순서가 없다). 읽기를 한 번에 하나로 두고, 일시정지(숨김·
  `pagehide`)가 epoch을 올려 그 전 응답을 버린다. 테스트가 "숨긴 채 응답 지연 → 보임 → 새 응답
  먼저 → 옛 응답 도착"을 그대로 재현하고, epoch 검사를 빼면 실패한다.
- `closed` 사유별 동작: `revoked`/`reauthenticate`는 모든 것을 끝내고 로그인으로, `unverified`와
  전송 CLOSED는 2→4→…→30초 백오프, CONNECTING은 브라우저에 맡기고 폴링. heartbeat 두 주기
  침묵은 죽은 연결로 본다. `EventSource`가 없는 브라우저는 폴링만 하고 실시간이라 말하지 않는다.
- `auth.js`는 한 줄만 바뀌었다 — 로그인으로 보내며 던지는 오류에 `name = 'AuthenticationLost'`를
  붙여 스케줄러가 "이미 떠나는 중"과 "다시 시도할 실패"를 구분한다.
- 4B2가 "10D2에서 만료"라고 적어 둔 타이머 울타리(`test_external_realtime.py`)는 없애지 않고
  "어디에 살아도 되는지"로 바꿨다: `kitchen_live.js`에만, 단발만, 템플릿에는 `setTimeout`도
  `visibilitychange`도 없음.
- 변경 파일: `kitchen_live.js`(신규)·`kitchen_supervisor.html`·`auth.js`, 테스트
  `scripts/test_kitchen_live.cjs`(신규, CI 추가)·`orders/tests/test_realtime.py`(신규)·
  `test_external_realtime.py`, `scripts/kitchen_board_browser.mjs`(신규), 문서 `KITCHEN_CLIENT.md`(신규)·
  `DECISIONS.md`(D-061, D-019 확정)·`BLUEPRINT.md`·`RISK_REGISTER.md`(R020/R033/R037/R038)·`README.md`·
  `SSE_SERVER.md`. **마이그레이션 없음.**
- 검증: 스케줄러 Node 테스트 **20건**(변이 3종 — `hub_ok` 무시·epoch만 제거·`revoked` 재접속 — 각각
  하나를 실패시킴), 격리 PostgreSQL **마이그레이션 26건 + 애플리케이션 528건 통과**(신규 11건),
  `manage.py check`·`makemigrations --check` 이상 없음.
- **V-BROWSER 실행함.** Chrome 확장·Playwright 브리지가 둘 다 연결되지 않아(4B2와 같음) 로컬
  Chrome을 headless로 띄우고 DevTools 프로토콜로 직접 구동했다(`scripts/kitchen_board_browser.mjs`,
  의존성 없음). 격리 PG의 일회용 DB + uvicorn 1워커. **17건 통과:** 다른 연결의 커밋이 0.6~1.7초 뒤
  표시, `+1`은 PATCH→snapshot 순서로 152ms, 탭 숨김에 스트림 닫힘·보임에 154ms 뒤 실시간, 서버
  SIGKILL 뒤 154ms에 "연결 중 · 5초마다 다시 읽음", 복구 3.1초 뒤 새로고침 없이 실시간, 비활성화
  0.5초 뒤 로그인 이동, 페이지 오류 0.
- **우연히 본 것:** SIGTERM으로 죽인 uvicorn은 열린 스트림을 기다리는 정상 종료 상태가 돼 스트림은
  살고 새 요청만 실패했다. 보드는 "읽기 실패 → 폴링"으로 맞게 처리했다. 운영 스택은 10A가
  `--timeout-graceful-shutdown`으로 이 창을 묶어 둔다.
- 코드 리뷰: HIGH 1 — **epoch 검사에 자기만의 테스트가 없었다.** 제가 돌린 변이는 seq 검사까지 같이 뺀
  것이라 잡혔고, epoch만 빼면 18건이 전부 통과했다. "숨긴 채로 옛 응답이 도착"하는 경우(새 읽기가 없어
  seq가 못 막는 유일한 경우)를 테스트로 추가해 닫았다. MEDIUM(실패 중 `change`마다 오류 로그 2회)·
  LOW(재개 시 백오프 미초기화)도 반영.
- 보안 리뷰: CRITICAL/HIGH/MEDIUM 없음. LOW 1(브라우저 스크립트의 대상 DB 확인) 반영 — DB 이름이
  `bk_dev*`/`bk_test*`가 아니면 모든 쓰기를 거부.
- **PR #80 리뷰 반영(코드·보안·아키텍처, CRITICAL/HIGH 없음).** 아키텍처 리뷰가 **제가 쓴 근거 하나를
  반증했다** — "D-059의 버전은 순서가 없다"는 generation을 넘을 때만 참이고, 같은 세대 안에서는 D-058의
  잠긴 행이 순서를 만든다. 비교가 불가능한 게 아니라 읽기가 하나라 불필요한 것이었다. DECISIONS·
  BLUEPRINT·KITCHEN_CLIENT·SSE_SERVER·RISK의 문장을 바로잡았다. 코드 세 곳: (MEDIUM) `applied`를 `onApply`
  전에 기록해 렌더가 던지면 안 그린 버전으로 `unchanged`를 받아 "실시간" 아래 얼어붙던 경로 — 순서를
  바꾸고 테스트 추가. (MEDIUM) 상태 보고마다 보드 전체를 `innerHTML`로 다시 그려 heartbeat마다 카드
  노드를 버리고 쓰기 중 비활성화한 버튼을 새 것으로 바꾸던 것 — 상태 줄만 갱신, 울타리 테스트. (MEDIUM)
  "프레임마다 `hub_ok`"는 거짓(`change`에는 없다) — `change` 도착을 허브 정상의 증거로 삼아 첫 구독자의
  `ready`가 거짓을 실었을 때 바쁜 주방이 계속 폴링하던 경로를 닫음. (LOW) `heartbeat_ms` 누락 시 침묵
  감지가 꺼지던 것 — 15초 fallback. (LOW) 재접속 지터(줄이는 방향만). 테스트 공백 둘(취소 뒤 늦은 목록,
  PATCH와 늦은 목록 경합)은 노드 테스트로 수렴 순서를 고정했고, 실제 브라우저는 응답을 붙들 수 없어
  재현하지 못한다고 적었다. 브라우저 스크립트는 건너뛴 단계를 통과와 따로 센다. `auth.js` 409 백오프가
  타이머 울타리의 예외임을 테스트와 문서에 명시. 노드 25건.
- 남은 것: 렌더링 문자열 조립(11), 실제 프록시 경유·다중 워커(12A), 요청 제한(12A1), 모바일 실기기,
  실제 `pagehide`/`pageshow`, 첫 구독자 `ready`의 `hub_ok` 경합 테스트, `expires_at`·`id:` 테스트(10D1 인계).
  검사 후 개발 서버·일회용 DB·compose 프로젝트는 제거했다.

## 2026-09-21 — 10D1 인증된 SSE 서버·허브와 세션 회수 (D-060)

- 브랜치 `phase-10d1-sse-hub`, 기준 `develop` 4010690. 관문 둘을 먼저 물었고 사용자가
  **"EventSource + 리프레시 쿠키"**와 **"이벤트마다 재확인"**을 골랐다(D-060).
- **이 단계가 다른 단계와 다른 점 하나.** 요청은 한 번 인가되고 끝난다. 스트림은 한 번
  인가되고 저녁 내내 열려 있다. 나머지 시스템이 "요청마다 DB를 다시 읽는다"에서 공짜로 얻던
  보장을 전부 의도적으로 다시 세워야 했고, 그래서 이 단계의 테스트는 대부분 스트림을
  **먹이는** 것이 아니라 **끝내는** 것에 관한 것이다.
- **쿠키를 고른 이유는 `EventSource`가 헤더를 못 붙이기 때문만이 아니다.** 대안인
  fetch+ReadableStream은 재접속·백오프·프레임 파싱·BFCache를 전부 직접 쓰게 만드는데, 그게
  BK-R020/033이 말하는 표면 그 자체다. 리프레시 쿠키는 HttpOnly라 스크립트가 닿지 못하고,
  회전시키지 않는다(읽기이고 다른 탭과 경합한다). 거절은 **JSON**이어야 한다 — 로그인
  리다이렉트를 `EventSource`는 불투명한 실패로 보고 **영원히 재시도**한다.
- **"이벤트마다 재인가"를 묶음 조회로 감당한다.** 변경 하나가 N개 화면을 깨울 때 기기 행을
  N번이 아니라 한 번에 읽는다. 고른 의미는 그대로고 비용만 변경당으로 묶인다. 10A가 경고한
  "연결 수가 열린 화면 수를 따라가는" 경로를 이렇게 피했다.
- **승인된 문서 둘이 충돌해서 해소했다.** 10D1 카드는 "발생 빈도 정보 노출 거부"를 요구하고
  D-059는 같은 누출을 버전에 대해 의도적으로 허용한다. 둘 다 유지했다 — D-059가 거부한 것은
  **쓰기 쪽** 표시를 쪼개는 것(두 번째 쓰기 잠금과 그 획득 순서 = 교착 위험)이었고, **허브는
  카운터가 아니다.** 각 scope가 볼 수 있는 것을 **읽기 쪽**에서 비교하며 거기엔 순서를 정할
  잠금이 없다. 비교 대상은 화면이 스스로 가져갈 바로 그 snapshot이다 — 손으로 고른 컬럼
  지문은 `prepared_qty` 하나만 빠져도 보드를 아무 오류 없이 얼린다.
- **테스트가 제 설계 오류를 고쳤다.** 초안은 "표시를 못 읽음"과 "인가를 확인 못 함"을 같이
  다뤄 둘 다 스트림을 끊게 했다. heartbeat 테스트가 실패하면서 드러났다 — 앞의 것은 끊으면
  화면이 재접속해 같은 고장 난 허브를 만나 **루프**가 된다. D-019가 판단을 클라이언트에 두므로
  (허브 정상성 + 완전한 snapshot) 열어 두고 `hub_ok: false`를 싣는 것이 맞다. 인가 실패는
  반대로 **닫히는 쪽으로 실패**한다 — 카드가 말한 "상한"은 이벤트 0건이다.
- **연결 규칙이 10A에서 뒤집힌다.** 허브는 워커당 스레드 하나·연결 하나를 수명 내내 쥐고,
  스트림은 인증 직후 놓는다. **스트림당 놓고, 허브당 쥔다.** 10C가 10D1 인계로 남긴 항목이다.
- **측정(`scripts/hub_fanout.py`):** 변경당 쿼리가 화면 3개 이상에서 **22.0으로 평평**
  (인가 묶음 1 + scope 3 × snapshot 7), 깨운 비율 **100% → 67%**. 10C가 측정한 헛수고 33%가
  그대로 사라진 몫이다.
  **지연은 싣지 않았다** — 첫 실행에서 화면 수를 따라 17.5→41.1ms로 오르는 것처럼 보였는데
  `--screens 12,6,3,1`로 뒤집자 12개가 17.9ms·3개가 22.8ms였다. 추세가 화면 수가 아니라 실행
  순서를 따라간 것이라 결과가 아니다. **불편한 몫도 적었다:** 허브가 scope마다 온전한 snapshot을
  가져가므로 쿼리 총량 기준 손익분기는 화면 약 10개다. 그 아래에서 값을 하는 이유는 쿼리 수가
  아니라 폴 간격만큼의 지연 제거와 헛수고의 무조건적 소멸이다.
- 변경 파일: `orders/services/hub.py`(신규)·`orders/views/stream.py`(신규)·
  `orders/services/__init__.py`·`orders/urls.py`, 테스트 `test_sse_server.py`(신규),
  `scripts/hub_fanout.py`(신규), 문서 `SSE_SERVER.md`(신규)·`DECISIONS.md`(D-060, D-019 갱신)·
  `BLUEPRINT.md`·`RISK_REGISTER.md`(BK-R038)·`README.md`. **마이그레이션 없음.**
- 검증: 격리 PostgreSQL **마이그레이션 26건 + 애플리케이션 512건 통과**(신규 15건).
  변이 확인 — 재인가를 건너뛰면 회수 테스트 2건 실패, scope 비교를 없애면 "포장 화면이 홀
  변경에 깨지 않는다" 실패.
- **아키텍처 리뷰 반영: HIGH 5 + MEDIUM 일부.** 공통점은 "아무 오류 없이 보드가 멈추는"
  경로다. (H1) `Health.ok`에 신선도 항이 없어 폴러가 아예 죽으면 영원히 `hub_ok: true`였다 —
  `failures`는 읽기가 *실패할 때만* 움직인다. (H3) scope 조회가 한 번 실패하면 그 변경이
  영구히 사라졌다. (H4) digest가 `MAX_QUEUE` 절단을 무시해 500건 위에서 보드가 멈췄다 —
  10C에는 없던 구멍이라 그 경계에서 퇴보였다. (H5) `change`의 `version`이 scope 필터가 막은
  것을 되돌려줬다(전역 카운터라 간격이 곧 못 들은 변경의 개수). 프레임을 비웠다. (H2)
  `id(loop)` 키잉은 주소 재사용으로 죽은 허브를 물려받는다 — `WeakKeyDictionary`. (M2)
  `scope_key`가 권한 집합 전체라 같은 보드를 두 번 조회했다. 정규화하되 역할 변경 탐지는
  원본 튜플로 남겼다.
- **제가 문서에 쓴 "워커당 연결 하나"가 거짓이었다.** Django가 모든 요청을
  `ThreadSensitiveContext`로 감싸므로 `thread_sensitive=True`는 요청별 executor를 쓰고, 허브는
  자신을 시작시킨 요청의 스레드를 물려받았다가 그 요청이 끝나면 옮겨 간다. `AsyncClient`에는
  그 컨텍스트가 없어 **테스트가 운영과 다른 모양을 검증한다.** 참인 것은 "감지가 워커당"이라는
  방향뿐이라 그렇게 고쳐 적었다.
- **측정 주장도 낮췄다.** 22.0이 평평한 것과 67%는 발견이 아니라 하네스 구성의 산물이고
  (역할 3종만 돌리니 scope가 3을 넘을 수 없다), **워커 수가 비용을 곱하므로** 손익분기는
  화면 ~10이 아니라 `--workers 3` 기준 ~28이다. 재검증 518건 통과.
- **10D2 인계:** `unverified` 재접속이 자기 제한적이지 않아 ~3초 루프가 되는데 서버가 `retry:`를
  안 보내 백오프할 수단이 없다. 브라우저 출처당 연결 한도(~6) 때문에 탭이 6개면 주방이 자기
  snapshot 요청을 막는다. `expires_at` 만료와 `id:` 부재에 테스트가 없다. `BLUEPRINT.md`가 없는
  파일(`test_sse_auth`)을 검증 명령으로 적고 있다.
- **화면은 아직 이 스트림에 붙지 않는다**(10D2). 다중 워커 전달과 실제 프록시 경유는 재지
  않았고, 요청 제한은 12A1이다.
- **보안 리뷰 반영: CRITICAL 1 + HIGH 2 + MEDIUM 1.** 넷 다 근본 원인이 같다 — 인가 판단을
  손으로 다시 구현한 것. (i) **PIN 회전이 열린 스트림을 끊지 못했다** — 허브가 조건을 다시
  나열하며 credential fingerprint 비교를 빠뜨렸고, 이 저장소에서 그 비교가 곧 D-045의 회수다.
  회전이 모든 요청을 막고 스트림은 하나도 막지 못했다. `device_is_current()`로 술어를 합쳤다.
  (ii) 자원 반환 closer로 `lambda: None`을 등록해 그물이 무력했다 — 끊긴 태블릿이 반복되면
  24슬롯이 차고 정상 화면이 영구히 503을 받는다. 진짜 함수를 멱등으로 등록했다. (iii) 슬롯을
  잡은 뒤 첫 `yield` 전 구간이 무방비였다(전진하지 않은 제너레이터는 `try`에 들어가지도 않는다).
  (iv) 한산한 보드에서 "이벤트마다"가 아무 상한도 아니었다 — heartbeat 주기에도 같은 검사를
  돌린다. 변이 확인: fingerprint 비교를 없애면 새 스트림 테스트가 기존 토큰 테스트 6건과 함께
  실패한다. 재검증 516건 통과.
- 다른 세션이 `UI_UX_REDESIGN.md`·`UI_REFERENCES.md`와 이 파일 하단을 동시에 편집 중이라,
  커밋에는 제 hunk만 선별해 올렸다.

## 2026-09-20 — 10C 버전과 일치하는 권한 snapshot (D-059)

- 브랜치 `phase-10c-snapshot`, 기준 `develop` 7230cce. 10C의 결정 관문 세 개를 먼저 물었고,
  사용자가 **"REPEATABLE READ 트랜잭션"**, **"generation을 지금 넣기"**,
  **"측정하고 전역 1행 유지"**를 골랐다(D-059).
- **문제는 읽기가 두 문장이라는 것.** autocommit에서 표시를 읽는 SELECT와 주문을 읽는 SELECT는
  서로 다른 PostgreSQL 스냅샷이고, 사이에 커밋이 끼면 **한 번도 함께 참인 적 없는 짝**이 나간다.
  주문을 먼저 읽으면 화면이 자기가 보여 주는 것보다 앞선 버전을 저장하고, 다른 변경이 올
  때까지 틀린 것을 계속 보여 준다 — 10B가 쓰기 쪽에서 막은 영구 누락이 읽기 쪽으로 돌아오는
  경로다. 그래서 snapshot은 짧은 REPEATABLE READ 트랜잭션 하나다.
- **버전은 비교하는 것이지 크기를 재는 것이 아니다.** `generation:value:scope`. `generation`은
  복원이 숫자를 되돌리는 경우를 잡고(`>`면 영원히 안 받고, `!=`여도 이미 본 번호를 새 것으로
  받는다), `scope`는 요청마다 DB에서 읽히는 권한이 바뀐 경우를 잡는다. 둘 중 하나라도 다르면
  가운데 숫자는 의미가 없으므로 커서를 거부하고 전체를 준다 — 400이 아니라 200 + 전체 목록이다.
  화면이 두 경우에 할 일이 같은데 왕복만 늘기 때문이다.
- **잘린 목록에는 `complete=false`를 붙인다.** `MAX_QUEUE`가 자를 수 있고, 잘린 목록에 붙은
  버전은 "전부 가졌다"는 약속이 아니다. 10B 아키텍처 리뷰가 지목한 항목이다.
- **테스트가 제 버그를 잡았다.** `_isolate()`가 `connection.in_atomic_block`으로 "내 트랜잭션인가"를
  판단했는데 **방금 연 블록 안이라 항상 참**이었고, `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ`가
  한 번도 실행되지 않았다. 읽는 도중 커밋을 barrier로 끼워 넣는 테스트가 `2 != 1`로 실패해
  드러났다 — 격리가 없으면 스냅샷이 새 주문을 담은 채 옛 버전 라벨을 달고 나온다. 트랜잭션을
  열기 **전에** 계산한 플래그를 넘기도록 고쳤고, 그 테스트가 곧 이 단계의 변이 검사다.
- **엄격함을 하나 되돌렸다.** 중첩 호출에서 격리를 못 걸 때 초안은 예외를 던졌다. 그 결과
  저장소의 모든 `TestCase`에서 엔드포인트가 도달 불가가 됐고(권한 매트릭스 4 ERROR), 게다가
  바깥 트랜잭션 안에서는 이 격리 수준이 막으려는 커밋이 어차피 안 보여 **잃는 보장이 없었다.**
  던지지 않고 `Snapshot.isolated`로 보고하고, 운영이 조용히 그리로 가지 않음은
  `ATOMIC_REQUESTS`가 꺼져 있다는 테스트로 고정했다.
- **읽기 증폭 측정(독립 2회, `scripts/snapshot_amplification.py`).** 10B가 판단 근거 없이 남기고
  10C 승인 기준에 넘긴 항목이다. 대기 홀 40 + 포장 40, 홀 변경 20회, 화면 1·3·6·12:

  | 화면 | 재조회 | 헛수고 | 헛수고% | 쿼리/폴 | 중앙값 ms | p90 ms |
  | --- | --- | --- | --- | --- | --- | --- |
  | 1 | 20 | 0 | 0% | 7.0 | 4.78 / 3.44 | 5.88 / 4.00 |
  | 3 | 60 | 20 | 33% | 7.0 | 4.56 / 4.04 | 7.06 / 6.73 |
  | 6 | 120 | 40 | 33% | 7.0 | 5.28 / 4.05 | 6.30 / 4.93 |
  | 12 | 240 | 80 | 33% | 7.0 | 4.95 / 5.14 | 9.23 / 7.13 |

  두 숫자가 예상보다 셌다. (i) **재조회 횟수 = 폴 횟수** — 변경이 계속 있으면 전역 표시 때문에
  모든 화면이 모든 변경마다 다시 받고, `unchanged`로 싸게 끝나는 폴은 조용할 때만 나온다.
  (ii) 그 재조회의 **3분의 1이 헛수고**다(다른 scope의 변경에 깨어나 이미 가진 것을 그대로 받음).
  그래도 유지한다 — 폴 하나가 쿼리 7개·수 ms이고, 쪼개면 scope 간 잠금 획득 순서라는 새 교착
  위험을 산다. 단서: 단일 프로세스·순차 폴링이라 **동시 폴링의 연결 경합은 재지 않았다**(10D1).
- 변경 파일: `orders/services/snapshots.py`(신규), `orders/models/revisions.py`(`generation`)·
  `orders/migrations/0029_revision_generation.py`(신규), `orders/services/revisions.py`(`state()`)·
  `orders/services/__init__.py`, `orders/views/api.py`(`snapshot_waiting`)·`orders/urls.py`,
  `scripts/snapshot_amplification.py`(신규), 테스트 `test_snapshot_consistency.py`(신규)·
  `test_migration_paths.py`·`test_permissions.py`, 문서 `SNAPSHOT.md`(신규)·`DECISIONS.md`(D-059,
  D-019 갱신)·`BLUEPRINT.md`·`RISK_REGISTER.md`(BK-R037)·`README.md`.
- 검증: 격리 PostgreSQL 전체 — 마이그레이션 26건 + 애플리케이션 490건 통과(신규 23건),
  `manage.py check` 이상 없음, `makemigrations --check` 변경 없음. 0029 정·역방향을 주문과 표시가
  이미 있는 DB에서 확인했다.
- **화면은 아직 이 엔드포인트를 부르지 않는다**(10D2). SSE·heartbeat·재접속·세션 회수는 D-019에
  그대로 남아 10D1 시작 전에 확정해야 한다. 요청 제한은 10B와 같이 12A1 인계다.
- 이 저장소에서 다른 세션이 `UI_UX_REDESIGN.md`·`UI_REFERENCES.md`와 이 파일 하단을 동시에
  편집 중이라, 커밋에는 제 hunk만 선별해 올렸다.

- **리뷰 반영(보안·아키텍처·코드 3건).** 보안은 CRITICAL/HIGH 없음이었고, 나머지 둘이
  **제가 쓴 근거 다섯 개를 반증했다.** 전부 사실 관계라 확인 후 고쳤다.
  1. **"중첩돼도 잃는 보장이 없다"가 거짓.** 저장소 어디에도 격리 수준을 올리는 곳이 없어
     모든 `atomic()`은 READ COMMITTED이고, 거기서는 **문장마다 새 스냅샷**이다. 동일 시점
     보장은 중첩되면 진짜로 사라진다. 보고(`isolated`)하기로 한 결정은 유지하되 근거를
     바꿨다 — 사라져도 안전한 이유는 `waiting()`이 **버전을 먼저, 주문을 나중에** 읽어
     최악의 짝이 "데이터가 버전보다 새것"(한 번 더 받고 수렴)이기 때문이다. **읽기 순서가
     하중을 받는 설계인데 그걸 지키는 테스트가 없었다.** 추가했고, 반환 순서를 뒤집으면
     실패한다. `isolated`는 계산만 되고 읽는 곳이 없었어서 엔드포인트가 경고를 남기게 했다
     (저장소의 첫 로거다).
  2. **`ATOMIC_REQUESTS` 검사가 아무것도 검사하지 않았다.** `settings_test_pg.py:70`이
     `DATABASES`를 리터럴로 통째 교체하고 그 리터럴에 그 키가 없어, **없던 키가 없음을**
     확인하고 있었다. 실제 설정을 별도 인터프리터로 부팅하는 `test_required_settings.py`로
     옮겼다(그 파일 주석이 이미 "여기가 실제 설정을 부팅하는 유일한 곳"이라 적고 있었다).
  3. **복원 테스트가 `generation` 없이도 통과했다.** 값까지 함께 옮겨 숫자만으로 버전이
     달라졌기 때문이다. 게다가 근거로 적은 위험("이미 본 301·302를 새 것으로 받는다")이
     애초에 위험이 아니었다 — 수렴 계약에서 한 번 더 받는 건 무해하다. 진짜 위험은
     **충돌**이다: 복원된 카운터가 화면이 아직 쥔 값에 도달해 `unchanged`를 답하고 복원
     이전 화면이 남는 것. generation만 돌리고 값은 그대로 두는 사례로 바꿨다.
  4. **측정 두 가지를 하네스가 정해 놓고 "발견"이라 적었다.** "재조회 = 폴"은 변경당 폴을
     1회로 고정했으니 다른 답이 나올 수 없었다. `--polls-per-change`를 넣고 1:3을 재니
     **폴 3개 중 1개만 재조회**, 폴당 쿼리 7.0→5.0, 중앙값 4.6ms→1.0ms였다. 33%도 설계가
     아니라 화면 구성비 × 변경 구성비(100% 홀)의 산물이다. 그리고 "`CONN_MAX_AGE=0`이라
     폴마다 새 연결"이라는 단서는 **이 하네스에서 거짓**이었다 — 요청 주기가 없어 전 구간이
     연결 하나를 재사용하므로 지연은 오히려 낮게 나왔다. p90 인덱스도 절삭이라 표본이 10의
     배수가 아니면 틀렸다(기존 값은 전부 20의 배수라 영향 없음). 전부 고쳤다.
  5. **지연 import의 "순환 때문" 설명이 거짓.** `orders/views/__init__.py`는 아무것도
     import하지 않고 `selectors`는 `services.scope`만 되짚는다. 양쪽 진입 순서로 확인했고
     최상단으로 올렸다. 부르는 것 자체는 맞지만(대안이 보드 질의의 두 번째 사본)
     **오늘 일치하는 이유가 `OrderType` 멤버가 둘뿐이라는 우연**이었으므로 두 질의가 같은
     주문을 고른다는 테스트를 넣었다. 10D2가 바로 이 자리를 바꾼다.
- **변이로 확인했다**(리뷰가 지적한 게 "통과하지만 아무것도 잡지 않는 테스트"였으므로):
  generation 제거 → 복원 테스트 2건 실패, 반환 순서 뒤집기 → 중첩 방향 테스트 실패,
  `ATOMIC_REQUESTS: True` → 설정 테스트 실패. 셋 다 초안 테스트로는 통과했다.
- 그 밖에 10B가 10C에 넘긴 "활동률 누출"을 D-059에서 둘로 갈라 답했다(비율은 표시를 쪼개야
  닫히므로 의도적 허용, 절대 크기도 함께 허용). **요청 제한은 이 누출을 닫지 못하므로**
  12A1에 위임하지 않는다. 8B가 남긴 `COUNT(*)` 경합이 한 트랜잭션 안에서 함께 닫힌 것,
  복제본을 붙이면 버전과 데이터가 갈라진다는 것도 적었다.
- 리뷰 반영 후 검증: 격리 PostgreSQL **마이그레이션 26건 + 애플리케이션 497건 통과**,
  `manage.py check` 이상 없음.

## 2026-09-20 — 10B 모든 writer의 영속 변경 감지 (D-058)

- 브랜치 `phase-10b-change-detection`, 기준 `develop` d01d812. 10B의 결정 관문 D-019가 열려 있어
  먼저 물었고, 사용자가 **"최신 대기 상태 수렴"**과 **"서비스 계층 writer 통합"**을 골랐다(D-058).
- **먼저 writer를 전수 조사했다.** 서비스 계층 통합은 DB trigger와 달리 누가 기억한 호출 지점만
  덮으므로, 그 목록이 곧 이 단계의 위험이다. 조사가 설계를 두 번 바꿨다.
  1. **시그널 리시버가 저장소 전체에 하나도 없다.** `post_save` 기반 훅은 선택지가 아니었다.
  2. **주방의 자기 쓰기가 서비스 밖에 있다.** `prepared_qty`는 `views/api.py`에 인라인으로
     저장되고, 품목 4개 중 1개만 익으면 주문 상태는 `PREPARING` 그대로다. 상태 서비스에만 건
     표시는 이 경우를 통째로 놓친다.
  3. **`EventDay`가 가장 날카롭다.** 행사일 등록이 `series_for()`를 뒤집어 화면의 연습 배지를
     모든 주문에서 바꾸는데 `orders_order` 행은 하나도 쓰지 않는다. → **주문별 표시로는 안 된다.**
- **시퀀스가 아니라 잠긴 행을 쓴 이유.** 카드가 인수 기준에 지목한 "ID 10/11 커밋 역전"이다.
  10을 받은 트랜잭션이 11을 받은 것보다 늦게 커밋하면, 11을 본 화면은 10이 설명하는 변경을
  영원히 받지 못한다. 시퀀스는 롤백해도 번호가 살아남아 있지도 않은 변경으로 화면을 다시 받게
  만들기까지 한다. 잠긴 행은 "나중 번호"와 "나중 커밋"을 같은 말로 만든다(D-047과 같은 기법).
- **잠금은 항상 마지막.** 주문 생성은 번호 카운터를, 조리 진행은 주문·품목 행을 먼저 잠근다.
  표시를 먼저 잡으면 교착한다 — 카드가 `도메인/revision 잠금 역순 재현`을 검증 항목으로 지목한
  이유다. 그 결과로 **행별 revision은 두지 않았다**: 늦게 잠그면 값이 INSERT 시점에 없고
  PostgreSQL은 CHECK를 지연시킬 수 없으며(UNIQUE·FK·EXCLUDE만 가능), 수렴 계약에도 필요 없다.
- **테스트가 제 설계 하나를 먼저 반증했다.** "트랜잭션당 한 번만 센다"는 제약을 넣으려 했는데,
  연결에 메모를 남기면 롤백 시 그 메모가 다음 트랜잭션으로 새어 bump를 건너뛴다. 읽는 쪽은
  "달라졌는가"만 보므로 애초에 필요 없는 제약이라 뺐다. 대신 "단조 증가"와 "주문 하나 = 정확히
  한 칸"을 고정했다.
- **측정(독립 2회, `scripts/marker_contention.py`):** 모든 쓰기가 커밋 전에 행 잠금 하나를 잡으므로
  직렬화된다. 직렬로는 차이 없음(두 회차가 반대 방향 = 잡음). 동시 4—16에서 **처리량 −24%―−38%**,
  **p90 2—3배**(16 동시 21.96→46.04 / 16.88→55.46ms). 16 동시에서 중앙값은 오히려 나아졌는데
  (12.21→10.77) 직렬화가 대기를 고르게 만들기 때문이고 값은 전부 꼬리로 간다 — 중앙값만 보고
  공짜라고 말하면 안 된다. 바닥값 670—720 writes/s는 이 주방의 쓰기량보다 두 자릿수 위다.
- 변경 파일: `orders/models/revisions.py`(신규)·`orders/models/__init__.py`,
  `orders/migrations/0028_change_revision.py`(신규), `orders/services/revisions.py`(신규)·
  `orders/services/__init__.py`, `orders/services/totals.py`(트랜잭션+표시 부여)·
  `orders/services/status.py`(`change_by_id`), `orders/views/api.py`(생성·상태·조리 진행 3경로),
  `orders/admin.py`(`MarksTheBoard` 믹스인 + `OrderAdmin` 직접 쓰기 2곳),
  `scripts/marker_contention.py`(신규), 테스트 `test_change_tracking.py`(신규)·
  `test_writer_coverage.py`(신규)·`test_migration_paths.py`,
  문서 5개(`CHANGE_DETECTION.md` 신규, DECISIONS D-058·D-019, BLUEPRINT 10B, RISK BK-R036, README).
- **리뷰 반영(PR #77, security·architect·code-reviewer).** 세 건은 제 주장이 틀렸다는 지적이고
  맞았다. 두 리뷰가 독립적으로 같은 버그를 찾았고 한쪽은 실제 PostgreSQL에서 재현했다.
  1. **(CRITICAL) "모든 writer가 표시한다"가 이미 깨져 있었다.** 조리 진행에서 표시가 품목
     수량 변화(`changed`)에만 걸려 있었다. 부분 조리 주문을 수동으로 READY로 올린 뒤 이미 끝난
     품목을 다시 누르면 `changed=False`인데 `sync_from_items`가 주문을 PREPARING으로 되돌린다 —
     주문 행이 커밋되고 표시는 그대로. 폴링이 없으므로(4B2) **화면이 영구히 낡는다.** 이 단계가
     없애겠다고 선언한 실패 그 자체다. `if changed or order.status != previous:`로 고치고
     회귀 테스트로 고정했다(되돌려서 실패하는 것까지 확인).
  2. **(HIGH) "표시는 항상 마지막에 잠근다"가 관리자에서 거짓이었다.** `save_model`에서 표시한
     뒤 Django가 인라인 품목을 쓰므로 순서가 역방향이었고, 표시 행을 폼 제출 끝까지 쥐고 있었다.
     더해서 목록 일괄 편집은 **행마다** 표시하므로 표시를 잡은 뒤 다음 행을 잠근다 —
     **표시가 순환의 한가운데인 ABBA 교착**이 성립한다(운영자 둘이 정렬을 다르게 해 겹치는 행을
     수정). 관리자는 `save_related`에서 표시하고 목록 POST는 전체를 감싼 트랜잭션에서 한 번만
     표시하도록 고쳤다. 그 래퍼가 Django가 안 감싸 주는 일괄 삭제에도 트랜잭션을 준다.
     문장도 좁혔다 — 성립하는 명제는 "다른 writer가 다툴 수 있는 행은 표시 뒤에 잡지 않는다".
  3. **(HIGH) 분류 기준이 틀려 `AccountAdmin`을 놓쳤다.** "화면이 그리는가"로 물었는데,
     권한은 요청마다 DB에서 읽히고(`_identity`) `scope.visible`이 그걸로 주문을 좁힌다. 즉
     권한을 끄면 **화면이 볼 수 있는 집합**이 주문 행 하나 없이 바뀐다 — `EventDay`와 같은
     종류인데 놓쳤다. 맞는 질문은 "화면이 **무엇을 볼 수 있는지** 바꾸는가"다. 믹스인을 붙이고,
     AST가 원리적으로 못 보는 관리자를 **런타임 레지스트리로 훑는 테스트**를 추가했다.
  4. **(MEDIUM) 근거가 무효였다.** "PostgreSQL이 CHECK를 지연시킬 수 없어 행별 revision을 못
     둔다"고 적었는데, 사실이지만 근거가 못 된다 — nullable 컬럼 + 트랜잭션 끝 UPDATE면 제약이
     아예 필요 없다. 유효한 이유 둘로 바꿔 적었다.
  5. **(MEDIUM) 제약 이름이 거짓말했다.** `change_revision_never_decreases`는 `value >= 0`만
     강제하므로 5→3도 통과한다. `change_revision_is_not_negative`로 고치고, 단조성은
     "`mark()`가 유일한 writer"라는 사실을 테스트로 고정했다(0028은 미머지라 직접 수정).
  6. 그 밖: `except Exception` → `IntegrityError`(0028 미적용 DB에서 모든 쓰기가 원인 없는 500이
     되는 배포 순서 함정), 스캐너의 중첩 함수 오귀속 수정(리뷰어가 재현 — 클로저 안 쓰기가
     바깥 함수로 귀속돼 안전망이 뚫렸다), `NOT_A_MODEL` 축소(`form`/`request`/`results` 등은
     실제 모델을 담는 흔한 이름이라 거짓 음성을 만든다), async 쓰기 3종 추가,
     `save_and_mark()` 무인자 호출이 전체 행을 덮어쓰던 것 거부, `recalc_totals`에 행 잠금,
     보장된 3초 대기 제거(테스트 5.0초→2.8초).
- **범위 밖으로 남긴 것(기록만):** 쓰기 엔드포인트 요청 제한(이 단계가 증폭했지만 12A1 소관),
  전역 표시가 권한 경계 너머 활동량을 흘리는 것(10C가 정할 것), `board_write()` 컨텍스트
  리팩터(구조적으로 맞지만 11단계/10D1), 읽기 증폭 측정(10C 승인 기준).
- **10C 읽기 계약 세 줄을 문서에 박았다:** 표시를 데이터보다 먼저 읽을 것(반대로 하면 쓰기
  쪽에서 막은 커밋 역전이 읽기 쪽으로 돌아온다), 비교는 `!=`일 것, `has_more`면 표시를
  완전함의 근거로 쓰지 말 것.
- 검증: 격리 PostgreSQL에서 **마이그레이션 25건 + 애플리케이션 467건 통과**(신규 33건, 리뷰 반영 후 재실행).
  `manage.py check` 이상 없음, `makemigrations --check` 변경 없음. 0028 정·역방향을 주문이 있는
  DB에서 확인했고 되돌린 뒤 스냅샷이 적용 전과 일치한다. 주문 생성과 조리 진행 동시 실행에서
  교착 없음(201/200).
- 남은 것: **화면은 아직 이 숫자를 읽지 않는다** — 10C(같은 시점 snapshot)와 10D1(허브).
  D-019의 snapshot 격리·generation·cursor·heartbeat·재접속은 여전히 pending이며 10C 전에 확정해야
  한다. `OrderAdmin.has_delete_permission` 공백과 writer 없는 `FloorOrderCounter`는 11단계 인계.

## 2026-09-20 — 10A ASGI·미들웨어·프록시 최소 실행 증명 (D-057)

- 브랜치 `phase-10a-asgi-runtime`, 기준 `develop` df9c35a. 사용자 지시: "기다렸다가 리뷰 반영하고 머지한 뒤
  10A 진행해". 범위를 물었고 **"운영 실행까지 ASGI로 전환"**을 골랐다. 워커는 **uvicorn 단독 --workers 3**,
  정적 파일은 **nginx 직접 제공**을 선택했다(D-057).
- **운영이 WSGI로 돌고 있었다.** `compose.prod.yaml`이 `gunicorn ...wsgi:application`을 실행했고, WSGI 워커는
  스트리밍 응답을 모아서 한 번에 보낸다. `asgi.py`는 있었지만 아무도 실행하지 않았다. 이 구성에서 SSE는 느린
  것이 아니라 불가능했다(BK-R035).
- **동기 미들웨어 하나가 요청 경로를 스레드로 끌어내리고 있었다.** 미들웨어 8개 중 `WhiteNoiseMiddleware`만
  `async_capable=False`였고, Django는 동기 전용 미들웨어 **안쪽 전체**를 `async_to_sync`로 감싼다. 체인 생성을
  계측해 `BRIDGE async_to_sync around middleware whitenoise...`를 확인했다. WhiteNoise는 최신 6.12에도 async
  경로가 없어 정적 파일을 프록시로 옮겼다(저장 백엔드는 유지). 되돌아오는 것은 시스템 검사 `orders.E001`이 막는다.
- **대가를 재 보니 제가 처음 적은 것보다 작았고, 원인도 달랐다.** 초안은 동기 미들웨어가 async 뷰를
  **다른 이벤트 루프**에서 돌린다고 적었다. 그것을 증명하려고 쓴 테스트가 **실패**했다. asgiref의
  `AsyncToSync`는 `SyncToAsync` 스레드 안에서 호출되면 코루틴을 `main_event_loop`로 되돌린다 — 루프는 갈리지
  않는다. 실제 `ASGIHandler`로 32 동시 × 128요청을 돌려 잰 값은 `async만 p90 36~39ms` 대 `동기 1개 p90 44~50ms`,
  직렬로는 차이 없음(1.43 vs 1.41ms). 즉 **정확성이 아니라 꼬리 지연**이다. 테스트를 뒤집어
  `OneLoopEitherWayTests`로 두 경우 모두 루프가 같음을 고정했고, `checks.py`·`settings.py`·probe의 근거를
  측정값으로 전부 고쳐 적었다.
- **`--no-proxy-headers`가 보안 경계다.** uvicorn의 프록시 헤더 처리는 기본 켜짐이고 gunicorn과 달리
  `REMOTE_ADDR`을 덮어쓴다. 켜 둔 채 전환했다면 이슈 #61의 판단이 `TRUSTED_PROXY_IPS`에서 명령줄로 조용히
  옮겨 갔을 것이다. 프록시 경유 실패 11회 `200×9, 429, 429`, 스푸핑한 `X-Forwarded-For`로도 429로 재확인했다.
- **측정이 제가 넣을 뻔한 결함을 잡았다.** 스트리밍 location에 `proxy_set_header Connection "";`을 넣자 400이
  났다. nginx는 자기 레벨에 `proxy_set_header`가 하나라도 있으면 **상위의 것을 전부 상속하지 않는다**. 헤더 하나를
  더한 것이 `Host`·`X-Forwarded-For`·`X-Forwarded-Proto`를 통째로 떨어뜨렸다. 공통 헤더를
  `scripts/nginx_proxy_headers.conf`로 빼고 프록시하는 모든 location이 include하도록 했고, 회귀 테스트로 묶었다.
- V-STREAM(실제 `compose.prod.yaml` 스택, uvicorn 워커 3개, nginx, `curl -N`): 프레임 간격
  `[503, 502, 501, 504, 502] ms`(요청 500ms), 첫 프레임 t+75ms, 응답 종료 t+2587ms. 열린 스트림 0/6/24/48에서
  `GET /orders/menus/` 중앙값 20/21/22/19ms, DB 연결 1 고정, 워커 스레드 9/15/33/57, FD 63/69/87/111.
  클라이언트가 모두 사라지면 스레드 9·FD 63·DB 1로 기준선 복귀. 스트림을 연 채 `stop -t 30 app`이 10.7초에 종료
  (`--timeout-graceful-shutdown 10`). 정적 파일은 프록시가 내고 **앱이 본 `/static/` 요청 0건**.
  측정 절차는 즉석 스크립트로 끝내지 않고 `scripts/stream_smoke.py`로 커밋해 재현 가능하게 했다.
- **인계(10D·D-007):** 스트림 1개가 워커 스레드 1개를 차지한다. **원인을 처음에는 "인증이 DB를 읽으려고 만든
  스레드"라고 적었는데 틀렸다.** `SyncToAsync.__call__`을 계측해 보니 요청당 첫 thread-sensitive 호출은
  `Signal.asend.<locals>.sync_send`, 즉 `request_started`의 동기 리시버(`reset_queries`,
  `close_old_connections`)이고 요청 객체·미들웨어·인증보다 **먼저** 스레드를 만든다. 그러므로 "인증을 async로"
  같은 완화책으로는 스레드가 **하나도** 줄지 않는다 — 요청당 1개는 구조적이다. CPU는 쓰지 않고 RSS는 스트림당
  약 90kB다. 동시 화면 상한과 목표는 D-007에 남는다.
- **"DB 연결 1"은 런타임의 성질이 아니라 이 뷰의 성질이다.** probe는 첫 프레임 전에 연결을 놓고 다시 읽지 않는다.
  이벤트마다 DB를 건드리는 10D1의 허브는 매번 놓지 않으면 연결 수가 열린 화면 수를 따라간다. `CONN_MAX_AGE=0`의
  놓고-다시-여는 비용도 그때 드러나므로 연결 재사용·pooler는 10E에서 다시 본다.
- **리뷰 반영(PR #76, code-reviewer·security-reviewer·architect).** 세 건은 제 주장을 반증한 지적이라 문서를
  다시 썼고(위 두 항목), 나머지는 코드로 막았다. (1) probe에 동시 상한이 없어 인증된 기기 하나가 워커 스레드를
  계속 늘릴 수 있었다 → 워커당 `MAX_OPEN_STREAMS = 32`, 초과는 `503 + Retry-After`, 슬롯 반납은 제너레이터의
  `finally`와 `_resource_closers` 양쪽에서 멱등하게. (2) `orders.E001`이 CI에서만 살아 있었다 → 컨테이너 시작
  명령이 `python manage.py check`를 먼저 돌리고 그다음 `exec uvicorn`(컨테이너 로그로 확인). (3) 정적 파일을
  프록시로 옮기며 `nosniff`·`Referrer-Policy`·COOP가 사라졌다 → `scripts/nginx_static_headers.conf`,
  실제 응답으로 확인. (4) `/static/staticfiles.json`이 그대로 나갔다 → `return 404`, 확인. (5) 프록시의
  비버퍼링 location 밖에 스트리밍 경로를 하나라도 두면 조용히 WSGI처럼 보인다 → 뷰에 `streams = True`를 달고
  URLconf를 훑어 nginx prefix와 대조하는 테스트. (6) `stream.py`라는 이름이 10D1의 자리를 먼저 차지했다 →
  `stream_probe.py`로 `git mv`.
- 변경 파일: `bazaar_kiosk/settings.py`(미들웨어·정적·`CONN_MAX_AGE`·probe 스위치), `orders/checks.py`(신규),
  `orders/apps.py`, `orders/views/stream_probe.py`(신규), `orders/views/guards.py`(async 경로), `orders/urls.py`,
  `requirements*.txt`(gunicorn→uvicorn), `Dockerfile`(app/proxy 두 타깃), `compose.prod.yaml`,
  `scripts/nginx_prod.conf`, `scripts/nginx_proxy_headers.conf`(신규), `scripts/nginx_static_headers.conf`(신규),
  `scripts/stream_smoke.py`(신규), `.env.example`,
  테스트 `test_asgi_stream.py`(신규)·`test_runtime_config.py`, 문서 6개(`ASGI_RUNTIME.md` 신규,
  DECISIONS D-057·D-006, BLUEPRINT 10A, RISK BK-R035·BK-R039, README, DEPLOYMENT_CANDIDATE).
- 검증: `.venv/bin/python scripts/test_postgres.py` -> 마이그레이션 24건, 애플리케이션 435건 통과(리뷰 반영 후 재실행).
  `manage.py check` 이상 없음, `check --deploy` 경고는 이전과 동일, `makemigrations --check` 변경 없음.
  **스키마 변경과 마이그레이션 없음.** 측정 후 컨테이너·볼륨·합성 비밀 파일 제거.
- 남은 것: 브라우저·HTTP/2·여러 탭·BFCache는 BK-R039로 12A1. 실제 SSE는 10B/10C/10D. D-019는 여전히 pending이며
  10B 시작 전에 확정해야 한다.

## 2026-09-20 — 9 API 입력 계약과 경계 추출

- 브랜치 `phase-9-api-boundaries`, 기준 `develop` 2475b54. 사용자 지시: "10D 시작하자 pr 올리고 리뷰 돌린 뒤 머지".
  10D는 선행 카드 넷(9·10A·10B·10C)이 모두 미구현이라 시작할 수 없음을 보고했고, 지금 가능한 9와 10A 중
  사용자가 **9**(임계 경로)를 골랐다. D-019는 여전히 pending이며 10B 시작 시 확정해야 한다.
- BK-R015: 쓰기 엔드포인트 셋이 본문을 파싱한 결과를 매핑처럼 다뤄, `[]`·`"text"`·`5`·`null` 같은 유효한 JSON이
  `AttributeError`로 500을 냈다. 필드 단위로도 같았다(숫자 `floor`가 `.upper()`에서 끝남). 구현 전 적대적 입력
  조합에서 **500 36건**을 측정했고 구현 후 **0건**이다. `orders/views/validators.py`가 본문과 필드 타입을 경계에서
  거르고 위반을 문장과 400으로 답한다. `idempotency.fingerprint`도 items가 목록이 아닐 때 순회하지 않도록 고쳤다.
- BK-R024: `orders/views/api.py`(573줄, 그중 `orders_collection` 하나가 228줄)에서 직렬화를 `serializers.py`로,
  조회를 `selectors.py`로 동작 변경 없이 꺼냈다. 515줄로 줄었다. 큰 감소가 아니며 이 단계는 성능 개선이 아니다.
- 동작 보존: URL·역할·응답 그대로. `floor`·`order_type`은 기존대로 공백을 다듬지 **않고**, `is_takeout`은 기존대로
  `bool()` 강제를 유지했다. 받는 범위를 넓히거나 좁히는 것 둘 다 동작 변경이기 때문이다.
- 인계: 쿼리 기준선(주방 보드 6쿼리 이하, 주문 2건과 20건이 동일 — N+1 없음. 주문 상세 8쿼리 이하)과
  writer 책임표 8개를 `API_CONTRACTS.md`에 적었다. 10B가 revision을 어디에 붙일지 판단할 입력이다.
- 변경 파일: `orders/views/validators.py`·`serializers.py`·`selectors.py`(신규), `orders/views/api.py`,
  `orders/services/idempotency.py`, `orders/tests/test_api_contracts.py`(신규), 문서 4개(`API_CONTRACTS.md` 신규,
  BLUEPRINT 9, RISK BK-R015·BK-R024, README).
- 검증: `.venv/bin/python scripts/test_postgres.py` -> 마이그레이션 24건, 애플리케이션 401건 통과.
  `manage.py check` 이상 없음, `makemigrations --check` 변경 없음. **스키마 변경과 마이그레이션 없음.**
- 남은 것: `orders_collection`은 아직 GET과 POST를 한 함수에 담고 있고, 쪼개면 URL 계약을 건드린다. 명령 추출은
  10B가 revision을 붙일 때 함께 보는 편이 낫다. API 버전 표기는 없다(D-008).

## 2026-09-20 — 4B2 브라우저의 외부 Realtime 제거, 폴링도 함께 제거 (D-056)

- 브랜치 `phase-4b2-remove-external-realtime`, 기준 `develop` c76bccb. 사용자 지시: "4B2 시작하자 pr 올리고 리뷰 돌린 뒤 머지".
- 결정 관문: 폴링 주기를 물었더니 사용자가 **"어차피 SSE로 갈 거고 지금 서비스 중 아니라서 폴링도 같이 없애 버릴 생각"**이라고
  답했다. 제시한 세 선택지(5초·2초·가변) 어느 것도 아닌 네 번째 답이라 D-056으로 기록했다.
- 제거: CDN의 외부 Realtime SDK `<script>`, HTML에 주입하던 프로젝트 URL·익명 키, `orders_order`·`orders_orderitem` 직접 구독,
  5초 폴링 타이머, `_supabase_context`, `SUPABASE_URL`·`SUPABASE_ANON_KEY` 설정(운영·테스트 프로필·`.env.example` 모두).
- 남긴 갱신 경로: 새로고침 버튼, 카드 조작, 탭 복귀 시 **단발** 읽기(타이머 아님). 상태 줄이 자동 갱신 없음과 목록 읽은 시각을 말한다.
- 변경 파일: `orders/templates/orders/kitchen_supervisor.html`, `orders/views/pages.py`, `bazaar_kiosk/settings.py`,
  `settings_test_pg.py`, `.env.example`, `orders/tests/test_external_realtime.py`(신규), `test_settings_isolation.py`, 문서 8개
  (`EXTERNAL_REALTIME_REMOVAL.md` 신규, D-056, BLUEPRINT 4B2와 10B·10C·10D1·10D2 롤백 주석, RISK 4건, README,
  CONTENT_SECURITY, SESSION_SETUP).
- 검증: `.venv/bin/python scripts/test_postgres.py` -> 마이그레이션 24건, 애플리케이션 389건 통과. `manage.py check` 이상 없음,
  `makemigrations --check` 변경 없음. **스키마 변경과 마이그레이션 없음.**
  격리 PostgreSQL(포트 55471, 전용 compose 프로젝트)에 개발 서버(8010)를 띄워 실제 HTTP로 확인했다. 세 페이지 모두 외부 origin 0,
  외부 토큰 0, `setInterval` 0. 주문 생성 201 -> 보드 `mode=queue count=1 total=1`. 계정 비활성화 후 같은 토큰 401,
  페이지 302, refresh 401. 검사 후 서버 종료와 `down -v`로 제거했고 무관한 컨테이너는 건드리지 않았다.
- **V-BROWSER 미실행.** Chrome 확장과 Playwright 브리지가 모두 연결되지 않아 실제 브라우저 네트워크 기록을 남기지 못했다.
  카드 인수 기준 미충족 상태이며 배포 전에 확인해야 한다.
- 리뷰(PR #74): 코드 APPROVE, 보안 HIGH 2, 아키텍처 조건부 승인 HIGH 3. 코드 결함은 하나였다. 상태 줄의 "읽은 시각"이 실제로는
  렌더 시각이라 단건 갱신이 그 시각을 밀어 올렸고, 이 단계가 유일한 완화책으로 내세운 고지가 스스로 거짓이 됐다. 목록 읽은
  시각으로 고정했다. 읽기 실패 시 카드를 지우지 않도록 바꾸고, 새로고침 버튼에 진행 표시를 넣었다. 타이머 회귀 울타리를
  재귀 `setTimeout`과 공유 JS까지 넓혔고, 외부 origin 검사를 벤더 이름 대신 절대 URL·스트림 API 자체로 바꿨다.
- 받아들인 잔여 위험: 탭을 바꾸지 않는 배치는 갱신 0, 앞에 떠 있는 화면은 권한 회수를 감지하지 못함, `prepared_qty`의 stale
  절대값 쓰기 창이 5초에서 무한. 셋 다 10D가 닫는다. **실제 행사 운영 전 10D 선행 필수.**
- 남은 것: 외부 publication·RLS·키 회수·배포 env 정리는 승인이 필요한 인계 목록이며 BK-R018은 열려 있다. BK-R029는 CSP가
  남아 부분 해결이다(12A1).

## 2026-09-20 — 8B 주방 대기 목록 완전성과 캐시 정확성 (D-055)

- 브랜치 `phase-8b-kitchen-queries`, 기준 `develop` ecb9844. 사용자 지시: "8B 시작하자 pr 올리고 리뷰 돌린 뒤 머지".
  8C는 이미 머지돼 있어(PR #71) 다음 미구현 카드가 8B임을 확인한 뒤 사용자가 8B를 골랐다.
- 결정 관문: 대기 목록 계약을 물었고 사용자가 **"오래된 순서로 전부"**(권장)를 골랐다 -> D-055.
- BK-R009: 화면이 `limit=80`을 보내고 서버가 최신순으로 잘라서, 대기 81건부터 가장 오래 기다린 주문이
  표시 없이 빠졌다. 전날 넘어온 주문이 항상 먼저 사라지는 쪽이었다. `orders/services/queues.py`를 추가해
  대기 큐(오래된 순 전부, 상한 500)와 조회 페이지(최신 순, `limit` 유지)를 나눴다. 응답은 항상 `total`과
  `has_more`를 싣고, 대기 목록에서는 호출자의 `limit`을 무시한다. 역할 필터는 잘라내기 전에 적용된다.
- BK-R010: `_get_table_by_number`의 프로세스 `lru_cache`를 제거했다. 이 조회가 주문 생성의 유일한 테이블
  사용 가능 검증이라서, 캐시가 있으면 같은 POST가 어느 워커에 걸리느냐에 따라 성공·실패가 갈렸다.
  메뉴·테이블 목록의 `cache_page(60)`도 제거했다. 기본 백엔드가 프로세스 메모리라 워커마다 창이 따로 돌았다.
  테스트 10곳의 `cache_clear()` 호출도 함께 없앴다.
- 변경 파일: `orders/services/queues.py`(신규), `orders/services/__init__.py`, `orders/views/api.py`,
  `orders/templates/orders/kitchen_supervisor.html`, `orders/tests/test_kitchen_queries.py`(신규),
  `orders/tests/test_cache_behavior.py`(신규), `cache_clear` 호출이 있던 테스트 8개, 문서 5개.
- 검증: `.venv/bin/python scripts/test_postgres.py` -> 마이그레이션 24건, 애플리케이션 363건 통과.
  `manage.py check` 이상 없음, `makemigrations --check` 변경 없음. **스키마 변경과 마이그레이션 없음.**
- 남은 것: 폴링 주기·재접속 계약은 4B2·10D, revision 일관성은 10C. 500건 상한에 실제로 걸리는 운영은
  관측된 적이 없고, 걸린다면 목록 문제가 아니라 조리 능력 문제다.

## 2026-09-20 — 메뉴 10개·내 메뉴 후속 Figma 비교안

- 사용자 요청: 메뉴 수 증가와 로그아웃/업무 이동 메뉴에 대한 검토를 별도 비교본으로 만든다.
  04 섹션(`2126:643`)에 A 직전 배치+10개, B 밀도 개선+10개, C 내 메뉴, D 스크롤 주문 모달을 추가했다.
- 두 목록은 동일한 합성 메뉴/가격/수량을 사용한다. 한 줄 헤더, 92px 메뉴 행, 44px 수량 버튼,
  홀/포장 수량, 주문 요약 고정. 내 메뉴에서 권한 화면 이동과 로그아웃을 구분했다.
- 미저장 주문 이탈 확인을 예시로 연결했고, 모달은 본문만 스크롤하고 합계/저장을 고정했다.
  실제 인증·입력 보존·수량 계산·주문 처리는 구현하지 않았다.
- 검증: 기존 01~03 fingerprint 동일, 양쪽 메뉴 10개, 첫 화면 노출 3→6개(캔버스 측정),
  글꼴·텍스트 경계·18개 연결 검사 통과. 주요 렌더링과 문서 링크·렌더링·diff 공백 검사 통과.
- [UI_UX_REDESIGN.md](UI_UX_REDESIGN.md)에 화면 링크와 검증 한계를 기록했다.
  문서 작성 당시 브랜치는 `phase-8c-reporting`. 이번 작업은 Figma·문서 변경이며 앱·push/merge는 건드리지 않았다.

## 2026-09-20 — 서빙 수량 조절·주문 정보 모달 비교 사본

- 사용자 요청대로 기존 Figma 개선안을 덮어쓰지 않고 오른쪽에 03 비교 섹션을 추가했다.
  A는 기존 서빙 프리뷰 복사, B는 메뉴별 `− 숫자 + 삭제`, C는 주문 정보 모달을 연 상태다.
- 모달은 테이블·담은 메뉴·결제를 묶었으며 결제 입력 후 저장하는 순서를 유지한다.
  B 하단의 OVERLAY 열기와 배경/돌아가기의 CLOSE 연결을 기록했다. 입력·계산·저장은 실행하지 않는다.
- 검증: 기존 02 섹션 862개 노드 fingerprint 동일, 새 비교안 글꼴·텍스트 경계·목적지 검사 통과,
  전체 비교판과 주요 화면 렌더링 확인. 문서 링크·렌더링·diff 공백 검사 통과.
- 상세 링크·제안 범위는 [UI_UX_REDESIGN.md](UI_UX_REDESIGN.md)의 추가 비교안을 따른다.
  다른 세션의 `phase-8c-reporting` 앱 변경은 보존했다. 이번 작업은 Figma·문서만 변경했다.

## 2026-09-20 — Figma 개선안에 개인 계정·권한 4종 반영

- 사용자 요청: 현재 PR과 개인 계정(이름 + 행사 공용 비밀번호), 권한 4종, 이름 기반 기록,
  JWT 자동 갱신을 확인하고 Figma 개선안에 반영. PR #67 MERGED, #68 OPEN을 확인했다.
- Figma `lrCdmOhZQfKiUIfz76tXvt`의 기존 개선안 섹션 `2004:3`을 수정했다.
  역할 선택/PIN을 개인 로그인/일반 오류로 교체하고 서빙·모니터링·통계에 개인 이름과 범위를 반영했다.
  내 업무 탐색, 재로그인/403/연결 오류/로그인 제한, 개인 계정·복수 권한 관리, 읽기 전용 주문 이력을 추가했다.
- JWT 동작은 구현을 유지한다. 자동 갱신은 사용자 조작 없이 진행하며, 새 안내와 탐색은 UI 제안이다.
  통합 모니터링은 두 권한 조합, 누적·통계는 Django 관리자와 별개임을 명시했다.
- 검증: 원본 11개 화면/2,202개 노드 fingerprint 동일. 변경 화면 17개의 글꼴 일치,
  텍스트 넘침 0건, 끊어진 목적지 0건. 주요 Figma 렌더링을 확인하고 툴바 넘침을 수정했다.
  문서 로컬 링크·Markdown 렌더링·미완성 표식·diff 공백 검사를 수행했다. 실제 인증 E2E는 범위 밖이다.
- 상세 화면 링크·구현과 제안의 구분·기존 작업 이력은 [UI_UX_REDESIGN.md](UI_UX_REDESIGN.md)에 기록했다.
- 시작 브랜치는 `fix/order-create-serving-only`였고 작업 중 다른 세션에서
  `phase-7a-payment-validation`으로 변경됐다. 해당 세션의 앱/마이그레이션/테스트 변경은 건드리지 않았다.
  이번 작업에서는 애플리케이션 수정, 커밋, push/merge, 운영 배포를 하지 않았다.

## 2026-09-20 — 7C 레거시 금액·과거 데이터 (D-054)

- PR #71 머지(develop `1570fed`) 뒤 사용자 지시 “7C 시작하자”. 결정 관문 D-012를 물어 **D-054로 확정**했다:
  “원본 그대로, 점검 도구만”(권장과 같음). 브랜치 `phase-7c-legacy-amounts`.
- **전제 확인이 먼저였다.** D-037로 배포 시 보존할 과거 주문이 없다. 그래서 이 단계는 값을 복원하지 않는다.
  남은 문제는 (1) 스키마에 남은 모호한 형태를 통계·상세가 해석해야 한다는 것(BK-R007), (2) 그런 행이 있는지
  알 방법이 없었다는 것(BK-R031)이다.
- 구현: `orders/services/legacy_audit.py`(집계 쿼리 하나, 쓰기 없음)와 읽기 전용 관리 명령
  `check_legacy_amounts`(문장·`--json`). 주문 생성은 `or None`을 버리고 **모든 금액 칸에 숫자를 저장**한다(0 포함).
  0원 주문도 `NULL`이 아니라 0이다. 관리 명령 패키지를 새로 만들었다.
- 에이전트 판단(D-054에 표시): 점검 항목 구성과 해석 가능/불가 구분, 0원 저장.
- TDD: `test_legacy_reconciliation.py` 13개를 먼저 썼다. 새 주문의 금액 칸, 새 DB의 빈 점검 결과, 단일·혼합 집계,
  합계와 분할 불일치, 누락 집계, 점검이 아무것도 쓰지 않음, 명령 출력 두 가지, 세 형태를 상세와 통계가 같게 읽는지 대조.
- 마이그레이션 없음. 백필 없음.
- 검증: 전용 PG `check`·`makemigrations --check` 무결, **마이그레이션 24 + 앱 326 통과, skip 0**.
- 문서: [LEGACY_AMOUNTS.md](LEGACY_AMOUNTS.md) 신설, DECISIONS D-054·D-012, BLUEPRINT 7C, RISK BK-R007/031, README.
- **PR #72 리뷰:** 코드 에이전트 CRITICAL/HIGH 없음(MEDIUM 1, LOW 1 반영). DB 에이전트가 실측으로 HIGH 2건을
  찾아 둘 다 고쳤다. (1) 한쪽 수단만 기록된 행이 어느 집계에도 잡히지 않아, 7C 이전 주문만 있는 DB가 "문제 없음"으로
  보고됐다 -> `half_split` 집계 추가. (2) 분할 합산이 `int4`라 큰 금액 두 칸이 만나면 감사 전체가
  `integer out of range`로 실패했다 -> `bigint` 캐스팅. 인덱스 제안은 실측 결과 실행 계획이 바뀌지 않아 도입하지
  않았다. 자세한 내용은 LEGACY_AMOUNTS.md.
- 남은 것: 운영 DB에 데이터가 발견되면 D-037 무효(이 명령이 근거), 삭제된 필드 복구는 백업뿐, 메뉴 이름 스냅샷(D-008).

## 2026-09-20 — 8C 통계 정확성: 기간·정산·과거 표시 (D-053)

- PR #70 머지(develop `4236630`) 뒤 사용자 지시 “8C 시작하자”. 결정 관문 D-013을 물어 **D-053으로 확정**했다:
  “가장 최근 행사일, 없으면 오늘”(권장과 같음). 브랜치 `phase-8c-reporting`.
- **선행 조건 처리:** 카드의 선행은 8A·7C·5다. 7C(레거시 금액 정합, D-012)는 아직이므로 **보고는 옛 수납 기록을
  해석만 하고 원본을 바꾸지 않으며 해석한 건수를 응답에 표시**한다. 데이터 정합 자체는 7C에 남는다.
- **고친 것:** 기간이 `2025-10-18`로 고정돼 있었다(BK-R006). 메뉴 집계가 이름 기준이라 동명이 메뉴가 한 줄로
  합쳐졌다(BK-R034). 현금 지표에 거스름돈이 반영되지 않아 금고 잔액과 달랐다. 시간별 집계가 UTC로 잘렸다.
- 구현: `orders/services/reporting.py`(`resolve_period`·`clean_floor`·`dashboard`), 뷰는 HTTP만 담당.
  금액은 SQL 식으로 옛 행까지 주문 상세와 같게 읽고, 취소 건수·해석 건수를 따로 센다. 카운터 화면에 기간 선택과
  거스름돈·순현금·취소 표시를 추가했다(DOM API, `innerHTML` 없음).
- TDD: `test_reporting_dates.py`·`test_reporting.py`를 먼저 써서 RED(모듈 부재 2, 옛 의미 5)를 확인한 뒤 구현.
  기존 특성화 테스트(`test_dashboard_execution`, `test_order_numbering`의 연습 주문)는 명시 기간을 요청하도록 바꿨다.
- 검증: 전용 PG `check`·`makemigrations --check` 무결, **마이그레이션 24 + 앱 310 통과, skip 0**. 마이그레이션 없음.
- **관찰(고치지 않음):** 첫 전체 실행(46초)에서 `test_jwt_http`의 로그인 제한 1건과 `test_payments`의 인증 3건이
  실패했다가 재실행(23초)과 단독 실행에서 재현되지 않았다. 변경 전 코드에서도 단독 통과를 확인했으므로 8C가 아니라
  부하가 큰 환경에서 드러나는 기존 불안정 테스트로 본다. 원인은 규명하지 않았다.
- 문서: [REPORTING.md](REPORTING.md) 신설, DECISIONS D-053·D-013·D-012, BLUEPRINT 8C, RISK BK-R006/026/034, README.
- **PR #71 리뷰:** 코드·DB 에이전트 2개, CRITICAL/HIGH 없음. 코드 MEDIUM 1건(제거된 import를 참조하는 죽은 헬퍼)과
  LOW 3건 반영. DB MEDIUM 4건 반영: 취소·매출 집계를 한 스캔으로, 품목 수는 메뉴 집계에서 계산해 **쿼리 5→3**,
  옛 혼합 결제의 구분 불가 금액을 응답·화면에 드러냄, NULL 단가를 명시적으로 0 처리. DB 측정 결과 복합 인덱스는
  플래너가 쓰지 않아 추가하지 않았다. 상세는 REPORTING.md.
- 남은 것: 메뉴 이름 스냅샷(D-008), 레거시 수납 정합(D-012, 7C), 환불 기록(D-048), 브라우저 여정.

## 2026-09-20 — 7B 관리자 쓰기와 불변 조건 연결 (D-052)

- PR #69 머지(develop `e53b32c`) 뒤 사용자 지시 “7B 시작하자”. 결정 관문 D-011을 선택지로 물어 **D-052로 확정**했다:
  “품목 수정 허용, 서비스 경유”(권장은 “읽기 전용 + 상태만 서비스 경유”, 권장과 다름). 브랜치 `phase-7b-admin-invariants`.
- **고친 것:** 관리자에서 수량을 바꾸면 저장 합계가 그대로였고(BK-R008), 단가·번호·수납을 폼으로 덮어쓸 수 있었고,
  취소된 주문을 준비중으로 되살릴 수 있었으며, 주문 생성도 관리자에서 가능했다.
- 구현: `orders/services/order_edits.py`(검사 `check_lines`, 적용 `apply_line_changes`), `OrderEventKind.ITEMS`(0027,
  choices만), 관리자 인라인 formset의 `clean()`이 서비스 검사를 먼저 돌려 문장으로 거부, `save_model`은 행을 잠근 채
  주방 전이표를 지나고, `save_related`가 합계·거스름돈 재계산과 이력·상태 동기화를 실행. 단가·번호·수납·합계·거스름돈
  읽기 전용, 새 품목 단가는 저장 시점 메뉴 가격, 주문 생성 불가.
- 에이전트 판단(D-052에 표시): 거스름돈 재계산, 수납 부족 시 거부(D-048), 조리 수량 미만·이력 있는 삭제 거부,
  품목 변경 후 상태 재동기화, 취소 주문 편집 거부, 행위자 NULL.
- TDD: `test_admin_integrity.py`(실제 admin form POST 14개)를 먼저 썼다. 첫 실행 17/18, 조리 이력 삭제 거부는 Django의
  보호 객체 검사가 먼저 걸려 문구가 달랐고 우리 검사를 앞으로 옮겼다.
- 검증: 전용 PG `check`·`makemigrations --check` 무결, **마이그레이션 24 + 앱 284 통과, skip 0**, `git diff --check` 깨끗.
- 문서: [ADMIN_EDITS.md](ADMIN_EDITS.md) 신설, DECISIONS D-052·D-011, BLUEPRINT 7B, RISK BK-R008, README.
- **PR #70 리뷰:** 코드·보안 에이전트 2개. HIGH 1건(검증과 저장 사이 경합에서 거부 예외가 500) → 변경 폼 POST의 첫
  읽기부터 `select_for_update`로 닫음. MEDIUM 3건(읽기 전용 집합 회귀, 비활성·비주방 메뉴 추가, 수량 상한) 반영, LOW 3건
  반영. test_admin_integrity 19개 등 35개 재실행 통과. 상세는 ADMIN_EDITS.md.
- 남은 것: 관리자 사용자와 `Account` 연결(행위자), 브라우저 admin 폼 여정.

## 2026-09-20 — 7A 서버 결제 검증과 금액 의미 (D-048 구현)

- PR #68 머지(develop `7e99436`) 뒤 사용자 지시 “7A 시작하자”로 착수. 브랜치 `phase-7a-payment-validation`.
- **고친 것:** 금액을 `int()`로 받아 `True`→1원, `1.9`→1원으로 잘렸고 5000원 주문에 0원 수납도 201이었다(BK-R014).
  이제 `orders/services/payments.py`가 정수·숫자 문자열만 받고 float/bool/음수/소수/상한 초과를 400으로 거부하며,
  합계(서버 가격 스냅샷 × 수량)보다 적은 수납은 **아무것도 저장하지 않고 400**이다(D-048). 거스름돈은 생성 시
  서버가 정해 `Order.change_amount`(0026, 추가만)에 저장한다.
- 에이전트 판단(뒤집을 수 있음): 식권 초과분은 거스름돈이 아니다(기존 `_serialize_order` 계산과 동일). 상한은
  금액 한 칸·합계 1,000만 원, 수량 99. 단일 결제는 `received_cash_amount`/`received_ticket_amount`를 우선 읽고
  `received_amount`와 함께 오면 일치해야 한다. 주문 화면의 거스름돈 표시를 서버 규칙에 맞췄다(전에는 식권 초과분도 표시).
- TDD: `test_payments.py`를 먼저 써서 모듈 부재로 RED를 확인한 뒤 구현. 첫 전체 실행에서 기존 테스트 26+7건이
  실패했는데, CASH 결제가 `received_cash_amount`만 보내는 경우를 서버가 읽지 않은 것이 원인이라 서비스를 고쳤다.
  남은 5건은 감사 테스트 픽스처가 실제 부족 결제(2,000원 주문에 1,000원)였고 픽스처를 고쳤다(업무 규칙은 바꾸지 않음).
- 검증: 전용 PG `manage.py check`·`makemigrations --check` 무결, 마이그레이션 24 통과(0026 정·역방향 포함), 앱 270
  중 위 5건 수정 후 test_audit·test_payments 33개 재실행 통과. 전체 재실행 결과는 PR에 기록.
- 문서: [PAYMENTS.md](PAYMENTS.md) 신설, BLUEPRINT 7A, DECISIONS D-048·D-005, RISK BK-R014/R030, README.
- 전체 재실행: 마이그레이션 24 + 앱 270 통과, skip 0. CI 통과.
- **PR #69 리뷰:** 코드·DB 에이전트 2개. HIGH 1건(`str.isdigit()`가 유니코드 숫자·4300자 초과 문자열을 통과시켜
  500)을 ASCII 숫자 1~12자 제한으로 고치고 회귀를 추가했다(77개 재실행 통과). MEDIUM 2건(단일 결제 교차 검증 문서화,
  6A 지문의 금액 정규화 불일치)은 PAYMENTS.md에 기록. DB: 0026 안전, 인덱스 불필요.
- 남은 것: 환불 기록(D-048 미결), 취소 주문 매출 제외(8C), 레거시 수납 필드 정합(7C), 브라우저 여정.

## 2026-09-20 — 주문 생성 POST 서빙 한정 (D-051 판단 5 확정)

- PR #67 머지(develop `6ffafdb`) 뒤 사용자가 “주문생성은 서빙 권한으로”라고 결정했다. 브랜치
  `phase-4a4-order-create-serving`.
- 변경: `orders-collection` POST 가드를 `by_method={"GET": 읽기 권한, "POST": (SERVING,)}`로 좁혔다.
  `roles.SERVING_PERMISSIONS` 추가. 4A4까지는 인증된 전원이 생성할 수 있었다.
- TDD: 권한 매트릭스의 생성 행을 `("SERVING",)`으로 바꿔 RED 4건(HALL/TAKEOUT/STATS/BOTH 201≠403)을
  확인한 뒤 가드를 고쳤다. 6A “다른 계정의 요청 ID 재전송” 테스트는 카운터 계정 대신 두 번째 서빙 계정을 쓴다.
- 검증: 전용 PG에서 test_permissions·test_idempotency·test_audit·test_scope·test_baseline·test_order_modes·
  test_order_numbering 112개 통과. 전체 스위트는 CI에서 확인.
- 문서: ACCOUNTS 매트릭스·남은 것, DECISIONS D-051 구현 메모·D-003 행.

## 2026-09-20 — 4A4 개인 계정·권한 4종·행위자 기록 (D-051 구현)

- PR #66 머지(develop `61b9412`) 뒤 브랜치 `phase-4a4-personal-accounts`에서 D-051을 구현했다.
  사용자가 4A4 착수와 "PR → 리뷰 에이전트 → 문제없으면 머지"를 승인했다.
- **바뀐 것:** 공용 계정 3개(`ROLE_ACCOUNTS`)가 사라지고 `Account`(이름 유일, 권한 4개 불리언, 활성)와
  행사 공용 비밀번호 해시 `EVENT_PASSWORD_HASH`로 로그인한다. 권한 코드는 SERVING·HALL_MONITOR·
  TAKEOUT_MONITOR·STATS. 토큰 `sub`는 계정 UUID이고 역할 claim은 없다. 권한은 매 요청 DB에서 읽어
  관리자 화면의 변경이 다음 요청부터 적용된다. 기존 기기는 0025가 전부 회수한다.
- **서버 경계:** `services/scope.py`가 주문을 매장 항목 유무로 HALL/TAKEOUT으로 나누고(혼합 = 식당),
  목록은 `Exists` 서브쿼리로 거르며 단건·상태·조리 진행은 범위 밖이면 403이다. 누적·통계는 전체를 읽는다.
- **행위자 기록:** `Order.created_by`와 append-only `OrderEvent`(CREATED/STATUS/PROGRESS)를 주문과 같은
  트랜잭션에 쓴다. 6A `OrderRequest.role`은 `actor`(계정 UUID)로 이름을 바꿨다.
- 페이지·API 가드는 `require_permissions`/`require_api_permissions`(any-of, all-of)로 바꿨다. 주방
  종합 화면은 두 모니터링 권한을 모두 요구하고 내비게이션은 가진 권한만 보인다.
- 검증(전용 PG fixture, 격리 프로젝트): `manage.py check` 무결, `makemigrations --check` 변경 없음,
  **마이그레이션 23 + 앱 242 = 265개 통과, skip 0**, `node --test scripts/test_auth_client.cjs` 12개 통과,
  `git diff --check` 깨끗. 브라우저 여정은 돌리지 않았다(PR 리뷰 뒤 남은 위험으로 기록).
- 에이전트가 정한 것(사용자 확인 대상 아님): 주문 생성 POST는 현행대로 인증된 전원이 가능하다(D-051
  판단 5, 확인 필요). 테스트 계정 별칭(ORDER/KITCHEN/B1_COUNTER)은 옛 여정을 그대로 읽히려는 용도다.
- 문서: [ACCOUNTS.md](ACCOUNTS.md) 신설, JWT_AUTHENTICATION·API_AUTHORIZATION·REQUIRED_SETTINGS·
  DEPLOYMENT_CANDIDATE·SESSION_SETUP·BLUEPRINT(4A4)·DECISIONS(D-051 구현 메모)·RISK_REGISTER·README.
- 남은 위험: 이름만으로는 사칭을 막지 못한다(공용 비밀번호). 운영 인수 시 실제 비밀번호 해시와 계정
  등록이 필요하고, 배포 직후 모든 기기가 재로그인한다. 다음: PR 리뷰 → 머지 → 7A.
- **PR #67 리뷰:** 코드·보안·DB 에이전트 3개, CRITICAL/HIGH 없음. MEDIUM 2건(0025 잠금 창 → 트래픽 없는
  배포 창 명시, 포장 목록 anti-join 확장성 → 필요 시 부분 인덱스)과 LOW 3건을 ACCOUNTS.md에 기록했다. CI 통과 후 머지.

## 2026-09-19 — 기획 변경: 개인 계정·권한 4종 (D-051)

- 사용자가 기획 변경을 전달했다. 개인 계정, 이름 입력 기반 로깅·권한 부여, JWT 인증·인가와
  access 자동 갱신, 권한 4종(포장 모니터링·식당 모니터링·서빙·누적+통계).
- 확인한 사실: JWT·자동 갱신·기기별 회전은 4A2에서 이미 구현돼 있어 그대로 쓴다. 바뀌는 것은
  주체 모델이다. D-032/034/035/040/045가 모두 “공용 계정, 개인 식별 없음”을 전제했다.
- 갈림길 네 가지를 선택지로 물어 **D-051로 확정**했다. “이름 + 행사 공용 비밀번호”(권장과 다름),
  “여러 개 가능 (권장)”, “서버가 강제 (권장)”, “DB에 행위자 저장 (권장)”. 권한 코드·혼합 주문 분류
  (매장 항목이 있으면 식당)·미등록 이름 처리·관리자 화면 등록·행위자 표 구조는 에이전트가 정하고 표시했다.
- 문서만 갱신했다: DECISIONS(D-051, 대기 목록 D-002/D-003), BLUEPRINT(4A4 카드, 의존성 표,
  7A/10C/10D1 선행, 4A2 안내), RISK_REGISTER 머리말, API_AUTHORIZATION 안내, README, 이 로그.
  코드·마이그레이션·테스트는 바꾸지 않았다.
- 브랜치 상태: `phase-6b-status-consistency`에 6B 구현이 **커밋되지 않은 채** 남아 있다. 이 문서 변경도
  같은 워크트리에 있으므로 커밋 시 6B 코드와 분리하거나 한 PR에 담을지 정해야 한다.
- 다음 권장: 6B 커밋·PR → 머지 후 `phase-4a4-personal-accounts` 브랜치에서 4A4 착수. 착수 시
  주문 생성 POST를 서빙 권한으로 한정할지 한 번 확인한다.

## 2026-09-18 — 6B 상태 전이와 포장 번호 (D-050)

- 6A 머지(#65) 뒤 이어서 진행했다. 브랜치 `phase-6b-status-consistency`, 기준 develop `f66ab90`.
  결정 관문 D-014/D-015 중 업무 규칙 세 가지를 사용자에게 물어 **D-050으로 확정**했다.
  “취소는 최종 (권장)”, “완료→준비중 되돌릴 수 있다 (권장)”, “사용 중인 포장 번호 거부 (권장)”.
  셋 다 권장안과 같다. 질문하지 않은 빈칸(완료 주문의 취소, 같은 상태 재전송, 거부 코드,
  두 writer 우선순위, 홀 테이블 중복)은 에이전트가 정하고 그렇게 표시했다.
- **고친 것:** 취소된 주문에 PREPARING을 보내면 되살아났다(200). 상태 엔드포인트는 받은 값을
  그대로 저장했고, 조리 진행 엔드포인트는 취소를 거부해 두 writer의 규칙이 달랐다. 아무도
  주문을 잠그지 않아 취소와 진행이 동시에 오면 취소가 사라질 수 있었다. 포장 번호표(101~120)는
  제한이 없어 손님 두 명이 같은 번호를 들 수 있었다.
- 구현: `orders/services/status.py`에 전이표를 두고 두 엔드포인트를 모두 통과시켰다.
  상태 변경은 주문 행을 잠그고 읽기·쓰기를 한 단계로 만든다. 조리 진행도 품목이 아니라
  주문을 잠근다. 포장 번호는 부분 유니크 제약
  `UNIQUE(table) WHERE order_type='TAKEOUT' AND status IN ('PREPARING','READY')`으로 막고,
  뷰는 문장으로 답한다. 주문 화면은 409의 `detail`만 꺼내 보여준다(이전에는 JSON 원문이 떴다).
- TDD: `test_status.py` 12개와 `test_order_modes.py` 10개를 먼저 써서 12개 실패를 확인했다.
- 검증: 전용 PG **234개(마이그레이션20+앱214), skip0 통과**, 실제 Chromium 8개 통과.
  브라우저에서 105번 중복 거부 문구, 106번 정상 저장, 주방 취소 후 되살리기 409를 확인했다.
- **검사 신뢰성:** 전이표를 빼면 3개가 실패한다. DB 제약을 빼고 뷰의 사전 확인만 남기면
  **동시 요청 테스트에서 두 주문 모두 201**로 같은 번호를 가져갔다. 사전 확인만으로는 막지 못한다.
- 정리: 합성 DB·로컬 서버·브라우저 스크립트는 저장소 밖에 두었고 컨테이너와 볼륨을 삭제했다.
- 상세: [상태 전이와 포장 번호](ORDER_STATE.md).
- **2026-09-20 PR #66 리뷰 반영:** 코드·DB 리뷰 에이전트 2개. HIGH 2건을 머지 전에 고쳤다.
  (1) 같은 `request_id` 재전송이 포장 번호 충돌과 겹치면 자기 주문 대신 "다른 번호" 409를 내던 경로:
  IntegrityError 뒤 요청 ID를 먼저 재조회하도록 순서를 바꿨고 동시성 회귀를 추가했다(RED 201/409 → GREEN 200/201).
  (2) 0024가 기존 중복 활성 포장 주문에서 안전하게 멈추는(23505, 행 보존) 경로를 고정하는 마이그레이션
  테스트 2개와 배포 전 점검 쿼리를 추가했다. MEDIUM: `sync_from_items`가 `change()`를 지나게 했다.
  전용 PG: test_migration_paths 22개, test_order_modes·test_status·test_idempotency 통과.

## 2026-09-18 — 6A 중복 요청 경계 (D-049)

- 5단계 머지(#64) 뒤 이어서 진행했다. 브랜치 `phase-6a-idempotency`, 기준 develop `9b69545`.
  결정 관문이던 D-007/D-008에서 실제로 필요한 값은 네 가지(요청 식별·ID 없는 POST·내용 충돌·
  ID 보존)였고 모두 기술 판단이라 **에이전트가 정하고 D-049로 기록**했다. 사용자가 고른 값이 아니다.
- **고친 것:** 저장을 눌렀는데 응답이 오지 않아 다시 누르면 주문이 두 개 생겼다. 분석 당시
  같은 요청 16번에 주문 16개였다(BK-R012). 서버는 재전송과 다음 손님을 구분할 수단이 없었다.
- 구현: 화면이 `request_id`를 만들고, 서버는 `OrderRequest`(키·역할·지문·주문)를 **주문과 같은
  트랜잭션에** 쓴다. 재전송은 저장된 주문을 200으로 돌려주고, 같은 ID에 다른 내용·다른 계정이면
  409다. ID 없는 POST는 400으로 거부한다. 만료는 두지 않았다(만료는 중복을 막지 못하고
  생기는 시점만 바꾼다). 동시 제출은 유니크 인덱스가 막고, 진 쪽은 트랜잭션 전체가 롤백되어
  번호도 낭비하지 않는다. 화면은 주문 내용이 바뀌면 ID를 버린다.
- `crypto.randomUUID`는 보안 컨텍스트에서만 있어서 `getRandomValues` 대체 경로를 넣었다.
- TDD: `orders/tests/test_idempotency.py` 18개와 Node `scripts/test_request_id.cjs` 7개를 먼저 썼다.
  요청 ID 필수화로 기존 주문 생성 테스트 16개가 깨졌고, 계약 변경이므로 픽스처에 ID를 넣어 고쳤다.
- 검증: 전용 PG **206개(마이그레이션20+앱186), skip0 통과**, Node 30개, 실제 Chromium 8개.
  브라우저 검사는 응답을 0.7초 지연시켜 첫 응답 전에 두 번째 탭이 들어가게 했고, 두 요청이
  같은 ID로 201·200을 받아 **같은 주문 하나**를 가리켰다. 주방에는 2개만 떴다.
- **검사가 보지 못한 것:** 브라우저 검사는 `127.0.0.1`에서 돌았고 브라우저는 localhost를 보안
  컨텍스트로 친다. 비보안 대체 경로는 브라우저에서 실행되지 않았고 Node 테스트로만 확인했다.
- **부수적으로 확인한 별개 문제:** 진짜 비보안 컨텍스트를 보려고 LAN 주소로 열었더니 메뉴가
  뜨지 않았다. `JWT_COOKIE_SECURE=True`라 refresh 쿠키가 평문 HTTP에서 저장되지 않아 로그인
  루프가 된다. **배포 후보(4A3)는 평문 80을 공개하므로 그 구성에서는 브라우저 로그인이 불가능하다.**
  4A3 검증이 curl이어서 드러나지 않았다. 코드는 바꾸지 않고 배포 후보 문서에 정정을 적었다.
  12A1의 TLS는 선택이 아니라 동작 조건이다.
- 리뷰 반영: 코드 리뷰 MEDIUM 1건(지문이 금액 타입·모드 대소문자를 정규화하지 않음)을
  테스트로 재현한 뒤 고쳤다. 현재 화면은 항상 같은 형식으로 보내 잠재 결함이었지만, 다른
  클라이언트의 정상 재전송이 409로 거부될 수 있었다. 보안 리뷰는 CRITICAL/HIGH 0건이고
  MEDIUM(쓰기 경로 속도 제한 부재)은 기존 공백이라 문서에 남겼다. `PROTECT` 유지 이유와
  미사용 `serve.html` 건도 문서에 적었다.
- 최종 검증: PG **212개(마이그레이션20+앱192), skip0 통과**.
- 정리: 합성 DB·로컬 서버·브라우저 스크립트는 저장소 밖에 두었고 컨테이너와 볼륨을 삭제했다.
- 상세: [중복 요청 경계](IDEMPOTENCY.md).

## 2026-09-18 — 5단계 주문 번호 계약과 행사일 등록 (D-047)

- 사용자 결정: 주문 번호는 **해마다 1번부터**, 화면에는 **숫자만**, 그리고 “행사 날짜를 관리자
  페이지에서 정하거나 미리 확정해두는 방식… 저기서 행사 날짜를 써두면 그 날짜로 카운트 되고
  나머지는 dev로 빠지는 느낌”. 미등록 날짜는 **테스트로 처리**, 연습 주문은 **통계 제외·주방 표시**.
  결제 규칙(D-048)도 같은 자리에서 확정했다(부족 결제 저장 거부·취소 매출 제외·거스름돈 저장).
  두 결정을 DECISIONS.md에 D-047/D-048로 기록하고 D-004/D-005 대기 행을 갱신했다.
  브랜치 `phase-5-order-numbering`, 기준 develop `16a94a6`.
- **고친 것:** 시퀀스 `orders_floor_b1_seq`는 초기화가 없고, 연습 주문이 진짜 번호를 당겨 쓰고,
  롤백해도 번호를 소비했다. 1년에 한 번 쓰는 서비스에서 두 번째가 실제 피해다.
- 구현: `EventDay`(관리자 등록)와 `OrderNumberCounter`(계열·연도·층) 추가. 할당은 카운터 행을
  `select_for_update`로 잠그고 주문 트랜잭션이 끝날 때까지 쥔다. 유니크 제약을
  `(floor, number_series, EXTRACT(YEAR FROM order_date), order_no)`로 바꿨다(연도는 주문일에서 도출).
  트랜잭션 밖 호출은 거부한다. 0022가 시퀀스를 제거하고 역방향에서 복원한다.
  통계는 `REAL` 계열만 집계하고, 주방 화면은 연습 주문에 `연습` 배지를 붙인다.
  **행사일 미등록 경고**를 주문·카운터·주방 화면에 넣었다. 등록을 잊는 것이 이 설계의 실패 모드다.
- TDD: `orders/tests/test_order_numbering.py` 20개를 먼저 써서 실패를 확인했다. 대시보드
  특성화 fixture는 매출을 다루므로 `REAL` 계열로 갱신했고, 마이그레이션 헤드 테스트는
  새 계약(시퀀스 부재)에 맞춰 고치고 0022 역방향 테스트를 추가했다.
- 검증: 전용 PG에서 **188개(마이그레이션20+앱168), skip0 통과**, Node 23개 통과,
  실제 Chromium 12개 통과(배너 표시/미표시, 연습·행사 번호 공존, 주방 배지).
- **검사 신뢰성:** 구현을 두 번 고의로 망가뜨렸다. `series_for`를 항상 `REAL`로 바꾸면 6개가
  실패한다. 그런데 **카운터 락을 제거해도 처음에는 통과했다.** 유니크 제약이 충돌을 잡아
  재시도로 번호가 갈렸기 때문이다. 충돌 복구 호출을 감시하고 카운터 행이 이미 있는 상태에서
  경합시키도록 고친 뒤에야 실패했다. 결과만 보면 락 없는 구현도 옳아 보였다.
- 리뷰 반영: 코드 리뷰가 HIGH 2건(둘 다 기존 데이터가 있는 DB에서의 마이그레이션 안전성),
  MEDIUM 1건, LOW 3건을 냈고 보안 리뷰는 CRITICAL/HIGH 0건이었다.
  0022에 **기존 번호 보유 주문의 `REAL` 분류**와 **같은 해 번호 충돌 사전 거부**를 넣고
  각각 마이그레이션 경로 테스트로 고정했다(제거하면 2개 실패 / 원문 unique 오류로 깨짐을 확인).
  `stats_menu_counts`는 오늘의 계열을 따르게 했고, `order_no`가 있으면 `order_date`를
  요구하는 CheckConstraint를 추가했으며, 낡은 주석을 고쳤다.
  보안 리뷰의 MEDIUM(관리자 화면 접근 정책 부재)은 코드 변경 없이 문서에 남겼다.
  행사일 등록이 매출 집계 여부를 가르는 통제가 됐는데 `/admin/`에는 계정 발급·잠금·감사
  정책이 없다. D-011 범위 또는 별도 결정으로 다룬다.
- 최종 검증: PG 전체 **188개(마이그레이션20+앱168), skip0 통과**, check 문제0, drift 없음.
- 정리: 합성 DB·로컬 서버·브라우저 스크립트는 저장소 밖에 두었고 컨테이너와 볼륨을 삭제했다.
- 상세: [주문 번호 계약](ORDER_NUMBERING.md).

## 2026-09-18 — 4B1 주문·카운터 화면의 안전한 렌더링

- 사용자 지시: “이슈 닫고 머지된 브랜치 3개 지운 다음 4B1 진행하자”. 이슈 #39·#43·#47·#55·#57을
  머지 근거와 함께 닫고, 머지된 브랜치 3개를 원격·로컬에서 삭제했다. 브랜치 `phase-4b1-content-security`,
  기준 develop `03d4feb`.
- **취약점 실증:** 수정 전 코드에 합성 메뉴 이름 `<img src=x onerror=...>`를 넣고 실제 Chromium으로
  주문 화면을 열어 **스크립트 실행(`window.__xss===1`)과 `<img>` 삽입**을 확인했다.
  정상 이름 `A&W <cola> "큰컵"`도 `<cola>`가 사라져 표시가 깨졌다. 보안 문제이자 표시 버그였다.
- 구현: 공용 헬퍼 `orders/static/orders/ui/dom.js`(`window.BazaarDom`, 저장소의 auth.js와 같은
  IIFE 방식)를 만들고 `order.html`·`b1_counter.html`을 텍스트 노드·DOM 속성·이벤트 위임으로 옮겼다.
  인라인 `onclick` 5개를 제거했고 버튼은 `data-id`만 들고 이름·가격은 화면 보관 목록에서 읽는다.
  `app.js`의 비우기도 DOM 제거로 바꿔 파서로 가는 쓰기를 남기지 않았다.
  주방 화면은 원래 `escapeHtml`을 적용 중이라 범위에 넣지 않고 회귀로 고정했다.
  미사용 `serve.html`은 고치지 않고 **다시 참조되면 실패하는 테스트**를 넣었다(삭제는 11단계).
- TDD: `orders/tests/test_content_security.py` 9개와 Node `scripts/test_dom_helpers.cjs` 9개를
  먼저 작성해 실패를 확인했다. Node 테스트는 가짜 DOM에 헬퍼를 올려 공격 문자열이 텍스트로만
  들어가는지 본다. CI의 node 단계에 이 파일을 추가했다.
- 검증: 전용 PG에서 전체 **163개(마이그레이션16+앱147), skip0 통과**, check 문제0, drift 없음.
  실제 Chromium 12개 통과(390×844 주문, 1280×900 카운터). 공격 문자열 미실행·요소 미삽입·
  literal 표시·버튼 동작·정상 이름 보존을 확인했다.
- **검사 신뢰성 정정:** 수정 전 템플릿으로 되돌려 같은 검사를 돌렸을 때 처음에는 통과로 나왔다.
  `--noreload` 서버가 템플릿을 캐시하고 있었기 때문이다. 서버를 재시작해 다시 비교했고 그때
  5개가 실패하며 취약점이 재현됐다. 통과만 보고 인수하지 않는다.
- 정리: 브라우저 검사 스크립트와 Playwright는 저장소 밖 작업 디렉터리에만 두었다. 합성 개발 DB·
  로컬 서버는 종료·삭제했고 포트 사용이 없음을 확인했다.
- 리뷰 보완: 독립 보안 리뷰가 머지 차단 없음으로 판정하며 둘을 지적해 반영했다.
  (1) 헬퍼의 `attrs`가 `on*`이나 `javascript:` 주소를 그대로 설정할 수 있어 거부하도록 했다.
  향후 호출자가 기억해야 하는 보장을 헬퍼 안으로 옮긴 것이다. (2) 인라인 핸들러 회귀의 정규식이
  이벤트 이름 6개만 보고 있어 `\son[a-z]+\s*=`로 넓혔다. Node 회귀 2개와 Django 회귀 1개를 추가했고
  재검증에서 전체 **164개(마이그레이션16+앱148), skip0 통과**. 소스 검사의 우회 가능성과
  표 이름·요청사항의 왕복 미검증은 한계로 문서에 적었다.
- 남은 것: 주방 화면 문자열 조립 제거(9·11), `serve.html` 삭제(11), CSP(12A1. 4B2는 외부 스크립트 제거만 했다).
  BK-R011은 Repo-fixed(주문·카운터)이며 해결 상태는 운영 인수 전까지 Open이다.
- 다음: 남은 단계는 대부분 D-004(주문번호)·D-005(결제 규칙) 등 사용자 결정이 선행이다.

## 2026-09-18 — 4A3 배포 후보 구성과 프록시 뒤 클라이언트 주소 경계

- 사용자 지시: “브랜치 지우고 4A3 진행하자 그리고 프록시 뒤 ip 뭉침은 이슈로 달아줘”.
  PR60 머지 후 `phase-4a2-jwt-auth`를 원격·로컬에서 삭제했고, 프록시 위험을 [이슈 #61]로 등록했다.
  브랜치 `phase-4a3-runtime-config`, 기준 develop `395fcba`, 시작 트리 깨끗.
- 결정: D-006의 4A3 실행분을 D-046으로 확정했다(Compose 한 스택, 파일 비밀값,
  내부 네트워크 전용 DB·TLS 생략, 단일 DB 역할). 단일 역할은 권장과 다른 선택이며
  앱 장악 시 자기 테이블 변경·삭제가 가능하다는 잔여 위험을 결정과 문서에 적었다.
- 구현: `<NAME>_FILE` 비밀값 읽기(동시 설정·읽기 실패 거부, 끝 줄바꿈 제거, 내용 미노출),
  `Dockerfile`(비루트·빌드 시 collectstatic), `compose.prod.yaml`(프록시만 발행,
  `internal: true` 네트워크, 고정 프록시 IP), `scripts/pg_prod_init.sql`(NOSUPERUSER·
  NOCREATEDB/ROLE·PUBLIC 권한 회수), `scripts/nginx_prod.conf`.
- **정정:** gunicorn `--forwarded-allow-ips`는 클라이언트 주소를 복원하지 않는다.
  `REMOTE_ADDR`은 소켓 peer 그대로이며 그 옵션은 스킴 등 헤더 신뢰만 정한다.
  후보 스택 로그에서 앱이 항상 프록시 IP를 본다는 것을 실제로 확인했다.
  따라서 이슈 #61을 앱에서 닫았다: `orders/client_ip.py`가 `TRUSTED_PROXY_IPS`에 있는
  peer일 때만 `X-Forwarded-For`를 오른쪽부터 읽고, 그 외에는 peer 주소를 쓴다.
  프록시는 인바운드 헤더를 `$remote_addr`로 덮어쓴다.
- TDD: 비밀값 파일 5건·배포 후보 노출 6건·클라이언트 주소 12건을 먼저 작성해 실패를 확인했다.
  PyYAML이 없어 compose 검증이 조용히 건너뛰던 것을 발견해 `requirements-ci.txt`에 고정하고
  skip을 제거했다.
- 검증: 전용 PG(포트 55453)에서 `scripts/test_postgres.py` **147개(마이그레이션16+앱131),
  skip0 통과**, check 문제0, drift 없음. 전용 Compose `bk4a3-candidate`로 실제 기동해
  config·빌드·앱 역할 migration(0021)·프록시 경유 200·포트 미발행·컨테이너 내부 신뢰 경계·
  프록시 경유 로그인 9회 200/10회 429를 확인했다. `check --deploy`는 HSTS·HTTPS 리다이렉트
  경고 2건이 남으며 실제 TLS 종단이 정해지는 12A1에서 처리한다.
- 정리: 후보 컨테이너·볼륨과 합성 비밀 파일을 제거했다. `secrets/`는 `.gitignore`에 넣었다.
  호스트의 5432 포트는 이 저장소와 무관한 다른 컨테이너의 것이며 후보 스택은 발행하지 않는다.
- 리뷰 보완: 독립 Python 리뷰가 `TRUSTED_PROXY_IPS`의 잘못된 항목이 요청 중 `ValueError`로
  터져 로그인 전면 500이 되는 경로를 찾았다. 시작 시점 거부(항목을 지목하는 메시지)로 옮기고,
  요청 경로에서는 해당 항목을 건너뛰도록 했다. 파싱 결과는 캐시한다. 회귀 6개를 추가했다
  (잘못된 항목 4종의 시작 거부, 정상 3종 시작, 요청 중 미예외, IPv4-mapped IPv6 fail-closed).
  재검증에서 전체 **152개(마이그레이션16+앱136), skip0 통과**.
- 독립 보안 리뷰: 머지 차단 없음. 신뢰 경계는 단일 프록시·단일 홉 구성에서 건전하다고 판정.
  지적 중 둘을 반영했다. (1) 대괄호 IPv6+포트 분기에 회귀가 없어 테스트를 추가했다.
  (2) 비밀번호 파일이 비면 암호 없는 DB 역할이 생기던 것을 초기화 중단으로 바꿨다.
  실제로 빈 파일로 부팅해 역할 0개와 중단 메시지를 확인했고, 중단 후 재시작하면 초기화가
  다시 돌지 않는다는 점(볼륨 삭제 필요)도 문서에 적었다. 프록시 하드닝과 IPv4-mapped IPv6
  정규화는 12A1로 넘겼다.
- 남은 것: 실제 EC2·도메인·인증서·SG/IAM, 헬스/레디니스와 로그·메트릭, 백업·복원(12A2),
  데이터 이전(12A3). BK-R043/044는 Open이다.
- 다음: BLUEPRINT 순서의 4B1(안전한 DOM 렌더링) 또는 사용자가 지정하는 단계.

## 2026-09-17 — 4A2 남은 인증 정책 확정(D-045)과 PR60 반영

- 사용자 지시: “docs 하위 문서 읽고 다음으로 진행해야할 작업 진행하자”. 시작 브랜치 `phase-4a2-jwt-auth`,
  HEAD `917fff1`, 작업 트리 깨끗, 열린 PR은 Draft PR60(CI 통과)뿐이었다.
- 문서상 다음 작업은 PR60의 정책 관문 세 가지였다. 선택지와 사실(`menus`는 주문 화면만,
  `tables`는 미사용 `serve.html`만 호출)을 제시하고 답을 받았다. [D-045](DECISIONS.md).
  비밀번호 교체 시 전 기기 로그아웃(권장·현행), 5분 10회/5분 잠금(권장 5회와 다름),
  메뉴·테이블 조회 인증된 세 계정(현행 유지, 권장과 다름).
- 구현: 실패 횟수를 환경 변수에서 코드 상수 `LOGIN_MAX_FAILURES = 10`으로 옮기고 운영 필수 설정·
  `.env.example`·테스트 프로필의 합성 값 5를 제거했다. 로그인 503은 계정 미설정일 때만 남는다.
  이 이동은 에이전트 판단이며 D-045에 근거를 적었다. 회수·조회 정책은 코드 변경이 없다.
- TDD: 부팅 probe가 환경 값(미설정·0·-1·비숫자·99999)과 무관하게 `[10, 300, 300]`으로 시작하는지,
  HTTP에서 9회 실패는 200·10회째 429와 `Retry-After: 300`인지 먼저 작성해 실패 12건(예상 원인)을 확인했다.
- 검증: 전용 Compose `bk4a2-policy-*`, localhost55452에서 `scripts/test_postgres.py`
  **124개(마이그레이션16+앱108), skip0 통과**, check 문제0, migration drift 없음.
  Node 클라이언트12개 통과, `git diff --check` 통과. 변경 Python의 Ruff는 기존
  `settings_test_pg.py` E402 한 건만 남았다(PR60 HEAD에도 존재, 이번 변경 아님).
- 문서: DECISIONS(D-045, D-002·D-003 해소, D-040/042/044 후속 표기), JWT_AUTHENTICATION,
  README, SESSION_SETUP, BLUEPRINT 4A2, API_AUTHORIZATION·REQUIRED_SETTINGS 배너, RISK_REGISTER.
- 남은 것: 운영 자격증명 공급·HTTPS·프록시 뒤 peer IP 묶임 검토(4A3/12A1). BK-R001/002/019는
  운영 인수 전까지 Open. 배포·실제 자격증명 변경은 하지 않았다.
- 리뷰(사용자 지시 “리뷰는 돌리자”): D-045 커밋 Python 리뷰는 경계(9회 200·10회 429)·테스트 격리·
  잔여 환경 변수 참조·문서 일관성 모두 문제 없음. PR60 전체 보안 리뷰는 머지 차단 결함 없음.
  JWT 알고리즘 고정·type 구분·회전 잠금·타이밍 균등화·401/403·CSRF·쿠키 범위·D-040 매트릭스를 확인했다.
  지적 두 건(IP별 예산의 분산 추측, 프록시 뒤 IP 뭉침으로 인한 잠금)은 코드 결함이 아닌 운영 위험이라
  JWT_AUTHENTICATION 남은 위험과 BLUEPRINT 12A1 인수 기준에 기록했다. 앱이 해시만 받아 강도 검사는 불가하다.
- 다음: PR60 머지 후 BLUEPRINT 순서의 다음 독립 단계(4A3 또는 4B1 등)를 문서 관문 기준으로 고른다.

## 2026-09-15 — 4A2 JWT 인증 구현 후보

- 사용자 지시: PR59를 “머지했고 다음”. GitHub에서 PR59 MERGED와 develop
  `609e69f`를 확인하고 `phase-4a2-jwt-auth`를 만들었다. 시작 작업 트리는 깨끗했다.
- 구현: ID/비밀번호 로그인, PBKDF2 해시 환경 설정, PyJWT2.14.0 고정,
  access15분/refresh절대12시간, 기기별 원자적 회전·로그아웃·401/403,
  CSRF 보호, 레거시 PIN/세션 인가 제거. Migration0021은 인증 테이블 두 개만 추가한다.
- API는 Bearer만 받는다. HTML 이동은 refresh를 검증만 하며 화면 역할/기기를 고정한다.
  브라우저는 메모리에 access를 저장하며 갱신 후 역할/기기가 다르면 쓰기를 재전송하지 않는다.
  모든 활성 화면의 fetch를 공통 클라이언트로 연결했다.
- 독립 JS 리뷰가 계정 변경 후 다른 계정으로 쓰기 재전송과 세 탭 이상 회전 경합을 찾았다.
  화면 세션 결속과 5초 동안 현재 토큰의 access 발급만 허용하는 방식으로 보완했다.
  이때 refresh 회전/쿠키 쓰기는 생략하고 직전 토큰은409를 반환한다.
- 독립 Python 리뷰의 API 캐시, 비정상 숫자 클레임, 사용 불가능한 PBKDF2 해시 지적을 수정했다.
  비공개/no-store 응답, OverflowError 정규화, base64/길이·중복 JSON 키 검증을 추가했다.
  후속 리뷰는 모두 통과했다. 예기치 않은 API 오류에서도 가드의 토큰 지역변수를 가린다.
- 검증: JWT HTTP 경계의 기존 구현 실패를 먼저 확인했다. 새 migration이 생겨
  fresh-install 테스트의 최종 head 기대를0021로 갱신했다. dashboard의 옛 세션 주입은
  실제 JWT 로그인 helper로 바꾸고 계산 단언을 보존했다.
  전용 PG 전체123개(마이그레이션16+앱107), skip0 통과; 이후 추가한 가드 오류보고
  회귀를 포함한 HTTP11개도 통과했다. 최종 발견 수는124개다.
  Django check 문제0, migration drift 없음, Node 클라이언트12개 통과, Ruff·diff check 통과.
  CI에도 로컬 검증과 같은 Node24.7.0 및 클라이언트 테스트를 추가했다.
- 브라우저: 합성 계정과 별도 PG DB로 390x844 주문 로그인/메뉴/4,300원 주문 저장,
  1280x900 주방 로그인/홀·포장·전체 이동/준비 완료/POST 로그아웃/카운터 통계 응답을 확인했다.
  다른 탭의 계정 변경 후 이전 주문 화면은 로그인으로 이동했고 주문이 중복 생성되지 않았다.
  카운터의 과거 고정 날짜는 기존8C 범위로 남겼다. 테스트 프로필의 HTTP 검증이며
  운영 HTTPS·프록시·외부 Realtime·실기기 인수를 뜻하지 않는다.
- 합성 서버·DB와 소유 라벨을 확인한 전용 Compose 컨테이너·볼륨을 모두 정리했다.
  Markdown 링크/펜스와 pip check도 통과했다.
- 아직 미답: 비밀번호 교체 시 전 기기 회수, 실패 제한 수치, 메뉴·테이블 조회 역할.
  구현된 회수·5분 제한은 검토 가능한 제안이며 승인으로 기록하지 않는다.
  LOGIN_MAX_FAILURES는 운영에서 명시해야 하며 실제 자격증명은 공급하지 않았다.
  정책 확인 전에는 구현 후보로 유지하고 머지·배포하지 않는다.
- 다음: 정책 답변을 반영해 최종 PR을 인수한 뒤 4A2 운영/환경 관문을 확인한다.
  [JWT 설정·서비스·복구 계약](JWT_AUTHENTICATION.md), [D-044](DECISIONS.md)를 따른다.

## 2026-09-15 — 4A2 주방 공용 역할 단일화 (D-034)

- 사용자 지시: “docs 문서 읽고 다음으로 작업해야 하는거 진행하자”. 기존 리뷰·PR·문제 없으면 머지 지시를 유지한다.
- 브랜치: `phase-4a2-auth-session-lifetime`, 시작 HEAD `70fe186`, 기준 develop `536a863`.
  시작 작업 트리는 깨끗했고 열린 PR은 없었다.
- **인계 오류 정정:** D-034가 이미 “주방계정 1개로”를 accepted로 기록했는데,
  직전 로그와 인수인계가 통합 여부를 다시 사용자 결정으로 올렸다. 새 승인이 필요한 사항이 아니었다.
  실제 운영 id/password 역시 합성 값으로 하는 로컬 구현의 선행 조건이 아니다.
- **구현:** 역할을 `ORDER`·`B1_COUNTER`·`KITCHEN`으로 통합했다. 주방 전체·홀·포장 URL과
  `ALL`·`HALL`·`TAKEOUT`은 유지하고 모두 KITCHEN을 요구한다. 로그인 카드도 세 개다.
  구 역할의 로그인과 기존 세션은 자동 승격 없이 거부한다. 현재 계정의 API 매트릭스는 유지했다.
- **설정 전환:** 운영 허용 역할을 과거 공개 PIN 목록과 분리했다. 과거 공개 PIN 거부 근거는 보존하고
  개발 기본값·예시·PG 합성 설정은 세 역할로 바꿨다. 기존 환경에서 `KITCHEN_HALL`·`KITCHEN_TAKEOUT`
  항목을 제거하고 재시작해야 한다. 해당 기기는 KITCHEN으로 다시 로그인한다. 운영 적용은 하지 않았다.
- **리뷰 보완:** 홀·포장 로그인 카드 제거가 필터 화면의 유일한 진입점을 없애는 문제를 독립 리뷰가 찾았다.
  주방 화면에 전체·홀·포장 링크와 현재 선택 표시를 추가했다. 세 URL의 링크와 선택 상태를 회귀로 고정했다.
- **검증:** 변경 전 로그인·운영 설정 기준 18개 통과. 새 계약은 기존 코드에서 예상된 단언 7개가 실패했다.
  필터 링크 회귀도 보완 전 세 페이지에서 실패했다. 이후 CSS 선택자까지 세던 테스트의 문자열 집계를
  HTML 속성과 활성 URL 검사로 정정했다. 최종 `.venv/bin/python scripts/test_postgres.py`에서
  **97개(마이그레이션15+앱82), skip0**, `manage.py check` 문제0, 마이그레이션 변경 없음.
  전용 Compose `bk4a2-20260915-unify`, localhost55439, 매 실행 UUID DB를 사용했다.
- **브라우저:** 별도 합성 PG DB·숫자 PIN으로 1280×900 주방 로그인→전체/홀/포장 링크와 선택 상태,
  POST 로그아웃, 390×844 주문 로그인→테이블7·4,300원 주문 저장, ORDER의 주방 접근 거부,
  KITCHEN 재로그인→생성 주문 조회→준비 완료 후 대기 목록 제거를 확인했다.
  실제 운영·외부 Realtime·실기기 인수를 뜻하지 않는다. 합성 서버·DB와 소유 라벨을 확인한
  전용 Compose 컨테이너·볼륨은 검증 후 제거했다. Markdown 링크·코드 펜스와 `git diff --check`도 통과했다.
- **독립 리뷰:** 문서 승인 근거 감사와 Python/보안 통합 리뷰를 수행했다. `origin/develop` 대비
  전체 브랜치 리뷰에서 위 UI·테스트 지적 보완 후 차단 문제 없음. 변경 Python Ruff 통과.
- **다음 범위:** D-035/042/043의 id/password·JWT 발급/갱신·기기별 토큰·401/403을 합성 계정으로 구현한다.
  메뉴/테이블 조회 주체, 자격증명 교체·회수 절차, 반복 로그인 제한 수치가 남은 정책 항목이다.
  현재는 PIN 세션이며 4A2 전체와 BK-R002/BK-R019 종료를 선언하지 않는다.

## 2026-09-14 — 4A2 착수: 모듈 분할, POST 로그아웃, 자격증명 회수

- 사용자 지시: "남은거중에 내가 꼭 결정해야하는건 이야기하고 그냥 처리할수 있는건 처리하자".
  결정이 필요한 것을 먼저 제시하고, 결정에 막히지 않는 것만 진행했다.
- **사용자에게 올린 결정 5개(모두 미답):** 계정 5개→3개 통합 여부(D-034 실행),
  `menus`·`tables` 조회 주체(D-040 잔여), 반복 로그인 제한 수치,
  자격증명 회수·교체 절차, 실제 id/password 값.
- **에이전트가 정한 것 2개(D-043):** 리프레시 쿠키 `SameSite`=Strict,
  리프레시 CSRF는 토큰으로 막고 `SameSite`는 2차 방어. 둘 다 운영 정책이 아니라 기술 판단이라
  직접 정했다. **사용자가 고른 값이 아니므로 뒤집을 수 있다.** D-035의 "둘 중 하나" 문구를 개정했다.
- **`auth.py`를 셋으로 나눴다**(`89281d4`). 역할 이름은 `orders/roles.py`, 인가 가드와
  `csrf_failure`는 `orders/views/guards.py`, 로그인·로그아웃 흐름만 `orders/views/auth.py`다.
  4A2가 JWT 발급·회전·기기 결속을 얹으면 한 파일이 400줄을 넘고, 단계3이 확정한 인가 매트릭스가
  4A2가 다시 쓰는 자격증명 처리와 같은 파일에 남는다. 동작은 바꾸지 않았고 본문은 그대로 옮겼다.
  `CSRF_FAILURE_VIEW` 점 표기 경로도 함께 옮겼다.
- **GET 로그아웃을 닫았다**(`238560b`). `<img src=".../logout/">` 한 줄이면 외부 사이트에서
  현장 화면을 로그아웃시킬 수 있었다. Django가 안전 메서드를 CSRF에서 면제하므로 막는 것이 없었다.
  `@require_POST`로 바꾸고 링크를 걸던 템플릿 2개를 CSRF 토큰이 붙은 form 으로 교체했다.
- **자격증명 회수가 기존 세션에 닿게 했다**(`238560b`). 가드가 세션의 역할을 **정적 표**에
  물었고 그 표는 런타임에 바뀌지 않는다. 그래서 PIN 을 지워도 로그인 화면만 막혔고
  이미 열려 있던 화면은 전부 그대로 접근됐다. 공용 계정에서는 그게 회수의 목적 전부다.
  `orders.roles.provisioned_roles()`를 요청마다 읽도록 두 가드를 바꿨다.
- **범위 경계:** 이것은 회수이지 교체가 아니다. PIN 값을 바꾸면 역할은 여전히 제공 중이므로
  옛 PIN 으로 연 세션은 살아 있다. 그것까지 끊으려면 세션이 자격증명에서 파생된 값을 지녀야 하고,
  그 방식은 아직 미결인 회수·교체 절차에 속한다. `provisioned_roles()` 문서에 적어 두었다.
- **아직 안 한 것:** JWT 발급·리프레시·기기 결속은 시작하지 않았다. 계정 구조(결정 1)와
  자격증명(결정 5)에 달려 있다. 401/403 분리(D-042)도 미뤘다. RFC 9110이 401에
  `WWW-Authenticate`를 요구하는데 아직 받아들이는 스킴이 없어서, 지금 나누면
  스킴 없는 401 을 내보내는 중간 상태가 된다. 토큰 흐름과 같이 한다.
- **리뷰가 치명적 결함을 찾았다.** 회수 기능이 **운영에서 도달 불가능**했다.
  4A1에서 내가 쓴 D-039 부팅 게이트가 `ROLE_PINS`에 역할 다섯 개를 전부 요구해서,
  회수하려고 항목을 지우면 앱이 시작을 거부했다. 게다가 `ROLE_PINS`는 import 시점에 읽히므로
  회수에는 재시작이 필수인데 그 재시작이 실패했다. 직접 부팅해서 재현하고 확인했다.
  게이트를 "모르는 이름은 거부, 아는 이름의 부분 집합은 허용"으로 바꿨다.
  오타 보호는 오히려 강해졌다. 빈 PIN 거부는 유지했다. 부팅 회귀를 추가했다.
- **내 문서가 재시작을 감추고 있었다.** "요청마다 읽는다"가 재시작이 불필요하다는 뜻으로 읽혔다.
  실제로 바뀌는 것은 재시작 필요 여부가 아니라 **재시작이 누구를 끊는가**다.
  예전 수단인 `SECRET_KEY` 교체는 전원을 끊었고, 지금은 그 역할만 끊긴다. 문구를 고쳤다.
- **커밋 메시지의 "템플릿 2개"가 부정확했다.** `serve.html`은 어떤 뷰도 렌더링하지 않는
  고아 템플릿이다. 살아 있는 것은 `kitchen_supervisor.html` 하나다. 삭제는 하지 않았다.
- 리뷰가 찾은 생존 변이 7개를 전부 막았다. 회수 대상이던 것: `ROLE_TO_URLNAME` 교집합,
  키 정규화, 로그아웃의 `rotate_token`, 잘못된 역할의 리다이렉트 대상,
  `_targets_the_api`의 리졸버(접두사 검사로 바꿔도 통과했다), 세션 역할 `.upper()`,
  그리고 **템플릿의 로그아웃 form**(GET 링크로 되돌려도 전부 통과했다. 서버는 막고 있으니
  버튼만 전부 405가 됐을 것이다). 교체가 세션을 끊지 않는다는 문서 주장에도 양성 대조를 붙였다.
  `/orders/api/` 밖에 마운트한 API 뷰용 테스트 URLconf(`orders/tests/urls_outside_api.py`)를 추가했다.
- 검증: 92개(15+77), 모두 PostgreSQL·skip0. 변이 누적 15개 전부 사망.
  낡은 `CSRF_FAILURE_VIEW` 경로는 테스트 이전에 `manage.py check`가 잡았다.
- **이슈 #55·#57 은 PR 이 머지됐는데도 열려 있다.** 닫으려 했으나 권한 분류기가 막았다.

## 2026-09-14 — 4A2 설계 확정과 4A1 잔여 구현

- 사용자 지시: "설계 결정을 지금 진행하면서 동시에 남은 부분 진행하자". 이슈 #57.
- 먼저 사용자가 과거에 말해둔 것을 찾아 대조했다. D-035(2026-09-12)가 역할별 고정 id/pw와
  JWT 방향을 담고 있었고 상세는 4A2로 미뤄져 있었다. 단계3이 그 선행 조건이었고 방금 끝났다.
- **D-042로 네 가지를 확정했다.** 각각 선택지로 제시하고 답을 받았으며
  네 가지 모두 사용자가 권장 표시된 선택지를 골랐다. 다른 문구는 덧붙이지 않았다.
  리프레시 토큰은 `httpOnly` 쿠키, 다중 기기는 기기별 토큰 분리, 수명은 액세스15분·리프레시12시간,
  거부는 401(미인증·만료)/403(역할 거부) 분리다.
  저장 방식은 D-035에서 사용자가 "보안 스토리지?"라고 불확실하게 말한 것을 에이전트가
  구체화한 것이라 적어 두었던 항목이다. 이번에 재확인받았다.
  401/403은 D-036이 미결로 남긴 것이며 갱신 흐름이 생기는 시점이라 이제 의미가 있다.
  **설계만 기록했다. 인증 코드는 건드리지 않았다.**
- 4A1 잔여(D-039)를 구현했다. 운영에서 `SECRET_KEY`·`ALLOWED_HOSTS`·`CSRF_TRUSTED_ORIGINS`·
  `ROLE_PINS`가 없거나 저장소 기본값이면 시작을 거부한다.
  **미설정과 "저장소에 적힌 값 그대로"를 같은 실패로 다뤘다.** 존재만 보면 `.env.example`을
  그대로 복사한 배포가 통과하는데, 그것이 정확히 막으려던 상황이다.
- **`DEBUG`의 기본값을 없앴다.** D-039의 문장을 넘어선 판단이라 결정 기록에 그렇게 표시했다.
  운영 여부를 `DEBUG`로 판정하는데 그 값이 기본 켜짐이면, 아무것도 설정하지 않은 배포가
  검사에 아예 닿지 않고 개발 설정 그대로 뜬다. 거부가 장식이 된다.
  **단계3에서 같은 종류의 실수를 이미 한 번 했다.** 매출 통계를 카운터 전용으로 막아 두고
  같은 숫자가 나가는 주문 조회를 열어 둔 것이다. 막았다고 적혀 있는데 막히지 않는 상태다.
  **`DEBUG` 줄이 없는 기존 `.env`를 쓰던 개발자는 한 줄을 추가해야 한다.**
  이슈 #57의 인수 기준 "개발 모드는 영향 없음"이 이 범위에서 문자 그대로 충족되지 않는다.
- 거부 메시지는 환경 변수 이름만 말하고 값은 넣지 않는다. 누락 항목은 한 번에 모두 보고한다.
  **이 경로에서는 Django 오류 보고가 렌더되지 않는다.** 설정 import가 끝나지 않아
  자격증명 필터도 활성이 아니다. 그래서 메시지 자체가 값과 로그 사이의 유일한 방벽이다.
- `.env.example`은 이미 있어 새로 만들지 않고 확장했다. 항목마다 필수/생성/입력/선택을 표시하고
  키 생성 명령을 넣었다. 4A2용 JWT 자리는 만들되 **필수로 걸지 않았다.**
  읽는 코드가 없는데 필수로 하면 쓰이지도 않는 값 때문에 시작이 막힌다.
- 회귀14개. 처음 9개를 썼는데 문서에는 **세어 보지 않고 10개라고 적었다.** 리뷰가 잡았다.
  리뷰 반영으로 5개를 더해 14개가 됐다. 그중 13개는 새 인터프리터를 띄워 실제로 시작해 보고
  결과를 읽는다. 나머지 하나는 예시 파일을 읽는 검사다.
  이 프로세스에서 설정을 불러오면 이미 import된 모듈이 캐시돼 아무것도 증명하지 못한다.
  정상 기동 대조군을 먼저 뒀다. 그것 없이는 거부가 검사 때문인지 탐침 오류인지 알 수 없다.
  필수 항목은 하나씩 따로 비웠다. 묶어서 비우면 어느 것이 실제로 강제되는지 알 수 없다.
- 기존 테스트 두 곳이 이 변경으로 깨졌다. `settings_test_pg`가 환경을 비우고 기본 설정을
  별표 import 해서 `DEBUG` 명시가 필요했고, `test_database_config`의 탐침도 같은 이유로 실패했다.
- **거부 경로가 하나에서 둘로 늘었다.** 같은 파일의 다른 테스트가 "오류가 났다"만 단언하는데,
  이 변경 전에는 `settings.py`의 `ImproperlyConfigured`가 `DATABASE_URL` 한 곳뿐이라
  그 단언이 충분했다. **이 변경이 두 번째 거부 경로를 만들어 그 단언을 불충분하게 만들었다.**
  거부 사유가 `DATABASE_URL`인지 확인하도록 좁혔다. 기존 결함을 발견한 것이 아니라
  내가 만든 위험을 같은 커밋에서 닫은 것이다.
- 1차로 변이10개를 주입해 전부 사망을 확인했다. 리뷰 반영 후 12개를 더 확인했고
  그중 1개는 생존한다. 길이 하한이 그 값을 독립적으로 잡기 때문이며 문서에 사유를 적었다.
  전체80개(15+65) 통과, skip0. 소유 label 확인 후 정리했다.
- 위험: **BK-R028·BK-R002 어느 쪽도 종료하지 않았다.** 저장소에서 기본값 대체를 막았을 뿐
  운영 실제 값은 미확인이다. BK-R002의 PIN 시도 제한 부재와 공용 계정 성질은 D-042의 4A2 전환이 다룬다.
  운영에서 `DEBUG=1`을 막는 것은 4A3의 `check --deploy` 범위다.

## 2026-09-13 — 단계3 구현: API 역할 인가와 CSRF 경계

- 사용자 지시: 단계3 구현 진행. 이슈 #55, 브랜치 `phase-3-api-authorization`.
- 착수 전에 D-040과 실제 화면을 대조해 충돌을 찾았다. D-040은 주문 취소를 주방 카운터에
  두었으나 취소 버튼은 주방 총괄 화면에만 있고 카운터 화면은 통계 전용이라 주문 목록조차 없다.
  서버만 조이면 아무도 취소할 수 없게 되는 상태였다. 사실을 알리고 선택을 받았다.
  사용자는 처음 "카운터 화면에 취소 UI까지"를 골랐다가 "취소랑 이런 부분은 주방에만 두고
  카운터는 그대로 두자"로 바꿨다. D-040을 개정으로 표시했고, 그 결과 세 항목이 모두
  현재 화면과 일치해 UI 변경 없이 서버만 조이는 작업이 됐다.
- 구현: `require_api_roles()`를 추가해 API 거부를 JSON403으로 답한다. 화면은 리다이렉트하지만
  API는 그럴 수 없다. 리다이렉트가 HTML 로그인 페이지로 도착하면 호출자에게는 권한 문제가
  아니라 JSON 파싱 오류로 보인다. 세션 없음과 역할 불일치를 모두 403으로 답하고,
  401/403 구분은 리프레시 흐름이 있는 4A2로 남겼다(D-036 미결).
- **인가를 `cache_page` 바깥에 두었다.** 안쪽이면 인가된 호출자가 채운 캐시 본문이
  그 뒤 누구에게나 제공된다. 메서드 검사보다도 먼저 실행되게 해서 미인증 호출자가
  경로의 허용 메서드를 알아내지 못하게 했다.
- 주체가 미확정인 엔드포인트5개는 **역할을 제한하지 않고 인증만 요구**했다.
  D-040이 정하지 않은 것에 역할을 추측으로 넣으면 받지 않은 승인을 만드는 것이다.
- CSRF: 쓰기3개의 `@csrf_exempt`를 제거했다. 프런트엔드는 이미 `X-CSRFToken`을 보내고 있었으나
  토큰을 `csrftoken` 쿠키에서 읽으므로, 쓰기 기능이 있는 화면4개에 `@ensure_csrf_cookie`를 붙여
  로그인과 첫 쓰기 사이에 쿠키가 사라져도 조용히 깨지지 않게 했다.
- 교체 순서를 지켰다. 준비 단계의 `OPEN` 기대값이 실제로 실패하는지 먼저 확인했고(43개 단언)
  그 다음 승인된 매트릭스로 바꿨다. 그 확인 없이는 통과하는 suite가 아무것도 증명하지 않는다.
- 기존 여정은 깨지지 않았다. 인가 적용 직후 실패43개가 **전부 `test_permissions`**였고
  baseline·dashboard는 그대로 통과했다. 그 회귀들이 이미 올바른 역할로 로그인하고 있었기 때문이다.
- 공허하지 않음: 변이8개를 주입해 모두 실패로 전환되는 것을 확인하고 원복했다.
  인가 제거, 역할 제한 완화, **인가를 cache 안쪽으로 이동**, GHOST 검사 제거,
  거부를 리다이렉트로, `csrf_exempt` 복원, `ensure_csrf_cookie` 제거, 거부 본문에 역할 노출.
  cache 순서와 쿠키 제거는 조용히 깨지는 종류라 특히 중요했다.
- 검증: 전용 Compose에서 전체57개(15+42) 통과, skip0. 소유 label 확인 후 정리했다.
  (리뷰 보강 후 59개(15+44)가 됐다. 아래 리뷰 항목 참조.)
- **독립 리뷰 3개를 돌렸고 머지하지 않았다.** 보안·테스트·문서 역할로 나눠 병렬 실행했다.
  보안과 테스트 리뷰가 **서로 독립적으로 같은 두 가지**를 지적했고 둘 다 직접 확인했다.
  - **매출 기밀성이 달성되지 않았다.** `stats-dashboard`를 카운터로 제한했지만
    `orders-collection` GET이 주문마다 `total_price`·`payment_method`·현금/식권 구성·거스름돈을
    담아 인증된 전 계정에 준다. `order-detail`도 같다. 즉 제한한 숫자가 옆문으로 나간다.
    D-040이 이 주체를 정하지 않아 좁히지 않았는데, 여기서는 "정하지 않음"이 중립이 아니라
    이미 내린 제한을 무효로 만든다. **사용자 결정 전까지 열어 둔다.**
  - **회귀가 역할 확대를 볼 수 없었다.** 테스트가 기대 허용 집합을 `KITCHEN_ROLES`·`COUNTER_ROLES`로
    **코드에서 import**했다. 상수를 넓히면 기대값이 같이 움직여 통과한다.
    변이 8개가 데코레이터 호출부만 건드렸기 때문에 이 종류를 못 봤다. 내 변이 설계의 결함이다.
- 보강: 승인된 매트릭스를 테스트에 리터럴로 적고 상수는 따로 대조한다. 엔드포인트 표를
  `orders/urls.py`의 API 경로 집합과 대조하고 개수도 고정한다(dict 리터럴은 중복 키를 조용히 버린다).
  거부 본문 단언이 영문 코드만 찾던 것을 한국어 표시명과 정확 본문까지로 넓혔다.
  `require_api_roles()`는 역할 이름을 받고도 집합이 비거나 모르는 이름이면 import 시점에 멈춘다.
- 새 변이 5개(역할 상수 확대2종, 빈 집합, 키 중복, 한국어 노출)를 주입해 전부 사망을 확인했다.
  전체59개(15+44) 통과, skip0. 소유 label 확인 후 정리했다.
- 리뷰가 지적한 인증 측 약점은 **이 단계에서 고치지 않았다.** 세션 고정(`cycle_key()` 없음),
  토큰 없는 쓰기가 CSRF middleware에서 HTML403으로 거부되는 점, 역할 회수가 기존 세션에 닿지 않는 점,
  CSRF 가능한 GET 로그아웃이다. 모두 인증 코드 변경이라 4A2 승인 사안이다.
  세션이 이제 9개 API의 유일한 인가 자격증명이므로 전보다 무겁다는 점은 기록했다.
- 문서 리뷰가 찾은 낡은 문장을 고쳤다. D-003 색인 행이 개정 전 주체(취소=카운터)를 그대로 말했고,
  D-036 실행 상태가 "아직 변경하지 않았다"였으며, PR #53 미머지 서술이 3곳 남아 있었다.
  #53 머지 시각을 2026-09-13으로 적었는데 실제로는 **2026-09-12 12:33(KST)**다. 추론값을 넣은 실수다.
  D-040에는 사용자가 붙인 "일단"과, `order-status` 전체로 읽은 것이 에이전트 판단이라는 점을 남겼다.
- **2차 반영(사용자 결정).** 매출 노출과 인증 약점을 어디까지 손댈지 물었고 답을 받았다.
  - **주문 조회를 주방·카운터로 제한**했다(D-040 2차 개정). 생성 POST는 전 계정 그대로다.
    `orders-collection`이 메서드별로 주체가 다른 첫 엔드포인트라 `by_method`를 추가했다.
    이 변경으로 baseline 회귀3개가 깨졌다. ORDER로 만든 주문을 ORDER로 읽어 검증했기 때문이다.
    **권한을 되돌리지 않고 읽기 전용 helper가 주방 세션으로 읽도록 바꿨다.**
    주문 화면은 생성만 하고 읽어오지 않으므로 이것은 검증 단계지 여정이 아니다.
  - **세션 고정과 CSRF 거부 형식**을 닫았다(D-041). 로그인 시 `cycle_key()`를 부르고,
    `CSRF_FAILURE_VIEW`로 API는 JSON·화면은 HTML로 거부한다. API 판정은 경로 접두사가 아니라
    URLconf 해석으로 한다. 접두사는 라우트가 옮겨지면 조용히 틀려진다.
  - 로그아웃 GET·역할 회수·PIN 시도 제한은 사용자 선택에 따라 4A2로 남겼다.
- 새 변이5개(조회 주체 확대, GET 제한 제거, `cycle_key` 제거, `CSRF_FAILURE_VIEW` 제거,
  화면까지 JSON)를 주입해 전부 사망을 확인했다. 누적 변이18개다.
  전체63개(15+48) 통과, skip0. 소유 label 확인 후 정리했다.
- **3차 리뷰.** 2차 반영으로 생긴 새 인가 코드를 다시 리뷰했고 여섯 가지가 더 나왔다.
  가장 무거운 것은 `by_method`가 **메서드 이름을 검증하지 않은** 점이다. 오타 난 키는
  영영 매칭되지 않아 그 메서드를 엔드포인트 기본값에 남기는데, 이 기능을 쓰는 유일한
  엔드포인트에서 그 기본값은 "인증만"이다. 역할 오타는 이미 막아 두고 정작 접근을
  **허용하는 쪽** 실수는 열어 뒀다. import 시점에 멈추게 했다.
  HEAD를 GET의 주체로 인가하게 했다. `require_http_methods`가 오늘 405로 막지만
  그 데코레이터는 가드의 안쪽이라 거기에 기대면 인가가 부수 효과가 된다.
  `cycle_key()`를 `flush()`로 바꿨다. 전자는 내용을 새 키로 옮긴다.
  `rotate_token()`을 더했다. 세션 키는 자격증명의 절반이고 Django의 `login()`도 둘을 같이 한다.
  CSRF 실패 뷰의 API 판정을 모듈 이름 `endswith`에서 가드가 다는 표시로 바꿨다.
- 새 변이7개를 주입해 전부 사망을 확인했다. 누적 변이25개. 전체66개(15+51) 통과, skip0.
- **테스트 엄밀성 리뷰는 실행하지 못했다.** 세션 한도로 중단됐다. 보안·정확성 리뷰만 완료했다.
  사용자에게 알리고 다시 돌릴지 물었고 **리뷰 없이 머지**를 선택했다.
  따라서 새 테스트의 공허성 근거는 내 변이25개뿐이며 독립 검토는 받지 않았다.
- 3차 리뷰가 집계 우회도 찾았다. `kitchen-menu-summary`의 메뉴별 미조리 수량과 `menus`의 단가를
  합치면 카운터 전용인 `stats-menu-counts`의 메뉴별 금액이 재구성됐다. 금액을 담지 않는 둘이
  합쳐서 금액이 된 경우다. 호출하는 화면이 없어 **사용자 결정으로 경로와 뷰를 지웠다.**
  주체를 새로 정하는 대신 표면을 없앤 것이라 D-040에 추측을 더하지 않는다.
  `test_baseline`이 이 집계를 교차 확인에 쓰고 있어 그 단언만 걷어냈다. 같은 수량을
  `order-detail`과 DB에서 확인하는 단언이 남아 불변조건은 그대로다.
  지운 경로를 가드 없는 뷰로 되살려 매트릭스가 잡는 것을 확인했다.
- 위험: BK-R001의 세 항목이 저장소에서 닫혔다. **해결 상태는 Open이다.**
  인증 방식을 바꾸지 않았고 브라우저 여정·401/403도 미검증이다.
  인증 방식은 바꾸지 않았으므로 BK-R002 공용 PIN 약점은 그대로다.
  브라우저 실제 여정과 401/403은 미검증이고 외부 노출·배포는 미실행이다.
- 다음: 401/403 구분, 주문 생성·조회 주체, 주방 계정 단일화, 토큰 수명·회수는 4A2다.

## 2026-09-12 — D-034~039 확정과 배포 브랜치 main 정렬

- 사용자에게 막힌 결정을 정리해 제시하고 답을 받았다. 확정한 것은 여섯 가지다.
  D-034 주방 공용 계정 단일화(D-032의3계정 구분 대체), D-035 JWT 역할 계정 인증과
  httpOnly 쿠키 리프레시 토큰, D-036 익명 차단·CSRF 면제 제거·JSON403,
  D-037 보존 대상 과거 주문 없음, D-038 EC2 배포와 main=배포/develop=개발,
  D-039 설정 누락 시 시작 거부와 예시 파일 제공.
- 주방 계정은 사용자가 "총괄은 한명 아니야?"라고 되물어 코드로 확인했다.
  `/orders/kitchen/`(`mode_scope: ALL`)이 이미 주방3역할 모두에게 열려 있고 홀·포장은 필터 뷰였다.
  사실을 알린 뒤 "1개로" 결정을 받아 D-032의 해당 항목을 개정으로 표시했다.
- 과거 데이터는 "아마 없을 것"이라는 앞선 언급을 추측으로 쓰지 않고 다시 물어 확정했다.
  D-037은 삭제 승인이 아니라 보존 대상 부재의 사실 확인이며, 운영 DB에 데이터가 발견되면 무효다.
- 리프레시 토큰 저장소는 사용자가 물음표를 단 "보안 스토리지"를 httpOnly 쿠키로 구체화했다.
  그 결과 CSRF 위험이 되살아나므로 D-036을 D-035의 필수 동반 작업으로 묶었다.
  공용 계정 다중 기기에서 토큰 회전이 서로를 로그아웃시키는 경합도 4A2 인수 조건에 넣었다.
- main 정렬: 조사 결과 main은 develop보다 커밋7개 앞서 있었으나 고유 파일이 없고,
  고유 diff는 전부 develop이 의도적으로 교체한 과거 버전이었다. 특히 main의 `0020`은
  빈 DB에서 22003으로 실패하는 수정 전 버전이라 그대로 배포하면 BK-R005를 재현했을 것이다.
  `numbering.py`는 D-029에서 제거한 SQLite fallback, `api.py`는 PR42가 고친 BK-R016 별칭 결함이었다.
- 정렬 방식은 일반 머지다. **force push·이력 재작성을 하지 않았다.** 머지 커밋의 부모는
  main(`bca9e40`)과 develop(`df837e7`) 양쪽이고 결과 트리는 develop과 바이트 동일하다. PR #53으로 올렸다.
- 레거시 브랜치는 사용자가 "날려도 된다"고 했으나 조사에서 `reactor`·`rlagycks-patch-1`·
  `chore/merge-main-into-develop` 3개에 develop에 없는 고유 diff가 있어 삭제하지 않았다.
  나머지5개는 고유 내용이 없다. BK-R025(단계 G)의 별도 확인 사안으로 남긴다.
- 위험 상태는 어느 것도 종료하지 않았다. BK-R001은 Critical·Open, BK-R028·BK-R025도 Open이다.
  BK-R017/D-008/D-017은 조건 소멸로 범위만 좁아졌고 검증 완료가 아니다.
- PR #52(단계3 준비 측정)를 머지하고 이슈 #51을 닫았다. 브랜치는 PR head 대조 후 삭제했다.
- 검증: 정렬 브랜치에서 전체53개(15+38) 통과, skip0. 문서 링크·앵커, `git diff --check` 통과.
- 리뷰3건(읽기 전용, 병렬): PR53 git 안전성 / PR54 기록 충실성 / 문서 세트 감사.
  PR53은 독립 검증을 통과했다. 리뷰어가 내가 하지 않은 확인까지 더해 머지 결과 트리가
  develop과 같은 트리 객체(`066c57b`)이고 main의 커밋7개가 모두 도달 가능함을 확인했다.
- PR54에서 지적받아 고친 것:
  - **완료되지 않은 일을 완료로 적었다.** "main은 develop과 일반 머지로 정렬했다"고 썼으나
    PR #53은 열려 있고 `origin/main`은 여전히 `bca9e40`이다. 세 곳을 미머지 상태로 고쳤다.
    위험 등록부는 그 노출을 과거 조건형으로 적고 있어 현재형으로 바꿨다.
  - **사용자가 결정하지 않은 것을 결정으로 적었다.** 거부 응답 JSON403은 언급된 적이 없고
    CSRF는 "준비는 해두자"인데 "제거한다"로 굳혔다. 익명 차단만 확정으로 남기고
    CSRF는 준비 범위, 401/403 구분은 미결로 되돌렸다.
  - **인용문을 변조했다.** "보안 스토리지?"의 물음표와 "당연히", "역활 별로 나누자"를 지웠다.
    물음표는 httpOnly가 에이전트 제안이라는 근거이므로 복원하고 그 사실을 명시했다.
  - D-021을 통째로 accepted로 바꿔 단일 호스트 수용과 리소스 생성 경계까지 풀 뻔했다. 부분 확정으로 고쳤다.
  - D-038에만 경계 절이 없었다. 배포 결정이라 가장 필요한 곳이었다.
  - 쿠키 인증이 CSRF를 전면 부활시킨다는 서술이 과장이었다. refresh 엔드포인트로 범위를 좁혔다.
  - `.env.example`이 이미 있는데 "만들지 않았다"고 적었다. 확장으로 고쳤다.
  - 사용자가 말한 v1/v2 버전 표기 지시를 누락했다. D-038의 미기록 잔여로 남겼다.
  - 홀·포장 페이지에 실제 역할 데코레이터가 있어 단일화 시 **넓혀야** 한다는 점을 빠뜨렸다.
- 문서 세트 감사에서 지적받아 고친 것: 필수 읽기 집합의 `README.md`·`BASELINE.md`를 열지 않았고,
  BLUEPRINT는 자기 수정 네 줄 아래에서 주방3계정 유지와5→3 통합 금지를 그대로 두고 있었다.
  SESSION_SETUP은 같은 문서 안에서 D-001 미정과 해소를 동시에 주장했다.
  AUTHORIZATION_MATRIX는 D-036이 답한 질문을 여전히 열린 질문으로 두고 있었다.
  6곳에 복제된 배너의 PR 목록은 머지될 때마다 다시 낡으므로 **포인터로 바꿔 구조적 원인을 제거했다.**
- D-040으로 사용자의 권한 답변을 기록했다. "총괄"이 3계정 중 무엇인지 모호해 직접 확인했고
  주방 카운터(B1_COUNTER)로 확정했다. 취소=카운터, 조리 진행=주방, 매출 조회=카운터다.
  사용자가 답하지 않은 생성·조회 엔드포인트는 미정으로 남겼다.
- 위험은 어느 것도 종료하지 않았다. BK-R001 Critical·Open, BK-R005는 main 미정렬로 현재 노출 중이다.
- 다음: PR54를 먼저 머지하고 PR53에 develop을 다시 합쳐야 main이 최신 문서를 갖는다.


## 2026-09-11 — 단계3 준비: BK-R001 권한 현황 전수 측정

- 사용자 질문 "다음 작업이 뭐지"에 대해 문서 기준으로 정리한 결과, 남은 작업이 대부분
  결정 관문에 막혀 있었다. 유일한 Critical인 BK-R001은 단계3이고 선행2A는 완료됐지만
  D-003 권한 매트릭스가 대기 중이다. 사용자가 고른 것은 결정 없이 가능한 준비 작업이다.
- BLUEPRINT 단계3의 "목표 매트릭스 확정 전에는 fixture/검사표만 준비한다" 범위에 해당한다.
  인가를 강제하는 코드는 변경하지 않았다. `orders/views/api.py`는 기준 커밋과 바이트 동일하다.
- 측정: 행위자7종(익명·역할5개·서버가 발급한 적 없는 역할을 담은 GHOST 세션)에 대해
  API9개와 화면5개의 실제 응답을 분류했다. 결과는 API9개 전부가 모든 행위자에게 열려 있고,
  쓰기3개는 CSRF를 강제하는 클라이언트에서도 토큰 없이 통과한다.
  ORDER 역할이 조리 진행 변경과 주문 취소를 모두 수행한다. 로그아웃은 API 접근을 바꾸지 않는다.
  `api.py`가 세션·역할을 한 번도 읽지 않으므로 화면 단위 권한은 실효가 없다.
- 공허하지 않음 근거 두 가지를 넣었다. 화면 권한이 같은 세션으로 실제 거부되는 것을 대조군으로
  고정해 "전부 OPEN"이 클라이언트 미인증 때문이 아님을 보였다. 또 `stats_dashboard`에
  역할 검사를 넣는 변이로 단언7개가 실제로 실패하는 것을 확인하고 파일을 원복했다.
  다른 엔드포인트 단언은 영향받지 않아 선택성도 확인했다.
- 산출물: [권한 회귀7개](../../orders/tests/test_permissions.py)와
  [측정과 D-003 결정표](AUTHORIZATION_MATRIX.md). 결정표는 답이 아니라 질문7개를 담았다.
- 위험 상태는 바꾸지 않았다. BK-R001은 Critical·Open이며 증거만 보강됐다.
  D-031 외부 접속 확정으로 이 위험의 "외부 노출 범위" 미확인이 노출 상향 방향으로 해소된 점을 적었다.
- 검증: 전용 Compose에서 전체53개(15+38) 통과, skip0. 소유 label 확인 후 정리했다.
  문서 링크·앵커, `git diff --check` 통과.
- 다음: D-003 결정이 없으면 단계3 구현은 시작하지 않는다. 결정표의 질문7개가 입력이다.

## 2026-09-10 — 머지된 작업 브랜치 정리와 인계 문서 갱신

- 사용자 지시: 브랜치를 정리하고 문서를 업데이트한다.
- 삭제 전에 각 브랜치 tip이 해당 PR의 머지 시점 head와 같은지 확인했다. PR36·38·40·42·44·46·48의
  7개 브랜치 모두 일치해 머지 이후 push된 커밋이 없음을 확인하고 원격·로컬에서 삭제했다.
  squash 머지라 `git branch --merged`로는 판정되지 않으므로 PR head 대조를 근거로 사용했다.
  삭제한 tip: `98df3cd` `4172e58` `a26d1a1` `2acfd4a` `fb87fb3` `fb120c0` `e64a44a`.
- 삭제하지 않은 것: `origin/main`과2025-09~10 사용자 브랜치8개는 이번 정리 대상이 아니다.
  이들의 정식 정리는 BK-R025(단계 G)의 별도 원격 승인 사안으로 남고 BK-R025는 Open 그대로다.
  로컬 `chore/astra-modernization-setup`(`2d5bb78`)은 develop에 없는 커밋2개가 있어 남겼다.
  `git push --delete`가 도구 정책에 막혀 같은 목적의 GitHub ref 삭제 API를 사용했다.
  보관 tag는 만들지 않았고 삭제한 팁은 `refs/pull/<번호>/head`로만 복구된다. 결정은 D-033에 기록했다.
- 문서: 5개 파일에 공유된 상태 배너가 PR44에 멈춰 있어 PR46·PR48을 반영했다.
  SESSION_SETUP은 "현재 브랜치는 phase-4a1-sensitive-errors"를 지우고 기준 ref를 고정하는 대신
  매 세션 조회하도록 바꿨다. 삭제한 브랜치와 남긴 브랜치의 이유도 적었다.
  SENSITIVE_ERRORS는 머지 커밋과 브랜치가 이력임을 명시하고 회귀4개→6개를 반영했다.
  변이8개는 저장소에 없는 로그의 기록된 관찰임을 밝히고 WORKLOG를 출처로 가리키게 했다.
  README·ANALYSIS_REPORT·GIT_RECOVERY·BLUEPRINT 단계 G와 BK-R028 행,
  RISK_REGISTER·MODEL_DELEGATION_REVIEW·03_IMPLEMENT_PHASE·POSTGRES_ONLY·
  DASHBOARD_EXECUTION·MIGRATION_REPAIR_REVIEW의 진행 중 서술과 누락된 출처도 고쳤다.
- 위험 상태는 바꾸지 않았다. BK-R028은 Open(4A1/운영 인수 대기)이고 env 누락 시작 실패는 여전히 미구현이다.
- 리뷰3건(읽기 전용, 병렬): 사실 정확성 / 문서 세트 일관성 / 프로세스·위험 상태 감사.
  같은 배너가5개 파일에 있는데4개만 고치고 WORKLOG에 개수까지 틀리게 적은 것,
  `열린 PR과 작업 브랜치는 없다`가 이 PR 자신 때문에 거짓인 것, develop SHA를 고정해
  머지 즉시 낡게 만든 것, README·GIT_RECOVERY·BLUEPRINT 단계 G가 브랜치 삭제와 모순인 것,
  측정값이던 `4개 테스트의6개 조건`을 근거 없는 `6개 테스트`로 바꾼 것,
  변이8개 목록에 없는 항목을 예시로 든 것, BK-R028 종료 증거에 `(PR46 적용)`을 붙여
  JSON 계약까지 처리한 것처럼 좁힌 것을 각각 지적받아 모두 되돌리거나 고쳤다.
  리뷰 하나가 "일치한다"고 넘긴 BK-R028·변이 목록 두 건은 직접 확인해 다른 두 리뷰가 옳았다.
- 검증: 변경한 파일의 상대 링크·앵커 해석, `git diff --check` 통과. 문서 외 파일 변경 없음.
- 다음 작업은 고르지 않았다. 코드·schema·migration·CI 설정 변경 없음. 문서와 브랜치 참조만 갱신했다.

## 2026-09-09 — PR48 머지와4A1 브랜치의 develop 통합

- 사용자 지시: PR48을 먼저 머지하고 PR46도 머지한다.
- PR48을 squash merge했다. develop 기준은 `c44338e`다.
- PR46은 develop 갱신 후 mergeable UNKNOWN이었고 `git merge-tree` dry-run이
  DECISIONS·RISK_REGISTER·WORKLOG3개 충돌을 보였다. 세 파일 모두 양쪽을 보존해 해소했다.
  DECISIONS는 D-030 뒤에 D-031·D-032를 이어 붙였고, WORKLOG는 파일이 요구하는 최신순으로
  다섯 항목을 재배열했다. RISK_REGISTER는 BK-R002의 D-031/032 한정과 BK-R028의 Repo-fixed를
  함께 남기고, 머리말이 이미 BK-R028을 노출 상향 대상으로 명시하므로 그 행에도 같은 한정을 적었다.
- 어느 위험도 종료·완화하지 않았다. BK-R028은 여전히 Open(4A1/운영 인수 대기)이다.
- 통합 후 PG 전체 회귀를 다시 실행해 기록한다. 운영 배포·계정/자격증명 변경은 없다.

## 2026-09-09 — 결정 문서를 4A1 브랜치에서 분리

- 독립 문서 감사가 D-031/D-032 변경이 `phase-4a1-sensitive-errors`에 미커밋으로 쌓여 있는 것을
  범위·인계 위험으로 지적했다. 사용자 지시로 develop 기준의 이 브랜치로 옮겼다.
  4A1 PR46은 오류 보고 비노출 범위만 남기고, 아래 세 항목의 결정 내용은 원문 그대로 옮겼다.
- 감사가 지적한 직접 충돌을 함께 처리했다. BK-R028의 "외부접속 여부 미확인"은 D-031이 답한
  미지수이므로 위험 등록부에 외부 접속 전제를 반영하고 BK-R002/R044의 노출 성격도 갱신했다.
  BLUEPRINT의4A1/4A2 D-002 관문 문구도 확정분과 미정분을 구분하도록 고쳤다.
- 위험 상태는 낮추지 않았다. 외부 접속 확정은 완화가 아니라 노출 상향이며 BK-R002/028/044는 Open이다.
- 계정 생성·인증 코드/스키마·자격증명·DNS/인증서/방화벽·배포는 여전히 미실행이다.
- 문서 링크·앵커·명령 구문·diff를 검증한다. 애플리케이션·DB·외부 서비스 변경 없음.

## 2026-09-09 — PR46 독립 리뷰3건 반영

- 사용자 지시: PR46을 PR40·42와 같은 방식으로 리뷰하고 지적을 반영한다. merge는 범위 밖이다.
- 리뷰3건(읽기 전용, 병렬): 구현 보안 정합성 / 테스트 검출력 / 문서·프로세스 감사.
  적용된 가림 구현 자체에는 CRITICAL·HIGH 지적이 없었다. 정규식 이어붙이기 안전성,
  DEBUG 기본값이 켜진 이 저장소에서 is_active 강제가 필요한 이유, 데코레이터 순서 무관성을
  Django5.2.17 소스와 실제500 발생으로 각각 확인했다.
- 반영한 테스트 지적: 빈 오류 보고에서도 통과하던 사례2개가 있었고, 그중 하나가
  `get_post_parameters` 오버라이드를 잡는 유일한 단언이었다. DEBUG일 때 보고서 표식을
  `request_failure`에서 확인하도록 올려 모든 본문 단언이 대조군을 갖게 했다.
  치환 문자열이 실제로 나타나는지, 과잉 가림 없이 `role`이 살아남는지도 고정했다.
  커버리지가 없던 `@sensitive_post_parameters`는 Django 기본 필터·DEBUG=False 조건의
  독립 사례로 고정하고, 상속 flags(대소문자 무시)를 `password` 필드로 고정했다. 회귀는4개→6개다.
- 반영한 구현 지적: POST 필드 대조를 정확 일치에서 상속 패턴 검색으로 바꿔 `role_pin`·
  `pin_confirm`·`password`도 덮게 했다. PIN 분기는 앞뒤를 비문자로 한정해 `NUMBER_GROUPING`·
  `pinned_note`의 과잉 가림을 없앴다. 가림 중 예외가500 처리 자체를 무너뜨리던 경로는
  전부 가린 값을 반환해 실패를 닫도록 했다.
- 반영한 문서 지적: 5개 파일의 배너가 수치만 갱신되고 머지 PR 목록은 PR42에 멈춰 있던 것,
  MODEL_DELEGATION_REVIEW가 PR44를 진행 중으로 서술하고4A1을 누락한 것,
  BLUEPRINT의4A1 승인 파일 목록이 실제 편집한 `orders/views/auth.py`(4A2 소유)를 담지 않아
  파일 소유권 교차가 기록되지 않은 것, RISK_REGISTER의 Repo-fixed가 그 행의 종료 증거보다
  강했던 것, 어느 문서도 PR46·head를 적지 않던 것, TESTING이4A1 회귀만 출처를 빠뜨린 것을 고쳤다.
  SENSITIVE_ERRORS에는 querystring이 reporter filter로 원리적으로 커버 불가라는 점과,
  가림이 `pin`·`expected` 이름에 묶여 있어 D-032 구현 시 함께 갱신해야 한다는 주의를 추가했다.
- 분리: 감사가 범위·인계 위험으로 지적한 미커밋 D-031/D-032 문서를 develop 기준
  `docs/external-access-shared-accounts` 브랜치로 옮겼다. 원문은 그대로 두고 외부 접속 전제의
  위험 재점검과 BLUEPRINT D-002 관문 문구를 그 브랜치에서 함께 처리했다.
- 검증: 격리 PG에서 보안 회귀6개 통과. 이전에 살아남던 mutant8개(상속 flags 제거,
  두 데코레이터 각각 제거,`get_post_parameters`/`get_cleansed_multivaluedict` 제거,
  전체 가림, 빈 치환 문자열, copy 제거)가 모두 실패로 전환됐다.
  빈 보고서 강제 실험에서 6개 전부 실패해 공허하지 않음을 확인했다. 총46개(15+31)다.
- 하지 않은 것: merge·운영 배포·계정/자격증명 변경·0019 정책. BK-R028과4A1 전체는 Open이다.

## 2026-09-09 — 주방 공용 계정의 기존 구분 유지

- 주방 계정을 하나로 합칠지 전체·홀·포장으로 나눌지에 대한 사용자 답변은 기존 구분 유지다.
  D-032와 현재 인계·계획에 KITCHEN/KITCHEN_HALL/KITCHEN_TAKEOUT별 공용 계정을 기록했다.
- 계정 구분을 현재 전체 주방 페이지 접근 제한이나 주문 취소·조회 권한 변경으로 해석하지 않았다.
  통계/관리자 권한 구분과 세션 정책은 미정이다. 앞선 미커밋 문서 변경은 보존했다.
- 문서 링크·앵커·렌더·명령 구문·위험/단계 연결·diff를 검증한다. 계정 생성·코드·스키마·배포·원격 Git 변경 없음.

## 2026-09-09 — 역할별 공용 계정 인증 방향 확정

- 사용자 답변에 따라 D-032에 인증 도입·역할별 공용 계정 방향을 기록하고 D-002를 갱신했다.
  직원별 계정 대신 공용 계정으로 인증하며 서버가 계정에 연결된 역할로 권한을 판단한다.
- SESSION_SETUP·BLUEPRINT에 반영했다. 앞선 외부 접속 결정의 미커밋 문서 변경을 보존했다.
- 주방 전체/홀/포장 계정 구성, 통계 조회/관리자 수정과 역할별 세부 권한, 세션 만료·회수는 미정이다.
  실제 계정 생성·인증 코드·스키마·자격증명·배포는 변경하지 않았다.
- 문서 링크·앵커·렌더·명령 구문·위험/단계 연결·diff를 검증한다. 이번 갱신은 로컬 문서만 반영한다.

## 2026-09-09 — 외부 접속 방향 확정

- 사용자 답변: 외부에서도 접속 가능하게 하고 HTTPS·도메인 연결을 검토 중이다.
- D-031에 외부 인터넷 접속 허용을 기록하고 D-002의 접속 범위만 부분 확정으로 갱신했다.
  SESSION_SETUP·BLUEPRINT에도 반영했다. 로그인 방식·역할 권한·세션 정책은 미정이다.
- HTTPS·도메인의 검토 상태를 구현 완료나 구체적인 DNS/인증서/EC2 작업 승인으로 확대하지 않았다.
- 문서 링크·앵커·렌더·명령 구문·위험/단계 연결·diff와 문서 외 무변경을 검사한다.
  이번 갱신은 로컬 문서4개만 변경하며 애플리케이션·DB·외부 서비스·원격 Git 작업은 수행하지 않는다.

## 2026-09-09 — PR44 머지와4A1 오류 보고 비노출

- 사용자 지시: 다음 단계 진행. PR44 head `fb87fb38b3a1e6536b7f73898bbfb406c3b1e0d0`의
  미반영 리뷰 없음·MERGEABLE/CLEAN, push/PR CI 성공을 확인했다. base 변경 때 취소된 중복 CI와
  완료된 최신 실행을 구분했다. 기존 로컬·CI40개 통과 이후 코드 변경이 없어 불필요하게 반복하지 않았다.
- PR44를 squash merge했다. 실제 develop 커밋은 `8b1740cc396078c119a39bbb41c2f81937c18987`.
  이슈45·브랜치 `phase-4a1-sensitive-errors`를 이 기준에서 생성했다. main·운영 적용은 변경하지 않았다.
- D-030: BLUEPRINT4A1의 독립 부분인 Django 오류 보고 PIN 가림만 선택했다.
  settings의 기본 reporter filter 지정, 별도 filter의 PIN 설정 패턴·DEBUG 중 민감값 가림,
  POST pin과 MultiValueDict 복사본 가림, login_view의 민감 POST/지역변수 주석을 적용했다.
  역할·성공/실패·리다이렉트·세션 정책·운영 필수값·DEBUG 기본값은 바꾸지 않았다.
- django-security 스킬을 참고하고 설치 Django5.2.17와 공식 오류 보고 API로 실제 확장 지점을 확인했다.
  예제의 별도 인증체계·운영 설정을 무조건 적용하지 않았다. helper는 hidden_settings의 기존 패턴/flags를 유지한다.
- 테스트: 새4개는 합성 값만 쓰고 DB 접속이 없다. 원본 동작 복원에서6조건 실패, 수정 후4개 통과.
  최초 테스트 URLconf namespace 누락은 의도한 로그인 실패보다 먼저 예외를 내므로 fixture를 고친 뒤 재현했다.
  독립 검토에서 데코레이터 이전 middleware 오류 경계를 확인해 해당 POST 노출을 실패 재현하고 필터에서 가렸다.
  PIN 패턴·DEBUG 가림·지역변수 주석·조기 POST 가림·MultiValueDict 가림 제거5종 모두 검출한다.
  독립 리뷰의 MultiValueDict 지역변수 검증 공백을 반영해 해당 프레임 fixture를 강화했고 집중4개가 통과했다.
  외부 메일을 보내지 않고 locmem backend의 보고서1건과 text/HTML 내용만 확인했다.
- 전체 검증: 새 Compose `bk-4a1-errors-20260909`, 고정 의존성 환경의
  `.venv/postgres-only/clean-env/bin/python scripts/test_postgres.py`로 migration15개·앱29개,
  총44개 통과·skip0, check 문제0·drift 없음. 기존 로그인·주문·주방·통계를 실제 PG에서 검사했다.
  후속 오류 경계 추가 전43개 결과와 최종44개 결과를 구분한다.
- 문서 검사: Markdown25개·링크615개·변경17문서 렌더·명령 구문·위험44개/35단계 DAG·diff 통과.
  이번 Compose의 프로젝트/목적 label을 확인하고 컨테이너·네트워크·볼륨을 정리했다.
- 기록: 무시 경로 `.venv/phase-4a1/`에 red/green·변이·PG·문서 검증을 보관한다.
  [구현 기록](SENSITIVE_ERRORS.md)에 공식 출처·보장 범위·미구현 경계·실행 방법을 기록했다.
- 남은 관문: 임의 exception/log 문자열·URL/querystring·다른 이름으로 복사한 지역변수 등은
  전역 정화하지 않는다. 운영 설정 누락 거부·공개 기본 PIN·식별/권한·D-002/003/006은 미정이다.
  BK-R028은 지정 경로의 Repo-fixed/Open이며4A1 전체·1B/2B·8A 최종 인수는 유지한다.
  다음은 이 좁은 구현의 PR 검토이며 운영 시작 규칙/권한 매트릭스가 정해지면 해당 범위를 이어간다.

## 2026-09-09 — PR42 머지 완료와 PR44 develop 통합

- PR42 수정 head `2acfd4a99f442272ab88026d3b91356daae12ae1`의 CI run34311793854,
  django-ci14초 통과 후 승인된 squash merge를 실행했다. 실제 develop 커밋은
  `c8c11b5c6811a97ca77e377c08b0adf552b4cf86`이다. main·운영 배포는 변경하지 않았다.
- PR42 문서 검사: Markdown23개·링크589개·변경13문서 렌더·명령 구문·44개 위험/35단계 DAG·diff 통과.
  PR42 전용 Compose 프로젝트·목적 label을 확인한 후 컨테이너·네트워크·볼륨을 제거했다.
- 후속 PR44의 `postgres-only-runtime`(시작 `9ab0cce`)에 develop을 일반 merge했다.
  squash로 겹친 문서와 테스트의 충돌을 해결하면서 PR42 리뷰 보완을 보존했다.
  기본 PG 설정·공통 실행기·Docker/CI·번호 경로는9ab0cce와 바이트 동일하며,
  통계 테스트/API·models·migration은 현재 develop과 동일함을 diff로 확인했다.
- 인계 문서에 PR42 머지 사실, PG 전체40개(migration15개·앱25개·통계7개 포함), 공통 실행 명령을 반영했다.
  과거 SQLite·앱12/16/19개·PR40 Draft 기록은 당시 증거로 구분한다. 번호·0019·정산 정책은 바꾸지 않았다.
- 검증: 새 Compose `bk-pr44-integration-20260909`, 고정 의존성이 설치된
  `.venv/postgres-only/clean-env/bin/python scripts/test_postgres.py`로 check 문제0·drift 없음·
  PG15.18 전체40개 통과(skip0). 로그와 문서 렌더/검사 JSON은 `.venv/pr44-integration/`에 보관한다.
- 통합 문서24개·링크599개·변경15문서 렌더·명령 구문·44개 위험/35단계 DAG·diff 검사를 통과했다.
  독립 통합 리뷰에서 추가 지적은 없었다. 통합용 Compose 프로젝트/목적 label 확인 후 소유 자원을 정리했다.
- PR44 base를 develop으로 전환하고 통합 커밋을 일반 push한다. PR44는 열린 상태로 유지한다.
  전체2B·8A 최종 인수,0019·번호 정책·운영 데이터 이전/EC2 적용 관문은 그대로다.

## 2026-09-09 — PR42 리뷰 권고 보완과 머지 준비

- 사용자 지시: 위 리뷰의 권고를 수정하고 머지. 대상 PR42의 리뷰 기준 head는 `8531e18`,
  브랜치는 `phase-8a-dashboard-execution`이다. 후속 PostgreSQL 전용 PR44는 별도로 유지한다.
- 반영: 통계 테스트4→7개. 수량 정렬과 이름 양방향 구분·동률 정렬, 지원하지 않는 층400,
  전부/일부 NULL 단가의 수량·금액 응답을 추가했다. created_at은 주문 날짜와 맞춘다.
  고정 기간은8C에서 바꿀 임시 특성화, counter 세션은 권한 검증 증거가 아님을 명시했다.
- 앱 집계3줄은 그대로다. `.annotate()` 호출의 이름 해석과 중첩 집계 FieldError 기전을 설명했고,
  이전 `-qty` 정렬이 GROUP BY를 쪼개는 오류도 기록했다. 동일 메뉴의 다른 수량 fixture를 유지한다.
  미지원 층을 만들기 위해0019 제약을 우회하지 않는다. 전역 변이 점수를 품질 수치로 사용하지 않는다.
- 문서: BASELINE의500을 과거 관찰로 구분, PR40 머지·8A 상태와 최신 PG 명령을 정리했다.
  MIGRATION_REPAIR_REVIEW의 앱12개는 당시0020 검증 범위임을 명시했다.
  timezone.utc의 naive 분기는8C 시간 처리 후속으로 추적한다. 권한·날짜·정산 정책은 변경하지 않았다.
- 검증: 새 Compose `bk-pr42-review-20260909`에서 PG15.18 migration15개·앱19개 모두 통과, skip0.
  check 문제0·drift 없음. 정렬 fixture 확장 후 집중7개도 통과했다.
  프로세스 내부 변이7종(이름 ASC/DESC 단독, 동률 제거/역순, 옛 qty 정렬,
  floor 검증 삭제, NULL 금액 fallback 삭제)을 모두 검출했다. 원본 앱은 수정하지 않았다.
  첫4메뉴 fixture는 동률 제거를 놓쳐28메뉴로 확장했다. 보조 probe의 TEST 옵션 초기화 오류는
  DB 생성 전에 중단됐고 설정 병합을 바로잡아 재실행했다. 앱 결함으로 세지 않는다.
- 독립 읽기 전용 리뷰: 실행 코드의 새 결함 없음. 발견된 후속 단계8B→8C 및 BLUEPRINT의
  구 테스트 수를 바로잡았다. 문서 링크·렌더·명령 구문·위험44개/단계35개 DAG·diff를 검증한다.
  로그·HTML·검사 스크립트는 무시 경로 `.venv/pr42-review-fix/`에 보관한다.
- 기존 phase-* 브랜치명은 push CI 필터와 불일치해 PR 이벤트 CI만 실행됐다.
  후속 PR44가 push 필터·PG CI를 보완한다. PR42 CI 녹색만으로 PG 인수를 선언하지 않는다.
- 공개 기록은 재작성하지 않는다. 이번 보완 커밋에 변경 이유·검증·범위를 본문으로 남기며
  저장소에서 요구하지 않은 모델·세션 trailer를 만들어 붙이지 않는다.
- 다음: 최종 head CI 확인 후 PR42 머지, PR44에 develop을 병합해 PG 전용 설정과 최신 회귀를
  통합 검증한다. PR44 기준을 develop으로 바꾸되 이 작업에서 자동 머지하지 않는다.
  0019·번호 정책·운영/EC2 적용과 전체2B·8A 최종 인수 관문은 유지한다.

## 2026-09-09 — D-029 PostgreSQL 전용 실행 전환

- 사용자 지시: SQLite 지원 제거, PostgreSQL만 남기고 Docker로 DB 관리.
  기준 PR42 HEAD `8531e181ed23acb17d32b2363d47d7061ebcd8ca`, 후속 브랜치 `postgres-only-runtime`.
  통계 PR42 리뷰 보완/머지를 대신하지 않고 별도 PR로 인계한다.
- 설정: 기본 DATABASE_URL 필수·비PG/불완전 URL 거부. SQLite settings_test 삭제,
  PG 설정에 환경 격리 통합. DB 장애 시 파일 DB fallback 없음. 번호 counter fallback 제거,
  기존 PG sequence 경로와 과거 migration20개·counter schema·기존 DB 파일은 보존했다.
- Docker/CI: loopback55436 개발용 영속 Compose와55437 전용 테스트 Compose 분리.
  이미지 index에 AMD64/ARM64 제공을 확인했다. 현재 패키지9개 버전을 CI 스냅샷으로 고정하고
  새 Python3.12 환경 설치·pip check를 통과했다. 주 버전 업그레이드는 없다.
- 검증: 새 설정 거부 회귀는 수정 전 실패→수정 후 통과. scripts/test_postgres.py는 프로젝트
  전체37개를 발견해 migration15개·앱/guard22개를 실제 PG에서 실행, 모두 통과·skip0.
  check 문제0·drift 없음. 별도 프로세스로 나눠 기존 control DB guard를 완화하지 않았다.
- 독립 리뷰 반영: --noinput 자동 DROP을 제거하고 UUID 앱 DB와 충돌 사전 거부·EOF 입력을 추가했다.
  중첩/다른 앱 테스트도 전체 discovery에서 분리한다. 실제 충돌 DB를 만들어 기존 DB 보존과 실행 거부를 확인했다.
  최종 독립 코드 리뷰에서 새로운 결함은 없었다.
- 개발 검증: 전용 임시 프로젝트 `bk-pgonly-dev-proof-20260909`에서 비superuser/NOCREATEDB 앱 역할로
  빈 DB 전체 migrate 성공. 합성 메뉴1개가 Compose down/up 뒤 남음을 확인했다.
  테스트 프로젝트는 `bk-pgonly-test-20260909`다. 이번 소유 label을 확인하고 두 임시 프로젝트/볼륨을 정리했다.
  실행 로그·문서 검증 결과는 무시 경로 `.venv/postgres-only/`에 보관한다.
- 문서: Markdown24개·링크592개·변경 문서17개 렌더·Python AST·Compose config·35단계 DAG·diff 검사 통과.
  외부 URL 응답은 검사하지 않았다. AGENTS·루트 README·현재 인계·테스트/계획/결정·과거 보고서의 현재 안내를 갱신했다.
  과거 SQLite 분석은 역사 기록으로 보존한다. D-029 전환/CI 기반 구현을1B/2B 전체 완료나
  운영 인수·0019/번호 정책 승인으로 확대하지 않는다.

## 2026-09-09 — PR40 머지와 독립8A 통계 실행성 수정

- 사용자 지시와 D-028: PR 리뷰·문제없으면 머지·다음 작업 진행. PR40의 최종 HEAD
  `a26d1a1af97b2e5833b92be9cbce7c5ee810b7d0`에서 CI pass·MERGEABLE/CLEAN을 확인하고
  squash merge했다. 실제 develop merge 커밋은 `f9b562c349a2a6318bcfa0b68fa45af800d3926e`다.
  원격 브랜치 삭제·운영 적용은 하지 않았다.
- 이슈 [41](https://github.com/rlagycks/bazaar_kiosk/issues/41), 새 브랜치
  `phase-8a-dashboard-execution`은 위 merge 커밋에서 시작했다.
  최초 fix/phase-8a-dashboard-execution 이름은 원격 fix 브랜치와 경로 충돌해 push가 거부됐다.
  기존 원격을 변경하지 않고 현재 이름으로 로컬 브랜치를 변경했다.
  0019 정책은 사용자에게 질문한 상태다. 답변을 대신 정하지 않고 계획의 독립8A만 진행했다.
- 앱 변경: stats_dashboard의 집계 별칭 qty를 qty_sum으로 분리하고 정렬/응답 매핑을 맞춘3줄.
  JSON qty 필드·기존 기간·결제·이름 그룹·인가·schema·migration은 유지한다.
- 실패 회귀: test_dashboard_execution4개가 수정 전 동일 FieldError로 모두 실패했다.
  수정 후 check 문제0·drift 없음, SQLite 전체31개 수집/16개 통과/PG15개 skip,
  PG 앱16개 통과/skip0. PR40에서 같은 세션에 migration15개가 통과했고 이후 migration은 무변경이다.
- 독립 코드 리뷰: 새 결함 없음. 수량 정렬 사례를 가나다순과 반대인 수량순으로 강화하고
  집중4개를 SQLite/PG 양쪽에서 재검증했다. 결제 정책·동명 메뉴 상세 계약 확장은
  해당 코드가 바뀌지 않았고 별도 보고 계약 범위라 추가하지 않았다.
- 전용 자원: 이번 PR40 검증의 Compose `bk40-final-20260909`를 순차 재사용해8A를 검증했다.
  결과 로그는 무시 경로 `.venv/phase-8a/`에 보관했다. 프로젝트/목적 label을 확인하고
  이번 컨테이너·네트워크·볼륨을 제거했다. 다른 프로젝트는 변경하지 않았다.
- 문서: Markdown23개·링크578개·변경 문서10개 렌더·명령 구문·44개 위험/35단계 DAG·diff 검사 통과.
  외부 URL 응답은 검사하지 않았다. 현재 인계·README·BLUEPRINT·위험 등록부·결정·테스트 명령과
  [8A 기록](DASHBOARD_EXECUTION.md)을 갱신했다.
  BK-R016은 Repo-fixed/Open(2B 이후 인수 대기),1B·2B 관문은 그대로다.8A 전체 종료나
  운영/실기기 인수·날짜·레거시/순매출 정확성 해결로 보고하지 않는다.

## 2026-09-09 — PR40 머지 전 최종 리뷰

- 사용자 지시: 열린 PR을 검토하고 문제없으면 머지한 뒤 다음 작업 진행.
  시작 HEAD와 원격 PR40은 `6c037824b6087543eb7f44cef65b88073a39516d`, base develop `3604cca`다.
- 승인된0020 diff와 나머지 migration 보존, 신규·기존·이미 적용·충돌·원자성 회귀를 검토했다.
  독립 코드 리뷰에서 새로운 결함은 없었다. BLUEPRINT/적용 기록의 예전 PG12개를15개로
  바로잡고 PG 안내에서 전체 leaf 설치 사례의 설명을 실제 검사와 일치시켰다.
  문서 독립 감사의 D-P07 잔여 대기 문구·최신 merge 승인·루트 README 격리 명령도 보정했다.
- 검증: SQLite check 문제0·drift 없음·27개 수집/12개 통과/PG15개 skip.
  전용 Compose `bk40-final-20260909`에서 PG migration15개·앱12개 모두 통과, skip0.
  로그는 무시 경로 `.venv/pr40-final-review/`에 보관한다. 운영 DB에 접속하지 않았다.
- 0019 정책은 사용자에게 확인 중이며 임의로 정하지 않는다.1B 미완료·2B 선행 관문을 유지한다.
  이후 독립 착수 가능한8A의 통계 집계500 수정만 진행하며 날짜·정산 정책은 변경하지 않는다.
  실제 머지 결과와 다음 브랜치/PR은 후속 작업 기록에 남긴다.

## 2026-09-08 — PR40 게시와 독립 리뷰3건 반영

- 사용자 승인: 적용 커밋의 PR 반영과 서브에이전트 리뷰 실행. merge·운영 적용은 여전히 범위 밖이다.
- 게시: `3f2bd75`를 `review/phase-1b-migration-repair`에 push했고 PR40 head가 같은 값으로 갱신됐다.
  제목을 "1B:0020 floor sequence 복구 적용과 PostgreSQL 회귀 전환"으로 바꾸고 본문 상단 상태를
  승인 대기 → 적용 완료로 고쳤다. Draft는 유지했다. CI `django-ci` pass이나 check/drift만 수행한다.
- 리뷰3건(읽기 전용, 병렬): migration·PG 정합성 / 테스트 코드 품질 / 문서·프로세스 감사.
  적용된 SQL 자체에는 CRITICAL·HIGH 지적이 없었다. 세 리뷰 모두 인벤토리 해시와
  "나머지19개 바이트 무변경" 주장을 독립적으로 재계산해 일치를 확인했다.
- 반영한 테스트 지적: 성공 3사례가 setval을 통째로 지운 구현도 통과한다는 지적에 따라
  `assert_sequence_state`로 `(last_value, is_called)`를 직접 고정했다. 실패 주입 후 재시도의
  번호 미검증,0020 삭제로 잃었던 모델별 빈 테이블 검사, patch 블록 중복도 함께 정리했다.
  다수 행 MAX와 역이행→재적용 경로를 신규 사례로 추가하고, frozen 사본이 수정 전 문장을
  유지하는지 검사하는 사례를 넣어 사본이 조용히 "수정"되는 것을 막았다. PG는7개→15개다.
- 반영하지 않은 지적과 이유: migration의 `WHERE floor = 'B1'`를 지워도 suite가 통과한다는 지적은
 0019가 모든 행에 `floor='B1'`을 강제하므로 위반 행이 있으면0020 이전에 중단된다. 음성 사례를
  만들 수 없어 다수 행 MAX 검증과 주석으로 대체했다.
- 반영한 문서 지적: BLUEPRINT 머리말과 인계 절이 D-P07을 proposed로 남겨 둔 자기모순(가장 중요),
  프롬프트03·MODEL_DELEGATION_REVIEW·BASELINE의 승인 대기·구 수치 서술, RISK_REGISTER의
  미정의 상태값과 "나머지43개" 산술, SESSION_SETUP의 "PR40 반영 승인됨"과 "push 범위 밖" 충돌,
 2B 착수 조건이 BLUEPRINT DAG와 어긋나던 문구, 후보 도구·suite가 적용 이전 커밋 전용이라는 사실,
  frozen 사본의 "바이트 동일" 주장(실제로는 docstring을 붙였으므로 본문만 동일)을 바로잡았다.
- 검증: SQLite27개 수집·12개 통과·PG15개 skip, drift 없음, check 문제0.
  전용 Compose `bk1b-rev-1788855884-82051`에서 PG migration15개·앱12개 통과, skip0.
  PG 프로필 통합 실행은27개 수집 중 migration15개를 guard가 거부한다(설계된 동작).
  Markdown22개·링크567개·앵커·`git diff --check` 통과. 전용 자원은 label 확인 후 제거했다.
- 남은 관문은 앞 항목과 같다. BK-R005는 운영 확인 대기이고 BK-R017·0019 정책·BK-R003은 Open이다.
  리뷰가 제기한 운영 준비 항목(`search_path` 고정, sequence `OWNED BY` 결정,42P07 복구 절차,
  복제·failover 시 번호 건너뜀)은 D-004/운영 런북 입력으로 넘긴다. 이번 범위에서 구현하지 않았다.

## 2026-09-08 — 1B:0020 복구 적용과 성공 회귀 전환

- 브랜치 / 워크트리: `review/phase-1b-migration-repair` / `/Users/gimhyochan/system/bazaar_kiosk`.
  시작 HEAD `84360dbde0de909ff8fcbc8d23dbf8ce51c394fd`, 시작 작업 트리 깨끗함.
  조회로 확인: PR40 OPEN/Draft, head OID가 로컬 HEAD와 일치, base develop `3604cca`, 열린 이슈는 #39.
- 승인 범위: 문서로 검토된 정확한0020 diff를 제시하고 사용자가 "0020 패치 적용 승인"을 선택했다(D-P07 accepted).
  0019 정책, 번호 정책(BK-R003), 운영 DB 적용·배포·merge·push는 명시적으로 제외했다.
- 적용: `orders/migrations/0020_create_floor_sequences.py`에 저장소의 patch 파일만 적용했다.
  `IF NOT EXISTS` 제거, setval 값 `GREATEST(...,1)`, is_called `MAX>0`의3줄이다.
  적용 전 해시 `b2ccbd94…`, 적용 후 `dbde0d9c…`. 나머지19개 migration은 바이트 무변경이다.
  적용 전 파일 사본을 `orders/tests/original_0020.py`로 보존했고 본문이 원본과 동일함을 확인했다.
- 테스트: 1A의 기대 실패2개를 성공 회귀2개로 바꾸고 번호0·원본 적용본 no-op·동명 sequence42P07·
  초기화 후 실패 원자성을 추가했다. 수정 전 SQL이 같은 빈 DB에서 여전히22003으로 실패함을
  `test_original_0020_still_fails_on_an_empty_database`로 고정해 이 패치가 원인임을 증명했다.
  PG 사례는7개에서12개가 됐고0019 제약 실패4개는 그대로 유지했다.
- 환경: Python3.12.11/Django5.2.17, Docker29.4.1, PostgreSQL15.18/aarch64.
  전용 Compose 프로젝트 `bk1b-apply-1788837903-56326`, loopback55437, 프로젝트 소유 볼륨.
  기존 다른 프로젝트의5432/6379/3307 컨테이너는 사용하거나 중단하지 않았다.

### 실행 명령과 결과

| 명령 | 결과 |
| --- | --- |
| `patch -p1 --dry-run` 후 적용, `git diff -- orders/migrations/` | 승인된2 hunk만 적용 |
| `check --settings=…settings_test` | 문제0 |
| `makemigrations --check --dry-run --settings=…settings_test` | 변경 없음 |
| `test orders.tests --settings=…settings_test` |24개 수집·12개 통과·PG12개 skip(리뷰 반영 전 수치) |
| `check --settings=…settings_test_pg` | 문제0 |
| `test orders.tests.test_migration_paths --settings=…settings_test_pg` | **12개 실행·통과·skip0** |
| `test orders.tests.test_baseline orders.tests.test_pg_guard orders.tests.test_settings_isolation --settings=…settings_test_pg` | **앱12개 통과** |
| `test orders.tests --settings=…settings_test_pg` | 빈 테스트 DB 생성은 성공, fixture guard가 당시 migration11개를 거부 |
| `docker volume inspect`, `compose down --volumes` | 이번 프로젝트 label 확인 후 정리, 다른 컨테이너3개 유지 |

- **새 사실:** 0020 적용 이후 Django runner의 빈 PG 테스트 DB 생성이 처음으로 성공했다.
  그래서 앱 테스트를 실제 PostgreSQL에서 실행할 수 있게 됐다. 다만 `test orders.tests`를
  PG 프로필로 한 번에 돌리면 runner가 `default`를 자기 테스트 DB로 바꿔1A fixture guard가
  의도대로 거부한다. 이는0020 실패가 아니며 두 명령을 나눠 실행한다. guard를 완화하지 않았다.
- 문서: MIGRATION_REPAIR_REVIEW(적용 기록으로 전환), DECISIONS(D-P07 accepted),
  MIGRATION_INVENTORY(해시·경로), SESSION_SETUP(단계·승인표·명령), POSTGRES_TESTING(기대 결과표),
  RISK_REGISTER(BK-R005를 저장소 수정·운영 확인 대기), BLUEPRINT·README·TESTING의 상태 문구.
- 남은 위험·관문: BK-R005는 운영 DB의 실제 적용 기록·sequence 값·소유권을 확인하기 전까지 종료하지 않는다.
  BK-R017과0019 정책(D-008/017/024)은 Open이다. BK-R003의 PG 다음 날 번호 연속은 이번 승인으로
  수용되지 않았고 D-004/단계5에서 결정한다. 운영 적용에는 writer 동결·사전 대조·백업 리허설이 필요하다.
- 하지 않은 것: 운영 접속·데이터 변경, 앱 업무 코드·0019·의존성·CI 변경, merge.
  실기기/브라우저·부하·CVE 스캔도 이번 범위가 아니다.
  이 항목을 작성한 시점에는 push도 하지 않았다. 이후 사용자 승인으로 push한 기록은 다음 항목에 있다.
- 적용 커밋: `3f2bd75`.
- 다음 권장: PR40에 이 적용 커밋을 반영해 리뷰받고, 이후0019 정책 결정 또는
 2B(의존성 재현성·PG CI 연결) 착수를 사용자와 정한다.

## 2026-09-08 — 모델 공통 인계 문서와 승인 상태 정리

- 사용자 범위: 과거 모델 설정·최신 단계·격리 테스트 명령·적용 승인 상태 정리 및 PR40 반영.
  시작 HEAD `262f3d544b36f55160c68b4a41e449be14f38ea0`, review/phase-1b-migration-repair.
- SESSION_SETUP을 현재 시작점으로 통일했다. Astra 설정과 초기 브랜치·인증·DB 기록을
  과거 기록으로 분리하고 README·BLUEPRINT·프롬프트01~04에 모델 공통 계약을 반영했다.
- 2A/1A 완료·머지,1B 후보 검토 중,2B 미착수를 명시했다. 원본 SQLite와 PG 실패 재현7개,
  임시 후보 PG12개·정상 흐름8개 명령을 구분하고 전체 PG suite 성공을 현재 전제에서 제거했다.
- D-P07 proposed와 정확한 원본0020 적용 승인 대기,0019 정책·BK-R003 미해결을 유지했다.
  문서 정리가 실제 위임·모델 설정 변경·migration 적용·배포·merge 승인이 아님을 명시했다.
- MODEL_DELEGATION_REVIEW의 최초 지적을 보존하고 문서 충돌 정리 이후 판정을 갱신했다.
  대상 모델의 실제 가용성·도구 지원·품질은 검증하지 않았다.
- 검증: Markdown22개·링크552개·변경 문서9개 렌더, 명령 구문·자리 표시자,
  위험44개/35단계 DAG·diff 공백 검사를 통과했다. 앱·원본 migration·후보 패치 무변경을 확인했다.
  문서만 변경하므로 앱/PG 테스트는 재실행하지 않았다.
  독립 읽기 전용 감사에서 지적한 PG 자원 정리 순서를 준비→검사→정리로 바로잡았다.
  외부 URL 응답 검사는 범위 밖이며 PR 상태는 별도로 조회했다.

## 2026-09-08 — PR40 리뷰 반영과 다른 모델 위임 준비도 검토

- 사용자 범위: PR40 코멘트 지적 수정·게시, Opus 5 구현 위임 가능 여부는 검토만.
  시작 HEAD `8b1dd86a0b7b490ec84b92f736707deb9feb5dda`, 동일 검토 브랜치와 Draft PR40을 유지한다.
  원본 migration 적용·실제 구현 위임·모델 설정 변경은 하지 않는다.
- 리뷰 반영: D-P07과 검토안에 PG 다음 날 번호가 이어지는 BK-R003을 명시했다.
 0020 패치 승인과 번호 정책/운영 위험 수용은 분리했다. reverse로 번호 위치를 잃을 수 있는 점과
  이번 임시 복사본의 정확한 경로만 정리하는 안내도 추가했다. MAX 두 번 조회는 최소 diff 유지로 남겼다.
- 후보 테스트의 반대 의미 이름2개를 성공 의미로 바꿨다. 원본 실패 suite를 수정하지 않고
  후보에서 해당 상속 메서드2개의 수집만 제외해 새 성공 이름으로 대체했다.
  새 준비 도구 복사본에서 후보 클래스12개·PG skip0 통과, 원본0020 패치는 변경하지 않았다.
- [위임 준비도 보고서](MODEL_DELEGATION_REVIEW.md): 모델별 과거 안내, 최신 단계/기준,
  격리 명령 충돌, 승인 상태, 대상 실행 환경을 검토했다. 독립 읽기 전용 감사에서도 같은 위험을 확인했다.
  Opus 5를 호출하거나 구현을 위임하지 않았고 기존 SESSION_SETUP/구현 프롬프트는 검토만 했다.
  현재 문서를 그대로 넘기는 것은 부적절하며 최신 인계와 정확한 작업 승인 후 단계별 위임이 가능하다는 판정이다.
- 최종 검증: 후보 PG12개 통과, Python AST·Markdown22개/링크533개/문서5개 렌더·
  위험44개/35단계 DAG·diff 공백 검사 통과. 원본 앱과0020 패치 무변경을 확인했다.
  외부 URL의 응답은 재검증하지 않았다. 이번 전용 Compose 자원과 이번 실행의 임시 복사본을 정리했다.

## 2026-09-08 — 1B 복구 후보 검증, 정확한 적용 승인 대기

- PR38 MERGED와 develop `3604ccad7add5c760c3b1cecfaa7032706ddc01c`를 확인했다.
  깨끗한 상태에서 `review/phase-1b-migration-repair` 브랜치를 만들었고
  [이슈 #39](https://github.com/rlagycks/bazaar_kiosk/issues/39)에 검토 범위를 기록했다.
- AGENTS/D-017/1B는 정확한 과거 migration 변경 승인을 요구한다. 원본에 패치를 적용하지 않고
  [검토안](MIGRATION_REPAIR_REVIEW.md)·전체0020 patch·임시 복사 도구·검증 suite를 작성했다.
  이번 산출물은 Draft PR 검토용이며1B 완료나 수정 승인 기록이 아니다.
- 메인 담당은0020 후보·PG 실행·산출물, 독립 검토자는0019 정책/구앱 호환성과0020 후보를 검토했다.
  리뷰의0경계·생성 후 실패 검증 보완을 추가했고 기존sequence충돌 시 중단과 writer 동결 조건을 명시했다.
- 후보: 빈/NULL/0이면sequence(1,false), 양수40이면(40,true), 원본이미적용이면no-op,
  이력 없는 기존sequence는42P07로 중단하고 재설정하지 않는다.
  원본 파일은 바꾸지 않았으며1A 테스트의 기대 실패도 그대로 보존했다.
- 검증 환경: 이전1A와 같은 Python3.12.11/Django5.2.17/PG15.18/aarch64,
  전용 Compose 프로젝트 `bk1b-review-20260908`, loopback55437 및 새 프로젝트 볼륨.
  `.venv/phase-1b/candidate/` 복사본에서 후보 suite12개 PG 통과·skip0,
  실제 빈 PG 테스트 DB 생성과 기존 정상 특성화8개 통과. 후보 SQLite drift 변경 없음.
  번호0 경계와 새 sequence 생성·초기화 뒤 예외 주입 시 행/이력 보존·sequence 제거도 확인했다.
- 0019 탐색:0018 합성 포장NULL 행에 NOT VALID 제약을 직접 적용하면 행은 유지되지만
  기존 상태 API가23514로 실패하고 VALIDATE도 실패한다. 실제0019 후보로 구현하거나
  정·역호환을 보장한 결과가 아니다. 수정 가능한 과거 주문이 필요한지 정책 결정이 남는다.
- 재현성: 저장소의 준비 도구가 생성한 patch 적용 결과와 실제 검증한 후보 파일의 바이트 일치 확인.
  명령은 검토안에 보관했다. 원본 기준 검사19개 중12개 통과·PG7개 skip도 유지됐다.
- 최종 검증: 원본20개 migration 바이트 보존, 후보 Python AST, Markdown21개/링크524개/
  문서4개 렌더·위험44개/35단계 DAG·diff 공백 검사 통과. 외부 URL 응답은 재검증하지 않았다.
  UUID/일반 테스트 DB0개·control 업무 table0개를 확인하고 이번 전용 Compose 자원을 제거했다.
- 다음 관문: D-P07의 정확한0020 패치 적용 승인.0019에 대한 임의 테이블 배정·삭제는 금지하며
  D-008/017/024는 미정이다. BK-R005/017을 포함한 위험은 해결 처리하지 않는다.

## 2026-09-07 — 1A: 격리 Compose PG와 migration 경로 재현

- 사용자2A 머지를 GitHub에서 확인: PR36 MERGED, develop `ff013b4b4934087dfa3f3e3ad368af9387554381`.
  깨끗한 상태에서 이 기준으로 `test/37-phase-1a-postgres` 브랜치를 만들었다.
  이슈 [#37](https://github.com/rlagycks/bazaar_kiosk/issues/37). 기존 PR 게시 절차를 이어가며 merge는 하지 않는다.
- 범위/D-027:1A 구현·검증·인계. compose.test.yaml, settings_test_pg.py,
  pg_init.sql·pg_support.py·test_pg_guard.py·test_migration_paths.py와 관련 문서를 추가했다.
  업무 앱·기존 migration·의존성·CI·운영 데이터·인프라 변경은 없다.
- 역할: 메인 담당은 Compose·대상/cleanup guard·실행·문서·Git, 분리된 테스트 담당은
  historical migration fixture를 작성했다. 독립 리뷰의 close 예외 시 복원/cleanup 중단 지적을
  반영해 중첩 finally와 실패 회귀를 추가했다.
- 환경: Python3.12.11/Django5.2.17/psycopg3.3.5, Docker29.4.1/Compose5.1.3,
  PostgreSQL15.18/aarch64. 검증 image digest는 compose.test.yaml에 고정했다.
  전용 프로젝트 `bk1a-37-review`, loopback55437, 프로젝트 소유 pg_test_data 볼륨을 사용했다.
  기존 다른 프로젝트의5432/6379/3307 컨테이너는 사용하거나 중단하지 않았다.
- 실제 신원: control DB bk_test_control, 사용자 bk_test_runner, DB owner 일치,
  NOSUPERUSER/CREATEDB/NOCREATEROLE/NOREPLICATION/NOBYPASSRLS와 전용 marker를 확인한다.
  URL·libpq 환경 guard 뒤 실제 서버 사실을 확인한 후에만 UUID fixture DB를 만든다.
- 실행: [PG 안내](POSTGRES_TESTING.md)의 Compose config·up --wait·PG check와
  `test orders.tests.test_migration_paths --settings=bazaar_kiosk.settings_test_pg` 실행.
  PG7개 실행·통과·skip0: 빈0020/번호NULL의22003,0018 포장NULL/F1/BOOTH의0019 제약23514,
 0019 포장행의 역이행23514, 양수40의0020 성공·이미적용 no-op. 각 실패 뒤 행·이력·제약 보존 확인.
- 초기 fixture 검증에서 다른 alias를 사용한 원본0014 default 조회와 historical 필드 선택 오류가
  드러나 테스트 장치를 수정했다. 이후 같은 PG7개가 모두 통과했다. 원본 migration은 수정하지 않았다.
  샌드박스에서 localhost 연결 거부로 실행되지 않은 결과도 PG 실패 재현으로 세지 않았다.
- 로컬: 기존9개 기준 검사를 먼저 통과했고 최종 `test orders.tests --settings=bazaar_kiosk.settings_test`
  수집19개 중12개 실행·통과/PG7개 명시 skip. guard는 잘못된 URL·PG* 우회·서버 identity/권한·
  close 실패·소유권 변경 거부를 검증한다. check 문제0, makemigrations --check --dry-run 변경 없음.
- 정리 검증: PG suite 후 UUID DB0개, control public table0개를 확인했다.
  연결 종료 실패에도 default 연결/설정 복원을 보장하고 자신이 만든 DB만 소유권 재검사 후 정리한다.
  강제 DROP/다른 세션 종료를 하지 않으며 중단 시 전용 Compose 자원 정리 절차를 문서화했다.
- 최종 검증: 원본20개 migration의 기준 커밋 대비 바이트·인벤토리 SHA256 일치,
  Python AST·Markdown20개/링크512개/문서8개 렌더·위험44개/35단계 DAG·diff 공백 검사 통과.
  외부 URL 응답은 재검증하지 않았다. 리뷰 수정 부분 재검토에서도 추가 지적 없음.
  전용 프로젝트 label을 확인한 뒤 이번 컨테이너·볼륨·네트워크를 제거했고 기존 개발 컨테이너3개는 유지됐다.
- 인계: [migration 인벤토리](MIGRATION_INVENTORY.md)의 원본20개 SHA256·경로·운영 확인 목록.
  테스트 통과는 결함 수정이 아니므로 BK-R005/017 및 기존44개 위험은 Open이다.
  다음은1B의 구체적 복구안 검토이며, 과거 산출물 수정·과거 테이블 배정 정책을 암묵적으로 결정하지 않는다.

## 2026-09-07 — 2A 첫 구현: 격리된 로컬 테스트

- 승인: 사용자가 첫 구현의 이슈·전용 브랜치·PR 게시를 요청했다(D-026).
  이슈는 [#35](https://github.com/rlagycks/bazaar_kiosk/issues/35), 브랜치는
  `test/35-phase-2a-baseline`, PR 대상은 조회한 현 GitHub 기본 브랜치 `develop`이다.
  merge·운영 이전·장기 기준 브랜치 정책 변경은 범위에 없다.
- 시작 HEAD: `2d5bb78c035555d6e4a58821600aec27a7927b86`.
  이전 준비2커밋과 최신 미커밋 문서를 보존했고, 분석/청사진 문서 체크포인트
  `03ac108` 이후 테스트 구현을 별도 커밋으로 구분한다.
- 구현: `bazaar_kiosk/settings_test.py`, `orders/tests/__init__.py`,
  `orders/tests/test_baseline.py`, `orders/tests/test_settings_isolation.py`.
  실행 안내는 [TESTING.md](TESTING.md), 현재 상태는 BASELINE·BLUEPRINT·RISK_REGISTER,
  사용자 승인 경계는 DECISIONS에 반영했다.
- 통합 책임: 메인 담당은 격리 설정·환경 검증·변이·문서·Git을 맡고,
  분리된 테스트 담당은 정상 흐름 fixture와 특성화를 작성했다. 별도 읽기 전용 코드 리뷰에서
  격리·트랜잭션 테스트·범위·계약 오류 지적 없음으로 검토를 마쳤다.
- 기준 검사: Python3.12.11/Django5.2.17, 격리 설정으로 check 통과, 초기 수집0개를 확인했다.
  구현 후 정상 특성화8개와 환경 격리1개가 수집·통과했다. 테스트는 role5개·홀/포장·
  현금/티켓/혼합 정상 결제·서버 가격·기존 단가·주방 진행·주문 원자성을 검증한다.
  격리 검사는 잘못된 DB URL과 합성 배포 자격증명을 주입한 새 프로세스에서 실제 메모리 SQL까지 실행했다.
- 실행 명령: TESTING의 `check`, `makemigrations --check --dry-run`,
  `test orders.tests.test_baseline`, `test orders.tests` 모두
  `--settings=bazaar_kiosk.settings_test` 사용. check 문제0·drift 변경 없음·전체9개 통과.
- 변이 검증: 무시되는 `.venv/phase-2a/mutations/`의 별도 앱 복사본2개에서
  `unit_price=1`은 가격 테스트의 `1 != 4300`, 생성 바깥 atomic 제거는 원자성 테스트의
  잔여 부모 주문 `1 != 0`으로 각각1개 assertion failure(exit1)를 확인했다.
  이는 예상한 검증 성공이며 정상 suite의 실패가 아니다. 원본 앱50개 파일 SHA256은 동일하다.
  재현 도구·출력은 `.venv/phase-2a/check_mutations.py`와 같은 경로 로그에 로컬 보관했다.
- 최종 검증: 추적/추가 대상 파일만 새 디렉터리에 복사한 깨끗한 체크아웃에서도
  check·drift·전체9개 테스트가 통과하고 db.sqlite3는 생성되지 않았다.
  Markdown18개·링크481개 대상/앵커·변경 문서6개 렌더·위험44개·35단계 DAG 검사와
  `git diff --check`를 통과했다. 외부 URL의 네트워크 응답은 별도 재검증하지 않았다.
- 발견/인계: 잘못된 PIN의 오류 context는 있으나 템플릿에 안내가 표시되지 않는다.
  정상 특성화에서는 로그인 실패의 세션 미생성만 확인하며 메시지 표시 개선은11에 인계한다.
- 한계: HTML 렌더는 실제 휴대폰/PC 브라우저·JS 인수가 아니다. SQLite 검사는 PG migration·
  sequence·잠금·동시성을 입증하지 않는다. CI 실행 강제와 PG는 후속2B이므로 BK-R004를
  포함한 기존44개 위험은 Open 유지한다. 알려진 취약 동작을 정상 계약으로 고정하지 않았다.
- 앱 업무 코드·기존 migration·의존성·CI·실제 인프라·운영 데이터 변경은 없다.
  롤백은 테스트/설정만 되돌리면 된다. 다음 구현 후보는1A의 격리 Compose PG와 실패 fixture이며
  과거 migration 복구는1B의 별도 결정 관문을 따른다.

## 2026-09-07 — 프롬프트02 청사진 재검토 완료

- 사용자 지시: 디자인은 추후 수정하고 현대화 순서·목적·기대 결과를 정리한 뒤 다음 단계 진행.
  이번 실행은 프롬프트02의 문서 검토 범위다. 기존 업무 흐름, 주문·서빙 휴대폰,
  주방·관리자 PC를 유지하고 디자인 적용은 보류한다.
- 브랜치/HEAD: `chore/astra-modernization-setup` / `2d5bb78c035555d6e4a58821600aec27a7927b86`.
  워크트리 `/Users/gimhyochan/system/bazaar_kiosk`. 이전 미커밋 문서 변경은 보존했다.
- 변경 파일: BLUEPRINT.md, DECISIONS.md, WORKLOG.md, prompts/03_IMPLEMENT_PHASE.md.
  실행 청사진을35개 추적 단위(분석 인계·Git·운영 실행·후속 UI 포함)로 나누고,
  위험44개(Critical1/High30/Medium13)를 각각 하나의 주 담당에 연결했다.
  위험 상태는 여전히 미해결이며, 단계 배정만으로 위험을 닫지 않았다.
- 실행 순서: 2A 격리 테스트와1A PG 실패 재현은 병행 가능하다. 보안 선행 수정은
  PG 복구 전체를 기다리지 않고 착수할 수 있다. 번호→중복 요청→상태→결제→관리자→과거 정합성,
  완전 조회·API, 자체 SSE, 운영 후보·복원·이전 리허설·최종 감사 순서로 합류한다.
  통합 책임자와 파일 소유권을 명시하고 SSE 클라이언트와 UI 모듈 편집은 직렬화했다.
- 결정 기록: 사용자 흐름·기기·디자인 보류를 D-025 accepted로 기록했다.
  재검토 실행 계획은 D-P06 proposed로 두었다. EC2, 번호/결제/권한 정책, 데이터 이전,
  지상·부스 제거와 SSE 전달 상세를 자동 승인하지 않았다.
- 독립 검토: 읽기 전용 서브에이전트의 초기10개 지적을 반영했다. 최종 추가3개 지적도 반영했다.
  4A2 최종 PG 검증은2B와 합류하고,10C 서버 snapshot 완료와10D1/2 통합 증거를 구분했다.
  모든 전이 재생을 선택하면 SSE 후속 카드를 재계획하도록 D-019 분기를 명시했다.
- 검증: `.venv/blueprint-review/validate_docs.py`로 저장소 Markdown17개를 파싱하고
  로컬 링크 대상·앵커·소스 줄 번호, 변경 문서4개 HTML 렌더, 코드 블록과 셸 명령 구문,
  분석/등록부/청사진 위험44개 대응,35개 단계의 누락·순환 의존을 검사했다.
  외부 URL은 분류만 했으며 네트워크 응답을 다시 검증한 것은 아니다.
  시작 시 SHA256과 비교해 허용4문서만 변경됐고 Git ref는 동일함을 확인했다.
  `git diff --check`와 앱·설정 경로의 HEAD 대비 무변경 검사도 통과했다.
- 앱 테스트는 문서 작업이므로 다시 실행하지 않았다. 앱 코드, 실제 인프라, migration,
  의존성, 운영 데이터, 원격 push/merge 변경은 없다. 미래 테스트 명령은 단계별 구현 시
  생성할 파일과 격리된 설정을 명시한 실행 계약이며 이미 통과한 테스트로 보고하지 않는다.
- 다음 구현 후보: 프롬프트03으로 **2A 현행 동작 특성화와 격리된 로컬 테스트**만 진행.
  목적은 현재 정상 흐름과 알려진 결함을 구분하는 안전망 확보다. 운영 DB에 접속하지 않으며
  SQLite 검사로 PG 동시성·migration 안전성을 입증했다고 주장하지 않는다.
  최신 미커밋 분석/청사진까지 인계에 포함해야 하며 전체 단계 일괄 구현·운영 전환은 별도 범위다.

## 2026-09-07 — 주문·서빙 / 주방 / 관리자 명칭 방향 반영

- 사용자 결정: “주문·서빙 / 주방 / 관리자 중심으로 정리하자 문서에도 반영해줘”.
  D-023 accepted로 기록했다. 지상/부스 기능·데이터 제거 범위는 D-024 pending으로 남겼다.
- 브랜치/HEAD: `chore/astra-modernization-setup` / `2d5bb78c035555d6e4a58821600aec27a7927b86`.
  워크트리 `/Users/gimhyochan/system/bazaar_kiosk`. 기존5문서 변경을 보존했다.
- 갱신: [DECISIONS.md](DECISIONS.md)의 결정·권한/데이터 경계,
  [ANALYSIS_REPORT.md](ANALYSIS_REPORT.md#functional-naming)의 현행→목표 기능 매핑,
  [BASELINE.md](BASELINE.md)의 사실/목표 구분, [RISK_REGISTER.md](RISK_REGISTER.md)의
  단계·기능 관계와 이 작업 로그. 위험44개와 기존 재현 결과는 유지한다.
- 반영 범위: B1_COUNTER의 실제 통계를 관리자 영역으로 식별하고 주문·서빙과 주방을 유지한다.
  세 기능 영역을 로그인 역할 세 개로 단정하지 않으며 통계 조회자에게 관리자 수정 권한을 부여하지 않는다.
  visible_booth 정리 후보와 실제 사용 중인 visible_counter/kitchen을 구분했다.
- 검증: 기존 URL/pages/auth·모델·메뉴 API·통계 템플릿/admin 확인 결과와 대조했다.
  `validate_docs.py`, `validate_infra_docs.py`로 링크/줄/앵커·Markdown 렌더·44개 위험·보관 명령
  구문을 검사하고 `git diff --check`와 이번 시작 SHA256/ref 대조를 완료했다.
  Markdown16개·링크296개·문서5개 렌더·위험44개 대응과 명령 구문이 통과했으며,
  이번 시작 대비 변경 파일은 지정5문서뿐이고 Git ref는 동일하다.
  앱 테스트 재실행은 없으며 앱·인프라·과거 migration·BLUEPRINT·Git ref 변경은 하지 않는다.

다음에 사용할 정확한 프롬프트:

```text
이 저장소의 AGENTS.md를 먼저 읽고,
docs/modernization/prompts/02_REVIEW_BLUEPRINT.md에 작성된 프롬프트를
이번 작업의 사용자 지침으로 그대로 실행해줘.

ANALYSIS_REPORT.md와 RISK_REGISTER.md의 44개 위험 및 DECISIONS.md를 근거로
블루프린트를 검토하고 실제 저장소 문서로 작성·검증해줘.
D-018 자체 SSE, D-020 Compose PostgreSQL, D-023 주문·서빙 / 주방 / 관리자 구분을 반영해줘.
EC2는 D-021 후보로, 지상/부스의 기능·데이터 제거 범위는 D-024 미정으로 유지해줘.
D-019/022의 SSE·DB 이전·백업/복구 관문과 역할/URL/과거 데이터 호환을 검토해줘.
결정이 없는 항목을 승인된 것으로 처리하지 말고 해당 관문을 명시해줘.
애플리케이션 코드나 실제 인프라는 변경하지 말고, 원격 push나 merge도 하지 마.
```

## 2026-09-07 — Compose PostgreSQL·EC2 후보와 DB 이전 분석 추가

- 결과: 사용자가 추가한 DB 자체 운영 방향과 EC2 후보를 기존 SSE/현대화 분석에 통합했다.
  분석은9월6일 시작해7일 검증을 마쳤다. 이전 두 분석의 기록·발견·허용 파일 범위를 유지했다.
- 브랜치/HEAD/워크트리: `chore/astra-modernization-setup` /
  `2d5bb78c035555d6e4a58821600aec27a7927b86` / `/Users/gimhyochan/system/bazaar_kiosk`.
  시작 상태는 기존5문서 변경만 있었고 추가 분석 직전71개 비무시 파일의 SHA256·ref를 보관했다.
- 사용자 지침: “docker compose로 postgre db를 올리는 형태로 전환”, “aws 같은곳에 ec2를 생각”.
  D-020은 Compose PostgreSQL 방향 accepted, D-021은 EC2 후보 proposed로 구분했다.
  D-022 이전/중단/복구 계약 pending과 D-P05 단계 분할 proposed를 추가했다.
- 작성 파일: [ANALYSIS_REPORT.md](ANALYSIS_REPORT.md#infrastructure-migration)에 목표 구성·
  코드 설정과 Compose 차이·영속 볼륨/백업·원본 객체/sequence·쓰기 동결/되돌림·SSE·인수 기준을 추가.
  [RISK_REGISTER.md](RISK_REGISTER.md)는4개 추가하여44개(Critical1/High30/Medium13).
  [BASELINE.md](BASELINE.md)는 합성 설정 근거와 목표/현행 구분,
  [DECISIONS.md](DECISIONS.md)는 신규 결정과 D-006/018/019 관계를 반영했다. `WORKLOG.md`는 이 항목.
- 허용 범위: 지정5문서만 갱신. 앱·migration·의존성·CI·BLUEPRINT·Compose/Dockerfile·Git ref
  변경 없음. 실제 Docker/AWS/원본 DB에 접속하거나 리소스를 만들지 않았다.
- 병렬 검토: 데이터 담당은 원본→PG restore·migration/sequence·writer 동결/rollback,
  보안 담당은 현행 설정·EC2/Docker 노출·secret/role·EBS/백업·SSE 운영 경계를 읽기 전용으로 검토.
- 반영한 재검토: PG 접속 실패와 URL 누락의 SQLite 선택 구분, default SSL/CA·허브 연결 수명,
  mountpoint/자동 재시작 검사, fresh/이미0020/historical/data-only 복원 분기·오류/객체 누락0,
  실제 앱 역할의 sequence/search_path·전체 행/금액 검증, 복원 세션 무효화와 새 공통 SSE generation,
  새 INSERT/UPDATE/DELETE 보존·낮은 major 역복원 제약·snapshot 복구 조건을 보완했다.

### 실행 명령과 검사 범위

| 명령 또는 검사 | 결과 |
| --- | --- |
| `git status --short --branch`, `git rev-parse HEAD`, `git show-ref`, 비무시 파일 SHA256 보관 | 기존 문서 변경 보존·추가 분석 전71파일 기준 확보 |
| `rg --files --hidden`의 Dockerfile/compose/.dockerignore/deploy/backup 이름 검사 및 settings·env 예시·CI·migration 읽기 | 현행 컨테이너/배포/백업 파일 없음·설정/번호 경로 확인 |
| `.venv/bin/python .venv/analysis-20260906/probe_infra_settings.py` | 합성5조건의 engine/sslmode/옵션 전달 확인. 설정 import만 실행, DB 연결 없음 |
| Docker·PostgreSQL·AWS 공식 문서 확인 | Compose env/secret/health/volume·PG 이미지/덤프·EBS/SG/SSM/백업 의미를 보고서에 직접 연결 |
| `.venv/bin/python .venv/analysis-20260906/validate_docs.py` | 전체 Markdown 링크·줄·앵커·fence·위험44개 대응·기존 스크립트·문서5개 HTML 검증 |
| `.venv/bin/python .venv/analysis-20260906/validate_infra_docs.py` | SSE/인프라 probe Python/bash 구문·위험 정렬/심각도·HTML 구조·추가 분석 전 파일/refs 대조 |
| `git diff --check` | 허용5문서의 공백/패치 검사 |

최종 검증 완료: Markdown16개·링크283개(로컬 경로/줄/앵커 검사 및 외부 URL 분류), 변경 문서5개
HTML 렌더 구조, 위험44개와 등록부 정렬/Critical1/High30/Medium13, 기존 Python 스크립트5개와
SSE/인프라 probe의 Python/bash 구문을 확인했다. 인프라 probe 원문과 문서 보관 코드도 일치한다.
추가한 외부 출처는 공식 문서 본문으로 확인했다. 초기 및 추가 분석 전 SHA256·전체 비무시
파일 집합·Git ref 대조와 git diff --check는 통과했고 지정5문서 외 파일 변경은 없다.
기존 Python/Django/PG 앱 결과는 이전 항목을 유지하며 코드가 바뀌지 않아 재실행하지 않았다.
이번 합성 parser 결과를 실제 TLS/컨테이너/EC2 검증으로 바꾸어 해석하지 않는다.
실제 인프라 장애·DB 유실은 재현하지 않았다.

### 수정한 가정과 미실행

- 최초 SSE 요청만으로 DB 호스팅 이전을 추정하지 않았던 판단을 후속 D-020 방향으로 확장했다.
  EC2 후보를 확정/구매 또는 단일 호스트 중단 위험 수용으로 기록하지 않았다.
- EBS/volume의 영속성과 호스트 밖 백업·새 호스트 복원을 구분했다. Compose restart를 HA로,
  DB healthcheck를 앱 schema/복원 성공으로, SSE 폴링을 행사 인터넷 장애의 오프라인 기능으로 보지 않는다.
- DB URL/secret 파일 주입과 SSL/CA 옵션의 실제 코드 차이를 확인하고, 신규 쓰기 후 URL만
  원복하는 rollback의 데이터 유실 위험을 관문으로 남겼다.
- 미실행: Compose config/build/up·새 이미지/컨테이너, AWS 인증/API·리소스/SG/EBS/SSM·과금,
  실제 원본 DB/Supabase·dump/restore·권한/extension·TLS handshake·부하·새 호스트 복원·실제 전환.
  검증된 Compose 배포 파일이 아직 없으므로 배포 성공이나 이전 완료를 선언하지 않는다.

### 다음에 사용할 정확한 프롬프트

```text
이 저장소의 AGENTS.md를 먼저 읽고,
docs/modernization/prompts/02_REVIEW_BLUEPRINT.md에 작성된 프롬프트를
이번 작업의 사용자 지침으로 그대로 실행해줘.

ANALYSIS_REPORT.md와 RISK_REGISTER.md의 44개 위험 및 DECISIONS.md를 근거로
블루프린트를 검토하고 실제 저장소 문서로 작성·검증해줘.
D-018 자체 SSE와 D-020 Docker Compose PostgreSQL 운영 방향을 반영해줘.
EC2는 D-021의 후보로 유지하고 D-019/022의 변경 감지·데이터 이전·쓰기 동결·백업/복원·
신규 쓰기 이후 되돌림 관문과 컨테이너/ASGI/운영 단계 분할을 검토해줘.
결정이 없는 항목을 승인된 것으로 처리하지 말고 해당 관문을 명시해줘.
애플리케이션 코드나 실제 인프라는 변경하지 말고, 원격 push나 merge도 하지 마.
```

원문: [prompts/02_REVIEW_BLUEPRINT.md](prompts/02_REVIEW_BLUEPRINT.md). 이번에는 청사진 자체와
실행 가능한 Compose/배포 파일을 수정하지 않았다.

## 2026-09-06 — 사용자 요청 자체 SSE 전환 분석 추가

- 결과: 브라우저 외부 Realtime을 자체 SSE로 바꾸는 범위·구조·전환/롤백·검증 계획을 기존
  분석에 통합했다. 실제 코드를 리팩터링한 단계는 아니다.
- 브랜치/HEAD: `chore/astra-modernization-setup` / `2d5bb78c035555d6e4a58821600aec27a7927b86`.
  워크트리 `/Users/gimhyochan/system/bazaar_kiosk`. 이전 분석의 문서5개 변경을 보존했다.
- 승인 범위: 사용자 후속 요청 “외부 서드파티 연결 안하고 직접 sse 방식 … 같이 분석해서 포함”.
  프롬프트01의 문서5개만 갱신, 앱·migration·의존성·CI·BLUEPRINT·Git ref 변경 없음.
- 작성 파일: [ANALYSIS_REPORT.md](ANALYSIS_REPORT.md#sse-migration)에 파일 교체 지도,
  영속 revision/NOTIFY/outbox 비교·writer/잠금·snapshot/세션·ASGI/프록시·부하·단계 분할 추가.
  [RISK_REGISTER.md](RISK_REGISTER.md)는 BK-R035~040 추가로40개(Critical1/High26/Medium13).
  [BASELINE.md](BASELINE.md)는 확인된 현재 구독/설치 런타임 사실,
  [DECISIONS.md](DECISIONS.md)는 D-018 accepted·D-019 pending·D-P04 proposed와 D-010 관계를 기록.
  `WORKLOG.md`에는 이 추가 항목을 작성했다. 이전34개/검증 기록은 당시 이력으로 유지한다.
- 결정 구분: D-018은 사용자가 직접 정한 자체 SSE/외부 브라우저 연결 제거 방향만이다.
  DB 호스팅 이전·세부 revision/trigger/outbox 설계·코드/배포 승인은 아니다.
- 위임: 프런트 담당은 실제 구독/파일 범위·탭 수명, 데이터 담당은 writer·커밋·잠금/조회 일관성,
  보안 담당은 연결 인증/회수·메타데이터·복구 계약을 읽기 전용으로 재검토했다.
- 반영한 재검토: trigger의 도메인/revision 잠금 역순, session.aget 캐시와 신선한 권한 확인,
  EventSource의 HTTP 상태 비노출·CLOSED 처리, 인증 상실 때 큐/화면/늦은 응답 폐기,
  전역 알림의 범위 노출, heartbeat와 감지 허브·snapshot 복구 완료의 구분.

### 추가 실행 명령과 결과

| 명령 또는 검사 | 결과 |
| --- | --- |
| `git status --short`, `git rev-parse HEAD`, `git show-ref`, 시작 파일 SHA256 보관 | 기존 문서 변경만 존재; 추가 분석 전 상태 보관 |
| `rg -n 'Supabase|supabase|EventSource|StreamingHttpResponse|LISTEN|NOTIFY' orders bazaar_kiosk requirements.txt .env.example` 및 관련 코드/설치 소스 읽기 | 활성 구독은 주방, 기존 SSE/DB 알림 구현 없음·writer/인가 지도 확인 |
| 보고서 E-SSE-STATIC의 `.venv/bin/python -` 합성 probe | 기본 sync/ASGIWorker import, WhiteNoise async=False·나머지7=True, 비동기 스트림2청크·프레임 종료 확인 |
| Django5.2·WHATWG·PG·PgBouncer·Nginx 공식 문서 읽기 | 스트림/재연결·트랜잭션/trigger/격리·pool·buffering 의미 확인, 보고서에 직접 링크 |
| `.venv/bin/python .venv/analysis-20260906/validate_docs.py` | 로컬 링크/줄/앵커·fence·위험40개·보관 스크립트 구문·문서5개 HTML 구조 검증 |
| `.venv/bin/python .venv/analysis-20260906/validate_sse_docs.py` | SSE probe Python/bash 구문·위험 정렬/심각도·HTML 표/앵커·추가 분석 전 SHA256/전체 파일 집합 대조 통과 |
| `git diff --check`, 초기 및 추가 분석 전 SHA256/Git ref 비교 | 지정5문서 외 파일 변경 없음·ref 변경 없음 |

검증 완료: Markdown16개·링크230개(로컬 경로/줄/앵커 및 외부 URL 분류), 변경 문서5개 HTML,
위험40개·등록부 정렬/Critical1/High26/Medium13, 기존 Python 스크립트5개와 추가 SSE probe
Python/bash 구문을 확인했다. 새 외부 출처는 공식 문서 본문으로 확인했다. 분석 시작 및 추가
분석 직전과 비교해 지정5문서 외 파일과 Git ref는 동일하다. 보조 검사에서 복원 예제의 표식까지
세던 정규식과 기준선 JSON 키 참조를 바로잡고 재실행하여 통과했다. 앱 결함으로 등록하지 않았다.
Django/PG의 기존 앱 검사 결과는 앞선 항목을 유지하고 반복하지 않았다. E-SSE-STATIC은 직접 iterator 순회이며 HTTP 서버
검사가 아니다. Gunicorn 공식 웹 문서는 도구 열기 오류로 사용하지 않았고 설치 소스로 확인했다.

### 미검증과 다음 작업

실제 SSE URL은 아직 없다. ASGI HTTP·권한/세션 회수·브라우저 외부요청0·프록시 flush/idle·
다중 워커·revision/trigger 경합·snapshot 복구·부하/배포 인수는 구현 이후 검사다. 외부 Supabase
설정과 운영 DB를 조회하거나 변경하지 않았다. 기존 위험은 구현 없이 해결 처리하지 않는다.

다음에 사용할 정확한 프롬프트는 아래와 같다. D-018을 다시 승인받는 질문은 필요 없고,
상세 정책 관문이 남아 있어도 독립적인 블루프린트 검토는 계속할 수 있다.

```text
이 저장소의 AGENTS.md를 먼저 읽고,
docs/modernization/prompts/02_REVIEW_BLUEPRINT.md에 작성된 프롬프트를
이번 작업의 사용자 지침으로 그대로 실행해줘.

ANALYSIS_REPORT.md와 RISK_REGISTER.md의 40개 위험 및 DECISIONS.md를 근거로
블루프린트를 검토하고 실제 저장소 문서로 작성·검증해줘.
사용자가 지정한 D-018 자체 SSE 전환과 외부 브라우저 Realtime 연결 제거를 반영하고,
D-019의 영속 변경 감지·snapshot·다중 워커·권한 회수·배포/복구 관문을 검토해줘.
결정이 없는 항목을 승인된 것으로 처리하지 말고 해당 관문을 명시해줘.
애플리케이션 코드는 수정하지 말고, 원격 push나 merge도 하지 마.
```

원문: [prompts/02_REVIEW_BLUEPRINT.md](prompts/02_REVIEW_BLUEPRINT.md). SSE 제안 단계 분할은
이번에는 BLUEPRINT에 반영하지 않았다.

## 2026-09-06 — 프롬프트01 증거 우선 분석 완료

- 권고: **점진적 현대화**. 분석 산출물·로컬 검증 완료이며 제품 계약 승인/구현/배포 판정은 아님.
- 브랜치 / 워크트리: `chore/astra-modernization-setup` /
  `/Users/gimhyochan/system/bazaar_kiosk`
- 시작 HEAD: `2d5bb78c035555d6e4a58821600aec27a7927b86`; 앱 기준 `origin/develop` `93a841a`.
  시작 작업 트리 깨끗함. 다른 프로젝트의 과거 작업 이력을 이번 승인으로 사용하지 않음.
- 승인 범위: `AGENTS.md`를 먼저 읽고 `prompts/01_ANALYZE.md`를 사용자 지침으로 수행.
  프로덕션/애플리케이션/마이그레이션/의존성/CI 변경 없이 지정된 분석 문서5개만 작성.
- 작성 파일:
  - [ANALYSIS_REPORT.md](ANALYSIS_REPORT.md):34개 위험의 근거·시나리오·회귀시험,
    경로/권한·데이터흐름·migration·성능계획·Git·재현가능 스크립트·최종 선택
  - [RISK_REGISTER.md](RISK_REGISTER.md):Critical1/High22/Medium11, 증거상태·의존성·담당·주 단계
  - [BASELINE.md](BASELINE.md):실행 증거와 초기 가정 정정
  - [DECISIONS.md](DECISIONS.md):D-001~013의 담당/근거, pending D-014~017, proposed D-P03
  - `WORKLOG.md`:이 인수인계 항목
- 위임: 보안, 도메인/데이터, 프런트/실시간을 독립 서브에이전트3개에 맡김.
  저장소 쓰기는 통합 담당만 수행. 반환 근거와 문서 사실을 보안·데이터 담당이 재검토함. 혼합 결제 도입 시점,
  ORM PROTECT/DB 외래 키 구분, 안전 메서드 로그아웃·RLS 목표 권한·PIN 회수 문구를 정정.
- 환경: 기존 `.venv` Python3.12.11/Django5.2.17/psycopg3.3.5. 새 패키지/이미지 설치 없음.
  SQLite는`:memory:`, PG는 기존 이미지`cd17e2ac9824` PostgreSQL15.18/aarch64의 로컬 일회용
  컨테이너. localhost임시포트56546, tmpfs, 운영볼륨 없음. 테스트 DB만 사용했고 컨테이너 종료·제거 확인.
- 재현 스크립트 원문과 복원 명령은 분석 보고서 부록에 보관. 실행 중 스크립트·결과·렌더HTML은
  무시되는 `.venv/analysis-20260906/` 아래에 두었으며 버전관리 산출물에 추가하지 않음.

### 실행 명령과 결과

아래 `manage_local.py`는 기존 settings를 읽되 DATABASE_URL을 제거하고 메모리 SQLite,
DEBUG=0, 긴 합성 SECRET·테스트호스트·빈 Supabase 설정으로 Django management command를 실행한다.
원래 앱 파일·기존DB·실제 자격증명을 수정하거나 재현에 사용하지 않는다.

| 명령 또는 검사 | 결과 |
| --- | --- |
| `git status --short --branch`, `git diff --stat`, `git rev-parse HEAD` | 준비 branch/깨끗한 시작 상태 |
| `.venv/bin/python -V`, `pip list`, `pip check` | Python3.12.11, 위 패키지 버전, 설치 충돌 없음 |
| `.venv/bin/python .venv/analysis-20260906/manage_local.py check` | 통과, 문제0 |
| 같은 wrapper `makemigrations --check --dry-run` | 변경 없음 |
| 같은 wrapper `test` | 정상 종료, **테스트0** |
| 같은 wrapper `migrate --noinput` | 빈SQLite의orders0020까지통과 |
| 같은 wrapper `check --deploy` | W004/W008 경고2; W009는약한진단키조건과분리 |
| `.venv/bin/python .venv/analysis-20260906/probe.py` | 합성API·무결성·캐시·cutoff·query/payload·템플릿JS 관찰 완료 |
| `.venv/bin/python .venv/analysis-20260906/probe_extra.py` | DEBUG 합성PIN노출,HEAD캐시차이,날짜helper·legacy합계차이 재현 |
| `docker version`, `docker image ls`, `docker run --pull=never ...` | 기존로컬이미지로만일회용DB실행; 정확한run명령은보고서부록 |
| `.venv/bin/python .venv/analysis-20260906/probe_pg.py` | 빈0020실패,합성0019양수MAX업그레이드통과,날짜/충돌/16병렬생성/통계500 재현 |
| `.venv/bin/python .venv/analysis-20260906/probe_pg_legacy.py` | 0018→0019/역방향 포장table제약실패·행보존 |
| `docker stop bk-analysis-20260906-01a076bc`, 이름filter `docker ps -a` | 분석컨테이너종료,목록에서사라짐 |
| 추적Python42개 `ast.parse`, Django템플릿7개 compile | 구문통과 |
| 렌더inline JS5개·`node --check orders/static/orders/ui/app.js` | 구문통과; 브라우저실행아님 |
| `git log --all --graph`, `for-each-ref`, `rev-list`, branch별`git diff` | main/develop동일tree,70커밋/16merge,오래된고유콘텐츠확인 |
| `git rev-list --objects --all` + `git cat-file` 전체blob읽기/패턴검사 | 410객체/187blob,공개기본값·예시DBURL/과거pyc분리; 내용값을scan출력에기록하지않음 |
| 문서validator: pandoc GFM AST/HTML·로컬링크/줄/앵커·fence·신규자리표시자·위험ID대조 | 통과; 변경문서5개HTML구조검사 |
| 보고서에보관된Python재현스크립트5개AST검사 | 통과; PG임시포트는복원시BK_ANALYSIS_PORT로전달 |
| `git diff --check`, 시작SHA256/refs와최종대조 | 통과; 지정문서외추적파일·Gitref변경없음 |

Docker socket의 첫 sandbox 읽기는 권한 오류였으며, 허용된 로컬 분석 목적의 escalation으로
Docker 환경 확인과 테스트를 완료했다. 미실행으로 남은 PG검사는 접근 불가가 아니라 아래
운영 범위/추가 workload에 해당한다. 검사 하네스의 경로·출력 인자 오류는 수정하고 해당 결과를
다시 수집했다. 이를 애플리케이션 결함으로 등록하지 않았다.

### 수정한 가정·결정과 남은 검사

- BK-R003/005를PG로재현하고,0018↔0019실패(BK-R017)를추가했다. 정상16개번호고유와
  실패후부모0행도함께기록하여 원자성/번호고유를 모두 깨졌다고 주장하지 않음.
- dashboard는기간오류만있는것이아니라별칭충돌(BK-R016)로먼저500이다.
  BK-R006/007은독립helper/aggregate계층에서검증했다.
- 기본PIN교체만으로DEBUG설정노출(BK-R028)을막을수없음을합성값으로확인했다.
- 목록은3쿼리일정이며N+1·성능향상을주장하지않음.캐시/80개누락은정확성위험으로구분.
- FloorOrderCounter와styles.css는사용중.미사용role_select렌더실패는활성로그인장애가아님.
- 과거68커밋/55파일과현재70커밋/69파일의준비문서추가를구분.원격인증상태는재확인하지않음.
- 신규결정은pending/proposed만추가.기존accepted D-P02는보존했고새로운제품결정을승인하지않음.
- **실패재현:** PGfresh0020,PG0018↔0019,번호충돌복구,dashboard500,입력500,
  DEBUG합성PIN노출,취소복귀·중복생성·부족결제·stale테이블·80개cutoff.
- **미실행:** 실제운영버전/정제복사본migration,이미0020적용DB의별도no-op검사,
  실제자정/다중프로세스잠금·번호경합,실제Supabase RLS/GRANT/publication·SDK장애,
  실제브라우저/실기기/접근성·XSS실행,관리자form전체,PG EXPLAIN/부하/SLO,
  의존성CVE전용스캔,운영배포·health·백업복원·구앱/새스키마·롤백 rehearsal.
  분석에필수적인로컬증거는수집했지만이범위의운영통과를선언하지않음.

### 다음에 사용할 정확한 프롬프트

다음 단계는 코드 구현이 아닌 **블루프린트 검토**다. 필요한 제품/운영 결정을 먼저
[DECISIONS.md](DECISIONS.md)에 제공한다. 결정이 남아 있으면 프롬프트02 규칙에 따라 독립
계획 부분을 완성하고 해당 관문을 pending으로 유지한다.

```text
이 저장소의 AGENTS.md를 먼저 읽고,
docs/modernization/prompts/02_REVIEW_BLUEPRINT.md에 작성된 프롬프트를
이번 작업의 사용자 지침으로 그대로 실행해줘.

완료된 ANALYSIS_REPORT.md와 RISK_REGISTER.md의 34개 위험 및 DECISIONS.md를 근거로
블루프린트를 검토하고 실제 저장소 문서로 작성·검증해줘.
결정이 없는 항목을 승인된 것으로 처리하지 말고 해당 관문을 명시해줘.
애플리케이션 코드는 수정하지 말고, 원격 push나 merge도 하지 마.
```

정확한 원문 위치: [prompts/02_REVIEW_BLUEPRINT.md](prompts/02_REVIEW_BLUEPRINT.md).
0019/0020복구·API보안·통계실행오류의단계분할/순서제안은아직BLUEPRINT에반영하지않았다.

## 2026-09-06 — 준비 문서 한국어화

- 브랜치: `chore/astra-modernization-setup`
- 기준 커밋: `5c1b942`
- 범위: 저장소 안내, 에이전트 규칙, 기준선, 청사진, Git 복구 전략, 결정/작업
  기록 및 Astra용 분석·검토·구현·감사 프롬프트의 한국어화
- 변경된 파일: `.env.example`, `AGENTS.md`, `README.md`,
  `docs/modernization/` 아래의 준비 문서와 프롬프트 14개
- 표기 원칙: 설명과 지시는 한국어로 작성하고, 명령, 경로, 환경 변수, 모델 ID,
  위험/결정 ID 및 상호운용에 필요한 상태 값은 원문을 유지하거나 한국어 뒤에 병기
- 검사:
  - `git diff --check`: 통과
  - Markdown 링크, 코드 펜스 및 자리표시자 검사: 통과
  - `env -u DATABASE_URL .venv/bin/python manage.py check`: 통과
  - `env -u DATABASE_URL .venv/bin/python manage.py makemigrations --check --dry-run`:
    변경 없음
  - `env -u DATABASE_URL .venv/bin/python manage.py test`: 테스트 0개로 통과
- 결과: 애플리케이션 코드와 원격 Git 상태는 변경하지 않음
- 다음 권장 작업: GPT-6 Astra `xhigh` 작업에서
  `prompts/01_ANALYZE.md`를 실행

## 2026-09-06 — Astra 현대화 준비

- 브랜치: `chore/astra-modernization-setup` (준비 당시 로컬에만 존재)
- 기준: `origin/develop`의 `93a841a`
- 범위: 클론, 검사, 로컬 기준선 재현, 에이전트/세션/계획 문서 작성;
  애플리케이션 구현 변경 없음
- 환경: Python 3.12.11과 Django 5.2.17을 사용하는 `.venv`; Git에서 무시되는
  SQLite 데이터베이스를 `orders.0020`까지 마이그레이션
- 검사:
  - 의존성 설치: 통과
  - `python manage.py check`: 통과
  - 마이그레이션 드리프트: 없음
  - 새 SQLite 마이그레이션 체인: 통과
  - `python manage.py test`: 테스트 0개로 통과
  - 배포 검사: 문서화된 경고 3건
  - PostgreSQL 및 브라우저 검사: 미실행
- Git 근거: 커밋 68개, 병합 16개; `main`과 `develop`의 조상 이력은
  분기되어 있지만 끝점의 트리는 동일함; GitHub CLI 토큰은 유효하지 않음
- 주요 발견 사항: 보호되지 않고 CSRF가 면제된 변경 API, 기본 공유 PIN,
  테스트 부재, 하드 코딩된 대시보드 날짜, 검증되지 않은 PostgreSQL 일일
  번호 부여 및 시퀀스 마이그레이션, 안전하지 않은 동적 HTML 후보, 느슨한
  의존성 범위
- 적대적 검토에서 추가된 사항: 마이그레이션 부트스트랩 의존성 역전, Django
  관리자 합계 드리프트, 역할 필터링 전에 주방 주문을 80개로 제한하는 문제,
  레거시 분할 결제 정합성 확보, 안전한 롤백 요구사항, 워크트리 체크포인트 검증
- 결정: 원격 Git 상태를 의도적으로 변경하지 않음
- 다음 권장 작업: GPT-6 Astra `xhigh` 세션에서
  `prompts/01_ANALYZE.md`를 실행한 다음, 구현 단계를 승인하기 전에
  D-001부터 D-013까지 결정

## 항목 템플릿

### YYYY-MM-DD — 짧은 제목

- 브랜치 / 워크트리:
- 기준 커밋:
- 승인된 범위:
- 변경된 파일:
- 명령 및 결과:
- 추가/변경된 결정:
- 가정:
- 남은 위험 또는 진행이 막힌 검사:
- 다음 권장 프롬프트/단계:

### 2026-09-07 — 현재 화면의 편집 가능한 Figma 사본

- 사용자 요청으로 개인 팀에 [Bazaar Kiosk · 현재 화면](https://www.figma.com/design/xMjsXUrlomJpUIrGy7WAHd)을 새로 생성했다.
- 현재 코드의 로그인, 주문(서빙), 주방 전체/홀/포장, 판매 통계, Django 관리자 메인/메뉴 목록/주문 목록/테이블 목록/주문 상세 총 11개 화면을 가져왔다. 기존 화면 명칭을 유지했다.
- 별도 메모리 SQLite와 예시 메뉴·주문·관리자 계정으로 로컬 화면을 렌더링했다. 운영 데이터나 실제 인증정보를 사용하지 않았다. 미리보기 코드는 무시되는 `.venv/figma-preview/`에만 작성했다.
- Figma 메타데이터로 11개 프레임의 분리된 텍스트 레이어를 확인하고 로그인·주문·주방·통계·주문 상세를 시각 검사했다. 변환 과정에서 누락된 주문 상세 저장 버튼 3개의 문구를 원본 Django 한국어 번역에 맞춰 편집 가능한 텍스트로 복원했다.
- 한계: 현재 데스크톱 기본 상태의 디자인 사본이며 실행 가능한 앱이나 모든 상호작용 상태의 프로토타입은 아니다. 메뉴와 주문은 예시 데이터다. 판매 통계는 기존 집계 API 오류 때문에 0/데이터 없음 상태다. 브라우저 시스템 글꼴은 변환기의 Figma 글꼴 대체가 적용될 수 있다. 디자인 시스템 컴포넌트 라이브러리로 재구축한 결과는 아니다.
- 애플리케이션 코드와 운영 인프라 변경, 원격 push/merge는 수행하지 않았다.

### 2026-09-07 — 서빙 화면 및 main/develop 재확인

- 사용자의 화면 불일치 지적에 따라 원격 `main`/`develop`을 fetch하고 `git ls-remote --heads origin main develop`로 GitHub의 최신 참조를 직접 확인했다.
- `main`: `bca9e409892d3769334176a61114d19de0d84c98` (2025-10-19), `develop`: `93a841a5ae12b576060f5006783879482a07e8b2` (2025-10-19). 두 참조의 tree는 `de8b3f3712ea25209e2d9e94d044002b3e9e7bff`로 같고 전체 파일 diff가 없다. main에만 존재하는 추가 코드 업데이트는 없다.
- 현재 HEAD의 `orders/`, `bazaar_kiosk/`, `requirements.txt` 역시 원격 main과 차이가 없다. 현재 주문(서빙) UI는 `orders/templates/orders/order.html`이며 홀/포장 탭, 테이블 번호 직접 입력, 현금/티켓/혼합 결제를 제공한다. main에서 이 파일의 마지막 변경은 2025-10-14 `4d3c482`의 거스름돈 계산 변경이다.
- 별도 `orders/templates/orders/serve.html`은 테이블 버튼과 요청사항 입력을 갖춘 미사용 템플릿이다. 현재 main의 뷰/URL에서 참조하지 않는다. 이를 최신 서빙 UI의 누락으로 단정한 앞선 안내를 정정한다.
- 비교용으로 해당 예전 템플릿의 [기본 화면](https://www.figma.com/design/xMjsXUrlomJpUIrGy7WAHd?node-id=18-2)과 [예시 장바구니 화면](https://www.figma.com/design/xMjsXUrlomJpUIrGy7WAHd?node-id=19-2)을 추가했다. 최신 화면으로 채택한 결정이 아니다. 두 캡처의 완료 응답은 확인했으나 Starter MCP 호출 한도로 이후 메타데이터/시각 검증은 실행하지 못했다. 화면 합계는 13개이며 앞선 11개 검증 범위와 구별한다.
- 실제 배포본이 기억과 같은지는 아직 확인하지 않았다. 배포 URL 또는 기억하는 구체적 UI 차이를 통해 추가 추적할 수 있다. 로컬 미리보기 서버는 종료했고 앱 코드 수정, checkout, push/merge는 하지 않았다.

### 2026-09-07 — 학생 계정 Figma 사본의 UI/UX 개선안

- 브랜치: `chore/astra-modernization-setup`. 워크트리: `/Users/gimhyochan/system/bazaar_kiosk`.
- 사용자 확정 기준: 현재 업무 흐름 유지, 차분하고 선명한 업무용 UI, 주문·서빙은 휴대폰, 주방·관리자는 PC. 기능과 권한 변경은 이번 범위에 포함하지 않는다.
- [학생 계정의 작업 파일](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt)에 원본 보존/개선안 섹션 2개를 구성했다. 원본 11개 프레임의 ID·절대 위치·크기를 유지했다. 사용자가 제거한 미사용 서빙 화면은 복원하지 않았다.
- [개선안 섹션](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2004-3)에 13개 화면·상태와 390×844 휴대폰 스크롤 프리뷰를 만들었다. 공통 컴포넌트 11개, 인스턴스 177개, 텍스트 420개, 색상 변수 10개를 읽어 확인했다. 이미지 채우기를 사용한 노드는 없다.
- 휴대폰 하단에 주문 요약과 주문 정보로 이동하는 고정 버튼을 추가했다. 기존 주문·결제 순서, 홀/포장 혼합 주문, 준비 수량 변경, 관리자 필드와 역할 구분을 유지하는 디자인 제안이다.
- 주요 화면 렌더링을 검사하고 텍스트 자동 높이·카드 여백·차트 기준선·표 정렬을 수정했다. 텍스트 경계 넘침 0건, 이동/스크롤 목적지 8개, 주요 텍스트와 컨트롤 경계 대비를 확인했다. 실제 Present 클릭·스크롤 E2E 및 실기기 검증은 수행하지 않았다.
- 변경 문서: [UI_UX_REDESIGN.md](UI_UX_REDESIGN.md), 이 WORKLOG. 공식 제품 참고 자료, 폰트 라이선스, 화면 링크, 검증 수치와 한계를 기록했다.
- 검증: 로컬 문서 링크/Markdown 구조/미완성 표식 검사, `git diff --check`, 애플리케이션 경로 diff 검사. 문서 렌더링은 번들 Node의 `marked`를 사용했다.
- 로컬 실행 기록과 Figma 검사 결과는 무시되는 `.venv/figma-redesign/`에만 저장했다. 기존 분석 문서 변경을 보존했고 앱 코드·운영 인프라·원격 push/merge를 변경하지 않았다.
- 한계: 예시 데이터 기반의 편집 가능한 1차 디자인이며 실제 기능 구현이 아니다. 통계 API 오류, 모든 오류/빈 상태, 전체 관리자 하위 폼과 인라인 편집 동작은 별도 구현·검증 대상이다.

### 2026-09-21 — 05안 Figma 댓글 반영

- 브랜치: `phase-10d2-kitchen-client`. 이번 작업은 Figma와 문서만 변경했다.
- 팀 댓글 8개와 관련 답글·모니터링 첨부 예시를 검토했다. 사용자에게 완료의 의미와 수정 범위를
  확인했고, **완료 = 준비 완료 후 손님께 서빙 출발**, **수정 = 준비 수량·상태**로 확정했다.
- [05안](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2135-907)의 메뉴를
  수량 선택 후 담기로 변경하고, 결제 장바구니를 바로 표시했다. 식당·포장·전체 모니터링에
  미완료 가로 목록과 전체 내역 세로 목록, 부분 준비·서빙 출발·취소 조회 상세를 반영했다.
- #021 주문의 식당·전체 완료 전후 비교와 복귀 연결을 추가했다. 기존 주문 전체 취소 진입은
  유지하되 메뉴·주문 수량·금액 수정 및 품목별 취소는 추가하지 않았다.
- 검증: Figma 렌더링, 텍스트 넘침·최상위 프레임 겹침·섹션 밖 배치·누락 글꼴·끊어진 목적지
  각 0건. 05안 프레임 51개, 텍스트 1,574개, 동작 113개. 다른 섹션과 사용자 별도 모바일
  프레임은 ID·이름·위치·크기·텍스트 해시가 작업 전후 일치했다.
- 문서: [UI_UX_REDESIGN.md](UI_UX_REDESIGN.md)에 댓글별 처리, 화면 링크, 확정 사항,
  검증 수치와 구현 경계를 기록했다. `git diff --check`와 변경 문서 링크·표 구조를 검사했다.
- 한계: 대표 화면 연결을 갖춘 편집 가능한 디자인이다. 실제 수량·금액 계산과 저장, 모든 행의
  동작, Present 클릭·스크롤 E2E는 구현·검증한 범위가 아니다. 서버 상태 계약은 변경하지 않았다.
- 다음 단계: 사용자 디자인 검토 후 해당 UI를 구현할 때 출발·복귀 상태, 준비 수량 처리와
  행위자 기록·동시성 정책을 검증한다. 댓글 답글 게시·해결 처리, 앱 코드 수정, push/merge는 하지 않았다.

### 2026-09-21 — UI-05A: 05안 채택·로그인/내 메뉴/휴대폰 주문·결제 구현

- 사용자 지시: 05안을 UI로 채택하고 문서와 코드에 적용, 추가 수정은 이후 순차 반영.
  D-062와 [UI_IMPLEMENTATION](UI_IMPLEMENTATION.md)에 채택 기준과 UI-05A→05B→05C 순서를 기록했다.
- 로컬 브랜치: `ui/05-serving-foundation` (`phase-10d2-kitchen-client`의 HEAD에서 생성).
  앞선 Figma 작업의 UI_UX_REDESIGN/WORKLOG 변경을 보존했다. commit/push/merge/배포는 하지 않았다.
- 구현: 공통 opt-in 스타일, 이름+행사 비밀번호 로그인, 권한별 내 메뉴, 한 열 메뉴·선택 수량/담기,
  고정 결제 진입, 테이블 아래 펼친 장바구니와 결제 대화상자. 주문 controller/state를 외부 JS로 분리했다.
  다른 화면의 스타일/주방 SSE/상태 API와 DB 스키마는 변경하지 않았다.
- 보존: 서버 가격·결제 규칙/번호/연습 배지, JWT 자동 갱신·계정/세션 결속, CSRF, 안전한 DOM.
  닫기 후 초안 유지, 실패 후 동일 요청 ID 재시도, 저장 중 편집/중복 제출 방어를 검증했다.
- 독립 리뷰: 일반 텍스트 서버 오류가 사라지는 문제, 현금+식권 연속 입력의 초점 유실을 수정했다.
  실제 Django 400은 텍스트 본문에도 `text/html`을 사용하므로 MIME만으로 오류를 버리지 않도록 했다.
  성공 상태라도 JSON/주문 ID가 없으면 초안을 보존해 같은 ID로 확인하도록 했다.
- 검증 완료:
  - PostgreSQL 전용 `scripts/test_postgres.py`: **마이그레이션 26 + 애플리케이션 533 통과**,
    system check 정상, `makemigrations --check --dry-run` 변경 없음. 첫 실행에서 인라인 JS를
    전제로 한 기존 문자열 검사 1건이 실패해 외부 controller 연결 검사와 실제 JS 동작 검사로 대체했다.
  - CI와 같은 Node 명령: **67 통과**(기존 인증·DOM·요청 ID·주방 스케줄러 + 새 주문 상태 4·controller 8).
    controller 테스트는 통신 실패, 불명확한 200, 일반 텍스트/JSON 거절, 재시도/연타/초기화/입력 초점을 검사한다.
  - 실제 앱 브라우저: 390×844, 320×568, 390×460. 합성 메뉴 10개, 홀2+포장1 혼합 15,000원,
    홀 현금 5,000원, 포장101 식권 5,000원 주문을 저장했다. 식권 초과분의 현금 거스름돈은 0원.
  - 수량 선택만으로 담기지 않음, 결제 닫기/재진입 때 테이블·금액·장바구니 유지, 등록되지 않은
    테이블의 구체적 오류, Escape/닫기 후 초점 복귀, 마지막 항목 삭제 후 저장 비활성화를 확인했다.
  - 좁은 화면 가로 넘침 없음, 낮은 화면에서도 고정 저장 버튼이 화면 안에 있음. 메뉴/장바구니의
    HTML 형태 이름이 텍스트로 표시되고 `img` 노드는 0개. 서빙 전용 계정에는 주문·서빙만,
    4권한 계정에는 허용 업무 5개(전체 모니터링 포함)가 표시된다. 로그아웃 후 로그인으로 복귀했다.
- 격리 환경: Compose 프로젝트 `bk-ui05-0921`, loopback55461의 폐기용 PG15. 검증 마커·소유권을
  확인하고 UUID DB를 만들어 썼으며 운영/개발 DB는 사용하지 않았다. 실행 로그는 무시되는 `.venv/ui05-preview/`.
  검증 후 임시 서버·브라우저 탭·viewport 설정과 해당 Compose 컨테이너/볼륨을 정리했다.
- 문서: README, BLUEPRINT, DECISIONS, SESSION_SETUP, UI_UX_REDESIGN과 새 UI_IMPLEMENTATION을 갱신했다.
  새 JS 테스트를 CI에 추가했다. 변경 문서의 로컬 링크와 `git diff --check`를 검사했다.
- 남은 범위: UI-05B 모니터링의 준비 수량/명시적 서빙 출발과 READY 자동 전이 정합성,
  UI-05C 누적·통계/공통 메뉴 확대. 실기기 소프트 키보드·음성 스크린리더는 미검증이다.
  UI-05A의 로컬 완료를 05안 전체/단계11/BK-R023/운영 인수 완료로 해석하지 않는다.

### 2026-09-21 — UI-05A PR 제출

- 사용자 후속 지시 “pr 올리자”로 `ui/05-serving-foundation`의 commit·push·PR 생성을 승인받았다.
  대상은 `develop`이며 merge·배포는 하지 않는다.
- 원격 확인: PR #80은 `develop`에 머지됐고 최신 `origin/develop`은 `1efb223`이다.
  작업 브랜치의 구현 전 HEAD와 최신 develop의 tree가 같아 이전 검증 결과를 그대로 사용한다.
- 포함 범위: 05안 채택/댓글 기록, 로그인·내 메뉴·서빙 UI, 관련 테스트와 CI, 인수 문서.
  PostgreSQL 26+533 및 Node 67 통과, 실제 휴대폰 viewport 검증은 위 UI-05A 기록을 따른다.
- 게시 전 `git diff --check`와 변경 범위·검증 로그를 확인했다. 임시 실행 파일과 합성 DB는 포함하지 않는다.
