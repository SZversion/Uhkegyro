# Illustration Reference Agent Design

## 현재 구현 단계

현재는 기반 골조 단계다. Pydantic 요청/선택 계약, 자체 TERM_CARD DB, 역할 검증, Pinterest URL 생성, `/health`, 팀이 관리하는 카드 검증 FastMCP 파이프라인을 구현한다. DB schema·적재·조회는 목표 설계에 포함하지만 아직 구현·적재하지 않았다. Getty는 용어 조사 참고 자료일 뿐 서비스 데이터로 사용하지 않는다. OpenAI, Langfuse, UI, 배포는 아직 구현하거나 호출하지 않는다.

## 책임 분리

| 계층 | 책임 |
| --- | --- |
| LLM (향후) | 일상어를 허용 term ID·근거·대안으로 구조화 |
| 결정론 코드 | 허용 ID, 역할 일치, 역할 순서, 검색어와 URL 인코딩 검증 |
| FastMCP | LLM이 선택한 허용 term ID를 검증하고, 자체 TERM_CARD DB의 용어·설명·검수 상태로 Pinterest 검색 계획을 반환한다. Getty API·SPARQL·웹 호출과 Getty 데이터 조회는 하지 않는다. |
| UI (향후) | 용어·근거·한계·역할별 Pin 미리보기를 표시 |

## 기반 계약

- 요청 모델은 `request_text` 1~500자와 UUID 형식 `anonymous_user_id`, `session_id`만 허용한다.
- 내부 선택은 `body | pose | view | perspective | layout`의 `role`, 정적 `term_id`, 근거, confidence를 가진다. 현재 활성 카드의 `role`·`term_id` 계약을 그대로 사용하며, `axis`·`kind` 필드는 사용하지 않는다.
- 검색 역할은 `body → pose → view → perspective → layout` 순서다. 실제로 선택된 역할만 만든다.
- 역할별 검색은 검증된 정적 카드의 `query_fragments`를 Pinterest 검색 provider에 전달한다. provider 결과의 Pin URL만 저장하고 이미지는 저장하지 않는다.

## 자체 관리 TERM_CARD 저장소

- 용어 선택의 단일 원본은 자체 TERM_CARD DB다. 역할별 JSON은 DB 적재 전의 검수·시드 자료이며, 외부 API·다중 provider·Getty 데이터는 조회·병합하지 않는다.
- 카드에 없는 표현 또는 저신뢰도 해석은 추가 질문 또는 `pending_human_review`로 처리한다. 사람 승인과 평가셋 회귀 확인 없이는 정적 카드·Skill에 자동 반영하지 않는다.
- Langfuse 도입 후에는 원문 요청 대신 해시, confidence, limitation code, 선택된 팀 카드 ID만 기록한다. 이 단계에서는 실제 Langfuse 호출을 하지 않는다.

## 정적 카드 검증 실험

- 실제 LLM 호출 전에는 `Selection`이 LLM의 구조화 출력을 나타낸다. MCP는 유효한 프로젝트 `role`·`term_id` 조합만 처리하며, 잘못된 역할 또는 term ID는 카드 저장소 조회 전에 거부한다.
- 필요한 카드가 없거나 저장소를 읽을 수 없으면 외부 조회로 보완하지 않고 `TEAM_TERM_CARD_UNAVAILABLE` 또는 `TERM_CARD_STORE_UNAVAILABLE`을 반환한다.
- Pinterest 링크는 검증된 정적 카드의 `query_fragments`로만 생성한다.

## 다음 단계 전제

`POST /api/agent`는 OpenAI Structured Output, 애플리케이션 재시도, 카탈로그 MCP 실패 정책, 최신 응답 계약을 한 단위로 추가할 때 구현한다. 카탈로그 레코드와 권리 검토 기준은 팀 승인 전까지 비어 있어야 한다.
