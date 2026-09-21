# Illustration Reference Agent Design

## 현재 구현 단계

현재는 기반 골조 단계다. Pydantic 요청/선택 계약, 정적 term ID 카드, 축/역할 검증, Pinterest URL 생성, `/health`, Getty AAT 용어 조회와 정적 카드 폴백 FastMCP 파이프라인을 구현한다. OpenAI, Langfuse, 권리 검토된 자체 카탈로그, UI, 배포는 아직 구현하거나 호출하지 않는다.

## 책임 분리

| 계층 | 책임 |
| --- | --- |
| LLM (향후) | 일상어를 허용 term ID·근거·대안으로 구조화 |
| 결정론 코드 | 허용 ID, 축/하위 역할 일치, 역할 순서, 검색어와 URL 인코딩 검증 |
| FastMCP | LLM이 선택한 허용 term ID를 검증하고, Getty AAT SPARQL 조회 성공 시 URI·label·출처를 반환한다. 후보 없음·장애 시 정적 `TERM_CARDS`로 폴백한 뒤 Pinterest 검색 계획을 반환한다. 향후 권리 검토된 자체 카탈로그의 구조화 출처 메타데이터를 조회한다. |
| UI (향후) | 용어·근거·한계·외부 링크만 표시 |

## 기반 계약

- 요청 모델은 `request_text` 1~500자와 UUID 형식 `anonymous_user_id`, `session_id`만 허용한다.
- 내부 선택은 `body | pose | view | perspective | layout`의 `role`, 정적 `term_id`, 근거, confidence를 가진다. 현재 활성 카드의 `role`·`term_id` 계약을 그대로 사용하며, `axis`·`kind` 필드는 사용하지 않는다.
- 검색 역할은 `body → pose → view → perspective → layout` 순서다. 실제로 선택된 역할만 만든다.
- 역할별 링크와 통합 링크는 `urllib.parse.urlencode`로 생성한다. Pinterest에 요청하거나 결과를 저장하지 않는다.

## Getty AAT 용어 보완

- 용어 후보 공급자 계약(`VocabularyCandidateProvider`)의 현재 구현은 Getty AAT SPARQL이다. 자체 DB가 준비되면 같은 `search_terms(query, limit)` 계약을 구현해 서버 구성에서 Getty를 대체할 수 있다. 이 단계에서는 여러 공급자를 병합하지 않는다.
- 용어 카드에 없는 표현 또는 저신뢰도 해석은 현재 Getty AAT SPARQL의 용어 후보를 조회해 사람 검토에 보낸다. Getty는 이미지 레퍼런스·Pinterest 결과·자체 카탈로그를 대체하지 않는다.
- 현재 Getty 기본 공급자의 후보 조회 결과는 AAT subject URI, label, Getty 출처 URL만 가진다. 미래 자체 DB 공급자는 같은 구조에서 자신의 `source_name`과 `source_url`을 반환한다. Metropolitan Museum API와 Getty Museum Collection API는 사용하지 않는다.
- `confidence=low`와 limitation이 모두 있을 때만 `pending_human_review` term 카드 초안을 만든다. 사람 승인과 평가셋 회귀 확인 없이는 정적 카드·Skill에 자동 반영하지 않는다.
- Langfuse 도입 후에는 원문 요청 대신 해시, confidence, limitation code, Getty 후보 수·URI만 기록한다. 이 단계에서는 실제 Langfuse 호출을 하지 않는다.

## Getty 조회와 정적 카드 폴백 실험

- 실제 LLM 호출 전에는 `Selection`이 LLM의 구조화 출력을 나타낸다. MCP는 유효한 프로젝트 `role`·`term_id` 조합만 처리하며, 잘못된 역할 또는 term ID는 Getty에 전달하지 않는다.
- 각 term ID에서 축 접두사를 제외한 영문 용어(예: `pose_contrapposto` → `contrapposto`)로 Getty AAT를 최대 한 건 조회한다. 성공하면 `getty_aat` 출처와 Getty URI·label·출처 URL을 반환한다.
- 후보 없음은 `GETTY_AAT_TERM_NOT_FOUND`, timeout·5xx·비정상 응답은 `GETTY_AAT_UNAVAILABLE` limitation code와 함께 `term_cards` 출처로 폴백한다.
- Pinterest 링크는 Getty의 동적 label이 아닌, 검증된 정적 카드의 `query_fragment` 또는 실패 상태 계약에서 검증한 임시 후보의 짧은 `search_token`으로만 생성한다.
- 필요한 팀 카드가 없으면 MCP는 `resolution_source=term_source_unavailable`, `limitation_codes=[TEAM_TERM_CARD_UNAVAILABLE]`을 반환한다. 카드 저장소를 읽지 못하면 같은 출처 상태와 `limitation_codes=[STATIC_CARD_STORE_UNAVAILABLE]`을 반환한다. `resolution_source`는 MCP의 출처 상태이고 API 사유 코드가 아니며, 서버는 `limitation_codes`의 대문자 공통 enum을 `reason_codes`에 변환 없이 보존한다. 서버는 실패 상태 계약에 따라 세 번째 LLM 폴백을 한 번 호출할 수 있으며, 성공한 후보도 `llm_fallback`·임시 후보·사람 검토 필요로 표시한다. 이 후보는 카드·Skill·DB에 자동 저장하지 않는다.

## 다음 단계 전제

`POST /api/agent`는 OpenAI Structured Output, 애플리케이션 재시도, 카탈로그 MCP 실패 정책, 최신 응답 계약을 한 단위로 추가할 때 구현한다. 카탈로그 레코드와 권리 검토 기준은 팀 승인 전까지 비어 있어야 한다.
