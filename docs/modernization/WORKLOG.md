# 현대화 작업 로그

각 항목은 새 세션에서도 이해할 수 있도록 짧되 충분하게 작성합니다. 최신
항목이 위에 오도록 합니다.

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
