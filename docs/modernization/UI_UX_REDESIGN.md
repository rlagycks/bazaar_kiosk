# Figma UI/UX 개선안

작성일: 2026-09-07. 범위: 기존 업무 흐름을 유지하는 편집 가능한 디자인 초안.

## 확정한 기준

- 사용자가 선택한 방향은 **차분하고 선명한 업무용 UI**다.
- **주문·서빙은 휴대폰**, **주방·관리자는 PC**를 기준으로 한다.
- 먼저 화면을 현대화하고, 업무 요구사항 변경은 이후 별도로 검토한다.
- 주문·서빙 / 주방 / 관리자는 화면을 설명하는 분류다. 기존 역할 5개와 Django
  관리자 권한을 합치거나 통계 접근 권한을 변경하는 결정이 아니다.
- 애플리케이션 코드, 운영 데이터, 인프라를 변경하지 않았다. push/merge도 하지 않았다.

기존 분석과 SSE·PostgreSQL·EC2 논의는 [분석 보고서](ANALYSIS_REPORT.md)와
[결정 기록](DECISIONS.md)을 따른다. 이 디자인으로 인프라 후보나 미확정 요구사항을
추가 승인한 것으로 해석하지 않는다.

## 작업한 Figma 파일

학생 계정으로 복제한 [현재 작업 파일](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt)을
사용했다. 이전 계정의 원본 파일에는 이번 개선안을 쓰지 않았다.

| 섹션 | 내용 |
| --- | --- |
| [01 · 현재 화면](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2004-2) | 기존 11개 프레임을 보존. ID·크기·캔버스 절대 위치 유지 |
| [02 · UI 개선안](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2004-3) | 개선 화면 13개, 휴대폰 스크롤 프리뷰 1개, 공통 컴포넌트와 검토 안내 |

이 사본에는 사용자가 정리한 11개 현재 화면만 있다. 미사용 `serve.html` 화면을
다시 추가하지 않았다. 현재 코드의 주문 화면은
[order.html](../../orders/templates/orders/order.html)이며 실제 배포 화면과의 일치 여부는
이번 디자인 작업으로 확인한 것이 아니다.

## 화면 목록과 개선 내용

| 화면 | 기준 | Figma | 개선 내용 |
| --- | --- | --- | --- |
| 역할 선택 | 휴대폰 390px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2008-7) | 기존 역할 5개를 큰 버튼으로 표시 |
| PIN | 휴대폰 390px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2008-22) | 선택 역할, 입력, 접속, 역할 재선택의 순서 명확화 |
| 주문·서빙 전체 내용 | 휴대폰 390px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2008-34) | 메뉴·주문 정보·담은 메뉴·결제의 읽는 순서 정리 |
| 혼합 결제 상태 | 휴대폰 390px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2008-125) | 같은 화면의 현금·식권 입력 상태를 별도 비교 프레임으로 표시 |
| 스크롤 프리뷰 | 휴대폰 390×844 | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2033-327) | 고정 하단 주문 요약, 주문 정보로 이동, 세로 스크롤 |
| 주방 전체 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2012-101) | 테이블·포장 번호와 메뉴별 준비 수량 강조 |
| 주방 홀 총괄 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2012-155) | 기존 홀 주문 범위를 유지한 동일 카드 체계 |
| 주방 포장 총괄 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2012-209) | 포장 전용 주문 범위를 유지한 동일 카드 체계 |
| 판매 통계 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2013-199) | 주요 수치, 시간대별 차트, 메뉴별 표로 정보 위계 정리 |
| 사이트 관리 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2014-253) | 메뉴·주문·테이블 및 사용자·그룹 관리 항목 유지 |
| 메뉴 관리 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2014-273) | 검색·필터·목록·저장 영역 정렬 |
| 주문 관리 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2014-311) | 검색·날짜 탐색·상태·합계의 표 구조 정리 |
| 테이블 관리 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2014-348) | 번호·이름·사용 여부·정렬 순서의 일관된 열 구성 |
| 주문 상세 | PC 1440px | [열기](https://www.figma.com/design/lrCdmOhZQfKiUIfz76tXvt?node-id=2016-304) | 편집 정보와 읽기 전용 정보 구분, 항목 표와 저장 동작 정렬 |

메뉴별 홀/포장 선택, 혼합 주문, 테이블 번호 직접 입력, 포장 슬롯 101–120,
수량 입력 및 ± 조절, 삭제, 현금·식권·혼합 결제, 거스름돈, 주문 저장·초기화를 유지했다.
주문 제출 전에 결제를 입력하는 현재 순서를 별도 결제 마법사나 선주문 흐름으로 바꾸지 않았다.
혼합 결제 프레임은 다른 단계가 아니라 같은 결제 영역의 상태 예시다.

주방은 메뉴별 준비 수량 ±, 새로고침, 취소를 유지한다. 새로운 서빙 완료 상태나
서버 기능을 정의하지 않는다. 관리자 필드는
[admin.py](../../orders/admin.py)와 [모델](../../orders/models/core.py)을 확인했다.
목록에서 관련 필드를 묶어 보여주는 것은 표시 방법의 제안이며 모델 필드 삭제가 아니다.

## 디자인 근거

2026-09-07에 공식 제품 자료를 확인했다. 아래는 참고한 일반적인 설계 원칙이며,
특정 제품의 화면·로고·이미지·아이콘을 가져오거나 그대로 재현하지 않았다.

| 공식 자료 | 참고한 점 | 이번 적용 |
| --- | --- | --- |
| [Linear UI refresh, 2026-03-12](https://linear.app/changelog/2026-03-12-ui-refresh) | 일관된 탐색과 콘텐츠 집중 | 반복되는 제목·도구 위치, 제한된 강조색 |
| [Square 모바일 POS](https://squareup.com/us/en/point-of-sale/restaurants/mobile-pos-demo) | 현장에서 손에 들고 주문을 다루는 맥락 | 휴대폰 터치 영역과 주문 합계 접근성 |
| [Toast KDS](https://pos.toasttab.com/hardware/kitchen-display-system) | 주방에서 주문과 준비 정보를 빠르게 읽는 맥락 | 주문 카드, 큰 테이블 번호와 준비 수량 |
| [토스플레이스 POS](https://tossplace.com/product/pos) | 한국어 업무 화면의 금액·수량 가독성 | 원 단위 표기, 정렬된 수치와 간결한 문구 |

글꼴은 Figma에서 사용 가능한 Noto Sans KR을 사용했다. 해당 글꼴 계열의
[SIL Open Font License 1.1](https://github.com/notofonts/noto-cjk/blob/main/Sans/LICENSE)을
확인했다. 로컬 폰트 파일을 복사하거나 수정·재배포한 작업은 없다.
이 기록은 외부 자산 사용 내역을 설명하며 모든 법적 위험이 없다는 보증은 아니다.

## 편집 구조와 접근성

- 공통 컴포넌트 11개: 주요/보조/선택/취소 버튼, 입력창, 메뉴, 장바구니 항목,
  통계 지표, 표 행, 주방 메뉴 준비 수량, 주방 주문 카드.
- 해당 컴포넌트 인스턴스 177개, 편집 가능한 텍스트 노드 420개, 색상 변수 10개.
  수치는 공통 컴포넌트 영역과 프리뷰를 포함한 최종 읽기 결과다.
- 관련 요소는 Auto Layout으로 묶고 텍스트 높이는 내용에 맞춰 자동 조정한다.
- 주요 터치 버튼 높이 52px, 수량 ± 버튼 52×52px, 인접 버튼 간격 최소 8px.
  [Android 접근성 권장치](https://support.google.com/accessibility/android/answer/7101858?hl=en)를
  참고했다. 웹 디자인의 CSS px와 Android dp는 동일 단위라고 가정하지 않는다.
- [WCAG 2.2 최소 타깃 크기](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html)의
  24 CSS px 기준과 별도로 더 큰 모바일 설계 목표를 선택했다.
- [WCAG 텍스트 대비 기준](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum)을
  참고해 주요 일반 텍스트 4.5:1 이상, 컨트롤 경계 3:1 이상을 목표로 확인했다.

| 색상 조합 | 계산한 대비 |
| --- | --- |
| 본문 / 흰색 | 14.52:1 |
| 보조 문구 / 흰색 | 6.24:1 |
| 보조 문구 / 화면 배경 | 5.70:1 |
| 강조색 / 흰색 | 7.12:1 |
| 강조색 / 선택 배경 | 6.17:1 |
| 조리 상태 문구 / 흰색 | 6.31:1 |
| 취소 문구 / 흰색 | 6.55:1 |
| 컨트롤 경계 / 흰색 | 3.98:1 |
| 컨트롤 경계 / 선택 배경 | 3.45:1 |

전체 접근성 적합성 인증이나 키보드·스크린리더 검증을 의미하지 않는다.
구현 단계에서 의미 있는 HTML, 포커스, 오류 안내, 모바일 키보드 및 실기기 동작을 검증해야 한다.

## 검증 결과와 한계

1. Figma 페이지의 최상위 섹션이 정확히 2개인지 확인했다.
2. 원본 프레임 11개의 ID·절대 위치·크기가 최초 읽기와 일치했다. 원본 텍스트는
   최종 읽기에서 607개이며, 원본 텍스트/스타일을 편집하지 않았다.
3. 개선안의 부모 경계를 벗어난 텍스트는 0개, 이미지 채우기를 사용하는 노드도 0개였다.
   세로 스크롤 프리뷰의 의도적인 화면 밖 콘텐츠는 일반 넘침 검사에서 구분했다.
4. 주요 화면을 Figma 렌더링으로 시각 검사했다. 고정 텍스트 높이, 과도한 카드 내부 여백,
   차트 기준선, 표 행 간격, 하단 고정 영역의 끝 여백을 보정했다.
5. 화면 이동 7개와 주문 정보로 스크롤하는 연결 1개의 목적지 ID를 읽어 검증했다.
   휴대폰 프리뷰는 높이 844, 세로 스크롤, 고정 하단 영역 1개로 설정되어 있다.
   Present 모드에서 실제 클릭·스크롤을 실행하는 E2E 검사는 하지 않았다.
6. 저장소 문서의 로컬 링크, Markdown 렌더링 구조, 미완성 표식, `git diff --check`를
   검사했다. 앱 코드 diff가 없는 것도 확인했다.

주문·매출은 모두 디자인 예시다. 통계 예시는 주문 48건, 판매 94개, 매출 298,000원이며
메뉴별·시간대별 합계가 맞는다. 현재 통계 API 오류는 수정하지 않았다.

이 산출물은 편집 가능한 **1차 화면 개선안**이다. 로그인·주문 저장·결제·검색·인라인
편집·삭제가 실제 실행되는 앱은 아니다. 표의 필터와 셀 조작, 모든 오류·빈 상태,
사용자/그룹 상세 및 관리자 추가/변경 하위 폼 전체를 상호작용 프로토타입으로 만든 범위도 아니다.
예시 주문은 화면별 검토 상태이며 서로 동기화된 실시간 데이터가 아니다.
승인된 UI 방향을 검토한 뒤, 기존 기능의 구현·접근성·실기기 검증을 별도 단계로 진행한다.
