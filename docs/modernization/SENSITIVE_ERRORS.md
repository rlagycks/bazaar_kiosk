# 4A1 — 오류 보고의 역할 PIN 가림

2026-09-09 · [이슈45](https://github.com/rlagycks/bazaar_kiosk/issues/45) ·
브랜치 `phase-4a1-sensitive-errors`, 기준 develop `8b1740cc396078c119a39bbb41c2f81937c18987`.
[PR44](https://github.com/rlagycks/bazaar_kiosk/pull/44)의 PostgreSQL 전용 전환을 머지한 뒤 진행한다.

## 목적과 범위

사용자의 다음 단계 진행 지시로 BLUEPRINT4A1에서 독립적으로 가능한 비노출 처리를 적용한다.
Django 기본 오류 필터는 ROLE_PINS를 민감한 설정 이름으로 인식하지 않았다. 또한 DEBUG=True에서는
민감 POST·지역변수 데코레이터의 가림이 비활성화돼 로그인 실패 도중 제출 PIN과 기대 PIN이 노출될 수 있었다.

[설정](../../bazaar_kiosk/settings.py)에서 [전용 필터](../../bazaar_kiosk/error_reporting.py)를 지정한다.
Django5.2의 SafeExceptionReporterFilter.hidden_settings 패턴·flags를 상속하고 PIN을 추가한다.
기존 SECRET_KEY·DB PASSWORD·AUTH/TOKEN/COOKIE 보호는 유지한다. is_active는 DEBUG와 무관하게 True다.
로그인뿐 아니라 모든 요청 POST의 pin을 뷰 진입 전 middleware 오류에서도 가리고,
보고서에 노출되는 MultiValueDict 지역변수의 pin도 보고용 복사본에서 가린다.
[로그인 뷰](../../orders/views/auth.py)의 pin·expected 지역변수와 POST pin에는 Django 민감값 데코레이터를 적용한다.
원래 요청이나 설정값을 변경하지 않으며 기존 역할·PIN 비교·성공/실패·리다이렉트는 유지한다.

공식 [Django5.2 오류 보고 API](https://docs.djangoproject.com/en/5.2/howto/error-reporting/#custom-error-reports)와
설치된 Django5.2.17 소스로 확장 지점을 확인했다. 현재 속성명은 hidden_settings이며 과거 이름으로 구현하지 않았다.

## 검증

[새 회귀4개](../../orders/tests/test_security_settings.py)는 매번 서로 다른 합성 PIN과 SECRET_KEY를 생성한다.

- DEBUG=True 오류의 HTML과 Accept: application/json 요청에 대한 기존 plaintext 보고에서 설정 PIN·secret 부재.
- 실제 login_view에서 제출/기대 PIN을 읽은 다음 렌더 오류를 주입해 POST·지역변수 가림 확인.
  실제 traceback의 login_view 프레임에 pin·expected가 존재하는지 함께 확인한다.
- 로그인 데코레이터 이전 middleware 오류에도 POST pin이 가려지고 원래 요청 값은 보존됨.
- DEBUG=False의 일반500, django.request의 표준 예외 기록, AdminEmailHandler의 text·HTML 보고를 검사.
  이메일은 메모리 backend에1건만 생성하며 외부로 보내지 않는다. 오류 설명과 비민감 role은 남아 있어야 한다.

Django는 비HTML Accept 요청에 JSON 대신 text/plain 기술 오류를 반환한다. 이 패치에서 새로운 JSON 오류 계약을
만들지 않았다. plaintext만으로 지역변수 보호를 입증하지 않고 HTML 및 프레임 데이터까지 검사한다.

원본 동작을 프로세스 내부에서 복원하면4개 테스트의6개 조건이 실패한다. PIN 패턴 제거,
DEBUG 가림 비활성화, 지역변수 주석 제거, 데코레이터 이전 POST 필터 제거, MultiValueDict 지역변수 필터 제거를 각각 검출했다.
추적 앱 파일을 변이 실험으로 변경하지 않았다. 초기 테스트 URLconf의 orders namespace 누락은 수정하고
의도한 로그인 렌더 오류에 도달한 뒤 실패/성공 근거를 다시 수집했다.

[PostgreSQL 준비·정리](POSTGRES_TESTING.md) 후 전체 검증:

```bash
.venv/bin/python scripts/test_postgres.py
```

새 Compose `bk-4a1-errors-20260909`, 고정 의존성의 Python3.12.11/Django5.2.17/PG15.18에서
migration15개·앱/guard29개, 총44개·skip0을 실행한다. 새4개는 DB 접근이 없는 SimpleTestCase이며
전체 suite의 기존 로그인·주문·주방·통계는 실제 PG를 사용한다. 결과는 [WORKLOG](WORKLOG.md)에 남긴다.

## 남는 경계

이것은 Django 기본 오류 보고의 설정값과 POST pin, 주석으로 지정한 로그인 지역변수 가림이다.
임의 exception 메시지·cause/context/notes, URL/querystring, 로그 메시지·formatter 출력에 직접 넣은 비밀값,
다른 이름·일반 dict/list로 복사한 지역변수, request별 필터·별도 reporter로 대체한 경로는 보장하지 않는다.
테스트의 표준 로그는 고정 오류 문구를 사용한다. 모든 로그 문자열을 자동 정화하는 필터를 추가한 결과가 아니다.

DEBUG 기본값, 공개 기본 PIN, SECRET_KEY 기본값, ALLOWED_HOSTS, 운영 필수 설정 실패 정책은 이번에 바꾸지 않았다.
운영 DEBUG=False와 필수값 정책은 D-002/006·4A1 나머지 범위이고, 권한·CSRF·세션 개편은3/4A2다.
BK-R028은 지정된 노출 경로를 저장소에서 수정했지만 전체 위험과4A1은 종료하지 않는다.
오류 보고서를 공개해도 안전하다는 의미가 아니며 운영 노출·실제 자격증명 회수·배포는 미실행이다.
4A1 전체 인수에 필요한 운영 설정 누락 거부는 미구현으로 남긴다.

schema·migration·번호/결제 계약·UI는 변경하지 않는다. 회귀가 생기면 실패 사례를 추가해 가림을 유지하는
정방향 수정을 한다. 기존 노출을 복원하는 되돌리기를 운영 복구 경로로 안내하지 않는다.
