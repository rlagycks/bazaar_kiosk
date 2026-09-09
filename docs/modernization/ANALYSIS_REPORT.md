# Bazaar Kiosk 증거 우선 현대화 분석

현재 실행 안내(2026-09-09, D-029): [PostgreSQL 전용 전환](POSTGRES_ONLY.md)과
[공통 검증 명령](POSTGRES_TESTING.md)을 따른다. 아래 SQLite 관찰·이전 수치·명령은 당시 증거다.
PR40은 머지됐고8A는 PR42에서 실행성 수정 후 리뷰/최종 인수 대기다. 현재37개를 PG에서 검증한다.

최종 검증: 2026-09-07 · 통합 책임: 주 에이전트 · 범위: 프롬프트 01 + 자체 SSE·Compose PostgreSQL·EC2 후보 분석

## 권고와 분석 경계

**점진적 현대화를 권고한다.** 주문 생성의 원자성, 서버 가격 스냅샷, 고유 번호의 정상 동시 할당,
조회의 사전 로딩 등 보존할 기반이 있다. 가장 큰 문제는 권한 경계, 마이그레이션 호환성,
번호 충돌 복구, 결제·상태 계약, 통계 실행 오류다. 프레임워크를 교체해도 이 문제의 계약과
데이터 호환성 검증은 필요하다. 부분 프런트엔드 교체는 API 안정화 뒤 D-009에서 재평가한다.

분석 산출물 작성·로컬 검증은 완료했다. **제품 계약 승인이나 블루프린트 전체 0단계 완료,
운영 배포 가능 판정은 아니다.** D-001~D-017·D-019·D-021/022는 남은 결정 또는 운영 증거가 필요하다.
사용자가 지정한 자체 SSE(D-018)와 Compose PostgreSQL 운영(D-020) 방향은 accepted다.
기능·명칭을 주문·서빙 / 주방 / 관리자 중심으로 정리하는 방향도 D-023 accepted이며,
지상·부스의 구체적 제거 범위는 D-024 pending이다.
EC2는 검토 후보(D-021 proposed)이며 리소스 생성·배포나 단일 호스트 위험 수용을 뜻하지 않는다.
프로덕션 데이터·Supabase에 접속하지 않았고, 애플리케이션·마이그레이션·의존성·CI·Git ref를
변경하지 않았다. 기존34개는 현행 코드 발견, BK-R035~040은 SSE 전환, BK-R041~044는
인프라 이전의 선행 조건·설계·운영 위험이다. 총44개(Critical1/High30/Medium13)이며 신규 구성의
장애를 재현했다고 해석하지 않는다. [SSE 분석](#sse-migration)과
[Compose PostgreSQL·EC2 후보/데이터 이전 분석](#infrastructure-migration)을 통합했다.

- 저장소: `/Users/gimhyochan/system/bazaar_kiosk`
- 브랜치: `chore/astra-modernization-setup`, 시작 HEAD `2d5bb78c035555d6e4a58821600aec27a7927b86`
- 앱 기준: `origin/develop` `93a841a`, 트리 `de8b3f3712ea25209e2d9e94d044002b3e9e7bff`
- 시작 상태: 깨끗함. 추적 파일 69개/6,481줄, Python 42개, 앱 템플릿 7개.
  원래 앱 스냅샷 55개/약4,753줄과 준비 문서 추가 후 규모를 구분한다.
- 자료: [작업 규약](../../AGENTS.md), [제어 센터](README.md), [기준선](BASELINE.md),
  [청사진](BLUEPRINT.md), [Git 복구](GIT_RECOVERY.md), [결정](DECISIONS.md), [작업 로그](WORKLOG.md).
- 보안, 데이터·도메인, 프런트엔드·실시간을 3개 독립 서브에이전트에 위임했다.
  통합 담당은 환경·Git·직접 재현·문서 작성을 맡고, 반환된 근거와 원본을 검토했다.

심각도는 Critical/High/Medium/Low, 증거 상태는 Reproduced/Code-supported/
Production-dependent/Hypothesis를 사용한다. Reproduced는 기재한 환경·fixture의 결과만 뜻한다.
Code-supported는 경로가 코드로 확인되지만 전체 실패 여정을 실행하지 않았다는 뜻이다.
Production-dependent는 실제 영향 판단에 외부 정책·운영 데이터가 필요하며, Hypothesis는
측정 전 병목 같은 가설이다. 확신은 심각도와 별개다. 담당자는 역할 단위의 제안이며 인사 배정은 아니다.

## 실행 환경과 검증 결과

실제 런타임은 Django 서버 렌더링 + 바닐라 JS/CSS다. `orders`의 Table, MenuItem, Order,
OrderItem, FloorOrderCounter가 핵심이다. URL은 Django WSGI/ASGI 진입점에서 연결되고,
PostgreSQL URL이 없으면 SQLite로 돌아간다. `.env` 자동 로더는 없다.
[settings.py:69](../../bazaar_kiosk/settings.py#L69), [요구사항](../../requirements.txt),
[CI:17](../../.github/workflows/ci.yml#L17)를 근거로 하며 운영 배포 플랫폼은 추정하지 않는다.
Gunicorn·WhiteNoise는 설치 대상이지만 실제 워커 수·시작 명령·정적 파일 배포 완료 여부는 미확인이다.

기존 `.venv`의 Python 3.12.11, Django 5.2.17, psycopg 3.3.5, WhiteNoise 6.10.0,
Gunicorn 26.2.0을 사용했다. 추가 의존성이나 이미지를 설치하지 않았다.
DB 명령은 상속된 `DATABASE_URL`을 제거하거나 검증된 localhost 테스트 DB로 명시했다.
기존 `db.sqlite3`와 `.env`를 사용하지 않았다. SQLite는 메모리 DB이며, PostgreSQL은 기존
`postgres:15-alpine` 이미지 `cd17e2ac9824`의 15.18/aarch64를 localhost 임시 포트에 실행했다.
컨테이너는 운영 볼륨 없이 tmpfs를 사용하고 분석 후 제거했다. 이 버전은 운영 기준 버전으로 승인된 것이 아니다.

| 증거 묶음 | 실행·환경 | 관찰 | 판정/한계 |
| --- | --- | --- | --- |
| E-BASE | Python3.12 `manage.py check` | 문제0 | 통과 |
| E-BASE | `makemigrations --check --dry-run` | 변경 없음 | 통과; 데이터 호환성 검증은 아님 |
| E-BASE | `manage.py test` | Found0, NO TESTS RAN | 명령 정상 종료, 동작 안전망 없음 |
| E-BASE | 새 SQLite `migrate --noinput` | orders0020까지 적용 | 통과; PG 전용0020 분기는 실행되지 않음 |
| E-BASE | `check --deploy`, DEBUG=0, 긴 진단 키 | W004 HSTS, W008 SSL redirect | 경고2; W009 약한 키 경고는 진단조건으로 제거 |
| E-BASE | `pip check` | 충돌 없음 | 설치된 패키지 호환성만 검사 |
| E-SQLite | CSRF 강제 Client, 합성 메뉴5000원/테이블1·101 | 익명 생성201·상태/진행200, 오역할 진행200 | BK-R001 재현 |
| E-SQLite | 주문/항목 생성 중 bulk_create 예외 주입 | 500, 부모 주문 증가0 | 기존 atomic 보존 근거 |
| E-SQLite | 동일 요청2번·금액/타입·취소/캐시 사례 | 중복2주문, 부족결제201, 취소복귀200, stale테이블201 | 위험 상세 참조 |
| E-PG | 빈PG 전체 migration | 0020 `setval(0)` DataError, head0019 | **실패 재현** |
| E-PG | 합성0019에 번호40 한 행 후 migrate | 0020 성공 | 해당 양수 MAX 경로만 통과 |
| E-PG | 날짜 모킹 9/6→9/7 | 41→42 | PG 일일 초기화 없음 재현; wall-clock 자정 경합은 미실행 |
| E-PG | 오늘번호100 + `setval(100,false)` 충돌 | TransactionManagementError, 부모 증가0 | 충돌 복구 실패·원자성 유지 |
| E-PG | 8스레드/16 POST, 동일 본문 | 201×16, 고유번호16개(201~216) | 정상 할당 성공, 요청 멱등성 없음; 부하/SLO 검증 아님 |
| E-PG-LEGACY | historical0018의 table=NULL 포장행→0019 | IntegrityError, 행 보존 | **업그레이드 실패 재현** |
| E-PG-LEGACY | 0019의 table있는 포장행→0018 | IntegrityError, 행 보존 | **역마이그레이션 실패 재현** |
| E-SQLite/E-PG | dashboard GET, 빈DB·합성DB | aggregate 별칭 FieldError/500 | BK-R016; 정상 통계 응답 기준선 없음 |
| E-SUPPLEMENT | 날짜 helper와 레거시 aggregate 직접 호출 | 요청 날짜 무시; 상세5000/분할SUM null | BK-R006/007의 독립 계층 재현, HTTP 정상보고 아님 |
| E-SUPPLEMENT | DEBUG=1, 합성 ROLE_PINS, JSON[] | 500 응답에 합성 marker 포함=true | BK-R028; 실제 PIN 사용·출력 안함 |
| E-STATIC | Python AST42, Django 템플릿 compile7 | 모두 구문 파싱 성공 | 타입/동작 검증 아님 |
| E-STATIC | 렌더된 인라인 JS5 + app.js, `node --check` | 모두 통과 | 브라우저 실행 아님 |
| E-STATIC | 미사용 role_select 렌더 | `NoReverseMatch: login_pin` | 현재 라우팅된 로그인 장애가 아님 |
| E-GIT | 로컬 refs·그래프·고유 blob 검사 | 아래 Git 절 참고 | 원격 최신 상태 조회 안함 |

검사 도구 자체의 잘못된 API 경로와 출력 인자·미사용 템플릿 처리 오류는 수정한 뒤 해당
검사를 완료했다. 이를 앱 결함으로 세지 않았다. 로컬 `staticfiles/` 미생성 경고는 실행 환경
한계이며 운영 정적 파일 장애라고 단정하지 않는다. HTML 구문 검사는 테스트에서 static URL
스토리지를 임시로 바꿨으며, 배포용 manifest/collectstatic 경로 검증은 미실행이다.

## 운영자 여정과 데이터 흐름

| 여정 | 현행 동작 | 보존할 것·결정할 것 |
| --- | --- | --- |
| 로그인 | 역할5종과 공유 PIN, DB 세션의 role; 관리자 인증은 별도 | 기명/기기/공유 식별 D-002, 목표 권한 D-003 |
| 메뉴/테이블 설정 | Django 관리자에서 가격·활성·표시 채널 변경 | 정수KRW·메뉴 활성 서버검증 보존; 캐시 갱신·관리자 쓰기 D-011 |
| 주문 | ORDER 화면에서 메뉴·수량·홀/포장 mode·테이블·수납 선택 | 메뉴 가격은 서버에서 읽어 항목 단가로 저장; 화면 가격과 달라질 때의 안내 필요 |
| 순수 포장 | TAKEOUT, 활성 테이블101~120 요구 | 이 번호는 전달 슬롯이며 order_no와 다른 개념; 슬롯 독점/재사용·범위 D-014 |
| 혼합 주문 | 홀 항목이 있으면 DINE_IN, 항목별 service_mode는 유지 | 홀/포장 보드 분류가 주문 전체인지 항목인지 D-014에서 확정 |
| 결제 | CASH/TICKET은 received_amount, 혼합은 분할액 또는 문자열 두 부분 fallback | 부족결제/과다식권/거스름돈/환불 D-005; 통화 단위는 KRW |
| 주방 | PREPARING 조회, 전체/홀/포장 필터, 품목 prepared_qty 갱신 | 모든 대기 작업·취소 종결성·복구 여정 보존 |
| 취소/완료 | 직접 status PATCH와 항목 기반 상태 동기화가 공존 | 어떤 전이가 허용되는지 D-015; 환불은 별도 데이터 구조 없음 |
| 통계 | B1_COUNTER는 현재 수납 입력 화면이 아니라 매출 대시보드 | 역할 로그인 설명과 현행 화면이 어긋남; dashboard 현재500, 정책 D-012/013 |
| 장애/재전송 | 주문 버튼은 요청 중 비활성화하지만 요청ID 없음; 주방 폴링/Realtime 혼용 | 버튼 제어는 응답 유실 재시도·서버 멱등성을 보장하지 않음 |

```text
브라우저 role/PIN → Django login → DB session(role) → 페이지 require_roles
브라우저 JSON → [현재 역할 검사/CSRF가 없는 쓰기 API]
  → 메뉴 활성/가격 조회 + 테이블 캐시 조회
  → atomic { Order 생성 → OrderItem bulk_create → 합계 update → 번호/일자 할당 }
  → 직렬화 JSON → 주방 조회/통계/운영자 화면
관리자 모델/인라인 저장 → 동일 DB (주문 명령·합계·번호 서비스 우회)
PostgreSQL → 외부 Supabase publication/RLS(미검증) → 브라우저 이벤트 → 단건 API 재조회
```

화면 상태와 API 권한, Django DB 세션과 Supabase 익명 클라이언트 사이에는 별도 신뢰 경계가
있다. API source 문자열도 호출자가 선택할 수 있어 감사 주체로 신뢰할 수 없다.
항목 단가는 저장 시점 가격 스냅샷이나 메뉴명은 현재 관계값이다. 합계는 생성 시 계산되며
이후 관리자 writer 전체에서 다시 계산하지 않는다.

현행 상태는 PREPARING/READY/CANCELLED 세 가지다. 항목 진행 경로는 잔여가 있으면 PREPARING,
없으면 READY이며 취소 주문을 거부한다. 직접 상태 경로는 세 값 사이 전이를 모두 받아
취소→활성이 가능하다. [상태 코드](../../orders/views/api.py#L346).
따라서 '취소하면 다시 주방에 나타나지 않는다', '재시도해도 같은 주문 하나다', '목록 제한으로
미처리 주문이 사라지지 않는다'를 사용자와 합의할 인수 예시로 제시한다. 아직 승인된 정책은 아니다.

<a id="functional-naming"></a>
## 사용자 지정 기능·명칭 정리 — 주문·서빙 / 주방 / 관리자

**D-023에 따라 세 기능 영역을 명칭·화면 구성의 기준으로 사용한다.** 아래는 현재 코드와
목표 영역의 매핑이다. 현재 URL·역할 코드를 이미 변경한 것으로 읽지 않는다.

| 목표 영역 | 현행 기능·근거 | 정리할 내용 |
| --- | --- | --- |
| 주문·서빙 | ORDER 역할과 주문 화면, 테이블·매장/포장·결제 입력 ([화면 경로](../../orders/urls.py#L15)) | 주방에 주문을 전달하는 업무 흐름 유지, 주문/서빙 명칭 일관화 |
| 주방 | KITCHEN/KITCHEN_HALL/KITCHEN_TAKEOUT, 전체·홀·포장 화면 ([페이지](../../orders/views/pages.py#L23)) | 준비 수량·완료·취소와 자체 SSE 유지; 홀/포장 화면·역할 병합은 별도 결정 |
| 관리자 — 통계 | B1_COUNTER 경로의 실제 판매 통계 대시보드 ([템플릿](../../orders/templates/orders/b1_counter.html#L36)) | 카운터라는 기존 명칭과 통계 목적을 분리하고 관리자 영역으로 식별 |
| 관리자 — 운영 관리 | Django admin의 메뉴·테이블·주문/항목 관리 ([등록](../../orders/admin.py#L17)) | 통계 조회와 데이터 수정 권한을 구분, 저장 합계/상태 무결성 검증 |

현재 로그인 설명의 B1_COUNTER는 “주방 카운터”이지만 실제 화면은 판매 통계다.
통계는 주문 수·판매 수량·매출·현금/식권·메뉴별·시간대별 집계를 제공하도록 작성돼 있으나,
기존 BK-R016의500 오류와 BK-R006의 고정 날짜 문제가 있다. 기능을 보존한다는 결정은 이
오류를 정상으로 인정하거나 통계 계산 계약을 확정한 것이 아니다. 관리자 편집의 합계 불일치
BK-R008도 그대로 개선 대상으로 남는다.

현행 [모델](../../orders/models/core.py#L6)과 신규 주문 API는 B1·매장/포장 중심이다.
F1/BOOTH의 독립 활성 화면·로그인 역할은 없지만, [visible_booth](../../orders/models/core.py#L54)는
관리자에 남아 있다. [메뉴 조회](../../orders/views/api.py#L125)는 visible_kitchen/visible_counter를
사용하므로 세 가시성 필드를 함께 미사용으로 판단하지 않는다. 과거 migration의 F1/BOOTH는
이력이며 지우는 대상이 아니다. 실제 운영 DB에 과거 행이 남았는지는 확인하지 않았다.

정리 순서는 명칭·기능 매핑 → 통계/관리자 권한 및 기존 URL 호환 계획 → 미사용 UI 정리 →
필요한 경우 별도 DB 변경 검토를 제안한다. 역할 코드와 저장된 source/floor, 층별 번호/제약,
과거 통계는 표시 이름과 별개다. 새 ADMIN 역할 코드·새 URL·데이터 재분류를 암묵적으로 만들지 않는다.
통계 조회자를 Django staff/superuser로 자동 승격시키는 것도 이 결정의 범위가 아니다.

지상/부스의 유지·종료 범위, 과거 주문/통계 보존, 관리자 수정 권한은 D-024와 기존 D-003/008/011에
남긴다. 자체 SSE의 현재 교체 대상은 주방이며 관리자 통계 자동 실시간 갱신은 별도 요구다.
프롬프트02에서 단계3의 역할/인가,8의 통계,9의 API/URL 호환,11의 화면·명칭 정리에 반영한다.
인수 기준은 세 영역의 메뉴/로그인 명칭 일관성, 기존 진입 URL의 호환 정책, 역할별 허용/거부,
통계와 주방 핵심 흐름 보존, 과거 source/floor/번호 데이터 보존이다. 이번에는 문서만 수정했다.

## 경로·메서드·권한 매트릭스

현재 구현의 허용 상태다. `전체`는 역할 검사가 없음을 뜻하며 성공 응답 보장은 아니다.
O/C/K/H/T는 ORDER/B1_COUNTER/KITCHEN/KITCHEN_HALL/KITCHEN_TAKEOUT이다.
페이지 역할 불일치는 로그인302다. `*`는 뷰에 명시적 메서드 제한이 없고 안전하지 않은
메서드에 기본 CSRF 미들웨어가 적용된다는 뜻이다. 모든 API의 목표 역할은 D-003에서 결정한다.

| 경로 | 메서드 | 현재 역할 | CSRF/주의 | 근거 |
| --- | --- | --- | --- | --- |
| `/` · `/orders/` | GET/HEAD/POST/PUT/PATCH/DELETE/OPTIONS →302 | 전체 | unsafe는 CSRF 적용 | [root](../../bazaar_kiosk/urls.py#L6), [orders](../../orders/urls.py#L10) |
| `/orders/login/` | POST 인증, 나머지 폼 | 전체 | POST CSRF 적용 | [auth19](../../orders/views/auth.py#L19) |
| `/orders/logout/` | * 세션 폐기 | 전체 | 안전 메서드(GET/HEAD/OPTIONS/TRACE)도 폐기·CSRF 검사 밖; POST 등은 CSRF 적용 | [auth51](../../orders/views/auth.py#L51) |
| `/orders/order/` | * | O | unsafe CSRF | [pages14](../../orders/views/pages.py#L14) |
| `/orders/b1-counter/` | * | C | unsafe CSRF | [pages18](../../orders/views/pages.py#L18) |
| `/orders/kitchen/` | * | K/H/T | H/T도 전체 보드 접근은 현행 명시 동작 | [pages23](../../orders/views/pages.py#L23) |
| `/orders/kitchen/hall/` | * | H | unsafe CSRF | [pages33](../../orders/views/pages.py#L33) |
| `/orders/kitchen/takeout/` | * | T | unsafe CSRF | [pages43](../../orders/views/pages.py#L43) |
| `/orders/tables/` | GET, cache-hit HEAD | 전체 | cold HEAD405/warm200; 인가는 캐시 밖에서 보장 필요 | [api114](../../orders/views/api.py#L114) |
| `/orders/menus/` | GET, cache-hit HEAD | 전체 | 위 HEAD 차이 직접 재현 | [api122](../../orders/views/api.py#L122) |
| `/orders/api/orders/` | GET/POST | 전체 | **CSRF 면제**, 생성201 | [api146](../../orders/views/api.py#L146) |
| `/orders/api/orders/<id>/detail` | GET | 전체 | 조회200 | [api480](../../orders/views/api.py#L480) |
| `/orders/api/orders/<id>/status` | PATCH | 전체 | **CSRF 면제**,200 | [api346](../../orders/views/api.py#L346) |
| `/orders/api/orders/items/<id>/progress` | PATCH | 전체 | **CSRF 면제**,200 | [api379](../../orders/views/api.py#L379) |
| `/orders/api/kitchen/menu-summary` | GET | 전체 | 조회200 | [api456](../../orders/views/api.py#L456) |
| `/orders/api/stats/menu-counts` | GET | 전체 | 조회200 | [api428](../../orders/views/api.py#L428) |
| `/orders/api/stats/dashboard` | GET | 전체 | 인가 없음; 별도 FieldError500 | [api489](../../orders/views/api.py#L489) |

GET 전용 API는 일반적으로 HEAD를 거부하며, 위 메뉴/테이블의 cache-hit 예외를 구분해야 한다.
잘못된 메서드의 거부 순서(CSRF403 또는 메서드405)도 계약 테스트 대상이다.

관리자는 PIN 역할과 별도인 Django 활성 staff + 모델별 view/add/change/delete 권한을 쓴다.
OrderItem은 독립 등록이 아닌 Order 인라인이며, 등록 모델은 Table/MenuItem/Order/User/Group이다.
[관리자 등록](../../orders/admin.py#L16). 기본 Django5.2.17 admin 소스를 읽어 아래 경계를 확인했으며,
관리자 폼을 실제 브라우저로 모두 제출한 것은 아니다.

| 관리자 경로군 | 메서드/인가 |
| --- | --- |
| `/admin/login/` | 공개 로그인 폼; GET/HEAD/POST/PUT/OPTIONS, CSRF |
| `/admin/logout/` | POST 로그아웃/OPTIONS; 인증 staff GET405 |
| `/admin/`, `/admin/{orders,auth}/` | staff, 앱/모델 목록은 부여된 권한에 따라 노출 |
| `/admin/password_change/` 및 `done/` | 본인 비밀번호 검증; done은 GET/HEAD/OPTIONS |
| `/admin/jsi18n/`, `/admin/autocomplete/` | staff; autocomplete는 대상 view/change; GET/HEAD/OPTIONS |
| `/admin/r/<content_type>/<id>/` | staff 대상 객체 URL 이동 |
| `/admin/<app>/<model>/` · `add/` | 목록 view/change, 추가 add; 실제 저장/action POST에 해당 권한 |
| `/admin/<app>/<model>/<id>/change/` | 조회 view/change; POST change |
| `.../<id>/delete/` · `history/` | 삭제 및 관련 객체 권한, 이력 view/change; 실제 삭제 POST |
| `/admin/auth/user/<id>/password/` | change_user, POST 변경 |

목표 매트릭스에는 API 객체/항목 mode 범위, 통계 노출, 메뉴/테이블 읽기 허용 여부, 관리자
수정 정책까지 포함해야 한다. 인증 추가 시 cache-hit가 검사를 우회하지 않는지도 검증한다.

## 마이그레이션·번호 부여·데이터 제약

| 구간 | 코드가 하는 일 | 검증과 제한 |
| --- | --- | --- |
| 0001~0009 | 메뉴/테이블/픽업 구조와 가시성/주문 필드 변천 | 빈SQLite/PG 체인 통과; 당시 행 보존은 별도 |
| 0010~0011 | 날짜 rename 및 번호·층·수납 등 삭제/새 필드·카운터/제약 변경 | 과거 값 복원 출처 미확인(BK-R031) |
| 0013~0014 | CANCELLED, prepared_qty, service_mode | API와 DB 사이 상태/수량 invariant가 완전하지 않음 |
| 0015~0016 | 카테고리/인덱스 정리·조건부 인덱스 생성 | 카테고리값은 역방향 스키마만으로 복구 불가 |
| 0017 | null 허용 분할 수납 열 추가, 데이터 backfill 없음 | 상세 fallback/aggregate 차이 재현 |
| 0018~0019 | choices 축소 후 B1+table 강제 | 합성 레거시/역방향 모두 PG 제약 실패 |
| 0020 | B1 sequence 생성 후 MAX번호로 setval(...,true) | 빈PG 실패; 양수MAX40 경로 성공 |

주요 현재 DB 방어는 Table.number 유일성, 주문의 B1+유효 type+non-null table CHECK,
조건부 `(floor,order_date,order_no)` UNIQUE, 양수 계열 필드의 비음수 제약, 외래 키 참조 무결성이다. Django ORM의 PROTECT 삭제 정책도
별도로 적용된다.
그러나 status/payment/source/service_mode의 choices는 모두 DB enum 제약으로 강제되는 것이
아니다. `prepared_qty <= qty`, 항목합계=주문합계, 수납 합계, 멱등성, 번호와 날짜의 non-null
조합도 완전한 DB 불변조건이 아니다. admin/직접 ORM writer를 포함해 검증해야 한다.

0018까지 유효한 `(B1,TAKEOUT,NULL table)`은0019에서 실패하고,0019에서 유효한 테이블 있는
TAKEOUT은 옛 제약으로 되돌릴 때 실패한다. 이 두 합성 fixture에서 migration 트랜잭션 실패 후
행은 남았다. 이를 운영 데이터가 이미 안전하다거나 모든 역방향 복구가 가능하다는 증거로
확대하지 않는다. D-008/D-017 없이 슬롯을 임의 배정하거나 과거 파일을 고쳐서는 안 된다.

PG 시퀀스는 날짜와 독립적이다. SQLite 카운터는 날짜별 키를 사용한다. 시퀀스 충돌 시
현재 생성의 outer atomic 안에서 예외를 잡고 다시 질의하므로 트랜잭션이 깨진 채 재시도한다.
정상 경합16건의 번호 고유성·실패 후 부모0행은 보존할 긍정 근거다. PG `nextval` 값은 롤백으로
돌아오지 않으므로 공백 없는 번호를 약속해서는 안 된다.
[PostgreSQL 공식 시퀀스 의미](https://www.postgresql.org/docs/current/functions-sequence.html).

블루프린트1은0020뿐 아니라0019 호환성·과거 적용 인벤토리를 다뤄야 한다. 0021만 추가하는
수정은 빈DB의0020 실패를 통과시키지 못한다. 신규 설치와 이미 적용된 데이터베이스를 분리한
복구 전략, 구 애플리케이션/새 스키마·새 쓰기 호환 시험, 백업 복원 또는 전진 수정 계획이 필요하다.

## 성능·실시간·프런트엔드 근거

목록에는 select_related(table)와 items/menu 사전 로딩이 있다. **이번 측정에서 목록 N+1은
발견하지 않았다.** 다음은 메모리 SQLite, ASCII 메뉴·테이블명, 주문당1항목, Django Client의
CaptureQueriesContext와 len(response.content) 결과다. 시간·처리량 benchmark는 아니다.

| 조회 workload | SQL수 | 원본 JSON bytes | 해석 |
| --- | --- | --- | --- |
| 목록 limit1 | 3 | 684 | 포장1건 |
| 목록 limit80 | 3 | 52,746 | 포장80건, 이전 홀 누락 |
| 목록 limit200(실제81건) | 3 | 53,410 | 홀1+포장80 |
| 단건 | 3 | 662 | 홀1건 |
| 주방 요약 | 1 | 72 | 81건 fixture |
| 메뉴 판매 집계 | 1 | 67 | 같은 fixture |
| 메뉴 cache clear후/반복 | 1 / 0 | 79 / 79 | response cache60초, 프로세스 로컬 기본 backend |
| dashboard | 2 후 실패 | 145(오류 HTML) | 성공 payload/latency 기준으로 사용 불가 |

인덱스는 floor/type/created_at, status/created_at, order_date, OrderItem(order,menu)/(order,id)
등이 있다. 실제 SQL 실행 계획 없이 추가 인덱스의 효과를 판단하지 않는다. DB 히스토리가 커지면
집계·정렬·payload 크기와 브라우저 전체 렌더 비용을 별도로 측정한다.

주방은5초poll, 목록 요청끼리 isLoading으로 중첩 방지, ID별120ms 이벤트 대기를 구현했다.
Supabase가 없거나 초기2초 이내 구독하지 못하면 폴링이 시작된다. SUBSCRIBED 이후 poll이
멈추지만 오류/종료에서 복귀시키지 않고, 재구독·탭 복귀 때 전체 재동기화도 없다.
loadOrders는 저장소 전체를 교체하고 단건은 버전 비교 없이 덮어쓴다. 120ms Set은 요청 전에
비워지므로 진행 중 단건 요청을 합치지 못한다. 서브에이전트의 콜백·역순응답 모의 검사도 이
코드 경로를 뒷받침했으나 실제 SDK·브라우저 네트워크 재현으로 표시하지 않았다.
[주방 요청 적용](../../orders/templates/orders/kitchen_supervisor.html#L261),
[연결 처리](../../orders/templates/orders/kitchen_supervisor.html#L426).

D-007 합의 전의 **제안 workload**는 화면1/5/20대, 대기20/80/201건, 주문당1/5/20항목,
메뉴20/100/500개, 이력1천/10만건, 워커1/4개다. 정상·순간폭주·같은 메뉴 집중 주문·응답 유실·
60초 네트워크 단절·재연결·탭 복귀를 구분한다. PG EXPLAIN(ANALYZE,BUFFERS)은 일회용 fixture에서만
실행하고 SQL수/DB시간/잠금대기, HTTP p50/p95/p99, 오류율, payload 원본/압축,
JS render시간, 이벤트→표시 지연, 누락·중복 여부를 기록한다. 현재 SLO 수치는 없으며 통과 기준을
임의로 만들지 않는다. 목표가 확정된 뒤 동일 workload의 변경 전후와 정확성을 비교한다.

화면당5초poll은 분당12회, 측정된80건 JSON이면 약633KB/분/화면(헤더·압축 제외)라는 산술
계산이다. 실측 운영 트래픽으로 쓰지 않는다. 이벤트 폭주 시 단건3쿼리×화면수와 전체 보드
재렌더가 병목인지 측정해야 한다. PostgreSQL 진행 갱신의 select_for_update가 join된 order/menu
잠금에도 영향을 줄 수 있으므로 같은 메뉴를 여러 주문이 공유하는 workload도 포함한다.

| 유지보수 대상 | 분류 | 다음 검사 |
| --- | --- | --- |
| order/kitchen_supervisor/b1_counter/login | 활성 템플릿, 인라인 JS/CSS·역할 흐름 집중 | viewport·터치/키보드·명시 label·focus·오류/재시도·CSRF 회귀 |
| styles.css | 활성 공유 자산 | 규칙별 사용 확인; 통째 미사용 판정 금지 |
| app.js | 저장소 내 import/script 참조 없음 | 외부 사용 확인 후 제거 후보 |
| serve.html | 현재 URL/page 참조 없음; tables 대신 구 응답키 기대 | 현재 UI로 복원하지 말고 사용/계약 확인 |
| role_select.html | 미참조, login_pin reverse 실패 | 활성 login.html과 구분 |
| forms_admin.py / admin/import_csv.html | 현재 admin 연결 없음 | 외부 확장·운영 사용 확인 전 삭제 금지 |
| recalc_totals | 서비스 export는 있으나 실행 호출 경로 미발견 | 관리자 자동재계산으로 오인하지 않음 |
| FloorOrderCounter | **SQLite 실행 경로에서 사용 중** | 미사용 코드 아님 |

저장 XSS는 주문/카운터의 문자열 HTML·onclick 보간 경로로 한정했다. 주방은 menu/name/note에
escapeHtml을 사용한다. 카운터 sink는 현재 dashboard500 때문에 정상 응답 경로가 막혀 있다.
실기기 지원, 터치 타깃·대비·스크린리더 결과, CSP·CDN 장애는 미검증이며 UI 프레임워크 교체 전에
활성 URL과 핵심 여정을 먼저 특성화한다.

<a id="sse-migration"></a>
## 추가 분석 — 외부 Realtime을 자체 SSE로 전환

**사용자가 지정한 방향은 브라우저의 외부 Realtime 연결을 없애고 자체 SSE로 전달하는 것이다.**
이 방향은 D-018에 accepted로 기록한다. 아래 상세 설계는 proposed이며 코드 구현·인프라 변경
승인은 아니다. 최초 SSE 요청만으로는 DB 호스팅 이전을 추정하지 않았으나, 후속 D-020에서
사용자가 Compose PostgreSQL 자체 운영을 지정했다. 현재 목표는 아래 [인프라 이전 절](#infrastructure-migration)을
함께 따른다. EC2 여부·버전·토폴로지 상세는 D-006/021/022에 남는다.

권고 구성은 **동일 출처 EventSource + Django 비동기 스트림 + PostgreSQL의 영속 변경 버전 +
권한이 적용된 전체 상태 재조회**다. SSE에는 화면을 다시 읽어야 한다는 작은 알림을 보내고,
주문·결제·준비량 변경은 기존 HTTP 명령 경로를 유지한다. 외부 메시지 SaaS나 Redis/Channels를
필수 구성으로 추가하지 않는다. SSE는 서버→브라우저 전송 방식이며 DB 변경 감지·권한·복구를
자동으로 제공하지 않는다. 모든 중간 이벤트의 재생보다 **현재 대기 작업의 정확한 복원**을
첫 목표로 제안한다. 소리 알림·감사 기록 등 모든 전이의 재생이 필요하면 D-019에서 별도 선택한다.

### 실제 교체 범위와 기존 기능 보존

| 현재 코드 근거 | SSE 전환 시 처리할 범위 |
| --- | --- |
| [주방82~85](../../orders/templates/orders/kitchen_supervisor.html#L82) | Supabase CDN script·URL·anon key의 브라우저 전달 제거 |
| [주방439~463](../../orders/templates/orders/kitchen_supervisor.html#L439) | createClient/channel/postgres_changes를 자체 EventSource 연결 관리로 대체 |
| [주방261~330](../../orders/templates/orders/kitchen_supervisor.html#L261) | Map/렌더 모델은 보존 가능하나 목록·단건 역전 방지와 버전별 snapshot 적용을 먼저 고정 |
| [주방333~375](../../orders/templates/orders/kitchen_supervisor.html#L333) | 취소·품목 PATCH는 HTTP로 유지, 성공 후 즉시 재조회; SSE 도착을 쓰기 성공 조건으로 삼지 않음 |
| [주방426~486](../../orders/templates/orders/kitchen_supervisor.html#L426) | 폴링·재접속·탭 복귀·종료 처리를 한 연결 상태 모델로 합침 |
| [pages8~45](../../orders/views/pages.py#L8) | _supabase_context 주입 제거 대상. 다만 ORDER/카운터는 현재 실제 Supabase 구독이 없음 |
| [order125~141](../../orders/templates/orders/order.html#L125), [counter97~105](../../orders/templates/orders/b1_counter.html#L97) | 기존 JSON fetch 유지. 카운터는 자동 실시간 구독 화면이 아니므로 새 자동갱신은 별도 제품 범위 |
| [settings92~94](../../bazaar_kiosk/settings.py#L92), [.env.example15~16](../../.env.example#L15) | Realtime 전용 환경 변수의 런타임 의존 제거·설정 문서 정리; DATABASE_URL은 별도 |
| [urls22~31](../../orders/urls.py#L22) | 인증된 이벤트 GET 경로 추가 제안: `/orders/api/events/`; 아직 존재하지 않는 제안 URL |

BK-R018/R029는 제거 계획만으로 종료하지 않는다. 새 브라우저 네트워크 기록에서 Supabase/CDN
요청이 없고, 페이지 소스에 Realtime 키가 없으며, 필요한 외부 구독·노출 설정의 정리 여부까지
담당자가 확인해야 한다. 외부 권한/설정 변경은 별도 승인 작업이다. 롤백은 **안전한 자체 API
폴링**으로 제한하고 외부 SDK나 취약한 익명 API를 다시 켜지 않는다.

### 데이터 변경 감지와 여러 워커의 전달

```text
권한·CSRF 검증된 HTTP 명령 / 승인된 관리자 변경
  → 짧은 DB 트랜잭션 {주문·항목 변경 + 영향받는 화면 범위의 revision 증가}
  → PostgreSQL 커밋
  → 각 ASGI 워커의 단일 허브가 영속 revision 확인
  → 해당 워커에 연결된 권한 있는 브라우저에 SSE invalidate
  → 브라우저가 권한 필터·revision을 포함한 현재 상태 snapshot 재조회
```

프로세스 로컬 허브는 연결 분배만 담당한다. 공유 진실은 DB에 있어야 다른 워커·재시작에서도
변경을 발견한다. 최초안은 워커당 하나의 관리된 task가 활성 범위의 revision을 짧은 질의로
확인하는 방식이다. 초기 비교값은1초 간격이며 운영 SLO가 아니다. 연결당 DB 폴링이나 DB 연결을
유지하지 않는다. 허브는 worker 시작/종료·reload·예외복구에 정확히 하나만 살아야 하며
`AppConfig.ready()`나 import 시점에 무조건 task를 생성하지 않는다.

| 선택지 | 장점 | 한계·판단 |
| --- | --- | --- |
| 메모리 queue 또는 on_commit 호출만 | 구현이 짧음 | 커밋 후 프로세스 종료, 다른 워커·재시작에서 누락. 정확성의 유일 근거로 채택하지 않음 |
| **DB revision + 워커별 공유 확인 + snapshot** | 별도 broker 없이 현재 상태 복구, 알림 합치기 가능 | writer 전체 연동·revision 잠금·추가 DB 읽기 필요. 현 범위의 우선 제안 |
| DB revision + LISTEN/NOTIFY 힌트 | 같은 DB로 깨우기 지연 감소 가능 | 연결 상실 시 영속 재생 없음. 주기적 revision 확인을 유지하고 운영 pool 지원을 확인 |
| 트랜잭션 outbox + 전달 담당 + SSE | 이벤트 보존·재생·감사 요구에 적합 | 보관/정리/전달확인·순서/중복 정책이 추가됨. 모든 전이 재생이 필요할 때 선택 |
| 자체 Redis/별도 broker | 큰 fan-out을 분리할 여지 | 추가 운영 요소; 현재 요구와 측정만으로 필수라고 볼 근거 없음 |

revision은 자동증가 sequence를 그대로 가져온 이벤트 ID가 아니다. 같은 범위의 revision 행을
writer 트랜잭션 안에서 갱신해 잠금/커밋 경계를 맞추고, 다중 범위는 일정한 순서로 잠근다.
예를 들어 outbox ID10을 받은 거래가 지연되고 ID11 거래가 먼저 커밋하면 단순히11 이후만
읽는 consumer는 나중에 커밋된10을 놓칠 수 있다. `updated_at > 마지막시각` 역시 현재
QuerySet.update·OrderItem 변경·삭제·동일 timestamp를 완전하게 잡지 못한다.

영속 버전 증가 실패는 함께 롤백해야 한다. `on_commit`은 즉시 깨우기의 보조 수단만 가능하다.
[생성 bulk_create/update](../../orders/views/api.py#L303),
[상태/항목 writer](../../orders/views/api.py#L346),
[관리자 인라인](../../orders/admin.py#L45),
[번호 update](../../orders/services/numbering.py#L35)까지 누락 없이 연결한다. post_save만 붙이면
bulk_create/QuerySet.update를 놓친다. 메뉴명·테이블명 변경도 화면 표시가 바뀌므로 invalidate
대상이다. 삭제, 취소, 모드 이동은 **변경 전 범위와 변경 후 범위** 모두 갱신해 이전 화면에서도
카드가 사라지도록 한다. 알림에는 필요 없는 금전·PIN·메모·전체 DB 행을 넣지 않는다.

대상 writer가 Django 밖의 SQL/운영 도구까지 포함되면 서비스 호출만으로 충분하지 않다.
D-008/D-019에서 외부 쓰기 금지 또는 DB trigger로 커버할 범위를 정한다. trigger도 migration,
성능·경합·롤백 검증이 필요한 별도 선택이다. writer 연동의 두 선택지는 다음과 같다. 아직 어느 쪽도 승인·구현하지 않았다.

- 명령서비스에서 범위별 revision을 같은 거래 안에 갱신: 영향 범위를 제한하기 쉽지만 관리자·
  bulk/update와 모든 외부 writer의 우회 금지/연동을 증명해야 한다.
- Order·OrderItem·MenuItem·Table에 DB trigger: `AFTER STATEMENT`로 전역 revision을
  갱신하는 최소 후보는 ORM과 외부 SQL 변경을 함께 잡는다. 한 거래에서 여러 번 증가하거나
  0행 변경 문장에서 증가해도 revision을 이벤트 개수로 해석하지 않으면 된다.
  [PG trigger 의미](https://www.postgresql.org/docs/15/sql-createtrigger.html).
  TRUNCATE·trigger 비활성화·복원은 일반 DML과 다르므로 허용 범위와 generation 교체가 필요하다.

revision 행은 migration에서 만들고 누락 시 UPDATE 0건을 성공으로 간주하지 않는다. 전역 행은
구현을 단순하게 하지만 모든 쓰기를 직렬화하고 변경 빈도를 다른 승인 범위에 노출할 수 있다.
범위별 행은 old/new 범위 합집합과 메뉴·테이블의 여러 주문 영향까지 계산해야 한다. 외부 정보
노출 허용 여부는 D-003, 서비스/trigger·전역/범위별 선택과 SQLite 개발 경로는 D-019에 남긴다.

**revision 행의 잠금은 거래 종료까지 유지된다.** 여러 revision 행끼리의 정렬만으로는 충분하지
않다. 생성은 이른 INSERT의 trigger에서 revision을 잠근 뒤 항목/FK에 접근할 수 있고,
[진행 처리](../../orders/views/api.py#L391)는 먼저 주문·항목·메뉴를 잠근다. 반대 순서로 두 자원을
기다리는 새 교착 시나리오를 BK-R040에 등록한다. 전체 도메인 행과 revision의 잠금 순서를
통일하거나 멱등한 전체 명령의 제한된 재시도를 검증해야 한다. 깨진 atomic 안에서 일부만 재시도하는
기존 번호 복구 방식을 복제하지 않는다. trigger 추가만으로 전달과 쓰기 가용성이 입증되지는 않는다.

NOTIFY는 트랜잭션 커밋 후 전달되며 현재 LISTEN 세션에 알리는 기능이다. 영속 변경 로그를
대신하지 않는다. LISTEN 등록을 커밋한 뒤 DB 상태를 읽어 초기 경합을 줄이고 재연결 때도
revision을 다시 확인한다. [NOTIFY](https://www.postgresql.org/docs/current/sql-notify.html),
[LISTEN](https://www.postgresql.org/docs/current/sql-listen.html).
LISTEN 옵션은 전용 세션 또는 session pooling이 필요하다. PgBouncer transaction pooling에서는
LISTEN이 지원되지 않지만 일반 revision 질의안은 이 전제에 의존하지 않는다.
[PgBouncer 기능표](https://www.pgbouncer.org/features.html).

### 이벤트·인증·연결 수명 계약 제안

| 항목 | 제안 계약 |
| --- | --- |
| 경로/전송 | 동일 출처 GET `/orders/api/events/`, UTF-8 `text/event-stream`; POST/PATCH 명령은 별도 |
| 인증 | Django 세션 쿠키, 서버가 계산한 역할/객체 범위. URL의 role/scope/커서는 권한 증거가 아님 |
| 응답 전 거부 | 비인증401·잘못된 역할403, 이벤트 본문 미노출. SSE에서 로그인 HTML로302하지 않음 |
| 세션 수명 | 구독 시작뿐 아니라 주기적으로 저장소의 만료/폐기·권한 버전을 다시 확인; 허용 지연 D-010 확정 |
| 인증 회수 | 서버가 권한 상실 시 발행을 중단하고 연결 종료. 클라이언트도 로그인/역할변경 시 close 후 새 연결 |
| 데이터 최소화 | `invalidate`는 버전과 승인된 화면 범위만, 상세 데이터는 별도 권한이 적용된 snapshot에서 읽음 |
| 준비/복구 | `hello`에 현재 generation/revision; 불명확 커서·복원·범위 변경은 `reset`으로 전체 재조회 |
| cursor | 서버 검증 가능한 bounded opaque ID, 프로토콜/범위/generation 포함; 오류·너무 큰 값은 reset 또는 명시4xx |
| heartbeat | 예시15초 주기(미승인), 실제 idle timeout보다 짧게 결정. JS 감지가 필요하면 named heartbeat를 보냄 |
| retry | native EventSource 재연결을 사용하고 별도 연결 생성 루프와 중복시키지 않음; 앱 차원의 재생성은 한 담당자가 제어 |
| cache/proxy | cache 금지·개인화 경계 유지, 중간 buffering/압축으로 프레임이 묶이지 않는지 실측 |
| 과부하 | 연결 수·사용자당 연결·프레임 크기·버퍼 상한, 느린 소비자는 invalidate 합치기 또는 reset/종료 |

다음은 합성 프로토콜 예시이며 최종 API 승인이 아니다. heartbeat는 데이터 cursor를 전진시키지 않는다.

```text
id: v1-kitchen-demo-42
event: invalidate
data: {"revision":42}

: keepalive

event: heartbeat
data: {"ok":true}

```

SSE의 프레임은 빈 줄로 끝나고 native EventSource는 재연결 때 Last-Event-ID를 전달한다.
이 값은 브라우저가 받은 이벤트 ID이며 **화면 적용 완료 확인이 아니다**. 새 EventSource 객체를
만들면 이전 객체의 커서를 자동 승계한다고 가정하지 않는다. `: comment`는 JS 이벤트를
발생시키지 않는다. 의도적인 재접속 중지는 HTTP204로 표현할 수 있지만 일반 장애나 인증 실패를
무조건204로 감추지 않는다. [WHATWG SSE 표준](https://html.spec.whatwg.org/multipage/server-sent-events.html).
기본 EventSource는 임의 Authorization 헤더를 설정하는 인터페이스가 없으므로 현재 앱에는
같은 출처 세션 방식이 맞는다. 장기 토큰/PIN을 URL에 넣지 않는다. 상태 변경에는 CSRF를 유지한다.
native EventSource의 error 콜백은 HTTP 상태를 직접 제공하지 않으므로 401/403을 JS에서 곧바로
읽는 설계를 피한다. 오류 시 제한된 동일 출처 상태/snapshot fetch로 인증 거부와 통신 장애를
구분하고, 인증 거부가 확인되면 연결·폴링을 종료하고 재로그인을 안내한다. 새 진단 경로가
필요한지는 API 계약 단계에서 정한다. 네트워크 오류만으로 로그아웃 처리하지 않는다.
연결의 CONNECTING은 native 재시도에 맡기고, 비200 응답 등으로 CLOSED가 되면 영구적으로
native 재시도를 기다리지 않는다. 인증이 유효한 일시 장애는 backoff를 둔 앱 재생성으로 처리한다.
이때 이전 객체를 close하고 연결 소유권 토큰을 바꿔 이전 timer/error 콜백이 새 연결을 만들지 못하게 한다.
이미 시작한 스트림의 HTTP 상태는401로 바꿀 수 없으므로 발행 중단·연결 종료 후 상태를 확인한다.

현재 [require_roles](../../orders/views/auth.py#L55)는 동기 wrapper와 요청에 캐시된 session.role을
사용한다. 이를 async 스트림에 그대로 붙이거나 연결 내내 최초 권한만 신뢰하지 않는다.
동기/비동기 모두 인식하는 인가 경계와 PIN 회수에 연동된 세션 폐기 계약이 선행해야 한다.
인가되지 않은 범위의 이벤트 ID·발생 시각만 유출되는 것도 D-003의 정보 노출 정책에 포함한다.
설치 Django의 session.aget도 객체 내부 캐시를 사용하므로 호출 반복을 재인증으로 간주하지
않는다. 원래 세션 키로 저장소를 새로 읽어 삭제·만료·역할·권한 버전을 확인한다. 역할이
바뀌면 기존 범위의 구독과 대기 큐를 폐기한다. 저장소 조회 실패 시에도 마지막 확인 뒤 허용된
시간을 넘어 발행하지 않도록 D-010에서 상한을 정한다. 승인 범위 밖의 변경만 발생한 경우
hello/reset/invalidate의 버전·시각이 노출되는지도 검사한다. opaque ID만으로 시각 노출은 사라지지 않는다.

### 최초 로드·재접속·늦은 응답 복구

1. 인증 후 연결을 열고 허브의 현재 revision을 확인한다. 모든 open/reopen에서 전체 snapshot
   재조정을 수행하며 Last-Event-ID가 같아도 이전 HTTP 재조회 실패 가능성을 고려한다.
2. snapshot에는 데이터와 같은 짧은 DB snapshot의 revision을 포함한다. PostgreSQL의 짧은
   REPEATABLE READ 읽기 거래 또는 전후 버전 확인과 제한된 재시도 방식을 비교한다.
   READ COMMITTED의 여러 prefetch 질의가 자동으로 같은 snapshot인 것으로 간주하지 않는다.
   [PG 격리 수준](https://www.postgresql.org/docs/15/transaction-iso.html). 직렬화에 필요한 지연 조회도
   거래 안에서 끝내고 이전 캐시 데이터에 새 revision을 붙이지 않는다.
3. 전체 대기 작업이 복구되어야 한다. 기존 limit80을 그대로 사용하는 전체 재조회는 복구가 아니다.
   페이지네이션이면 페이지들을 같은 일관성/버전 계약으로 모으거나 다시 시작한다.
4. 조회 중 도착한 변경은 최대 revision과 dirty 플래그로 남긴다. 화면에 성공적으로 적용한 뒤
   appliedRevision을 기록한다. 스트림 cursor만 높아졌다고 미적용 데이터를 버리지 않는다.
5. 현재 세대보다 오래된 HTTP 응답은 무시한다. 진행 PATCH의 즉시 재조회와 SSE 재조회도 한
   scheduler에서 합친다. 같은 인증·범위·generation에서도 응답 revision이 appliedRevision보다
   작으면 버린다. READY/CANCELLED/삭제는 새 snapshot에 없으면 기존 카드에서 제거한다.
6. 일반 단절·idle·서버 restart에서는 기존 화면에 '연결 끊김/갱신 시각'을 표시하고 인증된 API
   폴링으로 전환한다. 확인된 인증·권한 상실은 별도 종료 상태로 처리하여 스트림·폴링·재시도·
   진행 중 조회와 민감한 화면을 정리한다. 인증 세대를 바꾸어 이전 역할의 늦은 응답도 무시한다.
   동시에 둘 이상의 폴링 타이머·EventSource를 만들지 않는다.
7. DB 복원으로 revision이 작아지거나 범위·프로토콜이 바뀌면 generation을 바꾸고 reset한다.
   replica 지연으로 이전 상태가 섞이지 않도록 최초안의 revision/snapshot 읽기는 같은 primary를 쓴다.

새 구독자 등록과 허브 head 확인 사이에 변경이 발생하는 경우도 인수 검사에 넣는다. 허브가
관찰한 revision, 브라우저가 받은 revision, 화면에 적용한 snapshot revision을 구분한다.

연결 수명은 보이는 주방 문서당 EventSource 하나를 제안한다. 숨김 탭에서는 스트림과 폴링을
정리하고, 복귀 시 재연결·snapshot을 수행한다. pagehide/pageshow와 BFCache 복원도 처리한다.
배경 알림이 제품 요구이면 이 정책을 D-007/010에서 바꾼다. 연결 open만으로 정상 복구라 표시하거나
폴링을 중지하지 않는다. 현재 인증·범위·generation의 head까지 완전한 snapshot을 적용하고
변경 감지 허브가 정상적으로 DB 상태를 확인한 뒤 정상 상태로 전환한다. heartbeat만 살아 있고
허브의 revision 읽기는 실패하는 상태를 복구 완료로 표시하지 않는다. 마지막 DB 확인 시각·
허브 오류를 계측하고 실패 상태를 클라이언트에 전달하거나 스트림을 종료한다. JS idle 감지를
선택하면 named heartbeat를 계약에 포함해야 하며 comment만으로 대체할 수 없다.

기존 단건 조회를 살리는 주문ID 알림안도 가능하지만 삭제·이전 범위·응답 버전·전체 reset을
추가해야 한다. 초기 revision/snapshot안은 복구 계약을 단순하게 하는 대신 조회량이 늘 수 있다.
측정 후 ID별 힌트를 추가해도 전체 재조정 경로는 유지한다.

이 최초안은 이벤트마다 정확히 한 번 처리하는 전달 보장이 아니라, 중복·합쳐진 알림을 견디면서
현재 상태로 수렴하는 계약이다. 모든 중간 상태·소리 알림·감사 이벤트가 필요하면 outbox와
소비/재생 기준을 별도로 설계한다. 이 차이는 D-019의 결정 관문이다.

### ASGI·미들웨어·운영 배포의 실제 전제

E-SSE-STATIC에서 설치된 Gunicorn26.2.0은 기본 worker가 `sync`지만 **내장 asgi worker를
실제로 import할 수 있음**을 확인했다. Uvicorn/Channels가 반드시 새로 필요하다고 결론 내리지
않는다. 반면 `gunicorn>=22.0` 범위만으로 같은 worker가 항상 제공되는 것은 아니므로 D-006에서
지원 버전·실행 모드를 고정해야 한다. 저장소에 asgi.py가 있다는 사실도 ASGI 배포 증거가 아니다.

미들웨어8개 중 설치된 WhiteNoise6.10.0의 `WhiteNoiseMiddleware`는 `async_capable=False`,
나머지 Django 미들웨어7개는 True로 관찰됐다. 해당 파일과 기본 worker는 설치 코드의 사실이고
현재 운영 서버의 측정값은 아니다. SSE 경로를 완전한 비동기 stack으로 만들려면 정적 파일
전달 경계와 이 동기 미들웨어를 검토하되 인증·세션·CSRF 미들웨어를 임의로 제거하지 않는다.

Django5.2의 비동기 StreamingHttpResponse는 SSE에 사용 가능하지만 WSGI 스트리밍은 worker를
점유한다. 비동기 경로 안의 동기 middleware/ORM 호출도 이점을 줄일 수 있다. DB 거래는 짧은
동기 함수로 묶어 필요한 async adapter를 사용하고 **스트림 수명 동안 DB 거래/행 잠금을 열어
두지 않는다**. disconnect의 CancelledError에서 queue·task·연결을 해제한다.
[Django StreamingHttpResponse](https://docs.djangoproject.com/en/5.2/ref/request-response/#django.http.StreamingHttpResponse),
[Django 비동기 지원](https://docs.djangoproject.com/en/5.2/topics/async/).

리버스 프록시가 Nginx라면 SSE 경로의 proxy_buffering off 또는 X-Accel-Buffering:no 적용을
검토한다. 헤더가 실제로 존중되는지는 프록시 설정에 따라 다르다. idle timeout, 최대 요청 수명,
압축·캐시, graceful reload, health/readiness를 실제 호스팅에서 확인해야 한다. HTTP/1의 동시
연결 제한과 여러 탭, HTTP/2 협상도 대상 브라우저별로 검증하며 무조건 HTTP/2라고 가정하지 않는다.
[Nginx buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering).

### 성능·인수·변경 순서

revision polling은 대략 `워커수 W / 간격 Δ` DB 질의/초가 된다(활성 범위를 한 질의로 읽는
경우). 예를 들어4워커/1초는4질의/초라는 계산일 뿐 실제 속도 증거는 아니다. 변경이 잦으면
SSE invalidate마다 snapshot을 읽어 기존5초 폴링보다 트래픽이 커질 수도 있다. snapshot 최소
간격·알림 합치기·최대 대기시간을 정하고 기존 SQL/payload 기준선과 동일 workload에서 비교한다.

필수 추가 검사는 다음과 같다. **이번에는 SSE endpoint가 없으므로 모두 구현 단계의 인수 기준**이다.

| 검증 경계 | 실패를 드러낼 구체적 사례 | 주 담당 |
| --- | --- | --- |
| writer/commit | API 생성·bulk/update·상태·진행·관리자·삭제·메뉴/테이블 변경 각각 전달, rollback은 변경 없음 | 6/7/10 |
| 워커/복구 | writer와다른워커구독,알림직전/직후kill,reload,DB단절/복원,rev reset | 10/12A |
| cursor/snapshot | 최초구독경합,ID10/11커밋역전,조회중변경,늦은응답,재조회실패후재접속,81/201건 | 8/9/10 |
| 권한 | 익명/오역할·범위위조·커서재사용,로그아웃/PIN회수/만료·역할변경·저장소오류 중 열린스트림/큐/화면 정리 | 3/4A/10 |
| 네트워크/UI | 실제프레임·프록시flush/idle·여러탭/BFCache·느린소비자,401/403/503·CLOSED/CONNECTING,허브실패중heartbeat·이전retry콜백·같은세대43→42응답 | 10/11 |
| 외부 제거 | 실제브라우저에서Supabase/CDN요청0,키노출0,자체API만으로주방전체여정 완료 | 4B/10 |
| 부하 | 화면1/5/20·워커1/4·폭주에서SQL/lock/thread/FD/RSS·p95·이벤트→화면지연·누락/중복 | 10/12A |

기존 청사진을 이번 분석에서 수정하지 않고 다음 분할을 프롬프트02에 제안한다.

| 제안 작업 단위 | 기존 단계와 선행 조건 | 종료 증거 |
| --- | --- | --- |
| 권한·조회 계약 | 3/4A/8/9, D-003/014 | 권한별 완전한 snapshot, current state/이벤트 scope 계약 |
| 영속 변경 감지 | 5/6/7의 writer 안정화 + 10, D-019 | 합성 신규/기존 DB migration·모든 writer·롤백·다중범위 잠금 |
| 자체 SSE 서버 | 10, D-006/010; async stack 최소 배포 조건을12A보다 먼저 확보 | 다른워커전달·인증회수·재접속·ASGI stream/proxy 검사 |
| 주방 클라이언트와 외부 연결 제거 | 4B/10/11의 교체 범위를 하나의 통합 담당이 조정 | SDK/키/CDN 제거, UI/역전/재연결/폴링 fallback·외부요청0 |
| 부하·릴리스 복원력 | 10/12A, D-007/016 | 측정SLO·배포reload·백업복원·실패시자체폴링 복귀 |

4B에서 아직 필요한 구독을 삭제하고10까지 화면을 깨뜨려 두는 순서를 피한다. 사전 제거가
필요하면 먼저 권한·가시성이 보장된 폴링을 제공해야 한다. 양쪽 알림을 동시에 화면에 적용하지
않고 기능 전환 경계를 명시한다. 새 스키마의 revision을 갱신하지 않는 구 버전으로 롤백할 때는
SSE를 끄고 호환되는 자체 폴링을 사용한다. 구현 담당 파일 예상은 API/인가·명령서비스·관리자·
새 forward migration·주방 템플릿·ASGI 실행/설정·CI/검사다. 이 목록은 이번 수정 허용 범위가 아니다.

### 이번 추가 분석의 검증과 한계

E-SSE-STATIC은 기존 환경에서 worker import·middleware capability를 조사하고 합성 async
StreamingHttpResponse를 직접 순회했다. 결과는 `is_async=True`, `text/event-stream`,2청크,
각 프레임의 빈 줄 종료 확인이다. 서버를 열거나 SSE URL을 추가하지 않았으며 실제 ASGI HTTP,
권한·프록시·브라우저·DB revision 경합·부하 검사를 통과했다는 뜻이 아니다. 기존 앱 기준검사는
앞선 세션 결과를 유지하고 문서만 갱신된 이번 단계에서 반복하지 않았다.

재현 명령(상속된 DATABASE_URL 제거, 메모리 DB, 외부 접속 없음):

```bash
.venv/bin/python - <<'PY_SSE'
import os, asyncio
os.environ.pop('DATABASE_URL', None)
os.environ.update(DJANGO_SETTINGS_MODULE='bazaar_kiosk.settings', DEBUG='0',
                  SECRET_KEY='analysis-only-'+'x9!aB7'*12,
                  SUPABASE_URL='', SUPABASE_ANON_KEY='')
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
import django
django.setup()
from django.utils.module_loading import import_string
from gunicorn.config import Config
from gunicorn import util
print('default worker:', Config().worker_class_str)
print('ASGI worker:', util.load_class('asgi'))
for path in settings.MIDDLEWARE:
    cls = import_string(path)
    print(path, 'async_capable=', getattr(cls, 'async_capable', False))
from django.http import StreamingHttpResponse
async def frames():
    yield 'id: probe-1\nevent: invalidate\ndata: {"revision":1}\n\n'
    yield ': heartbeat\n\n'
async def probe():
    response = StreamingHttpResponse(frames(), content_type='text/event-stream')
    chunks = [chunk async for chunk in response]
    print(response.is_async, response['Content-Type'], len(chunks),
          all(chunk.endswith(b'\n\n') for chunk in chunks))
asyncio.run(probe())
PY_SSE
```

<a id="infrastructure-migration"></a>
## 추가 분석 — Compose PostgreSQL 자체 운영과 EC2 배포 후보

**DB를 Docker Compose의 PostgreSQL로 이전한다는 방향은 사용자 결정 D-020이다.**
AWS EC2는 사용자가 검토 중이라고 표현한 후보이므로 D-021 proposed로 기록한다. EC2 구매,
리전·사양·단일 서버 확정이나 실제 이전/배포 승인은 아니다. 이전 SSE 요청에서 DB 호스팅을
추정하지 않았던 경계는 이번 후속 요청으로 확장됐다. 이번에도 지정 분석 문서5개만 갱신했다.

### 제안하는 최소 배포 구성과 적용 조건

```text
행사 브라우저 ── HTTPS / 같은 출처 SSE ── 도메인
                                            │
                          EC2 한 대의 후보 구성
                          ┌──────────────────────────────────┐
                          │ TLS reverse proxy → Django ASGI  │
                          │                         │        │
                          │ 내부 Docker network → PostgreSQL │
                          │                         │        │
                          │ 확인된 데이터 mount → 암호화 EBS │
                          └──────────────────────────────────┘
                                                    │
                           호스트 밖 암호화 백업 저장소 후보(S3 등)
```

한 서버에서 proxy/web/db를 Compose로 재현하는 구성을 **조건부 첫 후보**로 제안한다.
사용자가 지정한 필수 방향은 DB의 Compose 운영이며 웹까지 컨테이너화하는 것은 통합 제안이다.
Compose는 단일 서버 배포에 사용할 수 있다. 이 선택으로 VM·가용 영역 장애의 자동 failover가
생기지는 않는다. [Docker 운영 배포](https://docs.docker.com/compose/how-tos/production/).
앱·DB가 같이 중단될 수 있는 구성인 만큼 복원 시간과 현장 중단 허용 시간이 맞는지 D-007/016/021로
판단한다. 맞지 않으면 별도 DB 호스트나 복제/대체 호스트 설계를 비교해야 하며 자동으로 RDS·EKS·
Redis·ALB를 필수 서비스로 추가하지 않는다. PostgreSQL 유지보수·백업·보안패치 책임은 직접 맡게 된다.

| 구성 요소 | 최초 제안 | 확정 전 증거 |
| --- | --- | --- |
| 호스트 | EC2의 한 Linux VM, 리전/CPU 아키텍처/사양은 대기 | 행사망 지연·대상 이미지/psycopg 호환·동시 화면·복원 시간 |
| proxy | HTTPS 종료, 자체 정적 파일, SSE 경로 flush/timeout 관리 | 도메인·인증서 갱신·헤더/포트 경계·실제 스트리밍 |
| web | 고정 이미지의 Django ASGI, 새 버전 배포와 DB 생명주기 분리 | Gunicorn 지원 버전·WhiteNoise 동기 경계·컨테이너 중단 시 SSE 정리 |
| db | 승인한 PG major/patch·이미지 digest 고정, 내부 서비스 이름으로 접근 | 원본 버전/extension·restore·빈 DB migration·DB TLS 계약 |
| 영속 데이터 | 루트 디스크와 구분한 암호화 EBS, 실제 mount 확인 뒤 DB 시작 | 재부팅/호스트 교체·마운트 누락 시작 거부·데이터 유지 |
| 백업 | 호스트 밖 암호화 저장, 보존/접근권한·복원 담당 분리 | 새 호스트에 복원해 행·금액·번호·시간을 대조 |
| 운영 접근 | 제한된 IAM 역할과 Session Manager 후보 | agent/권한/네트워크 경로·감사·접근 회수 확인 |

AWS 리전·EC2 타입·vCPU/RAM·EBS 용량/IOPS·예산 수치는 미확정이다. 비용은 VM뿐 아니라 EBS,
snapshot/백업 보관, 전송·공인 주소·로그와 운영 시간까지 같은 조건으로 비교한다. 가격을 조회하거나
비용 절감을 입증하지 않았다. CPU burst 계열을 선택한다면 credit 고갈도 부하 검사에 포함한다.
ALB/NAT Gateway·멀티 AZ 등은 필요 조건과 비용을 확인한 뒤 비교하며 첫 구성에 암묵적으로 넣지 않는다.

### 현행 코드에서 확인한 이전 장애 요인

E-INFRA-STATIC은 추적/비무시 파일 인벤토리와 합성 settings import 검사다. 저장소에는 Dockerfile,
Compose 정의, .dockerignore, 현행 배포/백업 실행 파일이 없다. 기존 CI는 Django check/drift만
수행한다. 이 사실은 외부 서버에 운영 체계가 전혀 없다는 뜻은 아니다.
[CI](../../.github/workflows/ci.yml#L17), [현재 설정](../../bazaar_kiosk/settings.py#L69).

| 근거 | 실제 관찰 | Compose 전환 시 필요한 계약 |
| --- | --- | --- |
| [settings84~90](../../bazaar_kiosk/settings.py#L84) | DATABASE_URL 누락 시 SQLite 선택 | 운영은 URL 누락/빈 값·의도치 않은 DB engine이면 시작 거부. 빈 SQLite로 정상 기동 판정 금지 |
| [settings70~81](../../bazaar_kiosk/settings.py#L70) | URL에 옵션이 없으면 sslmode=require | DB 서버의 실제 TLS와 연결 정책 일치; TLS 미설정 PG에 그대로 연결 성공한다고 가정하지 않음 |
| 같은 parser | sslmode=disable은 전달, URL의 sslrootcert는 OPTIONS에 포함되지 않음 | 원격 DB TLS는 검증 가능한 인증서/호스트 확인 계약. URL만 붙여 CA 경로가 적용됐다고 해석 금지 |
| [env 예시](../../.env.example#L1)·settings | .env 자동 로드·DATABASE_URL_FILE 지원 없음 | Compose 변수 치환과 컨테이너 환경 전달/secret 파일 읽기 구현을 별도로 연결 |
| [settings9~18](../../bazaar_kiosk/settings.py#L9), [108~111](../../bazaar_kiosk/settings.py#L108) | 개발 기본값, HTTPS 신뢰 헤더·secure cookie 분기 | DEBUG=0·필수 SECRET/PIN·host/origin·신뢰 proxy 경계를 시작 전 검사 |
| [requirements](../../requirements.txt), [middleware37](../../bazaar_kiosk/settings.py#L37) | 열린 버전 범위, 설치 WhiteNoise는 동기 | 재현 가능한 이미지·지원 ASGI 실행 조건, 기존 SSE BK-R035 유지 |
| [0020](../../orders/migrations/0020_create_floor_sequences.py#L1) | 이전 E-PG에서 빈 DB setval(0) 실패 | PostgreSQL 컨테이너 healthy만으로 신규 앱 bootstrap 성공 판정 금지 |

Compose의 .env는 치환 입력이며 앱 환경으로 모두 자동 전달되는 파일이 아니다. 필요한 값은
environment/env_file 또는 명시적 secret 읽기로 연결하고, 필수 값 누락은 시작 전에 거부해야 한다.
[Compose 변수 치환](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).
Compose secrets는 서비스별 파일 전달을 지원하지만, 현재 Django가 `_FILE`을 자동으로 읽지는 않는다.
호스트 원본 파일·백업·로그의 보호와 교체 절차도 필요하다.
[Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

브라우저→proxy HTTPS와 web→DB TLS는 서로 다른 경계다. 같은 호스트의 제한된 내부 DB 연결에서
명시적 비TLS를 허용할지, DB TLS를 구성할지는 보안 담당이 D-006/021에서 정한다. 분석 probe의
sslmode=disable은 parser 동작 확인이며 운영 암호화 해제를 권고하거나 적용한 것이 아니다.
웹 컨테이너의 localhost는 DB 컨테이너가 아니다. 내부 서비스 이름과 DB명·앱 전용 역할을 검증한다.
URL이 존재하는데 PG 연결이 실패하면 SQLite로 자동 전환하는 코드는 없다. 누락/빈 값에 따른
engine 선택과 접속 실패를 구분한다. sslmode=require만으로 서버 호스트명 검증까지 보장하지 않으므로
인증서·호스트명 검증 정책은 별도로 시험한다.
[PG TLS 모드](https://www.postgresql.org/docs/current/libpq-ssl.html).
설치 Django의 CONN_MAX_AGE 기본값은0이며 현재 설정은 같은 이름의 환경 변수를 읽지 않는다.
이 기본값이 장기 실행 SSE 허브의 DB 연결 정리·재접속을 대신하지는 않는다.

### 외부 노출·영속 데이터·컨테이너 수명

- 노출은 proxy의 HTTPS로 모으고 DB5432와 ASGI 포트를 공인 인터페이스에 게시하지 않는 안을
  제안한다. HTTP80은 redirect/인증서 방식에 필요한 경우만 연다. proxy와 web, web과 db의 네트워크를
  나누고 proxy에는 DB 접근이 필요하지 않다. SG와 Docker의 port publishing을 함께 검증한다.
  Docker는 호스트 주소를 생략한 게시 포트를 기본적으로 모든 호스트 주소에 연다.
  [Docker 포트 게시](https://docs.docker.com/engine/network/port-publishing/),
  [EC2 security group](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html).
- HTTPS 헤더는 신뢰 proxy가 덮어쓰고 web 직접 접근을 막는다. Session Manager를 쓰면 상시
  SSH 인바운드 없이 관리할 수 있지만 agent·IAM·서비스 연결 경로가 필요하다. 앱에 관리자 AWS 키나
  Docker socket을 전달하지 않고, 백업 접근도 필요한 저장소/작업 범위로 제한한다.
  [Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).
- Docker volume은 컨테이너와 별도 수명으로 남지만 데이터는 호스트 저장소에 있다. 볼륨 자체를
  삭제하거나 호스트 저장소를 잃는 상황까지 복구하는 백업은 아니다.
  [Docker volume 수명](https://docs.docker.com/engine/storage/volumes/).
  EBS 데이터 볼륨은 암호화·삭제 정책·mount 소유권을 명시하고, 예상 장치가 실제 mount되지 않았으면
  DB 시작을 거부한다. 빈 로컬 디렉터리에 새 DB가 초기화되는 상황을 막아야 한다.
  이미 존재하는 빈 mountpoint도 거부해야 하며 Docker 자동 재시작에서 검사가 우회되지 않도록 한다.
  볼륨 삭제·EC2 종료 시 데이터 볼륨 보존·mount 설정은 별도로 관리하고 기대한 DB 식별도 확인한다.
  EBS는 인스턴스와 별도로 유지될 수 있지만 같은 AZ 제약을 고려해야 한다.
  [EBS 볼륨](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-volumes.html).
- PG 이미지 버전을 고정하고 그 버전의 PGDATA·볼륨 경로를 검사한다. 공식 이미지에서18 이상은
  PGDATA가 major별 경로이고 volume 대상이 `/var/lib/postgresql`로 바뀌었다.17 이하는 기본
  `/var/lib/postgresql/data`를 사용한다. `latest` 변경이나 volume 이름/Compose project 이름 변경이
  무심코 신규 DB 초기화·업그레이드로 이어지지 않도록 고정한다. 기존 데이터에는 초기화 환경 변수가
  다시 적용되지 않으므로 POSTGRES_PASSWORD 값 변경만으로 기존 비밀번호가 바뀌지 않는다.
  [PostgreSQL 공식 이미지](https://raw.githubusercontent.com/docker-library/docs/master/postgres/README.md).
- 일상적인 앱 재배포에서 DB를 재초기화하거나 `down -v`·volume prune을 실행하지 않는다.
  initdb 스크립트는 최초 빈 데이터 디렉터리 초기화와 역할 생성용이며 기존 DB의 Django migration을
  매번 처리하는 수단으로 삼지 않는다. 앱 실행 역할과 schema migration/backup 역할을 분리하고
  운영 DB에 trust 인증을 사용하지 않는다. 이전 로컬 일회용 DB의 trust/tmpfs는 운영 예제가 아니다.
- DB healthcheck와 `depends_on: service_healthy`는 시작 순서를 돕는다. pg_isready 성공은 앱
  역할 권한·schema·0020·데이터 복원 성공을 증명하지 않으며 실행 중 DB 장애도 해결하지 않는다.
  migration은 한 번 실행하는 별도 단계에서 성공을 확인한 뒤 앱 트래픽을 연다.
  [Compose 시작 순서](https://docs.docker.com/compose/how-tos/startup-order/).

### 데이터 이전·검증·쓰기 전환 순서

원본이 실제로 Supabase인지, 사용 중인 PG 버전·extension·운영 schema가 무엇인지는 미확인이다.
앱 소스에 외부 Auth/Storage 호출이 없다는 사실만으로 DB 안의 관련 객체까지 없다고 가정하지 않는다.
원본·대상 계정 접근과 실제 dump/복원은 이후 승인된 이전 작업에서 수행한다.
원본 엔진이 SQLite로 확인되면 아래 pg_dump 경로를 사용할 수 없으므로 PK/FK·타입·시간·sequence를
보존하는 별도 이행 경로를 먼저 설계한다. Supabase 원본이라도 일반 PG 컨테이너에 DB를 복원하는
것은 Supabase 전체 서비스를 self-host하는 것과 다르다. Storage 파일 본문·외부 함수 배포 등은
DB 덤프만으로 옮겨지지 않으며 실제 사용 여부를 조사해야 한다.
[Supabase 복원 범위](https://supabase.com/docs/guides/self-hosting/restore-from-platform).

1. 원본 DB와 writer를 조사한다. 버전·collation/encoding·시간대, 적용 django_migrations,
   테이블/행·제약/FK·번호 sequence·함수/trigger/view·권한/RLS·extension·publication/subscription을
   기록한다. Supabase 관리 객체와 앱이 의존하는 객체를 구분하고 보존·변환·제외 목록을 검토한다.
   외부 플랫폼을 통째 복제하거나 필요한 의존을 추측으로 삭제하지 않는다.
2. 대상 PG major/이미지와 pg_dump/pg_restore 조합을 고정한다. pg_dump는 자신보다 새 major
   서버를 덤프하지 못하며 이전 major로의 restore는 일반적으로 보장되지 않는다. role/tablespace 같은
   클러스터 전역 객체는 DB dump 하나로 모두 이전되지 않는다. 필요한 앱 역할/소유권을 별도 매핑한다.
   [pg_dump 호환성·범위](https://www.postgresql.org/docs/current/app-pgdump.html).
3. 격리된 새 대상에 정제 복사본으로 예행 연습한다. **빈 DB→migration 체인**과 **기존 schema+
   데이터+django_migrations 복원→남은 migration**은 다른 경로다. 전자는 BK-R005/017의 복구 전략이
   선행한다.0020 적용 기록만 있고 실제 sequence가 빠진 복원을 성공으로 보지 않는다. 후자는 원본
   적용 이력·실제 schema를 함께 대조한다. `--fake`로 기록만 맞추거나 빈 DB에 임의 주문을 넣어
   선행 실패를 숨기는 방법을 표준 이전 절차로 사용하지 않는다.
   이미0020 적용된 원본의 객체/이력 복원에서는0020이 불필요하게 재실행되지 않는지 확인한다.
   최신 schema를 먼저 migrate한 뒤 data-only를 넣는 경로는 컬럼/제약/초기 행 충돌을 따로 검증해야
   하므로 기본값으로 선택하지 않는다. restore 오류 중단 정책·오류0/필수 객체 누락0을 인수 기준으로
   둔다. pg_restore는 기본적으로 오류 후 계속할 수 있고, 선택 테이블의 의존 객체를 모두 복원하지
   않는다. no-owner/no-acl만으로 RLS·함수 내부의 역할 의존이 해결되는 것도 아니다.
   [pg_restore의 오류·선택 복원](https://www.postgresql.org/docs/current/app-pgrestore.html).
4. 앱 행수·PK/FK·고유제약·nullable/레거시 결제·저장 총액/항목 합계·status/mode·메뉴/테이블,
   order_date/created_at의 Seoul 경계를 전후 대조한다. 기존 합계 오류를 이전 중 임의로 고치지
   않고 동일하게 보존됐는지와 나중에 조정할 불일치를 분리한다. PK sequence와 별도 층별 주문번호
   sequence의 이름/소유권/last_value/is_called·다음 번호 충돌을 확인한다. 검증용 쓰기는 복원용
   격리 DB에서 수행한다. sequence 증가는 단순 transaction rollback으로 되돌아간다고 가정하지 않는다.
   원본과 대상에서 전체 행을 볼 수 있는 승인된 역할로 PK 집합·NULL·날짜/결제/상태별 금액까지
   비교한다. 전체 합계만 맞거나 RLS로 일부 행만 추출된 상태는 통과가 아니다. schema 없는 층별
   sequence 이름을 사용하는 실제 앱 역할의 search_path/사용 권한도 검사하고 MAX로 무조건 재설정하지 않는다.
5. 앱과 SSE를 대상에서 검증한다. 명령/인가·세션·읽기·81/201 backlog·여러 워커·재접속·proxy,
   새 generation/reset·전체 snapshot을 확인한다. 옮긴 세션 유지 또는 강제 재로그인 정책도 명시한다.
   현재 통계는 BK-R016으로 실패하므로 이전 검증에서200/정확한 보고로 임의 통과시킬 수 없다.
   동결 전에 만든 백업에는 로그아웃으로 삭제되기 전 세션이 남아 있을 수 있다. 같은 서명 키와
   이전 쿠키로 세션이 되살아나는 경우를 가설로 시험하고, 트래픽 재개 전에 복원 세션 무효화 또는
   새 인증 세대 적용을 제안한다. DB 세션 재조회만으로 이 문제를 막았다고 보지 않는다.
   SSE generation도 복원된 과거 값을 재사용하지 않고 서비스 전체가 공유할 새 값으로 확정한다.
   워커마다 다른 값이나 단순 프로세스 재시작마다 새 값을 만드는 방식과 구분한다.
6. 허용 중단 창에서 **모든 writer를 차단**하고 진행 중 거래를 배출한 뒤 최종 일관된 export/restore·
   대조를 한다. API POST/PATCH뿐 아니라 관리자·SQL/외부 도구·배치도 포함한다. UI 숨김이나 DNS만
   바꾸어 동결한 것으로 판단하지 않는다. source는 계속 쓰기 금지로 두고 대상만 write authority가 된다.
   무중단이 꼭 필요하면 CDC/replication·sequence·DDL·전환을 별도 설계하며 dump 한 번으로 약속하지 않는다.
   세션을 보존한다면 로그인·로그아웃 writer의 동결/세션 처리도 포함한다. DATABASE_URL 변경만으로
   기존 브라우저 Supabase 구독이 새 DB를 관찰하지 않으므로 자체 SSE 또는 보호된 폴링이 전환 선행 조건이다.
7. 전환 시 old 앱·SSE 연결/재시도를 정리하고 새 DB만 바라보도록 검증한다. 신규 주문·결제·번호·
   주방 갱신·backup/alert의 smoke가 통과해야 트래픽을 연다. DB 이동과 위험한 도메인 변경을
   한 번에 합치지 않는 분할을 우선 검토한다. 원본 서비스 폐기/외부 publication 정리는 검증·보존 기간 후
   별도 승인으로 수행하고 즉시 원본을 삭제하지 않는다.

대상이 신규 쓰기를 받기 전에는 동결된 원본과 호환 앱으로 돌아가는 경로를 검증할 수 있다.
**대상에서 새 주문을 받기 시작한 뒤에는 DATABASE_URL/DNS만 되돌리면 새 주문이 사라진다.**
그 시점부터 rollback은 새 데이터를 보존하는 역방향 이전/대조가 필요하거나, 쓰기를 멈추고
정방향 복구해야 한다. 구·신 DB의 동시 쓰기를 기본 전략으로 두지 않는다. 이 관문과 허용 중단
시간·복구 시 데이터 손실 허용량은 D-016/022에서 정한다.
역이전은 새 INSERT뿐 아니라 취소/진행 UPDATE·삭제도 보존해야 한다. PG major를 올렸다면 원래
낮은 major로의 역복원이 보장되지 않으므로 새 DB와 호환되는 복구 환경 또는 정방향 복구가 필요하다.

### 백업·장애 복구·SSE 운영 인수

백업 주기·보존 기간은 목표 RPO(허용 데이터 손실 시간)와 RTO(복구 완료 시간)에서 정한다.
작은 DB의 정기 logical dump와 호스트 밖 보관을 첫 후보로 비교하고, 더 짧은 RPO가 필요하면
base backup+지속 WAL 보관/PITR을 검토한다. WAL 누락·보관 실패와 복원도 검사해야 한다.
이 계획은 백업 도구나 새 AWS 서비스를 이미 도입했다는 뜻이 아니다.
[PG 지속 WAL 보관과 PITR](https://www.postgresql.org/docs/current/continuous-archiving.html).

EBS snapshot은 요청 시 볼륨에 기록된 내용을 포함하고 앱/OS의 미기록 캐시는 포함하지 않는다.
실행 중 PG 데이터 디렉터리를 임의 복사한 결과나 snapshot 생성 성공만으로 DB 복구를 승인하지
않는다. PG 일관성·WAL·여러 볼륨을 고려한 절차로 새 호스트 복원을 재현해야 한다.
[EBS snapshot 주의사항](https://docs.aws.amazon.com/ebs/latest/userguide/ebs-creating-snapshot.html).
암호화 키와 복원 권한을 잃으면 백업이 있어도 복원할 수 없으므로 별도 운영자가 실제 복원 경로를 확인한다.
EBS snapshot 자체도 호스트 밖 백업 수단이 될 수 있다. 실행 중 snapshot이 모두 무효라는 뜻은
아니며 데이터·WAL·tablespace를 일관된 시점으로 확보하는 조건과 crash recovery를 검증해야 한다.
[PG 파일 백업 조건](https://www.postgresql.org/docs/current/backup-file.html).

호스트 장애, 디스크 부족/로그 폭증, DB 재시작, 인증서 갱신, 배포 재시작 동안 HTTP와 SSE가
함께 중단되는 상황을 시험한다. 재시작 정책은 프로세스 복구 수단이고, DB 불일치나 AZ 장애를
자동으로 해결하지 않는다. liveness와 앱 역할 DB 질의·schema readiness를 구분하고 DB 장애가
전체 컨테이너 재시작 폭풍으로 확대되지 않게 한다. 전체 DB 연결 수·app worker 메모리·PG cache/
autovacuum/backup·shared memory·디스크/WAL·TLS/SSE 연결 버퍼의 자원 경쟁을 함께 측정한다.

클라우드 배포는 행사장의 인터넷 경로에도 의존한다. 행사망이 끊기면 SSE뿐 아니라 같은 서버의
폴링·주문 저장도 실패한다. 폴링 fallback을 오프라인 주문 보장으로 설명하지 않는다. 보조 회선과
수동 주문/복구 대조 절차를 D-016에서 정하며 오프라인 DB·동기화 기능은 별도 제품 범위다.

| 인수 경계 | 승인된 구현/이전 단계에서 확보할 증거 | 연결 위험 |
| --- | --- | --- |
| 설정·부팅 | Compose config 검증, 필수 secret/URL·mount 누락 실패, 실제 DB/TLS/앱 역할 확인 | BK-R002/022/043/044 |
| 이미지·schema | 고정 아키텍처/버전으로 build, check/drift/test·fresh migration과 복원 migration 각각 | BK-R004/005/017/021/042 |
| 저장소·복원 | 컨테이너 재생성/호스트 재부팅·새 호스트 restore·키 접근·행/금액/sequence 대조와 소요 시간 | BK-R031/041/042 |
| 경계·SSE | 외부에서 DB/ASGI 접근 차단, HTTPS/세션·여러 워커/프록시/재연결·외부 Realtime 요청0 | BK-R001/018/035/038/039/044 |
| 전환·되돌림 | 모든 writer 동결, 한 DB만 쓰기, 신규 쓰기 전/후 rollback 분기·원본 보존 | BK-R003/012/017/022/042 |
| 운영·부하 | burst/backup 동시 부하·disk full·DB 단절·SSE drain·행사망 단절·경보/수동 복구 | BK-R032/040/041 |

### 청사진에 제안할 분할과 이번 검증 한계

기존12A에 컨테이너화·AWS 구축·DB 이전·백업·SSE·운영 인수를 한꺼번에 넣지 않는다.
다음 프롬프트02에서 (1) D-020/021/022와 원본 인벤토리, (2) 단계1/2의 target PG bootstrap·
컨테이너/CI 기반, (3) 단계3/4A의 운영 설정·노출 경계, (4) 단계10 전에 최소 ASGI/proxy 경로,
(5)12A의 저장소·백업/복원과 정제 데이터 이전 rehearsal, (6)12B의 인수 판정 후 별도 배포/실제
전환 승인을 분리하는 안을 검토한다. writer·DB 이전·SSE generation은 통합 책임자 한 명이 조정한다.
애플리케이션의 보안·결제·번호·통계 위험은 인프라 이전만으로 해결되지 않는다.

이번에는 설정의 합성 import5조건과 공식 문서 의미만 확인했다. Docker/Compose 실행·새 컨테이너·
이미지 build/pull·AWS API/리소스·원본 DB 접속·실제 dump/restore·네트워크/비용 측정은 하지 않았다.
현재 Compose 파일 자체가 없으므로 config/build/up이나 EC2 배포 통과를 선언하지 않는다.

E-INFRA-STATIC의 재현 코드는 아래와 같다. 설정만 import하고 DB에 연결하지 않는다.

```bash
.venv/bin/python - <<'PY_INFRA'
import json
import os
import subprocess
import sys

# Import settings only. No Django setup, DB connection, secrets file, or Docker call.
code = """
import json
from bazaar_kiosk import settings
db = settings.DATABASES['default']
print(json.dumps({'engine': db['ENGINE'], 'host': db.get('HOST'),
                  'options': db.get('OPTIONS', {}),
                  'conn_max_age_declared': 'CONN_MAX_AGE' in db}))
"""
env = os.environ.copy()
for key in ('DATABASE_URL', 'DATABASE_URL_FILE', 'PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE'):
    env.pop(key, None)
env.update(DEBUG='0', SECRET_KEY='analysis-only-synthetic-secret',
           ROLE_PINS='ORDER:synthetic-analysis-pin', SUPABASE_URL='', SUPABASE_ANON_KEY='')
cases = {
    'missing_url': {},
    'file_variable_only': {'DATABASE_URL_FILE': '/not-read-by-this-probe'},
    'default_ssl': {'DATABASE_URL': 'postgresql://analysis:synthetic@db:5432/bk_analysis'},
    'explicit_no_tls': {'DATABASE_URL': 'postgresql://analysis:synthetic@db:5432/bk_analysis?sslmode=disable'},
    'explicit_ca_option': {'DATABASE_URL': 'postgresql://analysis:synthetic@db:5432/bk_analysis?sslmode=verify-full&sslrootcert=/synthetic/ca.crt'},
}
for name, values in cases.items():
    result = subprocess.run([sys.executable, '-c', code], env={**env, **values},
                            capture_output=True, text=True, check=True)
    print(json.dumps({'case': name, **json.loads(result.stdout)}))
PY_INFRA
```

## 배포·운영과 테스트 공백 지도

CI는 Python3.12에서 설치·system check·migration drift만 실행하며 실제 migrate/test/PG/JS/
browser 검사는 없다. CI의 `DEBUG: 'True'`는 설정 코드가 오직 문자열`'1'`만 true로 보므로
실제로 DEBUG=False다. 이를 디버그 모드 검사 통과로 해석하지 않는다.
Django 요구 범위는 지원 종료5.0/5.1도 허용하지만 설치된5.2.17은5.2 LTS 계열이며 연장지원
기간은2028년4월까지다. 잠금과 지원 기준을 D-006에서 결정해야 한다.
[Django 공식 지원표](https://www.djangoproject.com/download/).

현재 healthz URL은 없으며 과거 `e76d9fb`에 존재했다. deploy workflow는 과거 삭제되었다.
소스의 Gunicorn 설치·ASGI/WSGI 파일만으로 실제 호스팅·연결풀·다중 워커·TLS·Supabase 구성은
확정할 수 없다. HTTPS redirect/HSTS는 프록시가 담당할 수도 있으나 그 증거는 없다.
SESSION/CSRF secure cookies는 DEBUG=False에서 켜지고 Django 기본 HttpOnly/SameSite/DB 세션은
유지된다. 개발 SECRET만으로 세션 위조나 원격 코드 실행을 주장하지 않는다.

| 경계 | 이번 증거 | 아직 필요한 의미 있는 테스트 | 담당 단계 |
| --- | --- | --- | --- |
| 역할/CSRF | 익명·ORDER 역할 PATCH 재현 | 전체 역할/경로/메서드, 토큰, session, cache-hit 권한 | 2,3,4A |
| XSS/외부 경계 | sink/escape/CDN/RLS 코드 분석, DEBUG 합성 노출 | 실제 저장문자열 DOM, CSP, Supabase 익명·역할 거부 | 4A,4B |
| 생성/번호 | 양DB 스모크·PG8thread·충돌·날짜 모킹 | 실제 자정·프로세스 동시성·응답유실·bounded retry | 5,6 |
| 결제/관리자 | 부족결제·단가/합계 드리프트 | 관리자 form·분할/환불/레거시 조정·overflow | 7 |
| migration/data | fresh0020/0018→0019/역방향 실패 | 운영 버전·정제복사본·이미0020 적용·구앱/새데이터 | 1,7,12A |
| 조회/보고 | cutoff·stale table·dashboard500·helper/aggregate | 정상보고정확성·동명메뉴·범위/자정·멀티워커 cache | 8 |
| Realtime/UI | 현행 소스·구문·모의응답, SSE 로컬 실행 조건 | 자체 SSE/다중 워커·세션 회수·재접속·snapshot·대상기기·외부요청0; 전환 전 SDK 노출 경계 | 10,11 |
| 성능 | SQL수·원본payload | PG계획·고부하·p95·렌더·이벤트지연·오류율 | 10 |
| 운영 복구 | 코드/워크플로 인벤토리·합성 settings5조건 | Compose/PG·EC2 후보 인수, EBS/호스트 밖 백업·restore시간·단일 writer 전환·RPO/RTO·health | 1,2,4A,12A,12B |

운영 통제 담당자가 확보할 증거는 배포명령/필수env/실제 버전·워커·DB풀, 마이그레이션 적용 목록,
백업 복원 가능성과 시간, 로그의 주문ID/요청ID/역할·오류 분류 및 자격증명 가림,
경보·장애연락·운영자 수동처리 정책이다. 소스에 없다는 이유만으로 외부 운영 체계가 전혀 없다고
판정하지 않는다. 복구 때는 인증·인가·CSRF·이스케이프를 되돌리지 않는 호환 버전이나
fail-closed 유지보수 경로가 필요하다. 이번 분석에서는 실제 배포·복원·운영 조회를 하지 않았다.

## Git 그래프·고유 작업·내용 수준 검사

모든 수치는 로컬 snapshot이며 fetch/원격설정 조회를 하지 않았다. `origin/HEAD`는 develop을
가리킨다. 현재70커밋/16merge이며, 초기68커밋에서 로컬 준비 문서2커밋이 더해졌다.
main/develop 대칭차이는 main7/develop19이고 트리는 완전히 같다. pack178.55KiB와 loose188KiB로
큰 객체 때문에 긴급하게 역사를 재작성할 이유는 발견하지 않았다.

다음 고유 수는 다른 모든 origin branch에서 도달할 수 없는 커밋 수다(심볼릭HEAD 제외).
대칭차이는 develop 전용/해당 branch 전용이다. 숫자는 고유 **콘텐츠 가치**를 의미하지 않는다.

| ref | 팁 | 대칭차이 | 타 origin에 없는 커밋 | develop과 다른 경로 수 | 비파괴 권고 |
| --- | --- | --- | --- | --- | --- |
| origin/develop | 93a841a | 0/0 | 0 | 0 | 현 기준 보존; 정식 선택 D-001 |
| origin/main | bca9e40 | 19/7 | 1 | 0 | 동일 콘텐츠, 계보 보존 |
| origin/mergefix | e5dea82 | 0/7 | 1 | 0 | 동일 트리 통합 팁, 보관 후보 |
| origin/Megesfile | 4f836dc | 1/6 | 1 | 1 | api 날짜필터가 선택기간/최신일 fallback; 보존·제품검토 |
| origin/mergebe | ac370cb | 2/5 | 1 | 1 | created_at 기준 날짜필터·시간표시 차이; 보존·제품검토 |
| origin/fix-refcator | cc86afd | 4/3 | 1 | 4 | 이전 counter/주방/URL/API 내용 검토 후 보관 후보 |
| origin/fix | c79d5b9 | 12/1 | 1 | 7 | 번호·화면·API 이전 세대; 필요 내용 확인 후 보관 후보 |
| origin/reactor | 9849690 | 10/1 | 1 | 7 | 시퀀스 이전/카운터 화면; 필요 내용 확인 후 보관 후보 |
| origin/chore/merge-main-into-develop | 8c5da31 | 27/9 | 9 | 40 | F1/BOOTH/구메뉴·pyc 포함; 고유작업 확인 전 보존 |
| origin/rlagycks-patch-1 | a77fbd6 | 41/1 | 1 | 58 | deploy workflow 삭제 팁, 이후 삭제 반영 확인; 보관 후보 |
| 로컬 chore/astra-modernization-setup | 2d5bb78 | develop 이후2 | 준비문서2 | 앱 차이0 | AGENTS/분석문서가 있는 작업 체크포인트 유지 |

오래된 chore branch 고유9개: `8c5da31,98f8287,bb252fc,d2b22d3,94367bb,85224d9,0a32092,e49c211,f79df28`.
다른 오래된 branch의 타-origin 고유1개는 표의 각 팁이다. 그래프상의 미도달을 미구현 기능으로
단정하거나, 최신 branch와 내용이 다르다는 이유로 그대로 merge하지 않는다. 날짜필터 후보도
현재 dashboard 별칭 오류와 제품 D-013을 검토한 뒤 별도 변경으로 다뤄야 한다.

내용 검사는 `git rev-list --objects --all`의410객체/187blob 전체를 열고173 UTF-8 blob에
정규식 패턴을 적용했다. private key marker, AWS/GitHub/OpenAI token 형태, JWT,
credential-bearing DB URL, literal secret assignment, fallback SECRET, 역할 PIN 패턴을
검사했다. 남은14개 Python bytecode blob은 실행하지 않고 ASCII 패턴 검사했다.
현행·과거 settings의 기본 PIN/개발 키가 발견됐고 값은 문서·로그에 복사하지 않았다.
DB URL2개는 USER/PASS/HOST 기호형 예시로 확인되어 실제 DB 자격증명 누출로 세지 않았다.
과거 bytecode settings3개에도 credential-URL 형태가 있어 원본과 함께 보존·검토 대상이다.
비밀값을 검증하려고 외부 서비스에 접속하지 않았다.

이것은 파일명 검사보다 깊지만 전용 스캐너·provider검증·고엔트로피/분할/암호화 secret 탐지를
대체하지 않는다. 확인한 token/private-key/JWT 패턴에 추가 매칭이 없다는 결과를 '비밀정보 없음'
인증으로 사용하지 않는다. 실제 사용 중인 값이 발견되면 별도 승인된 자격증명 회수·영향조사와
내용 제거 전략이 우선이며, 지금 증거만으로 history rewrite를 권고하지 않는다.

권고는 현재 팁·고유작업을 보존하고 D-001에서 정식 branch를 선택한 뒤 승인된 태그/보호규칙/
작은 squash PR 정책을 적용하는 것이다. 이번 작업에서는 commit/tag/branch 변경, push/merge,
삭제, 설정 변경을 하지 않았다. [기존 Git 전략](GIT_RECOVERY.md)의 원격 승인 경계는 그대로 유지한다.

## 위험별 상세 근거

[RISK_REGISTER.md](RISK_REGISTER.md)는 같은 ID의 정렬 가능한 요약이다. 아래는 각 위험의
시나리오·영향·최소 개선·의존성·회귀시험·확신과 미확인 범위를 보관한다. 신규 ID는 BK-R012부터
추가했으며 초기 BK-R001~011은 유지했다.

<a id="bk-r001"></a>
### BK-R001 — API 역할 인가 부재와 변경 API CSRF 면제

- 심각도/상태: **Critical / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:146-148](../../orders/views/api.py#L146),346-348,379-381; [orders/urls.py:22-31](../../orders/urls.py#L22); 재현 E-SQLite.
- 영향 불변조건: 서버 권한·주문 신뢰성·매출 기밀성. 시나리오: 로그인 없이 생성 201, 상태/진행 PATCH 200, 조회 200. ORDER 역할도 주방 진행 변경 200.
- 최소 개선: 경로·메서드별 역할 검사와 CSRF를 같이 강제; 페이지/버튼을 권한으로 삼지 않음.
- 의존성/담당: D-003; 단계 2; 단계 3; 보안 담당.
- 회귀시험: 모든 역할/익명/만료 세션, CSRF 없음·오류·유효, GET/POST/PATCH/HEAD 경계.
- 미확인: 외부 노출 범위, 승인된 역할 매트릭스; dashboard 자체는 별도 오류로 500.

<a id="bk-r002"></a>
### BK-R002 — 공개된 기본 역할 PIN·개발 설정으로 시작 가능

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [bazaar_kiosk/settings.py:9-18](../../bazaar_kiosk/settings.py#L9),108-130; [orders/views/auth.py:31-44](../../orders/views/auth.py#L31); .env.example:18-20.
- 영향 불변조건: 식별·권한·안전한 배포. 시나리오: 환경 변수를 누락하면 공유 기본 PIN·DEBUG 활성·개발 키가 사용됨. 인증 속도 제한 코드 없음.
- 최소 개선: 필수 환경 검증과 기본 인증값 제거; 사용자/기기 식별 모델 및 제한 정책을 결정.
- 의존성/담당: D-002,D-006; 단계 3; 단계 4A; 보안·운영 담당.
- 회귀시험: 설정 누락 시작 실패, 잘못된 PIN 반복, 공개 프록시/HTTPS 설정.
- 미확인: 운영에서 기본값 사용 여부·프록시 보호는 미확인; 실제 값은 문서에 싣지 않음.

<a id="bk-r003"></a>
### BK-R003 — PostgreSQL 날짜별 번호 계약 차이 및 충돌 재시도 실패

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/services/numbering.py:9-63](../../orders/services/numbering.py#L9); [orders/views/api.py:303-335](../../orders/views/api.py#L303); 재현 E-PG.
- 영향 불변조건: 번호 고유성·날짜 계약·원자성. 시나리오: PG 날짜 9/6→9/7에 41→42. 같은 날짜 번호 충돌 후 outer atomic에서 TransactionManagementError.
- 최소 개선: D-004 확정 후 날짜/할당 정책 통일, 제한된 재시도와 savepoint 경계 설계.
- 의존성/담당: D-004,D-006; 단계 1,2; 단계 5; 데이터 담당.
- 회귀시험: PG 자정/충돌/재시도/실패·동시 생성; 기존 번호·날짜 데이터와 호환.
- 미확인: 일일 초기화는 주석상 계약이며 사용자 미승인; 운영 시퀀스 상태 미확인.

<a id="bk-r004"></a>
### BK-R004 — 동작 테스트 0개와 실행을 강제하지 않는 CI

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [.github/workflows/ci.yml:28-44](../../.github/workflows/ci.yml#L28); E-BASE의 manage.py test.
- 영향 불변조건: 리팩터링 시 핵심 불변 조건 보존. 시나리오: 검사 green이어도 익명 생성과 dashboard 500을 감지하지 못함.
- 최소 개선: 동작 특성화·권한·금액·상태·PG 신규/업그레이드 검사를 CI 게이트로 도입.
- 의존성/담당: D-006,D-008; 단계 1; 단계 2; 테스트 담당.
- 회귀시험: 의도적인 핵심 회귀를 테스트가 감지하는지 검증; 개수 자체를 목표로 삼지 않음.
- 미확인: 운영 발생 빈도는 미확인.

<a id="bk-r005"></a>
### BK-R005 — 빈 PostgreSQL에서 0020 마이그레이션 중단

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/migrations/0020_create_floor_sequences.py:5-17](../../orders/migrations/0020_create_floor_sequences.py#L5); E-PG.
- 영향 불변조건: 신규 설치·복구 가능성. 시나리오: MAX(order_no)가 없으면 setval(0,true)이 minvalue 1 위반. 0019에서 중단되어 후속 수정 migration에 도달 불가.
- 최소 개선: 이미 적용된 DB 목록부터 확보하고 신규 bootstrap/대체 체인/정확히 승인된 이력 수정 경로 비교.
- 의존성/담당: D-006,D-008,D-017; 단계 1; 데이터·운영 담당.
- 회귀시험: PG 빈 DB 전체 체인, null/빈 번호, 기존 양수번호 DB, 이미0020 적용 경로·롤백.
- 미확인: 합성0019에 번호40 한 행을 둔 업그레이드는 성공; 운영 데이터 전체 호환성은 별도.

<a id="bk-r006"></a>
### BK-R006 — 통계 기간이 2025-10-18로 고정

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:90-105](../../orders/views/api.py#L90); E-SUPPLEMENT helper 호출.
- 영향 불변조건: 행사 매출·일자 경계 정확성. 시나리오: 2026-09-06 범위 요청을 helper에 전달해도 시작/끝 모두 2025-10-18.
- 최소 개선: D-013의 기본·명시 기간, Seoul 경계와 오류 계약을 쿼리에 반영.
- 의존성/담당: D-013; BK-R016; 단계 8; 조회·보고 담당.
- 회귀시험: 무기간/하루/범위/잘못된 날짜/자정/양 끝 경계.
- 미확인: 현재 전체 endpoint는 BK-R016 때문에 500; 잘못된 보고 응답의 운영 출력은 주장하지 않음.

<a id="bk-r007"></a>
### BK-R007 — 레거시 결제 분할 합계와 상세 응답 불일치

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/migrations/0017_order_payment_split.py:12-32](../../orders/migrations/0017_order_payment_split.py#L12); [orders/views/api.py:31-39](../../orders/views/api.py#L31),508-517; E-SUPPLEMENT.
- 영향 불변조건: 현금·식권 정산과 과거 데이터 보존. 시나리오: payment_method=CASH, received_amount=5000, 분할 null이면 상세 현금5000,aggregate cash null(후속0).
- 최소 개선: 원본 보존한 조정 정책 결정; 단일 결제 fallback과 혼합 미확정값을 구분.
- 의존성/담당: D-005,D-008,D-012; 단계 6; 단계 7; 재무·데이터 담당.
- 회귀시험: 0017 이전 CASH/TICKET 행과 0017 이후 혼합 결제·분할 누락 행, 원본/분할/보고 합계 대조·되돌림.
- 미확인: 실제 레거시 행 수 미확인; dashboard 정상응답은 BK-R016 해결 후 검증.

<a id="bk-r008"></a>
### BK-R008 — 관리자 항목 수정으로 저장 합계와 품목 합계 이탈

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/admin.py:45-50](../../orders/admin.py#L45),70-86; [orders/services/totals.py:1-10](../../orders/services/totals.py#L1); E-SQLite.
- 영향 불변조건: 서버 합계 무결성. 시나리오: 허용된 모델 편집과 같은 qty변경 1→3 후 저장 총액5000,품목 합계15000. 관리자 자동 재계산 hook 없음.
- 최소 개선: 관리자 편집 금지 또는 동일 명령서비스 사용 중 D-011 선택; 추가/삭제/상태/번호 포함.
- 의존성/담당: D-011,D-005; 단계 6; 단계 7; 재무·백엔드 담당.
- 회귀시험: 실제 관리자 form POST 추가·수정·삭제·상태, 가격 스냅샷/합계/번호.
- 미확인: 모델 경로 재현이며 실제 admin form 브라우저 제출은 미실행.

<a id="bk-r009"></a>
### BK-R009 — 최신 80개 이후 오래된 주방 대기 작업 누락

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/templates/orders/kitchen_supervisor.html:94](../../orders/templates/orders/kitchen_supervisor.html#L94),139-147; [orders/views/api.py:149-173](../../orders/views/api.py#L149); E-SQLite.
- 영향 불변조건: 모든 대기 작업의 가시성. 시나리오: 오래된 홀1건 뒤 포장80건 생성하면 limit80 응답에 홀없음; 200으로 조회하면 포함.
- 최소 개선: 역할·항목 mode 기준 필터를 절단 전에 적용하고 모든 대기 작업을 복구하는 조회 계약.
- 의존성/담당: D-003,D-010,D-014; 단계 3,6; 단계 8; 조회 담당.
- 회귀시험: 혼합·단일모드 81/200초과 backlog의 초기/폴링/재접속.
- 미확인: API cutoff는 재현; 역할 화면 브라우저와 실서비스 backlog 규모는 미검증.

<a id="bk-r010"></a>
### BK-R010 — 프로세스별 테이블 객체 캐시가 비활성화를 무시

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:108-110](../../orders/views/api.py#L108),207-230; E-SQLite.
- 영향 불변조건: 서버 기준 테이블 유효성. 시나리오: 캐시 warm 후 테이블 비활성·이름변경해도 주문201,이전 이름 응답.
- 최소 개선: 변경 가능한 ORM 객체 캐시 제거 또는 갱신 경계를 정의; 메뉴/테이블 응답 TTL도 계약화.
- 의존성/담당: D-014; 단계 3,6; 단계 8; 조회 담당.
- 회귀시험: 관리자 수정 전/후·다중 워커·TTL·삭제/비활성 재조회.
- 미확인: 단일 프로세스 stale은 재현; 워커간 불일치는 구조상 가능, 다중 프로세스 실측 없음.

<a id="bk-r011"></a>
### BK-R011 — 저장 문자열이 실행 가능한 HTML·인라인 핸들러에 보간

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [orders/templates/orders/order.html:260-269](../../orders/templates/orders/order.html#L260),318-332; [orders/templates/orders/b1_counter.html:133-139](../../orders/templates/orders/b1_counter.html#L133).
- 영향 불변조건: 운영자 세션·출력 이스케이프. 시나리오: 악성 메뉴명은 텍스트와 인라인 onclick 속성 경계를 넘을 수 있음. 메뉴 수정 권한/기존 악성 데이터가 선행.
- 최소 개선: textContent/DOM 생성·이벤트 연결로 문맥 제거; 저장값별 회귀 테스트.
- 의존성/담당: 단계 2,3; 단계 4B; 프런트·보안 담당.
- 회귀시험: 메뉴/테이블/메모의 HTML·따옴표·백슬래시·유니코드 payload 브라우저 검증.
- 미확인: 브라우저 코드 실행은 미재현; 주방에는 escapeHtml 헬퍼가 있어 같은 주장으로 묶지 않음.

<a id="bk-r012"></a>
### BK-R012 — 재전송·중복 제출에 멱등성 경계 없음

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:178-343](../../orders/views/api.py#L178); [orders/templates/orders/order.html:408-455](../../orders/templates/orders/order.html#L408); E-SQLite,E-PG.
- 영향 불변조건: 주문·결제 중복 방지. 시나리오: 같은 요청2번에 다른 ID/번호2개. PG8thread16동일요청도16주문. 응답 유실 후 재시도는 중복 생성 가능.
- 최소 개선: 클라이언트 요청ID, 서버 유일제약·응답 재사용·payload충돌·보존시간 계약.
- 의존성/담당: D-007,D-008; 단계 5; 단계 6; 주문 담당.
- 회귀시험: 더블탭/timeout후 재전송/병렬동일키/다른payload/키만료.
- 미확인: 독립 주문과 재전송 구분 정책은 미정; 동시번호고유는 멱등성 증거가 아님.

<a id="bk-r013"></a>
### BK-R013 — 취소에서 활성으로 전환 가능·상태 명령 간 경합

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:346-420](../../orders/views/api.py#L346); E-SQLite.
- 영향 불변조건: 취소 종결성·상태 무결성. 시나리오: CANCELLED PATCH 후 PREPARING PATCH가200. status 쓰기는 조회 후 무조건 저장하며 progress의 취소 guard와 정책이 다름.
- 최소 개선: 명시 상태 전이표·조건부 갱신·주문 중심 잠금으로 모든 writer 통합.
- 의존성/담당: D-015,D-003; 단계 5; 단계 6; 주문 담당.
- 회귀시험: 취소후 progress/직접상태/관리자, 취소와 완료 경합, stale absolute progress.
- 미확인: 취소복귀는 재현; 모든 동시 스케줄의 장애 재현은 미실행.

<a id="bk-r014"></a>
### BK-R014 — 부족 결제·소수 입력을 정상 주문으로 승인

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:232-301](../../orders/views/api.py#L232),325-327; E-SQLite.
- 영향 불변조건: 정수KRW·정산·서버 검증. 시나리오: 5000원 주문에 0/1원 수납도201; 1.9원 또는 수량1.9는1로 잘림. 음수는 DB제약500·잔여행0.
- 최소 개선: D-005 승인 후 형식·범위·부족/초과·식권 거스름돈을 서버에서 검증.
- 의존성/담당: D-005,D-012; 단계 6; 단계 7; 재무 담당.
- 회귀시험: 0/부족/초과/음수/float/bool/오버플로/복합 필드/메뉴 가격 변경.
- 미확인: 부족 결제 허용 여부는 제품 결정 대기; 소수 잘림은 재현된 현행 사실.

<a id="bk-r015"></a>
### BK-R015 — JSON 입력 타입·테이블 분기 불일치가 500으로 노출

- 심각도/상태: **Medium / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:24-28](../../orders/views/api.py#L24),184-229,285-292; [orders/models/core.py:105-120](../../orders/models/core.py#L105); E-SQLite.
- 영향 불변조건: 안정적인 입력·오류 계약. 시나리오: JSON배열,숫자floor,숫자table_number, DINE_IN+is_takeout=true가500; 마지막은 nulltable과 DB제약 충돌.
- 최소 개선: 경계 DTO/명시 타입 검사·논리적 boolean·일관된 JSON4xx; table/포장 의미 결정.
- 의존성/담당: D-014,D-008; 단계 6,7; 단계 9; API 담당.
- 회귀시험: 누락/null/list/dict/정수/문자열/UTF8/메서드별 오류 계약.
- 미확인: 금액·상태에 관련된 입력은 단계6/7에서 먼저 다뤄야 하며 단계9까지 방치하지 않음.

<a id="bk-r016"></a>
### BK-R016 — 통계 aggregate alias 충돌로 SQLite·PG 모두 500

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/views/api.py:526-532](../../orders/views/api.py#L526); E-SQLite,E-PG.
- 영향 불변조건: 매출 확인 가용성. 시나리오: qty=Sum(qty)를 정의한 뒤 amount의 F(qty)가 aggregate alias를 참조해 FieldError. 빈DB에서도 발생.
- 최소 개선: 고유 aggregate alias 또는 분리된 expression으로 수정하고 API 통계 계약 고정.
- 의존성/담당: BK-R004; D-013,D-012; 단계 8; 조회·보고 담당.
- 회귀시험: 빈DB/한행/동명메뉴/기간/취소/레거시 데이터의 endpoint200와 정확한 합계.
- 미확인: 현행 Django5.2.17 양DB 재현; 운영 Django 버전은 미확인.

<a id="bk-r017"></a>
### BK-R017 — 과거 스키마 축소와 신규 제약의 데이터 호환성 미검증

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [orders/migrations/0018_alter_order_floor_alter_order_order_type_and_more.py:12-32](../../orders/migrations/0018_alter_order_floor_alter_order_order_type_and_more.py#L12); [orders/migrations/0019_remove_order_orders_table_rule_and_more.py:12-20](../../orders/migrations/0019_remove_order_orders_table_rule_and_more.py#L12); E-PG-LEGACY.
- 영향 불변조건: 운영 데이터 보존·업그레이드·복구. 시나리오: 0018에 유효한 B1/TAKEOUT/table=NULL 한 행을 두면0019 IntegrityError. 최신table있는포장행도0018로 역마이그레이션 시 IntegrityError. 각각 실패한 마이그레이션의 행은 보존됨.
- 최소 개선: 적용 이력·정제 데이터 인벤토리와 신규/기존 분기 계획; 과거파일 임의수정 금지.
- 의존성/담당: D-006,D-008,D-017; 단계 1; 데이터·운영 담당.
- 회귀시험: 0018 시점 F1/BOOTH/포장null fixture→0019, 정제복사본 dry-run·백업복원·구앱 호환.
- 미확인: 합성 경로 두 개만 검증. 운영행 구성·수동 보정·과거 적용 여부와 구앱/새스키마 실행은 미확인.

<a id="bk-r018"></a>
### BK-R018 — Supabase 익명 구독의 RLS·이벤트 노출 경계 미확인

- 심각도/상태: **High / Production-dependent**. 확신: 높음.
- 근거: [bazaar_kiosk/settings.py:92-94](../../bazaar_kiosk/settings.py#L92); [orders/views/pages.py:8-12](../../orders/views/pages.py#L8); [orders/templates/orders/kitchen_supervisor.html:82](../../orders/templates/orders/kitchen_supervisor.html#L82),434-464.
- 영향 불변조건: 외부 실시간 경로의 권한·기밀성. 시나리오: 공개 클라이언트가 orders_order/orders_orderitem 이벤트를 구독. Django 세션 역할과 RLS 연결 증거 없음.
- 최소 개선: D-018에 따라 자체 SSE와 권한 있는 snapshot/폴링으로 교체. 전환 전에는 실제 publication/RLS/GRANT/JWT 노출을 검증하고 외부 구독을 안전하게 비활성화한다. 브라우저 제거만으로 기존 외부 접근 권한이 폐기되지는 않는다.
- 의존성/담당: D-010; 단계 3; 단계 4B; 보안·운영 담당.
- 회귀시험: 전환 전 외부 익명·역할별 행/열/이벤트 허용·거부, 전환 후 브라우저 외부 요청/키0·자체 SSE 권한 회귀·외부 노출 정리 증거. 새 SSE의 권한을 과거 RLS로 대신하지 않음.
- 미확인: Supabase 미접속; anon key 노출 자체를 비밀 누출이나 RLS 우회로 판정하지 않음.

<a id="bk-r019"></a>
### BK-R019 — 역할 로그인 세션 교체·만료 정책 부재와 GET 로그아웃

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/views/auth.py:31-37](../../orders/views/auth.py#L31),51-53; [bazaar_kiosk/settings.py:108-111](../../bazaar_kiosk/settings.py#L108).
- 영향 불변조건: 세션 수명·공유 기기 식별. 시나리오: 기존 세션에 role만 덧씀(cycle_key/login 없음), 역할 변경/공유기기 인계 정책 없음. PIN 교체·삭제만으로 기존 역할 세션이 회수되지 않음. 안전 메서드 로그아웃은 CSRF 검사 밖이며 POST 등에는 검사 적용.
- 최소 개선: 식별모델에 맞춘 세션교체/만료/로그아웃POST 및 사용자·기기 감사.
- 의존성/담당: D-002,D-003; 단계 4A; 보안 담당.
- 회귀시험: 로그인 전후 session id, PIN 회수·교체 후 기존 세션 거부, 역할변경·만료·공유기기·logout method.
- 미확인: 세션 고정 공격 성공 자체는 미재현; Django 기본 만료14일·HttpOnly/SameSite가 적용되며 무기한 세션으로 주장하지 않음.

<a id="bk-r020"></a>
### BK-R020 — Realtime 연결 상실 후 폴링 복귀·재동기화 부재

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [orders/templates/orders/kitchen_supervisor.html:289-330](../../orders/templates/orders/kitchen_supervisor.html#L289),426-465.
- 영향 불변조건: 주방 작업 가시성·재연결 복원력. 시나리오: SUBSCRIBED에서5초poll중단 후 ERROR/CLOSED에서 플래그복원·poll재시작 없음. 재구독/화면복귀 후 전체재조회도 없음.
- 최소 개선: 구독상태 머신·주기적 reconcile·응답세대/버전·bounded retry를 명시.
- 의존성/담당: D-010,D-007; 단계 4B,8,9; 단계 10; 실시간 담당.
- 회귀시험: SUBSCRIBED이후 CLOSED/ERROR/TIMEOUT, duplicate/out-of-order/drop, 느린응답·재접속.
- 미확인: 실제 네트워크 장애·Supabase 이벤트 순서/브라우저 실행 미검증.

<a id="bk-r021"></a>
### BK-R021 — 재현되지 않는 의존성 범위와 지원 종료 버전 허용

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [requirements.txt:2-6](../../requirements.txt#L2); [.github/workflows/ci.yml:21-31](../../.github/workflows/ci.yml#L21); 공식 Django 지원표.
- 영향 불변조건: 깨끗한 배포의 재현성·지원 버전. 시나리오: 열린 범위·transitive lock 없음. Django 범위는 지원종료5.0/5.1도 허용하나 로컬5.2.17을 취약하다고 단정할 근거 없음.
- 최소 개선: 지원 baseline·lock방식·해시/업데이트 주기 확정; 동작변경과 업그레이드 분리.
- 의존성/담당: D-006; 단계 2; 빌드·운영 담당.
- 회귀시험: 빈환경 재현·pip check·지원버전/보안패치 확인·PG CI.
- 미확인: 패키지 취약점 DB 감사는 미실행; 공식 지원표 2026-09-06 확인.

<a id="bk-r022"></a>
### BK-R022 — 배포·상태확인·복원·롤백 증거와 운영 계측 부재

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [bazaar_kiosk/urls.py:1-10](../../bazaar_kiosk/urls.py#L1); [.github/workflows/ci.yml:1-44](../../.github/workflows/ci.yml#L1); [bazaar_kiosk/settings.py:69-111](../../bazaar_kiosk/settings.py#L69); git log --all -- .github/workflows/deploy.yml.
- 영향 불변조건: 장애 복구·데이터 보존·안전한 배포. 시나리오: 현재 health route/deploy workflow/backup runbook/structured logging·metrics 설정이 없음. DB URL 누락시 SQLite fallback.
- 최소 개선: 토폴로지·환경 사전검증·readiness·구조화로그/메트릭·복원·구앱 호환과 fail-closed rollback 계획.
- 의존성/담당: D-006,D-008,D-016; 단계 4A,5,6,7,10,11; 단계 12A; 운영 담당.
- 회귀시험: 정제 복사본 복원시간·schema/oldapp rehearsal·PG불가/잘못된 env·release smoke.
- 미확인: 저장소 밖에 운영체계가 없다고 단정하지 않음; 현재 배포 플랫폼·워커·백업 모두 미확인.

<a id="bk-r023"></a>
### BK-R023 — 인라인 UI·실패 복구·접근성·미사용 화면의 유지보수 위험

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/templates/orders/order.html:1-535](../../orders/templates/orders/order.html#L1); [kitchen_supervisor.html:1-486](../../orders/templates/orders/kitchen_supervisor.html#L1); [b1_counter.html:1-185](../../orders/templates/orders/b1_counter.html#L1); [role_select.html:21-22](../../orders/templates/orders/role_select.html#L21).
- 영향 불변조건: 터치 운영·오류 복구·변경 검토 가능성. 시나리오: 주문/주방 화면에 상태·네트워크·DOM이 혼재; 미사용 role_select는 없는 login_pin URL로 렌더 실패.
- 최소 개선: 회귀 여정 확보 후 JS/CSS 역할 분리·의미론적 control/초점·오류/재시도 상태; 참조 확인 뒤 미사용 제거.
- 의존성/담당: D-007,D-009; 단계 4B,8,9; 단계 11; 프런트 담당.
- 회귀시험: 대상기기 viewport·키보드/터치/스크린리더·네트워크실패·기존 URL호환.
- 미확인: 템플릿/JS 구문은 검사했으나 접근성·브라우저 호환은 실기기 미검증.

<a id="bk-r024"></a>
### BK-R024 — API 뷰에 전송·쿼리·금액·명령이 집중

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/views/api.py:24-594](../../orders/views/api.py#L24); [orders/services/totals.py:1-10](../../orders/services/totals.py#L1); [orders/admin.py:8-14](../../orders/admin.py#L8),70-85.
- 영향 불변조건: 변경 안전성·오류 계약 일관성. 시나리오: 동작 변경과 추출을 섞으면 기존 오류·보안·금액 계약이 사라지거나 누락될 수 있음.
- 최소 개선: 검증/serializer/selector/명령서비스를 계약 테스트 아래 분리; broad exception 제거는 근거별로.
- 의존성/담당: D-008; 단계 8; 단계 9; 백엔드 담당.
- 회귀시험: 현재/목표 응답 schema·예외 분류·쿼리수 회귀·관리자 writer 매핑.
- 미확인: 코드 구조를 성능 결함이나 전면 재작성의 근거로 사용하지 않음.

<a id="bk-r025"></a>
### BK-R025 — 동일 트리와 고유 이력을 혼동한 Git 정리 위험

- 심각도/상태: **Medium / Reproduced**. 확신: 높음.
- 근거: E-GIT; GIT_RECOVERY.md; origin/Megesfile,origin/mergebe의 api.py 차이.
- 영향 불변조건: 작업·blame·배포 참조 보존. 시나리오: main/develop tree동일이 모든 오래된 브랜치 폐기 가능을 뜻하지 않음. chore계열9고유커밋,날짜필터다른팁 존재.
- 최소 개선: 정식기준 결정→팁/고유콘텐츠 목록보존→담당자 검토→별도승인 정리.
- 의존성/담당: D-001; 별도 원격 승인; 단계 G; 저장소 관리자.
- 회귀시험: refs/trees/left-right/branch diff/내용검사·체크포인트 AGENTS 존재.
- 미확인: 원격 fetch/API조회 안함; 로컬 origin/* snapshot기준. 태그·branch·설정 수정없음.

<a id="bk-r026"></a>
### BK-R026 — order_date와 created_at·자정 주방 집계 경계 불일치

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/services/numbering.py:28](../../orders/services/numbering.py#L28),47; [orders/views/api.py:155-173](../../orders/views/api.py#L155),435-474,539-550.
- 영향 불변조건: 주문일·시간대·자정 미완료 작업. 시나리오: 번호날짜는 할당 시점 Seoul,created_at은생성시각. 목록은과거대기도포함,요약은오늘만.자정 대기카드/요약 불일치 가능.
- 최소 개선: D-004/D-013에 주문일기준·전일대기·시간별보고 계약 포함.
- 의존성/담당: D-004,D-013; 단계 5; 단계 8; 조회·도메인 담당.
- 회귀시험: Seoul23:59:59→00:00,할당지연,전일대기,같은시각다른날짜 보고.
- 미확인: 실제 자정 전환/운영 일정 미검증; UTC설정 오류로 단정하지 않음.

<a id="bk-r027"></a>
### BK-R027 — 테이블 슬롯·항목 mode·포장 flag 의미 불명확

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/views/api.py:194-229](../../orders/views/api.py#L194),293-301; [orders/models/core.py:132-136](../../orders/models/core.py#L132).
- 영향 불변조건: 홀/포장 전달·과거 메뉴 정산 식별. 시나리오: DINE_IN은활성101도허용,TAKEOUT is_takeout=false가능; 항목mode와주문타입분리.
- 최소 개선: D-014로 슬롯·혼합주문 분류와 호환할 조합을 명시.
- 의존성/담당: D-014,D-008; 단계 5; 단계 6; 제품·주문 담당.
- 회귀시험: 101~120/일반테이블 경계·혼합항목·flag조합.
- 미확인: 지금 동작이 제품 요구에 맞는지는 사용자 결정 전 확정 불가.

<a id="bk-r028"></a>
### BK-R028 — DEBUG 오류 페이지가 환경에서 설정한 역할 PIN도 노출

- 심각도/상태: **High / Reproduced**. 확신: 높음.
- 근거: [bazaar_kiosk/settings.py:10](../../bazaar_kiosk/settings.py#L10),127-130; [orders/views/api.py:178-186](../../orders/views/api.py#L178); E-SUPPLEMENT.
- 영향 불변조건: 자격 증명 비공개·안전한 배포. 시나리오: DEBUG=True에서 JSON[] 요청500을 유도하면 임시 ROLE_PINS 값이 오류 응답에 포함됨(Boolean만 기록). 기본 PIN 교체만으로 방어되지 않음.
- 최소 개선: 운영DEBUG금지·시작검증·민감설정 마스킹·오류 경계.
- 의존성/담당: D-002,D-006; 단계 3; 단계 4A; 보안·운영 담당.
- 회귀시험: 합성 자격증명으로500 HTML/JSON·로그에 값이 없는지, env누락 실패.
- 미확인: 실제 운영DEBUG/PIN·외부접속 여부 미확인. 운영 자격증명은 읽거나 재현에 사용하지 않음.

<a id="bk-r029"></a>
### BK-R029 — 가변 CDN 스크립트와 콘텐츠 보안 정책 검증 부재

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/templates/orders/kitchen_supervisor.html:82](../../orders/templates/orders/kitchen_supervisor.html#L82); [bazaar_kiosk/settings.py:37-46](../../bazaar_kiosk/settings.py#L37).
- 영향 불변조건: 서드파티 코드 무결성·주방 가용성. 시나리오: supabase-js@2 가변CDN스크립트에SRI없음; 저장소에CSP설정없음. 콘텐츠변경/로드실패 영향 존재.
- 최소 개선: D-018에 따라 Supabase CDN/SDK와 Realtime 설정 주입을 제거하고 자체 SSE/보호된 폴링으로 대체. 남는 자체 스크립트에도 CSP·출력 경계 검증을 유지.
- 의존성/담당: D-010; BK-R011; 단계 4B; 보안·프런트 담당.
- 회귀시험: 외부 CDN/Supabase 요청0·키 주입0, 외부 연결 없이 주방 기본흐름, 자체 SSE 오류/폴링 복구·CSP 허용목록.
- 미확인: CDN침해나특정CVE발견아님; 프록시CSP가있을수있음.

<a id="bk-r030"></a>
### BK-R030 — 수납·거스름돈·취소 환불·순매출 계약 미확정

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [orders/views/api.py:31-40](../../orders/views/api.py#L31),99-105,269-270,508-517; [orders/models/core.py:25-28](../../orders/models/core.py#L25),92-99.
- 영향 불변조건: 현금시재·식권·매출 정합성. 시나리오: 5000원에현금10000이면상세거스름5000이나집계는수납10000.취소는보고에서빠지고환불기록필드없음.
- 최소 개선: 총수납/순현금/매출/식권소진/환불 지표를 D-005로 구분하고 원본보존.
- 의존성/담당: D-005,D-012; 단계 6; 단계 7; 재무·제품 담당.
- 회귀시험: 초과현금·과다식권·혼합거스름·취소전후·부분환불·레거시미분류.
- 미확인: 수납을매출로볼지는제품정책; 현재dashboard는BK-R016으로실패.실제손실주장아님.

<a id="bk-r031"></a>
### BK-R031 — 과거 삭제·재추가 필드와 카테고리의 복구 원천 미확인

- 심각도/상태: **High / Production-dependent**. 확신: 높음.
- 근거: [orders/migrations/0010_floorordercounter_delete_pickupcounter_and_more.py:57-96](../../orders/migrations/0010_floorordercounter_delete_pickupcounter_and_more.py#L57); [orders/migrations/0011_alter_floorordercounter_options_and_more.py:25-56](../../orders/migrations/0011_alter_floorordercounter_options_and_more.py#L25); [orders/migrations/0015_remove_menu_categories.py:25-32](../../orders/migrations/0015_remove_menu_categories.py#L25).
- 영향 불변조건: 과거 주문·정산 증거 보존. 시나리오: 번호·층·수납등삭제/신규필드와카테고리삭제시적용당시데이터가있었다면값소실가능. reverse_schema로값복원은불가.
- 최소 개선: 적용시점데이터·백업·원본 추적 후 읽기전용조정보고.불명확값을임의백필하지않음.
- 의존성/담당: D-008,D-012,D-017; 단계 1; 단계 7; 데이터·재무 담당.
- 회귀시험: 정제된과거버전fixture·행수/금액대조·백업복원·정방향완화.
- 미확인: 실제데이터손실은미확인.새빈DB마이그레이션성공은과거값보존증거아님.

<a id="bk-r032"></a>
### BK-R032 — 이벤트 단건 조회·전체 보드 렌더의 부하 상한 미측정

- 심각도/상태: **Medium / Hypothesis**. 확신: 구조 높음·병목 여부 낮음.
- 근거: [orders/templates/orders/kitchen_supervisor.html:258-278](../../orders/templates/orders/kitchen_supervisor.html#L258),303-330,446-448; E-SQLite 및 측정계획.
- 영향 불변조건: 대기작업지연·기기응답성. 시나리오: 이벤트마다단건3쿼리조회후전체정렬·보드교체.5초폴링은화면수비례하며총이력집계인덱스효과미측정.
- 최소 개선: 동일워크로드에SQL계획/latency/렌더/이벤트지연측정후병목만개선.
- 의존성/담당: D-007,D-006,D-010; 단계 8,9; 단계 10; 성능 담당.
- 회귀시험: 화면1/5/20,적체20/80/201,항목1/5/20,이벤트폭주·워커1/4.
- 미확인: N+1미발견(목록3쿼리일정).운영p95/처리량·멀티워커실측없음.

<a id="bk-r033"></a>
### BK-R033 — 주방 목록·단건 응답 순서 역전 방어 부족

- 심각도/상태: **High / Code-supported**. 확신: 높음.
- 근거: [orders/templates/orders/kitchen_supervisor.html:261-278](../../orders/templates/orders/kitchen_supervisor.html#L261),287-330.
- 영향 불변조건: 주방진행상태최신성·취소/완료가시성. 시나리오: 목록은Map전체교체,단건은버전없이적용.120ms중복대기는요청전Set에서제거.늦은응답이최신상태를덮을수있음.
- 최소 개선: ID정규화·진행중요청관리·서버버전/응답세대 계약과reconcile.
- 의존성/담당: D-010; 단계 8,9; 단계 10; 실시간 담당.
- 회귀시험: 완료단건뒤stale목록,진행2뒤0응답,삭제뒤늦은응답·중복ID이벤트.
- 미확인: 서브에이전트 모의응답검사는후퇴확인;실제브라우저/SDK의재현은미실행.

<a id="bk-r034"></a>
### BK-R034 — 현재 메뉴명으로 과거 주문 표시·동명 메뉴 합산

- 심각도/상태: **Medium / Code-supported**. 확신: 높음.
- 근거: [orders/views/api.py:61-63](../../orders/views/api.py#L61),441-446,526-532; [orders/models/core.py:132-136](../../orders/models/core.py#L132).
- 영향 불변조건: 메뉴별정산식별·과거표시보존. 시나리오: 단가는항목에스냅샷이있지만명칭은현재MenuItem참조.이름변경시과거표시도변경되고동명메뉴는하나로합산.
- 최소 개선: D-008에메뉴ID/표시명스냅샷·집계그룹계약을결정하고호환관리.
- 의존성/담당: D-008,D-012; 단계 7; 단계 8; 조회·재무 담당.
- 회귀시험: 동명서로다른ID·이름변경·가격변경·레거시집계·취소.
- 미확인: 합산이의도된정책인지미확인;dashboard결과는BK-R016선행.

<a id="bk-r035"></a>
### BK-R035 — 자체 SSE 실행에 필요한 비동기 경로·워커 조건 미확립

- 심각도/상태: **High / Code-supported**. 확신: 로컬 실행 조건 높음·운영 수용량 미확인.
- 근거: [settings.py:37](../../bazaar_kiosk/settings.py#L37), [asgi.py:12](../../bazaar_kiosk/asgi.py#L12), [요구사항](../../requirements.txt); E-SSE-STATIC의 worker import·middleware capability·async 응답 직접 순회.
- 영향 불변조건·시나리오: 주방 갱신과 주문 API 가용성. WSGI sync worker에 장기 스트림을 붙이면 worker를 계속 점유한다. 설치 WhiteNoise는 async_capable=False여서 ASGI 사용만으로 동시 처리 개선을 보장할 수 없다.
- 최소 개선: 지원 런타임과 실제 ASGI 실행 명령을 고정하고 인증을 유지한 비동기 스트림 경계·정적 파일 전달·task 종료를 검증. 설치 Gunicorn26.2.0은 내장 ASGI worker 사용 가능하므로 새 서버 패키지를 필수로 단정하지 않음.
- 의존성/담당: D-006,D-018,D-019; BK-R001/019; 주 단계 10; 실시간·운영 담당.
- 회귀시험: 실제 ASGI HTTP 스트림·일반 API 병행, 동기 middleware 적응/스레드·워커 수·disconnect/reload 정리.
- 미확인: SSE URL과 배포 설정은 아직 없고 실제 SSE 서버·프록시·동시성은 미실행. 현행 운영 장애를 재현한 위험이 아니라 전환 선행 조건.

<a id="bk-r036"></a>
### BK-R036 — SSE 변경 감지의 writer 누락·커밋 후 유실 가능성

- 심각도/상태: **High / Hypothesis**. 확신: 현재 writer 지도 높음·새 전달 경로는 설계 가설.
- 근거: [api.py:325](../../orders/views/api.py#L325), [api.py:414](../../orders/views/api.py#L414), [numbering.py:35](../../orders/services/numbering.py#L35), [admin.py:45](../../orders/admin.py#L45); [SSE 추가 분석](#sse-migration).
- 영향 불변조건·시나리오: 커밋된 주문·진행의 주방 가시성. post_save(Order)만 사용하면 bulk/update·부모 상태 불변인 항목 변경을 놓친다. 메모리/on_commit/NOTIFY만 쓰면 다른 워커·프로세스 종료·재접속에서 변경을 놓칠 수 있다.
- 최소 개선: 동일 거래의 영속 revision 또는 outbox, 모든 writer·변경 전후 범위·삭제의 커버리지 확보. 서비스 경유/DB trigger와 외부 SQL 허용 범위를 결정하고 워커마다 복구 가능하게 함.
- 의존성/담당: D-008,D-011,D-018,D-019; 단계 5,6,7; 주 단계 10; 데이터·실시간 통합 담당.
- 회귀시험: 생성/상태/항목/관리자/bulk/update/삭제/메뉴·테이블, rollback·커밋 직후 kill·다른 워커 구독·revision 행 누락.
- 미확인: DB revision·trigger·outbox는 존재하지 않으며 제안 방식의 누락/복구는 아직 재현하지 않음.

<a id="bk-r037"></a>
### BK-R037 — SSE cursor와 snapshot 불일치로 최신 상태 복구 실패 가능성

- 심각도/상태: **High / Hypothesis**. 확신: 조회 구조·프로토콜 의미 높음·새 구현 실패는 미재현.
- 근거: [api.py:76](../../orders/views/api.py#L76), [주방261](../../orders/templates/orders/kitchen_supervisor.html#L261), [주방303](../../orders/templates/orders/kitchen_supervisor.html#L303); [SSE 복구 계약](#sse-migration).
- 영향 불변조건·시나리오: 대기·완료·취소 화면의 최신성. 오래된 데이터에 최신 revision을 붙이거나 받은 Last-Event-ID를 적용 완료로 보면 재조회 실패 후에도 누락 상태가 유지된다. sequence ID의 커밋 역전도 단순 cursor 소비에서 유실을 만든다.
- 최소 개선: 데이터/revision의 일관된 짧은 DB snapshot, 전체 대기 작업 조회, received/applied 버전 분리·응답 세대·dirty 재조회, 모든 open/reopen 재조정과 generation reset.
- 의존성/담당: D-010,D-019; BK-R009/033; 단계 8,9; 주 단계 10; 조회·실시간 통합 담당.
- 회귀시험: 구독 등록 중 변경, snapshot 중 커밋, ID10/11 역전, HTTP 실패 후 재접속, 늦은 응답·81/201건·DB 복원.
- 미확인: 새 cursor/snapshot 구현은 없음. 기존 BK-R009/033과 별개로 신규 프로토콜의 인수 위험을 등록.

<a id="bk-r038"></a>
### BK-R038 — 장기 SSE의 세션 회수·범위 정보 노출 경계 누락 가능성

- 심각도/상태: **High / Hypothesis**. 확신: 현행 동기 인가·세션 구조 높음·SSE 적용 결과 미확인.
- 근거: [auth.py:31](../../orders/views/auth.py#L31), [auth.py:51](../../orders/views/auth.py#L51), [auth.py:55](../../orders/views/auth.py#L55); [인가·연결 계약](#sse-migration).
- 영향 불변조건·시나리오: 역할별 주문 정보 접근. 스트림 시작 시만 세션을 검사하면 로그아웃/PIN 회수/만료 후에도 이벤트를 받을 수 있다. 전역 revision만 보내도 타 범위의 변경 빈도를 알 수 있다.
- 최소 개선: 동일 출처 세션·async 인가, 캐시 밖의 저장소/권한 버전 재검증과 조회 실패 상한, 승인 범위·최소 payload. 권한 상실 시 연결/큐/조회/화면 정리·인증 세대 교체와 인증 fetch/재로그인 계약. 권한은 cursor에 의존하지 않음.
- 의존성/담당: D-002,D-003,D-010,D-019; BK-R001/019; 단계 3,4A; 주 단계 10; 보안·실시간 담당.
- 회귀시험: 익명/오역할·scope 위조·다른 역할 cursor·다중탭 역할 변경·로그아웃/만료/PIN 회수 중 열린 연결·인증 저장소 장애.
- 미확인: 새 SSE endpoint는 없으며 현재 SSE 정보 유출을 관찰한 것은 아님. 회수 허용 지연과 이벤트 메타데이터 노출 정책 대기.
- 인프라 연계: DB 백업 복원이 폐기한 세션/옛 generation을 되살릴 가능성도 D-016/022에서 검증한다. 복원 세션 무효화/인증 세대·새 SSE generation과 오래된 쿠키/커서 거부는 미재현 인수 항목이다.

<a id="bk-r039"></a>
### BK-R039 — SSE 프록시 buffering·timeout·브라우저 연결 제약 미확인

- 심각도/상태: **Medium / Production-dependent**. 확신: 확인할 운영 경계 높음·실제 영향 미확인.
- 근거: [asgi.py:12](../../bazaar_kiosk/asgi.py#L12), [settings.py:37](../../bazaar_kiosk/settings.py#L37); 저장소 배포 명령/프록시 설정 미발견, [SSE 운영 분석](#sse-migration).
- 영향 불변조건·시나리오: 주방 변경 지연·단절 복구. 중간 buffering이 알림을 모아서 보내거나 idle timeout이 스트림을 종료한다. 여러 탭의 장기 연결이 대상 브라우저/프록시 한도에 도달할 수 있다.
- 최소 개선: 실제 호스팅의 streaming 지원·flush·idle/최대 수명·캐시/압축 확인, named heartbeat와 한 연결 상태 모델, 인증된 자체 폴링 fallback.
- 의존성/담당: D-006,D-007,D-010; BK-R035; 단계 10; 주 단계 12A; 운영·프런트 담당.
- 회귀시험: 실제 프록시 경유 프레임 flush·idle·reload, HTTP/1·HTTP/2/여러 탭·BFCache·백그라운드 복귀·fallback.
- 미확인: 운영 프록시·호스팅·브라우저 연결 제한을 측정하지 않음. 최소 경로 검증은 단계10 전에 필요하고 최종 운영 인수는12A.

<a id="bk-r040"></a>
### BK-R040 — SSE revision 잠금 경합과 조회·버퍼 부하 증가 가능성

- 심각도/상태: **Medium / Hypothesis**. 확신: 부하·잠금 경로는 코드 기반 추론, 규모·발생 빈도 미측정.
- 근거: [api.py:303](../../orders/views/api.py#L303), [api.py:391](../../orders/views/api.py#L391), [주방281](../../orders/templates/orders/kitchen_supervisor.html#L281); [SSE 성능·잠금 제안](#sse-migration).
- 영향 불변조건·시나리오: 주문 처리 가용성과 화면 지연. 전역 revision 잠금과 도메인 잠금 순서가 반대면 교착 가능. 연결별 DB polling·폭주마다 snapshot·무제한 느린 소비자 queue는 SSE 전환 후 부하를 늘릴 수 있다.
- 최소 개선: 도메인+revision 잠금 순서·멱등 전체 명령 재시도 검증, 워커당 공유 revision 확인, 알림/조회 합치기·버퍼 상한·느린 소비자 reset/종료. 실제 경합이 확인되면 심각도 재평가.
- 의존성/담당: D-006,D-007,D-019; BK-R032/035/036; 주 단계 10; 데이터·성능 담당.
- 회귀시험: 생성과 진행/관리자 잠금 역순, 워커1/4·화면1/5/20·폭주·느린 소비자에서 lock/SQL/FD/RSS/p95/복구 지연.
- 미확인: 1초/15초 주기는 제안값일 뿐 SLO 아님. SSE가 현행 폴링보다 빠르거나 저렴하다는 측정 결과 없음.

<a id="bk-r041"></a>
### BK-R041 — 자체 DB 저장소·백업·단일 호스트 복구 경계 미확정

- 심각도/상태: **High / Production-dependent**. 확신: 제안 구성의 장애 경계 높음·운영 복구 성과 미확인.
- 근거: E-INFRA-STATIC의 Compose/배포/백업 파일 인벤토리 부재; [인프라 분석](#infrastructure-migration)의 volume·EBS·복원 설계와 공식 출처.
- 영향 불변조건·시나리오: 주문 데이터 보존과 행사 가용성. 컨테이너 volume만을 백업으로 믿거나 EBS mount 누락을 빈 DB로 초기화하면 데이터가 없어진 것처럼 동작할 수 있다. 같은 호스트/AZ 장애·행사망 단절은 앱과 DB 접근을 함께 끊는다.
- 최소 개선: 명시적 영속 mount·시작 전 장치 확인·삭제 방지, 호스트 밖 암호화 백업과 키/권한 보존, 새 호스트 복원·RPO/RTO·현장 수동 처리 인수. restart 정책을 HA로 해석하지 않음.
- 의존성/담당: D-006,D-007,D-016,D-020,D-021,D-022; BK-R022/039; 주 단계 12A; DB·인프라 운영 담당.
- 회귀시험: 컨테이너 재생성/재부팅·mount 누락 거부·새 호스트 restore·행/금액/번호와 시간 대조·disk full·백업/키 장애·행사망 단절.
- 미확인: EC2/EBS/Compose/백업은 아직 구성하지 않았고 실제 호스트 장애나 데이터 손실은 재현하지 않음. 단일 호스트 수용 여부 대기.

<a id="bk-r042"></a>
### BK-R042 — DB 이전의 객체 누락·쓰기 분기·신규 주문 rollback 유실 가능성

- 심각도/상태: **High / Production-dependent**. 확신: 현행 스키마·번호 실패 높음·원본 DB 구성 미확인.
- 근거: [0020:8](../../orders/migrations/0020_create_floor_sequences.py#L8), [numbering.py:21](../../orders/services/numbering.py#L21), [models/core.py:103](../../orders/models/core.py#L103); 기존 E-PG/LEGACY와 [이전 절차](#infrastructure-migration).
- 영향 불변조건·시나리오: 주문·재무·번호 이력 보존. 테이블만 복사하고 별도 층 sequence/권한/extension을 놓치거나 구·신 DB에 동시에 쓰면 불일치한다. 새 DB 쓰기 후 URL만 원복하면 신규 주문을 잃는다.
- 최소 개선: 원본 객체/버전·모든 writer 인벤토리, fresh와 기존 schema+data+이력 restore 경로 분리, 호환 도구·권한 매핑·정제 rehearsal. 최종 동결/단일 쓰기 권한과 새 쓰기 전후 복구 경계 확정.
- 의존성/담당: D-004,D-008,D-016,D-017,D-020,D-022; BK-R003/005/012/017/031/037; 단계 1,5,6,7,10; 주 단계 12A; 데이터 이전 통합 담당.
- 회귀시험: 원본/대상 객체·행·합계·PK/FK/sequence 대조, migration 두 경로, 관리자/SQL 포함 쓰기 동결·old stream·새 쓰기 후 역이전/정방향 복구.
- 미확인: 원본이 Supabase인지 실제 버전·관리 객체·적용 이력·중단 허용량은 미확인. 실제 export/restore·이중 쓰기·유실을 실행하지 않음.

<a id="bk-r043"></a>
### BK-R043 — Compose 환경·secret·DB TLS 계약과 현재 settings의 불일치

- 심각도/상태: **High / Code-supported**. 확신: 합성 settings import 결과 높음·실제 DB 연결 결과 미확인.
- 근거: [settings.py:70](../../bazaar_kiosk/settings.py#L70), [84](../../bazaar_kiosk/settings.py#L84), [.env.example:1](../../.env.example#L1); E-INFRA-STATIC 합성5조건.
- 영향 불변조건·시나리오: 의도한 운영 DB 사용과 주문 저장. URL 또는 _FILE 주입만 설정하면 실제로는 SQLite가 선택될 수 있다. 기본 sslmode=require와 DB TLS가 맞지 않으면 연결할 수 없고 URL의 CA 옵션을 자동 반영한다고 믿으면 검증 설정이 빠진다.
- 최소 개선: 운영 DB engine/URL·필수 secret 누락 시작 거부, Compose 치환/환경/secret 읽기 경로 명시, 내부 서비스 이름과 TLS 정책·CA 전달·앱 역할의 실제 연결 검증.
- 의존성/담당: D-006,D-020,D-021; BK-R002/022; 단계 2,3; 주 단계 4A; 설정·보안·인프라 담당.
- 회귀시험: URL 누락/빈 값·_FILE만·실제 secret 읽기·잘못된 DB·기본 SSL/명시 TLS/CA·재시작 후 동일 DB와 앱 권한 확인.
- 미확인: parser의 선택/옵션만 확인. Compose 주입·TLS handshake·실제 SQLite 오저장 사고는 미재현이며 sslmode=disable은 합성 입력일 뿐 운영 권고가 아님.

<a id="bk-r044"></a>
### BK-R044 — 자체 DB의 공인 포트·권한·비밀 전달 경계 구성 누락 가능성

- 심각도/상태: **High / Hypothesis**. 확신: 현재 신뢰 proxy/secret 코드 높음·새 네트워크 구성은 가설.
- 근거: [settings.py:9](../../bazaar_kiosk/settings.py#L9), [108](../../bazaar_kiosk/settings.py#L108), [127](../../bazaar_kiosk/settings.py#L127); [인프라 경계 분석](#infrastructure-migration), 현재 Compose/보안 그룹 정의 없음.
- 영향 불변조건·시나리오: 주문 DB·운영 자격증명 보호. Docker5432/ASGI 포트를 전체 인터페이스에 게시하거나 앱에 DB superuser/AWS 관리자 권한을 주면 침해 범위가 커진다. 이미지·config 출력·backup에 secret이 남을 수 있다.
- 최소 개선: proxy만 외부 노출·DB/ASGI 비게시, SG와 host/container 경계·헤더 검증, 앱/migration/backup 역할 분리·secret 원본/로그 보호·제한 IAM/SSM·교체와 접근 회수.
- 의존성/담당: D-002,D-003,D-006,D-020,D-021; BK-R001/002/028; 단계 3; 주 단계 4A; 보안·인프라 담당.
- 회귀시험: 외부 DB/ASGI 차단·신뢰 헤더 위조·앱 DDL/superuser 거부·이미지/config/log secret 검사·IAM/SSM/DB 권한 회수·기존 DB 비밀번호 교체.
- 미확인: AWS SG·공인 DB·실제 과다권한·secret 유출은 관찰하지 않음. 초기 로컬 trust/tmpfs fixture와 새 운영 설정을 구분.

## 재현 부록 — 문서에서 복원 가능한 로컬 검사

아래 스크립트는 분석 당시 사용한 검사다. 저장소의 기존 `.venv`만 사용하며 의존성을 추가하지
않는다. SQLite/입력 검사는 `:memory:`를 사용한다. PG 검사는 **새 일회용 컨테이너의 지정된
bk_analysis/bk_analysis_legacy에만** 적용한다. 검사 과정에서 합성 행·시퀀스·테스트 DB를 변경한다.
운영 URL이나 기존 DB에 적용하지 않는다. 생성되는 스크립트·결과는 Git에서 무시되는
`.venv/analysis-20260906/`에 둔다. 테스트 정책을 구현하거나 앱을 패치하는 코드가 아니다.

문서 코드블록을 복원하는 정확한 명령:

```bash
.venv/bin/python - <<'PY_RESTORE'
from pathlib import Path
import re
text = Path('docs/modernization/ANALYSIS_REPORT.md').read_text()
out = Path('.venv/analysis-20260906')
out.mkdir(parents=True, exist_ok=True)
for name, script in re.findall(r'<!-- analysis-script: ([\w.]+) -->\n```python\n(.*?)\n```', text, re.S):
    (out / name).write_text(script + '\n')
PY_RESTORE
.venv/bin/python .venv/analysis-20260906/manage_local.py check
.venv/bin/python .venv/analysis-20260906/manage_local.py makemigrations --check --dry-run
.venv/bin/python .venv/analysis-20260906/manage_local.py test
.venv/bin/python .venv/analysis-20260906/manage_local.py migrate --noinput
.venv/bin/python .venv/analysis-20260906/manage_local.py check --deploy
.venv/bin/python -m pip check
.venv/bin/python .venv/analysis-20260906/probe.py
.venv/bin/python .venv/analysis-20260906/probe_extra.py
node --check orders/static/orders/ui/app.js
```

PG 재현은 기존 로컬 이미지가 있어야 한다. 분석 당시 postgres15.18 이미지ID를 확인했다.
이미지가 없으면 자동 pull/설치하지 말고 실행 안 함으로 남긴다. 다음 명령은 분석용으로 확인한
컨테이너 이름이며, 같은 이름의 기존 컨테이너가 있으면 run이 실패하도록 두고 임의 삭제하지 않는다.

```bash
docker run --pull=never --rm -d --name bk-analysis-20260906-01a076bc -p 127.0.0.1::5432 --tmpfs /var/lib/postgresql/data:rw,nosuid -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=bk_analysis postgres:15-alpine
# docker exec ... pg_isready 가 준비 상태를 반환한 뒤 아래를 실행한다.
docker exec bk-analysis-20260906-01a076bc pg_isready -U postgres -d bk_analysis
BK_ANALYSIS_PORT=$(docker port bk-analysis-20260906-01a076bc 5432/tcp | cut -d: -f2) .venv/bin/python .venv/analysis-20260906/probe_pg.py
docker exec bk-analysis-20260906-01a076bc createdb -U postgres bk_analysis_legacy
BK_ANALYSIS_PORT=$(docker port bk-analysis-20260906-01a076bc 5432/tcp | cut -d: -f2) .venv/bin/python .venv/analysis-20260906/probe_pg_legacy.py
docker stop bk-analysis-20260906-01a076bc
```

분석 당시 실제 포트는56546이었다. 보관본은 같은 검사를 다른 일회용 포트에서도 실행하도록
`BK_ANALYSIS_PORT`를 받는다. DB/호스트 assertion은 유지한다. PG script의 fresh와 legacy fixture는
각각 한 번 실행하는 것을 전제로 한다. 다시 실행하려면 새 일회용 DB를 사용한다.

<details>
<summary>manage_local.py</summary>

<!-- analysis-script: manage_local.py -->
```python
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.cwd()))
os.environ.pop("DATABASE_URL",None)
os.environ["DJANGO_SETTINGS_MODULE"]="bazaar_kiosk.settings"
os.environ["DEBUG"]="0"
os.environ["SECRET_KEY"]="analysis-only-"+"x9!aB7"*12
os.environ["ALLOWED_HOSTS"]="localhost,127.0.0.1,testserver"
os.environ["SUPABASE_URL"]=""
os.environ["SUPABASE_ANON_KEY"]=""
from django.conf import settings
settings.DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}}
from django.core.management import execute_from_command_line
execute_from_command_line(["manage.py",*sys.argv[1:]])
```

</details>

<details>
<summary>probe.py</summary>

<!-- analysis-script: probe.py -->
```python
import os, sys, json, logging, pathlib, datetime, re, ast, subprocess
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path.cwd()))
os.environ.pop('DATABASE_URL',None)
os.environ.update(DJANGO_SETTINGS_MODULE='bazaar_kiosk.settings', DEBUG='0', SECRET_KEY='analysis-only-'+ 'x9!aB7'*12,ALLOWED_HOSTS='testserver,localhost,127.0.0.1', SUPABASE_URL='', SUPABASE_ANON_KEY='')
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
settings.STORAGES={'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}}
import django
django.setup()
logging.disable(logging.CRITICAL)
from django.core.management import call_command
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.db import connection, IntegrityError
from django.utils import timezone
from django.template.loader import get_template
from orders.models import Table, MenuItem, Order, OrderItem
from orders.views import api
from orders.services.numbering import allocate_floor_order_no
call_command('migrate',verbosity=0,interactive=False)
c=Client(enforce_csrf_checks=True,raise_request_exception=False)
t=Table.objects.create(number=1,name='analysis-table')
slot=Table.objects.create(number=101)
m=MenuItem.objects.create(name='analysis-menu',price=5000)
base={'floor':'B1','order_type':'DINE_IN','table_number':'1','payment_method':'CASH','received_amount':5000,'items':[{'menu_item_id':m.id,'qty':1}]}
def create(**kw):return c.post('/orders/api/orders/',json.dumps(base|kw),content_type='application/json')
def emit(name,**kw):print(json.dumps({'case':name,**kw},ensure_ascii=False))
r=create();o=r.json();oid=o['id'];iid=o['items'][0]['id']
reads=['tables','menus','orders/','orders/%s/detail'%oid,'kitchen/menu-summary','stats/menu-counts','stats/dashboard']
emit('anonymous',create=r.status_code,reads={p:c.get('/orders/'+p+'/' if p in ('tables','menus') else '/orders/api/'+p).status_code for p in reads},progress=c.patch('/orders/api/orders/items/%s/progress'%iid,json.dumps({'done':True}),content_type='application/json').status_code,status=c.patch('/orders/api/orders/%s/status'%oid,json.dumps({'status':'CANCELLED'}),content_type='application/json').status_code)
c.patch('/orders/api/orders/%s/status'%oid,json.dumps({'status':'PREPARING'}),content_type='application/json')
s=c.session;s['role']='ORDER';s.save()
emit('wrong-role-order',progress=c.patch('/orders/api/orders/items/%s/progress'%iid,json.dumps({'done':False}),content_type='application/json').status_code)
c.cookies.clear()
a=create().json();b=create().json();emit('duplicate',ids=[a['id'],b['id']],numbers=[a['order_no'],b['order_no']])
for amount in (0,1,-1,1.9):
 before=Order.objects.count();r=create(received_amount=amount)
 emit('payment',input=amount,status=r.status_code,new_rows=Order.objects.count()-before,total=r.json().get('total_price') if r.status_code==201 else None,received=r.json().get('received_amount') if r.status_code==201 else None)
r=create(items=[{'menu_item_id':m.id,'qty':1.9}]);emit('fractional-qty',status=r.status_code,qty=r.json().get('items',[{}])[0].get('qty'))
for body in ([],{'floor':3},base|{'is_takeout':True},base|{'order_type':'TAKEOUT','table_number':101}):
 before=Order.objects.count();r=c.post('/orders/api/orders/',json.dumps(body),content_type='application/json');emit('malformed',input_type=type(body).__name__,fields=list(body) if isinstance(body,dict) else [],status=r.status_code,new_rows=Order.objects.count()-before)
# Explicit resurrection, not a concurrency simulation.
c.patch('/orders/api/orders/%s/status'%oid,json.dumps({'status':'CANCELLED'}),content_type='application/json')
r=c.patch('/orders/api/orders/%s/status'%oid,json.dumps({'status':'PREPARING'}),content_type='application/json');emit('cancel-resurrection',status=r.status_code,state=r.json())
# Cached table after an administrator update.
Table.objects.filter(pk=t.pk).update(is_active=False,name='renamed')
r=create();emit('stale-table',status=r.status_code,returned_name=r.json().get('table',{}).get('name'),db_active=Table.objects.get(pk=t.pk).is_active)
Table.objects.filter(pk=t.pk).update(is_active=True)
# Admin-like model edits, with separate source evidence for admin allowing them.
it=OrderItem.objects.get(pk=iid);it.qty=3;it.save();oo=Order.objects.get(pk=oid);emit('total-drift',stored=oo.total_price,items=sum(x.line_total for x in oo.items.all()))
# Force child creation failure: outer atomic must remove the parent too.
before=Order.objects.count()
with patch.object(OrderItem.objects,'bulk_create',side_effect=IntegrityError('analysis injected')): r=create()
emit('atomic-rollback',status=r.status_code,new_rows=Order.objects.count()-before)
# Legacy payments only; fixed event day isolates baseline issues.
Order.objects.all().delete()
legacy=Order.objects.create(table=t,floor='B1',order_type='DINE_IN',status='READY',payment_method='CASH',received_amount=5000,total_price=5000,order_date=datetime.date(2025,10,18),order_no=1)
OrderItem.objects.create(order=legacy,menu_item=m,qty=1,unit_price=5000)
r=c.get('/orders/api/stats/dashboard?start_date=2026-09-06&end_date=2026-09-06');emit('dashboard-legacy',status=r.status_code,exception=str(r.exc_info[1]) if r.exc_info else None,data=r.json() if r.status_code==200 else None,detail_cash=c.get('/orders/api/orders/%s/detail'%legacy.id).json()['received_cash_amount'])
# Old active hall work + 80 newer takeout; no concurrency implied.
Order.objects.all().delete()
hall=create().json()
for i in range(80):create(order_type='TAKEOUT',table_number='101',items=[{'menu_item_id':m.id,'qty':1,'mode':'TAKEOUT'}])
for limit in (1,80,200):
 with CaptureQueriesContext(connection) as ctx:r=c.get('/orders/api/orders/?floor=B1&limit=%s'%limit)
 emit('query-list',limit=limit,count=r.json()['count'],queries=len(ctx),bytes=len(r.content),hall_visible=hall['id'] in [x['id'] for x in r.json()['results']])
for path in ('orders/%s/detail'%hall['id'],'kitchen/menu-summary','stats/menu-counts','stats/dashboard','menus','menus'):
 with CaptureQueriesContext(connection) as ctx:r=c.get('/orders/menus/' if path=='menus' else '/orders/api/'+path)
 emit('query-read',path=path,status=r.status_code,queries=len(ctx),bytes=len(r.content))
# Two mocked Seoul dates, real SQLite counter.
nums=[]
for day in (datetime.date(2026,9,6),datetime.date(2026,9,7)):
 oo=Order.objects.create(table=t,floor='B1',order_type='DINE_IN')
 with patch('orders.services.numbering.timezone.localdate',return_value=day):allocate_floor_order_no(oo)
 nums.append([str(oo.order_date),oo.order_no])
emit('sqlite-dates',values=nums)
# Parse all tracked templates and rendered inline scripts, no browser execution.
files=subprocess.check_output(['git','ls-files']).decode().splitlines();templates=[p for p in files if '/templates/' in p]
script_count=0
for f in templates:
 name=f.split('/templates/',1)[1];tpl=get_template(name)
 if name=='orders/role_select.html':
  try:tpl.render({})
  except Exception as e:emit('unrouted-template',file=f,error=type(e).__name__)
  continue
 html=tpl.render({'supabase_url':'','supabase_anon_key':'','mode_scope':'ALL','page_title':'analysis','page_hint':'analysis'})
 for n,script in enumerate(re.findall(r'<script\b[^>]*>(.*?)</script>',html,re.S|re.I)):
  if not script.strip():continue
  out=pathlib.Path('.venv/analysis-20260906')/(pathlib.Path(f).stem+str(n)+'.js');out.write_text(script)
  result=subprocess.run(['node','--check',str(out)],capture_output=True,text=True)
  emit('inline-js',file=f,script=n,exit=result.returncode,error=result.stderr[:300]);script_count+=1
emit('templates',count=len(templates),scripts=script_count)
```

</details>

<details>
<summary>probe_extra.py</summary>

<!-- analysis-script: probe_extra.py -->
```python
import os,sys,pathlib,json,logging
sys.path.insert(0,str(pathlib.Path.cwd()))
os.environ.pop('DATABASE_URL',None)
os.environ.update(DJANGO_SETTINGS_MODULE='bazaar_kiosk.settings',DEBUG='0',SECRET_KEY='analysis-only-'+'x9!aB7'*12,ALLOWED_HOSTS='testserver',SUPABASE_URL='',SUPABASE_ANON_KEY='')
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
logging.disable(logging.CRITICAL)
from django.test import Client,override_settings,RequestFactory
from django.core.management import call_command
from django.core.cache import cache
from django.db.models import Sum
from orders.models import Order,Table
from orders.views import api
call_command('migrate',verbosity=0,interactive=False)
c=Client(enforce_csrf_checks=True,raise_request_exception=False)
with override_settings(DEBUG=True,ROLE_PINS={'ORDER':'analysis-noncredential-marker'}):
 r=c.post('/orders/api/orders/','[]',content_type='application/json')
 print(json.dumps({'case':'debug-settings-disclosure','status':r.status_code,'synthetic_marker_in_response':b'analysis-noncredential-marker' in r.content}))
cache.clear()
a=c.head('/orders/menus/').status_code;b=c.get('/orders/menus/').status_code;z=c.head('/orders/menus/').status_code
print(json.dumps({'case':'menu-head-cache','cold_head':a,'get':b,'warm_head':z}))
_,start,end=api._filtered_orders(RequestFactory().get('/',{'start_date':'2026-09-06','end_date':'2026-09-06'}))
print(json.dumps({'case':'fixed-date-helper','start':str(start),'end':str(end)}))
t=Table.objects.create(number=1);o=Order.objects.create(floor='B1',order_type='DINE_IN',table=t,payment_method='CASH',received_amount=5000,total_price=5000)
print(json.dumps({'case':'legacy-split-aggregate','detail_cash':api._serialize_order(o)['received_cash_amount'],'aggregate':Order.objects.filter(pk=o.pk).aggregate(cash=Sum('received_cash_amount'))}))
```

</details>

<details>
<summary>probe_pg.py</summary>

<!-- analysis-script: probe_pg.py -->
```python
import os,sys,pathlib,json,datetime,io,logging
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(pathlib.Path.cwd()))
os.environ.update(DJANGO_SETTINGS_MODULE='bazaar_kiosk.settings',DATABASE_URL=f"postgresql://postgres@127.0.0.1:{int(os.environ['BK_ANALYSIS_PORT'])}/bk_analysis?sslmode=disable",DEBUG='0',SECRET_KEY='analysis-only-'+'x9!aB7'*12,ALLOWED_HOSTS='testserver,127.0.0.1',SUPABASE_URL='',SUPABASE_ANON_KEY='')
import django
django.setup()
from django.conf import settings
from django.db import connection,transaction,connections
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from orders.models import Table,MenuItem,Order
from orders.services.numbering import allocate_floor_order_no
logging.disable(logging.CRITICAL)
def emit(name,**kw): print(json.dumps({'case':name,**kw},ensure_ascii=False),flush=True)
assert connection.settings_dict['HOST']=='127.0.0.1' and connection.settings_dict['NAME']=='bk_analysis'
with connection.cursor() as cur:cur.execute('SELECT version()');emit('version',value=cur.fetchone()[0])
try:call_command('migrate',verbosity=0,interactive=False)
except Exception as e:emit('fresh-migrate',error=type(e).__name__,message=str(e))
with connection.cursor() as cur:
 cur.execute("SELECT name FROM django_migrations WHERE app='orders' ORDER BY name DESC LIMIT 1");emit('migration-head',migration=cur.fetchone()[0])
# Explicit synthetic nonempty 0019 fixture. Does not repair or fake empty migration.
t=Table.objects.create(number=1);m=MenuItem.objects.create(name='pg-analysis',price=5000)
seed=Order.objects.create(floor='B1',order_type='DINE_IN',table=t,order_date=datetime.date(2026,9,5),order_no=40)
call_command('migrate',verbosity=0,interactive=False);emit('nonempty-0019-upgrade',result='pass',seed_order_no=40)
values=[]
for day in (datetime.date(2026,9,6),datetime.date(2026,9,7)):
 with transaction.atomic():
  o=Order.objects.create(floor='B1',order_type='DINE_IN',table=t)
  with patch('orders.services.numbering.timezone.localdate',return_value=day):allocate_floor_order_no(o)
  values.append([str(o.order_date),o.order_no])
emit('pg-dates',values=values)
# Force same-day sequence collision, reproduces broken outer atomic retry.
conflict=Order.objects.create(floor='B1',order_type='DINE_IN',table=t,order_date=timezone.localdate(),order_no=100)
with connection.cursor() as cur:cur.execute("SELECT setval('orders_floor_b1_seq',100,false)")
before=Order.objects.count()
try:
 with transaction.atomic():
  o=Order.objects.create(floor='B1',order_type='DINE_IN',table=t)
  allocate_floor_order_no(o)
except Exception as e:emit('sequence-collision',error=type(e).__name__,message=str(e),new_rows=Order.objects.count()-before)
with connection.cursor() as cur:cur.execute("SELECT setval('orders_floor_b1_seq',200,true)")
base={'floor':'B1','order_type':'DINE_IN','table_number':'1','payment_method':'CASH','received_amount':5000,'items':[{'menu_item_id':m.id,'qty':1}]}
def create(i):
 try:
  c=Client(enforce_csrf_checks=True,raise_request_exception=False)
  r=c.post('/orders/api/orders/',json.dumps(base),content_type='application/json')
  return {'status':r.status_code,'no':r.json().get('order_no') if r.status_code==201 else None}
 finally:connections.close_all()
with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(create,range(16)))
emit('16-requests-8-workers',results=results,unique=len({r['no'] for r in results}))
c=Client(enforce_csrf_checks=True,raise_request_exception=False)
r=c.get('/orders/api/stats/dashboard');emit('pg-dashboard',status=r.status_code,error=str(r.exc_info[1]) if r.exc_info else None)
```

</details>

<details>
<summary>probe_pg_legacy.py</summary>

<!-- analysis-script: probe_pg_legacy.py -->
```python
import os,sys,pathlib,json
sys.path.insert(0,str(pathlib.Path.cwd()))
os.environ.update(DJANGO_SETTINGS_MODULE='bazaar_kiosk.settings',DATABASE_URL=f"postgresql://postgres@127.0.0.1:{int(os.environ['BK_ANALYSIS_PORT'])}/bk_analysis_legacy?sslmode=disable",DEBUG='0',SECRET_KEY='analysis-only-'+'x9!aB7'*12,ALLOWED_HOSTS='testserver',SUPABASE_URL='',SUPABASE_ANON_KEY='')
import django
django.setup()
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
assert connection.settings_dict['HOST']=='127.0.0.1' and connection.settings_dict['NAME']=='bk_analysis_legacy'
old=('orders','0018_alter_order_floor_alter_order_order_type_and_more');new=('orders','0019_remove_order_orders_table_rule_and_more')
e=MigrationExecutor(connection);e.migrate([old]);apps=e.loader.project_state([old]).apps
O=apps.get_model('orders','Order');T=apps.get_model('orders','Table')
o=O.objects.create(floor='B1',order_type='TAKEOUT',table=None)
try:MigrationExecutor(connection).migrate([new])
except Exception as err: print(json.dumps({'case':'legacy-null-takeout-forward','error':type(err).__name__,'message':str(err),'row_preserved':O.objects.filter(pk=o.pk).exists()}))
# Separate synthetic valid seed for reverse compatibility, after recorded forward failure.
o.delete();t=T.objects.create(number=101)
MigrationExecutor(connection).migrate([new])
e=MigrationExecutor(connection);apps=e.loader.project_state([new]).apps;O=apps.get_model('orders','Order')
o=O.objects.create(floor='B1',order_type='TAKEOUT',table_id=t.pk)
try:MigrationExecutor(connection).migrate([old])
except Exception as err:print(json.dumps({'case':'takeout-table-reverse','error':type(err).__name__,'message':str(err),'row_preserved':O.objects.filter(pk=o.pk).exists()}))
```

</details>

## 최종 의사결정 권고

**선택: 점진적 현대화.** 현재 Django를 유지하면서 테스트 가능한 경계를 만들고 위험 순서대로
수정하는 편이 가장 작은 검증·이행 범위를 제공한다. 이 권고는 proposed이며 사용자 승인으로
기록하지 않았다. 사용자 지정 자체 SSE 전환은 이 점진적 경로 안에서 수행할 수 있다.
D-018의 전송 방향·D-020의 Compose PostgreSQL 방향과 D-019/021/022의 상세 제안을 구분한다.
EC2 단일 호스트는 중단/복구 목표가 맞을 때의 첫 후보이며 데이터 이전의 위험을 프레임워크 재작성과
묶을 근거는 없다. 기존 DB의 객체·금액·번호를 보존하는 이전과 운영 복원성을 별도로 검증한다.

| 선택지 | 근거·장점 | 비용·위험 | 이번 판단 |
| --- | --- | --- | --- |
| 점진적 현대화 | 작은 앱, 원자적 생성·가격 스냅샷·사전 로딩·정상PG번호할당 보존 가능 | 과거 데이터·두 쓰기 경로·호환 계약을 단계적으로 다뤄야 함 | **권고** |
| 부분 교체 | 안정된 API 뒤 UI 또는 조회 계층만 교체 가능 | 지금 API 권한·상태·결제 계약이 미확정이라 먼저 교체하면 오류를 옮길 수 있음 | 단계9 이후 D-009/측정으로 재평가 |
| 완전 v2 재구축 | 제품/운영 방식의 큰 변경이 확정될 때 구조 선택 폭이 큼 | 인증·정산·번호·데이터 이전·동시운영·롤백을 모두 다시 검증; 현행 테스트0 | 현 증거로 정당화되지 않음 |

다음 [프롬프트02](prompts/02_REVIEW_BLUEPRINT.md)에서 청사진을 증거와 대조하되, 이번 단계에서는
청사진 자체를 고치지 않았다. 검토할 제안은 다음과 같다.

1. 단계1에0019 정방향/역방향 제약 실패와0020 신규 bootstrap을 함께 매핑하고 D-008/D-017을
   선행 게이트로 둔다. fixture와 데이터 인벤토리 확보는 복구 전략 결정 전에 가능하다.
2. 단계2의 로컬 특성화·권한 회귀 설계는 PG bootstrap 복구 결정과 병행할 수 있도록 검토한다.
   PG 성공을 요구하는 CI 종료 게이트는 유지한다. 보안 결함의 시급성을 단계1 대기로 숨기지 않는다.
3. 단계3·4A의 익명 쓰기와 DEBUG PIN 노출을 먼저 차단할 수 있는 작은 승인 범위를 검토한다.
   보안 롤백은 기존 취약 경계를 복원할 수 없다. 이번 분석은 해당 변경이나 배포를 승인하지 않는다.
4. BK-R016은 정책과 분리 가능한 통계 실행 결함이다. 정상 응답 특성화와 최소 수정 단위를
   단계8 전체의 긴 선행 의존성과 분리할지 검토한다. 이후 날짜·레거시·순수납 정확성 게이트는
   별도로 남겨야 한다.
5. 44개 위험의 담당 단계를 누락 없이 이어간다. 기존 BK-R012~034의 재접속·응답 역전,
   과거 데이터·정산 정의·SLO에 더해 BK-R035~040의 SSE 실행/전달/복구/권한/운영 관문을 매핑한다.
6. D-018의 자체 SSE 방향을 반영하고 D-019의 상세 전달 계약을 결정한다. 4B의 외부 SDK 제거와
   10의 SSE·11의 UI 전환을 조정하고, 최소 ASGI/프록시 검증은10에 선행시킨다. 영속 변경 감지는
   5/6/7의 writer와8/9의 snapshot 계약을 연결한다. 안전한 자체 폴링을 SSE 전환·롤백 경로로 둔다.
7. D-020의 Compose PostgreSQL과 EC2 후보를 반영해 컨테이너/환경 기반·데이터 이전·백업 복원을
   작은 검토 단위로 나눈다. BK-R041~044를4A/12A에 연결하고, 실제 이전 전에 원본 writer 동결과
   신규 쓰기 전후의 복구 경계를 검증한다. SSE 폴링은 클라우드/행사망 장애의 오프라인 해법이 아니다.

사용자에게 필요한 결정은 [DECISIONS.md](DECISIONS.md)의 담당자·근거 표에 있다. 우선 D-002/003
노출·역할, D-004/005 번호·금전, D-006/008/017 운영DB·보존·마이그레이션 복구, D-014/015
슬롯·혼합주문·취소 전이를 확정해야 한다. D-001 원격 Git 정리는 독립된 승인 작업이며,
D-007/009/010/012/013/016/019는 해당 성능·UI·실시간·정산·보고·복구 단계의 게이트로 유지한다.
D-018/020은 이미 사용자에게서 받은 방향이므로 동일한 SSE/Compose DB 선택을 다시 묻지 않는다.
EC2 확정·중단/RPO/RTO·원본 데이터 보존/전환은 D-021/022와 기존 담당 결정에서 확정한다.
D-023의 세 기능 영역 명칭은 다음 청사진에 반영하고, D-024의 지상/부스 삭제·보존 범위와
관리자 세부 권한은 미정으로 유지한다. 명칭 정리를 데이터 삭제나 역할 병합의 승인으로 확대하지 않는다.
분석의 성공을 운영 안전성이나 모든 위험의 해결로 바꾸어 해석하지 않는다.
