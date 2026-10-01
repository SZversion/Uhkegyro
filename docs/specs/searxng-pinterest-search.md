# SearXNG Google 이미지 검색 기반 Pinterest Pin 탐색

## Why

- **페르소나·상황**: Pinterest 원본 Pin을 찾는 일러스트 레퍼런스 Agent 사용자.
- **문제**: 서버 브라우저로 Pinterest 검색 HTML을 가져오는 방식은 차단·렌더링 변화에 취약하다.
- **측정 지표**: Google 이미지 카테고리의 JSON 결과에서 역할별 최대 8개의 유효 Pinterest Pin 링크를 조립한다.

## Goal

- SearXNG Search API의 이미지 카테고리와 Google Images 엔진만 사용해 Pin 결과를 찾는다.
- 활성 TERM_CARD 검색 조각에 `drawing site:pinterest.com/pin`을 추가해 검색하고 결과 중 Pinterest의 숫자 Pin 경로만 반환한다.
- 기존 Pinterest widget 조회와 thumbnail 비저장 계약은 유지한다.
- **범위 밖**: Pinterest 페이지 직접 크롤링, 다른 검색 엔진 사용, 원격 SearXNG 서버 운영, 이미지 바이트·Pin 부가 메타데이터 저장. 로컬 개발용 SearXNG Compose 서비스와 설정은 이 Spec 범위에 포함한다.

## What

1. Worker는 활성 카드의 검색 조각과 고정 검색 제한어를 SearXNG에 전달한다.
2. 요청은 검색어 앞의 `!goi`로 Google Images만 선택하고 `categories=images`, `format=json`, `language=en`으로 보낸다.
3. JSON 결과에서 URL을 읽고 `pinterest.com` 또는 하위 도메인의 `/pin/{숫자}` 경로만 정규화한다.
4. 중복 Pin ID를 제거하고 기존 순서대로 역할별 최대 8개를 반환한다.
5. 검색 0건은 `PIN_RESULTS_EMPTY`, SearXNG 요청·응답 실패는 `PIN_SEARCH_UNAVAILABLE`로 반환한다.
6. 기존 widget endpoint는 유효 Pin ID의 thumbnail URL을 조회한다. 완료 job 조회 응답의 각 Pin에는 `thumbnail_url`과 `pin_url`을 함께 넣어 프론트에 전달한다.
7. Docker Compose는 SearXNG를 `searxng` 서비스로 실행하고 API 컨테이너는 `http://searxng:8080`으로 Search API를 호출한다. SearXNG 설정은 JSON 응답과 Google Images 엔진을 활성화한다.

## How

- 설정: API 서버 전용 `SEARXNG_BASE_URL`; Compose 내부 기본 주소는 `http://searxng:8080`이며 끝의 `/`는 제거한다. 빈 값은 즉시 `CONFIGURATION_ERROR`로 처리한다. SearXNG의 `SEARXNG_SECRET`은 `.env`에서만 전달한다.
- API: `GET {SEARXNG_BASE_URL}/search`에 `q`, `categories=images`, `format=json`, `language=en`을 전달한다. Google Images 선택은 SearXNG 검색 문법 `!goi`로 고정한다. Search API의 JSON 출력은 SearXNG 인스턴스에서 활성화되어 있어야 한다.
- Compose: SearXNG 컨테이너는 호스트의 loopback 주소에만 포트 `8080`을 공개한다. 설정 파일은 JSON format을 허용하고 `google images` 엔진을 활성화한다.
- 검색어: `!goi {" ".join(query_fragments)} drawing site:pinterest.com/pin`; 사용자 문장이나 LLM 자유 텍스트는 추가하지 않는다.
- URL 검증: HTTPS, host `pinterest.com` 또는 그 하위 도메인, path `/pin/{ASCII digits}`만 허용한다. 반환 링크는 `https://www.pinterest.com/pin/{id}/`로 정규화한다.
- 결과 모델·widget·job 저장 경계는 `pinterest-widget-crawler.md`의 기존 `PinResult` 계약을 따른다. `GET /api/jobs/{job_id}` 응답은 같은 Pin 결과의 `thumbnail_url`과 `pin_url`을 함께 반환하고, `thumbnail_url`은 job 이력에 저장하지 않는다.
- `httpx`를 사용하며 요청 제한시간은 15초다. SearXNG 결과의 이미지 URL, 제목, 본문은 읽거나 저장하지 않는다.

## AC

- **Given** SearXNG JSON에 서로 다른 결과 URL이 있을 때, **When** 검색하면, **Then** 요청은 `!goi`와 images 카테고리로 Google Images만 선택한다.
- **Given** Pinterest pin URL과 타 도메인·비 Pin URL이 함께 있을 때, **When** 결과를 파싱하면, **Then** 숫자 Pin URL만 고유 순서로 최대 8개 반환한다.
- **Given** SearXNG가 성공 응답에 결과를 반환하지 않을 때, **When** 파싱하면, **Then** 빈 pins와 `PIN_RESULTS_EMPTY`를 반환한다.
- **Given** 설정이 누락됐을 때, **When** 검색하면, **Then** `CONFIGURATION_ERROR`로 즉시 실패한다.
- **Given** HTTP 오류, timeout 또는 잘못된 JSON일 때, **When** 검색하면, **Then** 기존 검색 실패 계약대로 `PIN_SEARCH_UNAVAILABLE`을 반환한다.
- **Given** Pin 결과를 job/API 응답으로 조립할 때, **When** 저장·조회하면, **Then** Pinterest widget 동작과 `thumbnail_url` 비저장 계약을 유지한다.
- **Given** widget에서 이미지 URL을 얻은 Pin이 있을 때, **When** 프론트가 완료된 job을 조회하면, **Then** 같은 결과 항목에 `thumbnail_url`과 `pin_url`을 함께 받는다.
- **Given** Docker Compose 환경을 시작할 때, **When** API가 SearXNG를 호출하면, **Then** API는 `http://searxng:8080`을 사용하고 SearXNG JSON Search API와 Google Images 엔진이 활성화되어 있다.
