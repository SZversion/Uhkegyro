# SearXNG Google Images Pinterest Pin 검색 provider

## Why

- **페르소나·상황**: 검증된 TERM_CARD로 Pinterest 원본 Pin을 찾는 백엔드 개발자.
- **문제**: Pinterest 검색 HTML 파서는 렌더링 변화와 차단에 취약하다.
- **측정 지표**: Google 이미지 JSON 결과에서 유효한 Pin URL을 순서대로 최대 8개 반환한다.

## Goal

- SearXNG Search API의 Google Images 엔진과 이미지 카테고리만 사용한다.
- 활성 카드의 `query_fragments`에 `drawing site:pinterest.com/pin`을 붙인다.
- URL이 HTTPS Pinterest 호스트의 숫자 Pin 경로인 결과만 반환한다.
- **범위 밖**: 이 PR에서 worker 연결, 기존 HTML 크롤러 제거, 이미지 파일 저장.

## What

1. provider가 `!goi` 검색 문법과 `categories=images`, `format=json`, `language=en`을 요청한다.
2. JSON의 `results[].url`만 읽어 Pinterest Pin ID와 정규화된 URL을 만든다.
3. 중복 ID를 제거하고 결과 순서대로 최대 8개 반환한다.
4. 정상 0건은 `PIN_RESULTS_EMPTY`, HTTP·응답 실패 또는 Google Images 엔진의 `unresponsive_engines` 오류는 `PIN_SEARCH_UNAVAILABLE`로 반환한다. 오류 원문은 로그에 남기지 않는다.

## How

- `SearXNGPinterestSearchProvider(base_url=...)`는 `GET {base_url}/search`를 `httpx`로 호출하며 제한시간은 15초다.
- 검색어는 `!goi {" ".join(query_fragments)} drawing site:pinterest.com/pin`이다.
- `https`와 `pinterest.com` 또는 하위 도메인, `/pin/{ASCII digits}` 경로만 허용한다.
- 반환 URL은 `https://www.pinterest.com/pin/{id}/`로 정규화한다.
- base URL 누락은 `CONFIGURATION_ERROR`이고, 이미지 URL·본문·제목은 읽거나 저장하지 않는다.

## AC

- **Given** 활성 카드 검색 조각이 있을 때, **When** provider가 검색하면, **Then** Google Images만 선택하는 파라미터를 보낸다.
- **Given** Pinterest와 외부 도메인 URL이 섞인 JSON일 때, **When** 파싱하면, **Then** 숫자 Pin URL만 고유 순서대로 최대 8개 반환한다.
- **Given** 검색 결과가 없을 때, **When** 파싱하면, **Then** `PIN_RESULTS_EMPTY`를 반환한다.
- **Given** SearXNG가 HTTP 200과 빈 결과, Google Images의 `unresponsive_engines` 오류를 반환할 때, **When** provider가 처리하면, **Then** `PIN_SEARCH_UNAVAILABLE`을 반환하고 worker가 최대 세 번 검색을 시도한다.
- **Given** 주소 누락·HTTP 오류·잘못된 JSON일 때, **When** 검색하면, **Then** 주소 누락은 `CONFIGURATION_ERROR`, 그 외 실패는 `PIN_SEARCH_UNAVAILABLE`로 처리한다.
