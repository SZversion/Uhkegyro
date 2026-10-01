# MCP SearXNG Pinterest Pin 검색

## Why

- **페르소나·상황**: 검증된 TERM_CARD의 검색 결과를 job 응답으로 보여 주는 사용자와 worker.
- **문제**: 현재 worker가 SearXNG를 직접 호출해 검색 실행 경계가 MCP 서버 밖에 있다.
- **측정 지표**: 검색 가능한 카드마다 MCP 도구 호출로 검증된 Pin을 최대 8개 반환하고 기존 검색 사유 코드를 유지한다.

## Goal

- MCP 서버의 `search_pinterest_pins` 도구가 SearXNG Google Images 요청과 Pin URL 검증을 실행한다.
- worker는 resolver가 승인한 카드의 `query_fragments`만 도구에 전달하고, 반환 Pin을 기존 widget 조회·응답 조립에 사용한다.
- 검색 0건, 검색 장애, 구성 오류 및 worker의 역할별 재시도 계약을 유지한다.
- **범위 밖**: TERM_CARD 후보 선택 변경, `get_active_term_card` 호출 연결, widget 조회 위치 변경, 이미지 저장.

## What

1. resolver 검증 후 LLM이 `search_pinterest_pins(role, query_fragments)` 호출을 선택한다. worker는 role과 조각 배열이 resolver가 승인한 카드와 정확히 일치할 때만 MCP에 전달한다.
2. MCP 서버가 입력의 역할과 조각 배열이 활성 TERM_CARD와 정확히 일치하는지 다시 확인한다. 일치하지 않으면 `INVALID_SEARCH_TERMS`를 반환하고 검색하지 않는다.
3. MCP 서버가 `!goi {fragments} drawing site:pinterest.com/pin`을 `categories=images`, `format=json`, `language=en`으로 SearXNG에 요청한다.
4. HTTPS Pinterest 호스트의 숫자 `/pin/{id}` 결과만 순서대로 중복 없이 최대 8개 반환한다.
5. MCP의 정상 빈 결과는 `PIN_RESULTS_EMPTY`, 검색 요청·응답 장애는 `PIN_SEARCH_UNAVAILABLE`로 반환한다. 필수 SearXNG 주소 누락은 `CONFIGURATION_ERROR`로 실패한다.
6. worker는 MCP 결과를 기존 `RoleSearchOutcome`으로 변환해 역할별 최대 3회 재시도하고, 검색 후 widget 조회를 백엔드에서 계속 수행한다.

## How

- `search_pinterest_pins` 입력은 `role` enum(`body`, `pose`, `view`, `perspective`, `layout`)과 비어 있지 않은 `query_fragments` 문자열 배열이다. MCP는 역할과 전체 배열이 활성 TERM_CARD 중 하나와 정확히 일치하는지 검사하며, 불일치는 `{"failure_code":"INVALID_SEARCH_TERMS"}`로 반환하고 SearXNG 요청을 하지 않는다. 일치한 조각에 도구가 `drawing site:pinterest.com/pin`을 덧붙인다.
- MCP 서버만 `SEARXNG_BASE_URL`을 읽고 기존 `SearXNGPinterestSearchProvider`를 호출한다. API worker는 SearXNG에 직접 요청하지 않는다.
- 검색 정상 반환은 `{"role": "pose", "pins": [{"pin_id": "...", "pin_url": "...", "thumbnail_url": null, "status": "available"}], "code": null}` 형태다. 정상 0건과 검색 장애는 각각 `pins=[]`, `code=PIN_RESULTS_EMPTY` 또는 `PIN_SEARCH_UNAVAILABLE`로 반환한다. 필수 설정 누락은 `{"failure_code": "CONFIGURATION_ERROR"}`로 반환한다.
- worker는 설정된 MCP URL에 Streamable HTTP로 접속한다. 로컬 Compose는 내부 `mcp` 서비스, Cloud Run은 IAM 인증된 서비스 간 호출을 사용한다.
- MCP 연결·도구 응답 오류는 검색 장애로 처리하되 구성 누락은 `CONFIGURATION_ERROR`로 구분한다. Pinterest widget 요청과 응답 전용 썸네일 정책은 기존 계약을 유지한다.

## AC

- **Given** 유효한 카드의 검색 조각이 있을 때, **When** worker가 검색하면, **Then** MCP 도구에 해당 역할과 조각만 보내고 API 프로세스는 SearXNG를 직접 호출하지 않는다.
- **Given** 도구가 검색 조각을 받았을 때, **When** SearXNG가 JSON을 반환하면, **Then** Google Images 파라미터를 사용하고 검증된 Pin을 순서대로 최대 8개 반환한다.
- **Given** 검색 결과가 0건일 때, **When** 도구가 처리하면, **Then** `PIN_RESULTS_EMPTY`를 반환하고 worker는 재시도하지 않는다.
- **Given** SearXNG 또는 MCP 호출이 실패할 때, **When** worker가 검색하면, **Then** `PIN_SEARCH_UNAVAILABLE`로 역할별 최대 3회 시도하고 다른 역할의 성공 결과를 보존한다.
- **Given** SearXNG 또는 MCP 필수 주소가 누락됐을 때, **When** 검색을 시작하면, **Then** 구성 오류로 실패한다.
- **Given** MCP 도구의 역할 인자가 전달될 때, **When** 도구 입력 스키마를 확인하면, **Then** `body`, `pose`, `view`, `perspective`, `layout` 중 하나만 허용한다.
- **Given** 유효한 Pin ID가 반환됐을 때, **When** worker가 응답을 조립하면, **Then** 기존 widget 조회가 현재 응답용 `thumbnail_url`을 채우고 저장하지 않는다.
