# Illustration Reference Agent Design

## 현재 구현 단계

현재는 기반 골조 단계다. Pydantic 요청/선택 계약, 정적 term ID 카드, 축/역할 검증, Pinterest URL 생성, `/health`만 구현한다. OpenAI, Langfuse, FastMCP 카탈로그, UI, 배포는 아직 구현하거나 호출하지 않는다.

## 책임 분리

| 계층 | 책임 |
| --- | --- |
| LLM (향후) | 일상어를 허용 term ID·근거·대안으로 구조화 |
| 결정론 코드 | 허용 ID, 축/하위 역할 일치, 역할 순서, 검색어와 URL 인코딩 검증 |
| FastMCP (향후) | 권리 검토된 카탈로그의 구조화 출처 메타데이터 조회 |
| UI (향후) | 용어·근거·한계·외부 링크만 표시 |

## 기반 계약

- 요청 모델은 `request_text` 1~500자와 UUID 형식 `anonymous_user_id`, `session_id`만 허용한다.
- 내부 선택은 `body | pose | composition | detail` 축과 정적 `term_id`를 가지며, 구도는 `view | perspective | layout` kind를 사용한다.
- 검색 역할은 `body → pose → view → perspective → layout` 순서다. 실제로 선택된 역할만 만든다.
- 역할별 링크와 통합 링크는 `urllib.parse.urlencode`로 생성한다. Pinterest에 요청하거나 결과를 저장하지 않는다.

## 다음 단계 전제

`POST /api/agent`는 OpenAI Structured Output, 애플리케이션 재시도, 카탈로그 MCP 실패 정책, 최신 응답 계약을 한 단위로 추가할 때 구현한다. 카탈로그 레코드와 권리 검토 기준은 팀 승인 전까지 비어 있어야 한다.
