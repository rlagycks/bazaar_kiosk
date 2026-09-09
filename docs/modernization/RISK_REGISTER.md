# Bazaar Kiosk 위험 등록부

최종 검증: 2026-09-09 · 기준 HEAD: `2d5bb78`(분석) · 사용자 위험 수용 없음
44개 모두 종료되지 않았다. BK-R005는 운영 확인 대기, BK-R016은 실행성 수정 후2B 이후 인수 대기다.

총44개(Critical1/High30/Medium13). BK-R035~040은 SSE, BK-R041~044는 Compose DB·인프라
이전의 선행 조건·설계·운영 위험이다. 신규 구성의 장애를 재현했다고 판정하지 않는다.
D-018/020의 사용자 방향도 위험 수용이나 해결이 아니다.

1A 후속: 전용 PG15.18에서7개 경로를 검증해 BK-R005/017의 실패·행/이력 보존을 재확인했다.
당시에는 신규 설치를 고친 것이 아니므로 모두 Open이었다. 명령은 [PG 안내](POSTGRES_TESTING.md)에 있다.

1B 후속(2026-09-08): D-P07 승인으로0020을 수정해 BK-R005의 신규 설치 중단을 저장소에서 해소했다.
빈/NULL/0/양수40/재적용/이미적용/동명sequence/실패 원자성을 실제 PG에서 확인했고,
수정 전 SQL이 여전히22003으로 실패함도 같은 suite에 고정했다. 다만 운영 DB의 실제 적용 기록·
sequence 상태와 운영 적용 리허설은 미확인이므로 종료로 처리하지 않는다.
BK-R017과0019 정책은 그대로 Open이며 BK-R003의 일일 번호 미초기화도 남아 있다.
근거는 [적용 기록](MIGRATION_REPAIR_REVIEW.md)에 있다.

2A 후속: 정상 특성화8개와 환경 격리1개가 추가되었다. 가격/atomic 변이를 검출했지만
PG 검증·CI 실행 강제가 남아 BK-R004는 Open이다. 초기 테스트0개는 분석 당시 증거이며
현재 구현 결과는 [테스트 안내](TESTING.md)와 [작업 로그](WORKLOG.md)를 따른다.

8A 후속(2026-09-09): 별칭 수정3줄과 회귀7개로 빈/단일/다중/제외 조건의200·합계를
PG에서 검증했다. SQLite 결과는 최초4개 회귀의 과거 검증이다.2B 이후 인수 관문은 유지한다. 날짜·레거시 결제·동명 메뉴·순매출 정책은
변경하지 않았다. [실행성 기록](DASHBOARD_EXECUTION.md)을 따른다.

각 행은 하나의 안정적인 위험 ID다. 심각도 순위(1이 가장 높음), 심각도, 증거 상태,
선행 결정/위험, 담당 역할, **주 담당 블루프린트 단계**를 독립 열로 두었다.
표 전체를 스프레드시트로 가져와 각 열로 정렬할 수 있다. 현재는 심각도→단계→ID 순서다.
담당은 제안 역할이며 개별 인력 배정이 아니다. 단계 변경 제안은 프롬프트02에서 검토한다.

Reproduced는 기재된 로컬 조건의 재현이며 해결 상태가 아니다. Production-dependent는 외부
환경/운영 데이터가 필요하고 Hypothesis는 측정 전 가설이다. Repo-fixed는 저장소 코드에서
원인을 제거하고 회귀로 고정했다는 뜻이며, 해당 단계의 최종 인수·운영 확인 전까지 해결 상태는 Open으로 둔다.
심각도와 증거 확신은 별개다.
각 행의 링크에 파일/줄·재현·영향·시나리오·최소 개선·회귀시험·확신/미확인을 모두 보관했다.

| 순위 | ID / 발견 | 심각도 | 증거 상태 | 해결 상태 | 선행 결정·의존성 | 담당 역할 | 주 단계 | 종료에 필요한 증거 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | [BK-R001 — API 역할 인가 부재와 변경 API CSRF 면제](ANALYSIS_REPORT.md#bk-r001) | Critical | Reproduced | Open | D-003; 단계 2 | 보안 담당 | 3 | 모든 역할/익명/만료 세션, CSRF 없음·오류·유효, GET/POST/PATCH/HEAD 경계 |
| 2 | [BK-R005 — 빈 PostgreSQL에서 0020 마이그레이션 중단](ANALYSIS_REPORT.md#bk-r005) | High | Repo-fixed | Open (운영 확인 대기) | D-006,D-008,D-017 | 데이터·운영 담당 | 1 | PG 빈 DB 전체 체인, null/빈 번호, 기존 양수번호 DB, 이미0020 적용 경로·롤백 |
| 2 | [BK-R017 — 과거 스키마 축소와 신규 제약의 데이터 호환성 미검증](ANALYSIS_REPORT.md#bk-r017) | High | Reproduced | Open | D-006,D-008,D-017 | 데이터·운영 담당 | 1 | 0018 시점 F1/BOOTH/포장null fixture→0019, 정제복사본 dry-run·백업복원·구앱 호환 |
| 2 | [BK-R004 — 동작 테스트 0개와 실행을 강제하지 않는 CI](ANALYSIS_REPORT.md#bk-r004) | High | Reproduced | Open | D-006,D-008; 단계 1 | 테스트 담당 | 2B | 2A 로컬 특성화·가격/atomic 변이 검출 완료; PG CI 및 회귀 감지 강제 필요 |
| 2 | [BK-R002 — 공개된 기본 역할 PIN·개발 설정으로 시작 가능](ANALYSIS_REPORT.md#bk-r002) | High | Code-supported | Open | D-002,D-006; 단계 3 | 보안·운영 담당 | 4A | 설정 누락 시작 실패, 잘못된 PIN 반복, 공개 프록시/HTTPS 설정 |
| 2 | [BK-R028 — DEBUG 오류 페이지가 환경에서 설정한 역할 PIN도 노출](ANALYSIS_REPORT.md#bk-r028) | High | Reproduced | Open | D-002,D-006; 단계 3 | 보안·운영 담당 | 4A | 합성 자격증명으로500 HTML/JSON·로그에 값이 없는지, env누락 실패 |
| 2 | [BK-R043 — Compose 환경·secret·DB TLS 계약과 현재 settings의 불일치](ANALYSIS_REPORT.md#bk-r043) | High | Code-supported | Open | D-006,D-020,D-021; BK-R002/022; 단계 2,3 | 설정·보안·인프라 담당 | 4A | URL 누락/빈 값·_FILE만·실제 secret 읽기·잘못된 DB·기본 SSL/명시 TLS/CA·재시작 후 동일 DB와 앱 권한 확인 |
| 2 | [BK-R044 — 자체 DB의 공인 포트·권한·비밀 전달 경계 구성 누락 가능성](ANALYSIS_REPORT.md#bk-r044) | High | Hypothesis | Open | D-002,D-003,D-006,D-020,D-021; BK-R001/002/028; 단계 3 | 보안·인프라 담당 | 4A | 외부 DB/ASGI 차단·신뢰 헤더 위조·앱 DDL/superuser 거부·이미지/config/log secret 검사·IAM/SSM/DB 권한 회수·기존 DB 비밀번호 교체 |
| 2 | [BK-R011 — 저장 문자열이 실행 가능한 HTML·인라인 핸들러에 보간](ANALYSIS_REPORT.md#bk-r011) | High | Code-supported | Open | 단계 2,3 | 프런트·보안 담당 | 4B | 메뉴/테이블/메모의 HTML·따옴표·백슬래시·유니코드 payload 브라우저 검증 |
| 2 | [BK-R018 — Supabase 익명 구독의 RLS·이벤트 노출 경계 미확인](ANALYSIS_REPORT.md#bk-r018) | High | Production-dependent | Open | D-010; 단계 3 | 보안·운영 담당 | 4B | 전환 전 외부 권한 검증, D-018 전환 후 외부 요청/키0·외부 노출 정리·자체 SSE 인가 |
| 2 | [BK-R003 — PostgreSQL 날짜별 번호 계약 차이 및 충돌 재시도 실패](ANALYSIS_REPORT.md#bk-r003) | High | Reproduced | Open | D-004,D-006; 단계 1,2 | 데이터 담당 | 5 | PG 자정/충돌/재시도/실패·동시 생성; 기존 번호·날짜 데이터와 호환 |
| 2 | [BK-R012 — 재전송·중복 제출에 멱등성 경계 없음](ANALYSIS_REPORT.md#bk-r012) | High | Reproduced | Open | D-007,D-008; 단계 5 | 주문 담당 | 6 | 더블탭/timeout후 재전송/병렬동일키/다른payload/키만료 |
| 2 | [BK-R013 — 취소에서 활성으로 전환 가능·상태 명령 간 경합](ANALYSIS_REPORT.md#bk-r013) | High | Reproduced | Open | D-015,D-003; 단계 5 | 주문 담당 | 6 | 취소후 progress/직접상태/관리자, 취소와 완료 경합, stale absolute progress |
| 2 | [BK-R007 — 레거시 결제 분할 합계와 상세 응답 불일치](ANALYSIS_REPORT.md#bk-r007) | High | Reproduced | Open | D-005,D-008,D-012; 단계 6 | 재무·데이터 담당 | 7 | 0017 이전 CASH/TICKET 행과 0017 이후 혼합 결제·분할 누락 행, 원본/분할/보고 합계 대조·되돌림 |
| 2 | [BK-R008 — 관리자 항목 수정으로 저장 합계와 품목 합계 이탈](ANALYSIS_REPORT.md#bk-r008) | High | Reproduced | Open | D-011,D-005; 단계 6 | 재무·백엔드 담당 | 7 | 실제 관리자 form POST 추가·수정·삭제·상태, 가격 스냅샷/합계/번호 |
| 2 | [BK-R014 — 부족 결제·소수 입력을 정상 주문으로 승인](ANALYSIS_REPORT.md#bk-r014) | High | Reproduced | Open | D-005,D-012; 단계 6 | 재무 담당 | 7 | 0/부족/초과/음수/float/bool/오버플로/복합 필드/메뉴 가격 변경 |
| 2 | [BK-R030 — 수납·거스름돈·취소 환불·순매출 계약 미확정](ANALYSIS_REPORT.md#bk-r030) | High | Code-supported | Open | D-005,D-012; 단계 6 | 재무·제품 담당 | 7 | 초과현금·과다식권·혼합거스름·취소전후·부분환불·레거시미분류 |
| 2 | [BK-R031 — 과거 삭제·재추가 필드와 카테고리의 복구 원천 미확인](ANALYSIS_REPORT.md#bk-r031) | High | Production-dependent | Open | D-008,D-012,D-017; 단계 1 | 데이터·재무 담당 | 7 | 정제된과거버전fixture·행수/금액대조·백업복원·정방향완화 |
| 2 | [BK-R006 — 통계 기간이 2025-10-18로 고정](ANALYSIS_REPORT.md#bk-r006) | High | Reproduced | Open | D-013; BK-R016 | 조회·보고 담당 | 8 | 무기간/하루/범위/잘못된 날짜/자정/양 끝 경계 |
| 2 | [BK-R009 — 최신 80개 이후 오래된 주방 대기 작업 누락](ANALYSIS_REPORT.md#bk-r009) | High | Reproduced | Open | D-003,D-010,D-014; 단계 3,6 | 조회 담당 | 8 | 혼합·단일모드 81/200초과 backlog의 초기/폴링/재접속 |
| 2 | [BK-R010 — 프로세스별 테이블 객체 캐시가 비활성화를 무시](ANALYSIS_REPORT.md#bk-r010) | High | Reproduced | Open | D-014; 단계 3,6 | 조회 담당 | 8 | 관리자 수정 전/후·다중 워커·TTL·삭제/비활성 재조회 |
| 2 | [BK-R016 — 통계 aggregate alias 충돌로 SQLite·PG 모두 500](ANALYSIS_REPORT.md#bk-r016) | High | Repo-fixed | Open (2B 이후 인수 대기) | BK-R004; D-013,D-012 | 조회·보고 담당 | 8 | 빈DB/한행/동명메뉴/기간/취소/레거시 데이터의 endpoint200와 정확한 합계 |
| 2 | [BK-R020 — Realtime 연결 상실 후 폴링 복귀·재동기화 부재](ANALYSIS_REPORT.md#bk-r020) | High | Code-supported | Open | D-010,D-007; 단계 4B,8,9 | 실시간 담당 | 10 | SUBSCRIBED이후 CLOSED/ERROR/TIMEOUT, duplicate/out-of-order/drop, 느린응답·재접속 |
| 2 | [BK-R033 — 주방 목록·단건 응답 순서 역전 방어 부족](ANALYSIS_REPORT.md#bk-r033) | High | Code-supported | Open | D-010; 단계 8,9 | 실시간 담당 | 10 | 완료단건뒤stale목록,진행2뒤0응답,삭제뒤늦은응답·중복ID이벤트 |
| 2 | [BK-R035 — 자체 SSE 실행에 필요한 비동기 경로·워커 조건 미확립](ANALYSIS_REPORT.md#bk-r035) | High | Code-supported | Open | D-006,D-018,D-019; BK-R001/019 | 실시간·운영 담당 | 10 | 실제 ASGI HTTP 스트림·일반 API 병행, 동기 middleware 적응/스레드·워커 수·disconnect/reload 정리 |
| 2 | [BK-R036 — SSE 변경 감지의 writer 누락·커밋 후 유실 가능성](ANALYSIS_REPORT.md#bk-r036) | High | Hypothesis | Open | D-008,D-011,D-018,D-019; 단계 5,6,7 | 데이터·실시간 통합 담당 | 10 | 생성/상태/항목/관리자/bulk/update/삭제/메뉴·테이블, rollback·커밋 직후 kill·다른 워커 구독·revision 행 누락 |
| 2 | [BK-R037 — SSE cursor와 snapshot 불일치로 최신 상태 복구 실패 가능성](ANALYSIS_REPORT.md#bk-r037) | High | Hypothesis | Open | D-010,D-019; BK-R009/033; 단계 8,9 | 조회·실시간 통합 담당 | 10 | 구독 등록 중 변경, snapshot 중 커밋, ID10/11 역전, HTTP 실패 후 재접속, 늦은 응답·81/201건·DB 복원 |
| 2 | [BK-R038 — 장기 SSE의 세션 회수·범위 정보 노출 경계 누락 가능성](ANALYSIS_REPORT.md#bk-r038) | High | Hypothesis | Open | D-002,D-003,D-010,D-019; BK-R001/019; 단계 3,4A | 보안·실시간 담당 | 10 | 익명/오역할·scope 위조·다른 역할 cursor·다중탭 역할 변경·로그아웃/만료/PIN 회수 중 열린 연결·인증 저장소 장애 |
| 2 | [BK-R022 — 배포·상태확인·복원·롤백 증거와 운영 계측 부재](ANALYSIS_REPORT.md#bk-r022) | High | Code-supported | Open | D-006,D-008,D-016; 단계 4A,5,6,7,10,11 | 운영 담당 | 12A | 정제 복사본 복원시간·schema/oldapp rehearsal·PG불가/잘못된 env·release smoke |
| 2 | [BK-R041 — 자체 DB 저장소·백업·단일 호스트 복구 경계 미확정](ANALYSIS_REPORT.md#bk-r041) | High | Production-dependent | Open | D-006,D-007,D-016,D-020,D-021,D-022; BK-R022/039 | DB·인프라 운영 담당 | 12A | 컨테이너 재생성/재부팅·mount 누락 거부·새 호스트 restore·행/금액/번호와 시간 대조·disk full·백업/키 장애·행사망 단절 |
| 2 | [BK-R042 — DB 이전의 객체 누락·쓰기 분기·신규 주문 rollback 유실 가능성](ANALYSIS_REPORT.md#bk-r042) | High | Production-dependent | Open | D-004,D-008,D-016,D-017,D-020,D-022; BK-R003/005/012/017/031/037; 단계 1,5,6,7,10 | 데이터 이전 통합 담당 | 12A | 원본/대상 객체·행·합계·PK/FK/sequence 대조, migration 두 경로, 관리자/SQL 포함 쓰기 동결·old stream·새 쓰기 후 역이전/정방향 복구 |
| 3 | [BK-R021 — 재현되지 않는 의존성 범위와 지원 종료 버전 허용](ANALYSIS_REPORT.md#bk-r021) | Medium | Code-supported | Open | D-006 | 빌드·운영 담당 | 2 | 빈환경 재현·pip check·지원버전/보안패치 확인·PG CI |
| 3 | [BK-R019 — 역할 로그인 세션 교체·만료 정책 부재와 GET 로그아웃](ANALYSIS_REPORT.md#bk-r019) | Medium | Code-supported | Open | D-002,D-003 | 보안 담당 | 4A | 로그인 전후 session id, PIN 회수·교체 후 기존 세션 거부, 역할변경·만료·공유기기·logout method |
| 3 | [BK-R029 — 가변 CDN 스크립트와 콘텐츠 보안 정책 검증 부재](ANALYSIS_REPORT.md#bk-r029) | Medium | Code-supported | Open | D-010; BK-R011 | 보안·프런트 담당 | 4B | D-018 외부 CDN/SDK·키 제거, 자체 SSE/폴링만으로 주방 여정·CSP |
| 3 | [BK-R027 — 테이블 슬롯·항목 mode·포장 flag 의미 불명확](ANALYSIS_REPORT.md#bk-r027) | Medium | Code-supported | Open | D-014,D-008; 단계 5 | 제품·주문 담당 | 6 | 101~120/일반테이블 경계·혼합항목·flag조합 |
| 3 | [BK-R026 — order_date와 created_at·자정 주방 집계 경계 불일치](ANALYSIS_REPORT.md#bk-r026) | Medium | Code-supported | Open | D-004,D-013; 단계 5 | 조회·도메인 담당 | 8 | Seoul23:59:59→00:00,할당지연,전일대기,같은시각다른날짜 보고 |
| 3 | [BK-R034 — 현재 메뉴명으로 과거 주문 표시·동명 메뉴 합산](ANALYSIS_REPORT.md#bk-r034) | Medium | Code-supported | Open | D-008,D-012; 단계 7 | 조회·재무 담당 | 8 | 동명서로다른ID·이름변경·가격변경·레거시집계·취소 |
| 3 | [BK-R015 — JSON 입력 타입·테이블 분기 불일치가 500으로 노출](ANALYSIS_REPORT.md#bk-r015) | Medium | Reproduced | Open | D-014,D-008; 단계 6,7 | API 담당 | 9 | 누락/null/list/dict/정수/문자열/UTF8/메서드별 오류 계약 |
| 3 | [BK-R024 — API 뷰에 전송·쿼리·금액·명령이 집중](ANALYSIS_REPORT.md#bk-r024) | Medium | Code-supported | Open | D-008; 단계 8 | 백엔드 담당 | 9 | 현재/목표 응답 schema·예외 분류·쿼리수 회귀·관리자 writer 매핑 |
| 3 | [BK-R032 — 이벤트 단건 조회·전체 보드 렌더의 부하 상한 미측정](ANALYSIS_REPORT.md#bk-r032) | Medium | Hypothesis | Open | D-007,D-006,D-010; 단계 8,9 | 성능 담당 | 10 | 화면1/5/20,적체20/80/201,항목1/5/20,이벤트폭주·워커1/4 |
| 3 | [BK-R040 — SSE revision 잠금 경합과 조회·버퍼 부하 증가 가능성](ANALYSIS_REPORT.md#bk-r040) | Medium | Hypothesis | Open | D-006,D-007,D-019; BK-R032/035/036 | 데이터·성능 담당 | 10 | 생성과 진행/관리자 잠금 역순, 워커1/4·화면1/5/20·폭주·느린 소비자에서 lock/SQL/FD/RSS/p95/복구 지연 |
| 3 | [BK-R023 — 인라인 UI·실패 복구·접근성·미사용 화면의 유지보수 위험](ANALYSIS_REPORT.md#bk-r023) | Medium | Code-supported | Open | D-007,D-009; 단계 4B,8,9 | 프런트 담당 | 11 | 대상기기 viewport·키보드/터치/스크린리더·네트워크실패·기존 URL호환 |
| 3 | [BK-R039 — SSE 프록시 buffering·timeout·브라우저 연결 제약 미확인](ANALYSIS_REPORT.md#bk-r039) | Medium | Production-dependent | Open | D-006,D-007,D-010; BK-R035; 단계 10 | 운영·프런트 담당 | 12A | 실제 프록시 경유 프레임 flush·idle·reload, HTTP/1·HTTP/2/여러 탭·BFCache·백그라운드 복귀·fallback |
| 3 | [BK-R025 — 동일 트리와 고유 이력을 혼동한 Git 정리 위험](ANALYSIS_REPORT.md#bk-r025) | Medium | Reproduced | Open | D-001; 별도 원격 승인 | 저장소 관리자 | G | refs/trees/left-right/branch diff/내용검사·체크포인트 AGENTS 존재 |



## 기존 기준선에서 바뀐 판정

BK-R003/005는 PG15.18로 재현해 가설을 해소했다. BK-R003은 최초 치명적 후보에서 High로
정밀화했다(정상16건 번호고유·실패후 부모0행). BK-R006/007은 helper/aggregate 계층에서 재현했고
당시 정상 dashboard 응답은 BK-R016에 막혔다.8A에서 별칭 오류를 수정해 합성 DB 응답을 복구했다. BK-R008/009/010도 제한된 로컬 fixture 재현으로
격상했다. BK-R002는 기본값 존재와 운영 사용을 분리하여 High로 분류하고 DEBUG의 재정의된
PIN 노출을 BK-R028로 별도 등록했다. BK-R011은 브라우저 실행 미재현 상태를 유지한다.

## 단계 간 경계

D-023의 주문·서빙 / 주방 / 관리자 구분을 목표 명칭으로 사용한다. 현행 B1_COUNTER 통계는
관리자 영역으로 매핑하며 BK-R006/008/016/030/034의 통계·관리 무결성 위험을 보존한다.
BK-R023/024의 UI/API 정리는 D-003/008/024의 역할·URL·과거 데이터 호환과 연결한다.
지상/부스 흔적 정리만으로 위험을 종료하거나 source/floor·과거 migration을 삭제하지 않는다.
위험 개수·심각도·증거 상태는44개 그대로이며 새 제품 방향을 새 결함으로 세지 않는다.

BK-R015의 금액·상태 입력 검사는 단계6/7에서 먼저 다루고 오류 어댑터 통합은9가 주 담당이다.
BK-R017은 신규/기존 bootstrap의1, BK-R031의 과거 데이터 조정은7이 담당한다. BK-R028의
환경 사전검증은4A, 운영 관측·복원은12A다. 캐시/적체 정확성8과 성능10을 구분한다.
공통 선행 조건은 [BLUEPRINT.md](BLUEPRINT.md), 제품 결정은 [DECISIONS.md](DECISIONS.md),
실행·미실행 검사는 [WORKLOG.md](WORKLOG.md)를 따른다.

SSE 전환의 주 담당은 BK-R035~038/040의10, BK-R039의12A다. 다만 최소 ASGI·프록시 경로는
10에 선행하고, 3/4A의 인가·회수, 5/6/7의 writer, 8/9의 완전한 snapshot이 필요하다.
4B 외부 연결 제거와10/11 교체의 분할·자체 폴링 롤백은 다음 프롬프트02에서 청사진에 반영한다.

인프라 추가 위험은 BK-R043/044의4A(필수 설정·노출/권한 경계)와 BK-R041/042의12A(저장소·
복원·DB 이전)가 주 담당이다. DB/이미지의 신규 bootstrap은1/2, 최소 ASGI/proxy는10에 선행한다.
최종 실제 인프라 생성·DB 이전·전환은12B의 검토와 별도 실행 승인 이후이며 이번에는 분석만 수행했다.
