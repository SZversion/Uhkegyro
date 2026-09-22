# TERM_CARD 출처·검수 기록

## 현재 데이터 계약

- 현재 TERM_CARD 저장소는 `index.json`과 index가 열거한 `body.json`, `pose.json`, `view.json`, `perspective.json`, `layout.json`이다.
- 과거 `TERM_CARDS_MASTER_100_DRAFT.json`은 카드 데이터가 아닌 폐기 포인터다. 로더와 검증 대상에 포함하지 않는다.
- 카드 수·역할별 분포·활성 조건은 `index.json`을 기준으로 검증한다.

## 작성 근거와 권리

- 카드의 한국어 설명, 선택 단서, 검색 조각, 초보자 혼동 안내는 팀이 작성·관리하는 데이터다.
- 도메인 검수 책임자는 오세창이다. 활성 카드는 각 카드의 `review_status`, `reviewed_by`, `reviewed_at` 필드로 검수 상태를 확인한다.
- 초기 작업에는 `TERM_CARDS_DRAFT_30.json`과 `POSE_RESPONSE_DRAFTS_87.json`이라는 팀 내부 초안이 사용됐다. 두 파일은 현재 저장소의 런타임 원본이나 제출 증거 파일이 아니므로, 존재하지 않는 경로를 `index.json`에 넣지 않는다.
- 역할별 카드 JSON과 목표 TERM_CARD DB에는 Getty AAT 객체·ID·URI·귀속·scope note를 저장하지 않는다. Pinterest 이미지·Pin 본문·외부 API 결과·제3자 이미지도 저장하지 않는다.
- Getty는 팀이 용어를 조사할 때 참고한 자료일 뿐 서비스의 데이터 출처가 아니다. 사용자 화면·MCP 응답·LLM 입력에는 팀이 작성·검수한 TERM_CARD 데이터만 사용한다.

## 변경 절차

1. 팀원이 역할별 JSON의 후보 카드를 제안한다.
2. 오세창이 용어의 의미·검색 조각·초보자 설명을 검수한다.
3. API 계약, Skill, 평가셋을 함께 갱신할 범위인지 확인한다.
4. 검수와 회귀 확인 전에는 `runtime_eligible=false`를 유지한다.
5. index 수·중복 term ID·활성 카드 수 검증을 통과한 변경만 PR로 반영한다.
