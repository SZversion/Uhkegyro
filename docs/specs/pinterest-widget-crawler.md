# Pinterest 공개 검색·Widget 조회

## Why

Pinterest API 승인이 없는 동안에도, 사전 허가된 범위에서 선택된 TERM_CARD의 검색 조각으로 외부 레퍼런스 링크와 응답 전용 미리보기를 제공해야 한다. 사용자는 역할별 원본 Pin 링크를 열어 레퍼런스를 확인하고, 서비스는 이미지 파일을 보관하지 않는다.

## Goal

- 서버의 Playwright 크롤러가 공개 Pinterest 검색 결과에서 역할별 Pin ID와 `pin_url`을 수집한다.
- 모든 수집 Pin ID는 `https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids={pin_id}`로 조회해 이미지 URL을 얻는다.
- 세션·job 이력에는 결과의 `pin_id`, `pin_url`, `status`만 포함하고, `thumbnail_url`과 이미지 바이트는 저장하지 않는다.

Pinterest API v5, `GET /v5/pins/{pin_id}`, 브라우저의 직접 크롤링, 이미지 다운로드·재게시, 외부 결과의 LLM 입력은 범위 밖이다.

## What

1. resolver가 활성 TERM_CARD의 `query_fragments`만 검색 provider에 전달한다.
2. Playwright는 공개 Pinterest 검색 결과에서 역할별 최대 8개의 고유 Pin ID와 원본 `pin_url`을 수집한다.
3. 수집한 각 Pin ID에 widget endpoint를 요청한다. 응답의 `images` 항목 중 가장 큰 면적의 URL을 `thumbnail_url`로 사용한다.
4. widget 응답에 이미지 URL이 없으면 해당 결과는 `pin_url`, `status="thumbnail_unavailable"`, `thumbnail_url=null`이다.
5. widget 응답의 이미지 URL은 현재 API 응답에만 넣는다. 세션·job 이력, 로그, trace, 카탈로그에는 저장하지 않는다.
6. 검색 페이지 또는 widget endpoint의 일시 실패는 기존 검색 provider 자동 재시도 대상이다. 재시도 소진 뒤 유효 카드가 있으면 `completed + partial_result`와 `PIN_SEARCH_UNAVAILABLE`을 반환한다.

## How

- crawler는 서버에서만 실행하며 Next.js UI·일반 브라우저는 Pinterest 또는 widget endpoint를 직접 호출하지 않는다.
- 공개 검색 요청 timeout은 15초, widget 요청 timeout은 10초다.
- 검색 URL은 선택된 `query_fragments`만 URL 인코딩해 만든다. LLM·사용자 입력·카드 밖 문자열을 추가하지 않는다.
- Pin ID와 `pin_url`이 모두 확인된 공개 결과만 후보로 사용한다. 중복 Pin ID는 역할 안에서 하나만 유지한다.
- 결과가 없으면 `pins=[]`, `reason_codes=["PIN_RESULTS_EMPTY"]`를 반환한다.
- widget 요청 실패, 차단, timeout, 형식 오류는 `PIN_SEARCH_UNAVAILABLE`로 분류한다. 이미지 URL 부재는 provider 오류가 아닌 `thumbnail_unavailable`이다.
- `pin_id`, `pin_url`, `status`는 세션·job 이력의 결과 필드로만 유지한다. `GET /api/jobs/{job_id}`는 저장된 `pin_id`로 widget을 다시 조회해 응답 전용 `thumbnail_url`을 조립한다. 별도 Pin 테이블·캐시·이미지 프록시를 만들지 않는다.
- `thumbnail_url`은 응답을 조립한 뒤 저장 전에 제거한다. 이미지 바이트·Pin 본문·작성자·보드·설명 등 widget의 나머지 응답 필드는 반환·저장·LLM 입력에 사용하지 않는다.

## AC

**AC-01 · Widget 기반 미리보기**

- GIVEN: crawler가 Pin ID와 `pin_url`을 수집했다.
- WHEN: widget endpoint가 하나 이상의 이미지 URL을 반환한다.
- THEN: 가장 큰 이미지 URL을 응답 전용 `thumbnail_url`로 반환한다.
- AND THEN: 세션·job 이력에는 `pin_id`, `pin_url`, `status`만 남긴다.

**AC-02 · 이미지 URL 부재**

- GIVEN: crawler가 Pin ID와 `pin_url`을 수집했다.
- WHEN: widget 응답에 이미지 URL이 없다.
- THEN: `thumbnail_url=null`, `status="thumbnail_unavailable"`과 원본 `pin_url`을 반환한다.

**AC-03 · 검색 장애**

- GIVEN: 공개 검색 또는 widget 요청이 일시적으로 실패한다.
- WHEN: 동일 job의 자동 재시도가 소진된다.
- THEN: 유효 카드가 있으면 `completed + partial_result`와 `PIN_SEARCH_UNAVAILABLE`을 반환한다.

**AC-04 · 외부 데이터 비저장**

- GIVEN: widget 응답이 이미지 URL과 추가 Pin 데이터를 포함한다.
- WHEN: API 응답과 세션·job 이력을 조립한다.
- THEN: `pin_id`, `pin_url`, `status`만 이력에 포함한다.
- AND THEN: `thumbnail_url`은 현재 API 응답에만 반환하고 저장·LLM 입력에 사용하지 않으며, 이미지 바이트와 Pin 본문·작성자·보드 정보는 저장·반환·LLM 입력에 사용하지 않는다.
