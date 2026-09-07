# 현대화 작업 제어 센터

이 디렉터리는 GPT-6 Astra를 사용한 Bazaar Kiosk 현대화 작업의 인수인계 중심입니다.
검증된 사실, 결정 대기 사항, 단계 경계 및 세션 프롬프트를 분리해 보관하므로 새 세션에서
이력을 재구성하지 않고 작업을 재개할 수 있습니다.

## 권장 순서

1. [SESSION_SETUP.md](SESSION_SETUP.md)를 읽고 GPT-6 Astra를 선택합니다.
2. [prompts/01_ANALYZE.md](prompts/01_ANALYZE.md)를 전용 분석 세션에 붙여 넣습니다. 해당
   세션은 구현이 아니라 근거를 산출해야 합니다.
3. [DECISIONS.md](DECISIONS.md)의 제품 관련 질문을 해결합니다.
4. [prompts/02_REVIEW_BLUEPRINT.md](prompts/02_REVIEW_BLUEPRINT.md)를 붙여 넣어 완료된 분석
   및 결정 사항에 구축 계획을 맞춥니다.
5. [prompts/03_IMPLEMENT_PHASE.md](prompts/03_IMPLEMENT_PHASE.md)를 사용해 승인된 단계를
   한 번에 하나씩 실행합니다.
6. 계획된 단계가 끝나면 [prompts/04_FINAL_AUDIT.md](prompts/04_FINAL_AUDIT.md)를
   사용합니다.

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

## 프롬프트 설계 출처

세션 지침은 2026-09-06에 검증한 공식
[GPT-6 Astra 모델 가이드](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-6-astra)를
바탕으로 작성했습니다. 특히 가이드에서 조정 가능한 Astra 동작으로 언급한 주도성, 지침
우선순위, 작성 방식, 위임 및 테스트 비례성을 프롬프트에 명시적으로 정의했습니다.

프롬프트는 가이드를 그대로 복사하지 않고 바꾸어 표현했습니다. 기능과 호환성은 변경될 수
있으므로 모델/API 매개변수를 변경하기 전에 공식 페이지를 다시 확인하세요.
