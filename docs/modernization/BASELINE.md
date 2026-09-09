# 레거시 기준선

후속1A 결과(2026-09-07): 전용 Compose PostgreSQL15.18에서7개 migration 경로를 검증했다.
0019/0020 실패 재현과 행·이력 보존을 확인했으며 당시 설치 결함은 미해결이었다.
후속1B(2026-09-08): D-P07 승인으로0020을 수정해 **빈 PG 설치 실패는 저장소에서 해소**했다.
0019의 과거 데이터 실패와 운영 확인은 남아 있다. 아래 기준선의0020 실패 서술은 수정 이전 관찰이다.
운영 DB와 다른 개발 컨테이너는 사용하지 않았다. [실행 안내](POSTGRES_TESTING.md), [적용 기록](MIGRATION_REPAIR_REVIEW.md).

후속2A 결과(2026-09-07): 현행 업무 코드를 보존한 상태로 정상 특성화8개·환경 격리1개를
추가했고 가격/atomic 변이 감지를 검증했다. 아래 테스트0개와 CI 결과는 초기 분석 시점의
기록이다. 최신 실행 방법·범위는 [TESTING.md](TESTING.md)를 따른다. PG/CI 위험은 미해결이다.

최종 검증일: 2026-09-07 · 기존 분석 + SSE/인프라 후속 증거 갱신

초기 앱 스냅샷: `origin/develop`의 `93a841a`, 트리 `de8b3f3712ea25209e2d9e94d044002b3e9e7bff`.
이번 분석 시작 HEAD: `2d5bb78`, 브랜치 `chore/astra-modernization-setup`.
앱·마이그레이션·의존성·CI는 위 앱 스냅샷과 같고 준비 문서 커밋2개만 더해졌다.
[전체 분석](ANALYSIS_REPORT.md), [위험 등록부](RISK_REGISTER.md), [작업 로그](WORKLOG.md)에
재현 절차·의존성·미검증 범위를 보관한다. 초기 위험 ID는 유지했다.

## 저장소와 환경

| 영역 | 현재 증거 |
| --- | --- |
| 스택 | Django 서버 렌더링, 바닐라 JS/CSS, PostgreSQL 또는 SQLite, 선택적 Supabase Realtime |
| 규모 | 초기 앱55파일/약4,753줄. 준비 문서 포함 이번 시작69파일/6,481줄; Python42개·템플릿7개 |
| 책임 집중 | api.py594줄, order.html535줄, kitchen_supervisor.html486줄 |
| 설치 환경 | 기존 .venv Python3.12.11, Django5.2.17, psycopg3.3.5, WhiteNoise6.10.0, Gunicorn26.2.0 |
| 재현성 | 열린 의존성 범위, lock 없음. 이번 작업에서는 설치·업그레이드 없음 |
| CI | Python3.12, 설치/check/drift만 실행. 실제 migrate/test/PG/JS/browser 없음 |
| 테스트 | 현재 테스트0개, `Found 0 test(s)`/`NO TESTS RAN`; 분석용 검사는 문서 부록에 별도 보관 |
| DB 설정 | DATABASE_URL이 있으면 PostgreSQL, 없으면 SQLite. `.env` 자동 로딩 없음 |
| 운영 | 실제 호스팅·배포명령·PG/Supabase 버전·워커·RLS·백업·복원·SLO는 미확인 |

일반 `python3` 대신 `.venv/bin/python`을 사용했다. 초기 준비에서 관찰된 시스템 Python3.9.6과
Django4.2.20은 CI 기준이 아니며 이번 검증 환경으로 사용하지 않았다.

## 이번 세션의 검사

검사 스크립트는 [분석 보고서의 재현 부록](ANALYSIS_REPORT.md)에 보관했다. SQLite는 메모리 DB,
PG는 기존 로컬 이미지로 만든 PostgreSQL15.18/aarch64 일회용 컨테이너다. 운영 DB, 기존
`db.sqlite3`, 실제 PIN·Supabase 키를 사용하지 않았다. 분석용 컨테이너는 제거했다.

| 검사 | 결과 |
| --- | --- |
| Django check / drift / pip check | 통과 / 변경 없음 / 충돌 없음 |
| 기존 test | 명령 정상 종료, 실행된 테스트0개 |
| 빈 SQLite 전체 migrate | orders0020까지 통과 |
| 배포 check | DEBUG=0·긴 진단 키 조건에서 W004(HSTS), W008(SSL redirect) 경고2개 |
| 빈 PostgreSQL 전체 migrate | **실패 재현**:0020 setval(0) 범위 위반, 적용 head0019 |
| 합성0019의 번호40 한 행→0020 | 해당 경로 통과; 전체 운영 업그레이드 증거 아님 |
| PG 번호 날짜 변경 | 9/6→9/7에41→42, 일일 초기화 없음 |
| PG 기존번호 충돌 | TransactionManagementError; 실패 후 부모 주문 증가0 |
| PG8스레드/16생성 | 모두201, 고유번호16개; 동일 요청도16주문이므로 멱등성 없음 |
| PG0018→0019 / 역방향 | 합성 포장행의 table NULL/있음 제약 충돌, 둘 다 IntegrityError·행 보존 |
| API/도메인 | 익명 생성·상태·진행, 오역할 진행, 부족결제, 취소복귀, stale테이블 재현 |
| dashboard | Django5.2.17 SQLite·PG 모두 aggregate 별칭 FieldError500 |
| DEBUG 자격증명 | 합성 ROLE_PINS marker가 오류 응답에 포함됨; 실제 값 미사용 |
| 정적 검사 | Python AST42·템플릿 compile7·렌더 inline JS5+app.js 구문 통과 |
| 미사용 role_select 렌더 | 없는 login_pin 때문에 NoReverseMatch; 활성 로그인과 구분 |
| 운영/브라우저/부하/복원 | 미실행. 코드·모의·로컬 DB 결과로 통과 처리하지 않음 |

## 초기 가정의 수정과 오탐 방지

- **BK-R003:** 초기 치명적 후보를 **High/Reproduced**로 정밀화했다. PG 일일 초기화 부재와
  충돌 복구 실패는 재현했지만 정상16건 번호고유·실패시 부모0행도 확인했다. 일일 초기화는
  코드 주석의 의도이며 D-004 사용자 승인 계약으로 바꾸어 기록하지 않았다.
- **BK-R005:** '안전하지 않을 수 있음'에서 **High/Reproduced**로 변경했다. 빈PG0020 실패를
  확인했으며 이후0021만 추가하는 방식으로 이 선행 실패를 우회할 수 없다.
- **BK-R006/007:** 날짜 helper와 독립 레거시 집계의 오류를 재현했다. 다만 정상 dashboard
  응답을 분석했다는 표현은 부정확하다. 새 **BK-R016** 별칭 충돌로 전체 endpoint가 먼저500이다.
- **BK-R008:** 허용된 관리자 편집과 같은 모델 저장 경로에서 저장5000/항목15000 불일치를
  확인했다. 실제 관리자 form 전체 실행은 미실행이다.
- **BK-R009/010:** 80개 cutoff와 비활성 테이블 캐시의201 생성을 재현했다. 실제 브라우저·
  다중 워커 부하까지 입증한 것은 아니다.
- **BK-R002:** 기본값은 공개되어 있으나 운영 사용 여부는 미확인으로 분리했다. **High**로
  분류하고, 환경에서 바꾼 PIN도 DEBUG 오류에 노출되는 **BK-R028**을 별도 등록했다.
- **BK-R011:** unsafe 문자열 sink는 코드 근거이며 브라우저 실행 미재현이다. 주방에는
  escapeHtml이 있다. 카운터 sink의 정상 응답 경로는 dashboard500 때문에 막혀 있다.
- 초기 배포 경고3개 중 약한 SECRET 경고는 진단용 키 조건에서 발생했던 것이다. 긴 진단
  키로 재검사한 경고는2개이며 운영 TLS 설정 확인까지 끝났다는 뜻은 아니다.
- FloorOrderCounter는 SQLite에서 **사용 중**이다. recalc_totals는 export만으로 실제 호출을
  입증하지 않는다. styles.css는 활성 자산이다. 미참조 파일을 일괄 삭제 대상으로 확정하지 않는다.
- 목록은1/80/81건에서 각각3쿼리였다. **목록 N+1이나 성능 향상을 주장하지 않는다.**
  예전 Git 커밋 제목의 '성능 최적화'도 측정 증거로 사용하지 않는다.
- RLS 비활성·Supabase 실제 유출·개발 SECRET에 의한 DB 세션 위조는 확인하지 않았다.

## Git 기준선 수정

- 현재70커밋/16merge: 초기68커밋에 로컬 준비2커밋이 추가됐다.
- 로컬 origin branch10개 + 심볼릭HEAD. main7/develop19 대칭차이와 동일 트리는 재확인했다.
- mergefix도 같은 트리지만 모든 오래된 브랜치의 내용이 같지는 않다. Megesfile/mergebe는
  날짜 조회 정책이 다르고, 오래된 chore branch에는 타 origin에 없는9개 커밋이 있다.
- 파일명 수준 초기 검사를 확장해410객체/187blob을 확인했다.173개 UTF-8 blob에 패턴 검사,
  14개 과거 pyc에는 실행 없이 ASCII 패턴 검사를 했다. 공개 기본값은 존재한다. DB URL2개는
  기호형 예시로 확인했으며 실제 유출로 세지 않았다. 전용 비밀정보 감사 완료 인증은 아니다.
- remote fetch/API·GitHub CLI 인증 재검사는 하지 않았다. 과거 'CLI 토큰 무효' 기록을
  현재 인증 상태로 재확정하지 않는다. 모든 수치는 로컬 origin snapshot 기준이다.
- 이번 분석에서 commit/ref/tag/원격 설정 변경은 없다. [Git 권고](GIT_RECOVERY.md)를 유지한다.

## 사용자 지정 자체 SSE 전환의 추가 기준선

- 현재 외부 Supabase 구독은 주방 템플릿 한 곳이다. CDN SDK, URL/anon key 주입,
  postgres_changes 구독과5초 폴링이 연결되어 있다. ORDER/카운터는 context를 받지만
  실제 구독은 없으며 기존 fetch를 사용한다. [정확한 파일 지도](ANALYSIS_REPORT.md#sse-migration).
- 사용자 방향 D-018은 브라우저의 외부 Realtime 연결 제거와 자체 SSE다. 후속 D-020은
  Compose PostgreSQL의 DB 자체 운영을 별도로 지정했다. EventSource/SSE endpoint·영속
  revision·outbox·LISTEN 구현은 아직 없다.
- E-SSE-STATIC: 기존 Gunicorn26.2.0의 기본 worker는 sync, 내장 ASGIWorker는 실제 import
  성공. requirements의 열린 범위만으로 같은 기능이 보장되지는 않는다.
- 설치 WhiteNoise6.10.0 middleware는 async_capable=False이고 나머지 Django middleware7개는
  True다. asgi.py 존재나 worker import 성공만으로 운영 ASGI 배포·성능을 입증하지 않는다.
- 합성 StreamingHttpResponse의 async iterator 직접 순회는 is_async=True·text/event-stream·
  2청크·빈 줄 종료 확인. 외부 접속·서버 기동·코드 변경 없이 수행했다.
- 영속 revision+워커별 확인+권한 snapshot은 제안이다. 서비스/trigger 선택·공유 잠금 교착,
  snapshot 일관성·Last-Event-ID/화면 적용 버전·세션 회수·프록시·부하는 미검증이다.
  SSE 분석 시점 위험은 BK-R035~040을 추가한40개였고 D-019에 상세 관문을 남겼다.
  아래 인프라 분석을 합친 현재 등록부는44개다.
- 기존34개 발견과 PG/SQLite 결과는 유지한다. 이번 추가 분석에서는 앱 검사를 불필요하게
  반복하지 않았으며 실제 SSE HTTP·브라우저·다중 워커·DB revision·부하·배포 검사는 하지 않았다.

## Compose PostgreSQL·EC2 후보의 추가 기준선

- 사용자 방향 D-020은 DB를 Docker Compose의 PostgreSQL로 이전해 직접 운영하는 것이다.
  EC2는 사용자 검토 후보(D-021 proposed)이며 리전·사양·단일 호스트·HA 수용은 확정되지 않았다.
- 현행 추적/비무시 파일에는 Dockerfile·Compose·.dockerignore·배포/백업 실행 파일이 없다.
  현재 운영 플랫폼/DB 버전/관리 객체가 무엇인지는 소스만으로 확정하지 않는다.
- E-INFRA-STATIC 합성 settings import5조건: DATABASE_URL 없음/`DATABASE_URL_FILE`만 지정은
  SQLite, 일반 PG URL은 sslmode=require, 명시 disable은 그대로 반영, URL의 sslrootcert는
  OPTIONS에 미포함. CONN_MAX_AGE는 현재 DATABASES에서 명시하지 않는다.
  DB 연결·TLS handshake·실제 secret 읽기 없이 parser와 engine 선택만 확인했다.
- PostgreSQL 연결 실패 시 SQLite로 자동 전환하는 코드는 없다. 설치 Django 기본 연결 수명은0이나
  현재 앱은 CONN_MAX_AGE 환경 변수를 읽지 않으며 장기 허브 연결 정리도 별도 검증 대상이다.
- Compose 환경 전달/secret 읽기와 실제 PG TLS 계약·필수 DB 시작 거부가 필요하다. 현재
  parser probe에서 비TLS를 허용한 것은 운영 권고나 암호화 해제 적용이 아니다.
- 제안: EC2 단일 호스트 후보의 proxy/ASGI/내부 PG·EBS mount·호스트 밖 백업을 비교하고
  전체 writer 동결/단일 쓰기 전환·원본/대상 객체/행/금액/sequence·새 주문 이후 복구를 검증한다.
- 기존 PG15.18 검사와0018↔0019 실패는 유지한다.0020 빈 DB 실패는 수정 이전 관찰이며
  현재는 성공 회귀로 고정돼 있다. 새 컨테이너가 healthy여도
  bootstrap/원본 restore가 성공한 것은 아니다. 신규/기존 migration 경로와 DB 이전을 구분한다.
- 신규 BK-R041~044를 포함해 총44개(Critical1/High30/Medium13). 설정 불일치는 코드/합성
  증거, 나머지는 원본/운영 의존 또는 구성 전 가설이다. 실제 새 인프라 사고를 재현하지 않았다.
- Docker/Compose·이미지 build/pull·AWS API/자원 생성·원본 접속·dump/restore·배포는 미실행.
  정확한 파일 지도·제안/조건·공식 근거·probe는 [인프라 분석](ANALYSIS_REPORT.md#infrastructure-migration)에 있다.
- 복원 시 삭제된 세션/옛 SSE generation이 되살아날 가능성은 새 인수 가설로 추가했다.
  복원 세션 무효화/인증 세대·공통 새 generation과 원본/대상 객체·권한 검사는 아직 미실행이다.

## 기능·명칭 정리 기준선

- D-023 accepted: 주문·서빙 / 주방 / 관리자 중심으로 기능·명칭을 정리한다.
- 현재 ORDER는 주문·서빙, KITCHEN 계열은 주방, B1_COUNTER 화면은 판매 통계다.
  Django admin의 운영 관리와 판매 통계는 관리자 영역으로 매핑하되 접근/수정 권한은 구분한다.
- 활성 지상/부스 화면·역할은 없고 모델 선택과 신규 주문은 B1 중심이다. visible_booth는
  관리자에서 편집 가능하지만 현행 메뉴 조회·생성에는 사용하지 않는다. visible_counter/kitchen은 사용 중이다.
- 위 사실은 과거 지상/부스 주문이 없다는 증거가 아니다. D-024의 기능/데이터 제거 범위는 미정이다.
  기존 URL·역할 코드·source/floor·번호·migration은 이번 문서 갱신에서 바꾸지 않았다.
- [기능 매핑과 인수 기준](ANALYSIS_REPORT.md#functional-naming)을 추가했으며 기존44개 위험은 유지한다.

## 다음 관문

[DECISIONS.md](DECISIONS.md)의 노출·역할, 번호·결제, 운영 DB·기존 데이터, 포장·상태·복구
정책과 SSE/이전 상세 D-019/022·EC2 후보 D-021은 pending/proposed다.
사용자 지정 자체 SSE·Compose PostgreSQL·세 기능 영역 방향 D-018/020/023은 accepted다.
지상/부스 정리 세부 범위 D-024는 pending이다. [프롬프트02](prompts/02_REVIEW_BLUEPRINT.md)에서
새 위험과 의존성·단계 경계를 검토한 뒤 승인된 구현 단계를 선택한다. 이번 분석에는 구현 승인이 없다.
