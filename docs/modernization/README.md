# 현대화 작업 제어 센터

이 디렉터리는 Bazaar Kiosk 현대화 작업의 인수인계 중심입니다.
검증된 사실, 결정 대기 사항, 단계 경계 및 세션 프롬프트를 분리해 보관하므로 새 세션에서
이력을 재구성하지 않고 작업을 재개할 수 있습니다.

## 현재 작업 재개

[SESSION_SETUP.md](SESSION_SETUP.md)의 최신 단계·승인표·격리 명령부터 확인합니다.
2026-09-08 기준2A·1A는 머지 완료입니다. 1B는 D-P07 승인으로0020을 적용해
[PR40](https://github.com/rlagycks/bazaar_kiosk/pull/40)에 담았지만0019 정책이 미정이라 미완료이며,
2B는 미착수입니다. 현재 PR head와 로컬 변경을 확인하고 승인된 하위 작업 하나만 이어갑니다.

[구현 프롬프트03](prompts/03_IMPLEMENT_PHASE.md)에 정확한 범위·기준·승인 근거를 채워 사용합니다.
0020 적용의 정확한 diff·검증·남은 관문은 [적용 기록](MIGRATION_REPAIR_REVIEW.md)에 있습니다.
기존 분석을 자동으로 다시 시작하지 않습니다. 새 분석이 필요하면 [프롬프트01](prompts/01_ANALYZE.md),
계획 재검토는 [프롬프트02](prompts/02_REVIEW_BLUEPRINT.md), 전체 종료 감사는
[프롬프트04](prompts/04_FINAL_AUDIT.md)를 사용합니다.
[모델 위임 검토](MODEL_DELEGATION_REVIEW.md)는 문서 준비 상태와 실제 실행 조건을 구분합니다.

현재 시작 문서는 다음과 같습니다.

- [BASELINE.md](BASELINE.md) — 검증된 스냅샷 및 초기 위험 가설
- [BLUEPRINT.md](BLUEPRINT.md) — 의존성 순서에 따라 구성된, PR 하나 규모의 단계
- [GIT_RECOVERY.md](GIT_RECOVERY.md) — 비파괴적인 기록 정리 선택지
- [DECISIONS.md](DECISIONS.md) — 제품 및 기술 결정 로그
- [WORKLOG.md](WORKLOG.md) — 세션 간 인수인계 기록

## 문서 상태

- `검증됨(Verified)`은 명령, 코드 위치 또는 재현 가능한 관찰 결과가 해당 내용을 뒷받침한다는
  의미입니다.
- `가설(Hypothesis)`은 위험에 개연성이 있지만 집중적인 재현이나 운영 환경 확인이 필요하다는
  의미입니다.
- `결정 대기(Pending decision)`는 구현 과정에서 사용자를 대신해 암묵적으로 선택해서는 안 된다는
  의미입니다.

사실을 다시 확인하면 `마지막 검증` 필드를 업데이트합니다. 이전 항목과 근거를 보존하지
않은 채 중요한 결정을 덮어쓰지 마세요.

## 과거 프롬프트 설계 출처

초기 세션 지침은 2026-09-06 당시 기록한 공식
[GPT-6 Astra 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)를
바탕으로 작성했습니다. 특히 가이드에서 조정 가능한 Astra 동작으로 언급한 주도성, 지침
우선순위, 작성 방식, 위임 및 테스트 비례성을 프롬프트에 명시적으로 정의했습니다.

프롬프트는 가이드를 그대로 복사하지 않고 바꾸어 표현했습니다. 기능과 호환성은 변경될 수
있으므로 모델/API 매개변수를 변경하기 전에 공식 페이지를 다시 확인하세요.

이 출처는 초기 설계 기록입니다. 현재 실행 계약은 모델에 공통이며 모델 선택·API 설정을 강제하지 않습니다.
