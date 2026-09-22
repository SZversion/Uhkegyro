# 신뢰 경계

## Why

사용자 입력과 검색 provider 결과는 신뢰할 수 없지만, TERM_CARD JSON과 결정론 검증은 팀이 관리한다.

## Goal

- LLM·사용자·외부 결과가 카드 ID, 검색어, Pin URL, 최종 상태를 임의로 결정하지 못하게 한다.
- 비밀값·사용자 원문·외부 원문이 UI, trace, 프롬프트에 불필요하게 노출되지 않게 한다.

## What

신뢰 원본은 시작 검증을 통과해 메모리에 로드된 TERM_CARD JSON 카탈로그와 서버 결정론 코드다. LLM 출력은 후보일 뿐이며 resolver가 역할·활성·조건을 다시 검증한다. 검색 provider의 Pin URL·썸네일 URL은 표시용 untrusted data이며 카드·검색어·프롬프트를 바꾸지 않는다.

## How

- 브라우저는 자연어 `request_text`만 전송한다.
- 사전 안전 검사는 프롬프트/비밀값 추출과 유해·불법 요청을 `unsafe_input`으로 끝내고 LLM·검색을 호출하지 않는다.
- 외부 원문·이미지·Pin 본문을 LLM 프롬프트나 RAG에 주입하지 않는다.
- 비밀값, 세션 토큰, 사용자 원문, 이미지 바이트는 UI와 trace에 노출하지 않는다.

## AC

**AC-01 · 카드 재검증**

- GIVEN: LLM 후보가 있다.
- WHEN: resolver가 처리한다.
- THEN: 메모리 카탈로그의 활성 term ID·역할·조건을 통과한 후보만 사용한다.

**AC-02 · 외부 데이터 격리**

- GIVEN: 검색 provider 결과가 있다.
- WHEN: 응답을 조립한다.
- THEN: Pin URL·응답 전용 썸네일은 표시할 수 있지만 LLM 입력·카탈로그·영구 저장에는 사용하지 않는다.
