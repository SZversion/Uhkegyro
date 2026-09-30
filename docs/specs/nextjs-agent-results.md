# Next.js Agent 결과·질문·Pin 표시 (작업 20)

## Why

- **페르소나**: 용어가 낯선 캐릭터 일러스트 초보 사용자
- **상황**: 완료된 Job에서 역할별 용어와 Pinterest 레퍼런스를 확인한다.
- **문제**: 질문·부분 실패·삭제된 Pin을 일반 성공 화면처럼 보이면 사용자가 다음 행동을 결정하기 어렵다.
- **측정 지표**: 완료 상태별 안내 표시율 100%, Pin 링크의 원본 URL 사용률 100%, 썸네일 영구 저장 0건

## Goal

- `success`, `needs_clarification`, `partial_result`, `out_of_scope`, `unsafe_input`과 Job `failed`를 계약대로 구분해 표시한다.
- 역할 탭과 원격 썸네일·원본 Pin 링크를 제공한다.
- **Out of Scope**: 이미지 저장·프록시, 대화 이력, 선택형 답변의 서버 생성([예정 계약](./clarification-choices.md))

## What

1. `success`와 `partial_result`에서 `reference_plan.terms`의 역할만 탭으로 표시한다. Pin이 있는 첫 역할을 기본 선택하고, 모두 비었으면 첫 역할을 선택한다.
2. 선택 역할의 한국어·영어 용어, 쉬운 설명, 선택 이유, 확인 포인트와 Pin 카드를 보여 준다. `available + thumbnail_url` 카드는 원격 이미지를 원본 `pin_url` 새 탭 링크로 표시한다. 이미지가 없거나 `deleted`면 접근 불가 안내를 표시한다.
3. `PIN_RESULTS_EMPTY`는 결과 0건, `PIN_SEARCH_UNAVAILABLE`은 검색 실패로 구분한다. 부분 결과는 성공한 다른 역할을 유지하고 실패 역할에 검색 링크·같은 조건 재검색·조건 수정 행동을 제공한다.
4. `needs_clarification`은 질문 하나와 직접 입력을 보여 주고 `reference_plan`은 숨긴다. 후속 계약 활성화 뒤 `clarification_choices`가 있으면 칩을 눌러 편집 가능한 새 요청을 채운다. `out_of_scope`, `unsafe_input`, Job `failed`는 안전한 사용자 메시지만 표시한다.

## How

- 브라우저는 `JobEnvelope.result`와 `failure.user_message`만 화면에 사용한다. 서버 제공 역할·Pin 순서를 유지하고 term ID, 검색어 또는 URL을 새로 생성하지 않는다.
- 결과는 React 메모리에만 둔다. `thumbnail_url`, 원문, session token과 Pin 본문을 localStorage·sessionStorage·URL·로그에 기록하지 않는다.
- 같은 조건 재검색은 현재 메모리의 이전 `request_text`를 새 UUID `Idempotency-Key`로 제출해 새 Job을 만든다. 검색 링크는 해당 역할의 서버 제공 `search_url`을, Pin 링크는 서버 제공 `pin_url`을 새 탭에서 연다.
- 질문 선택지는 필드가 없거나 빈 배열이면 표시하지 않는다. 칩 선택은 입력창 채우기만 하며 전송은 사용자 행동으로 수행한다.

## AC

**AC-01 · 역할과 원본 Pin**

- GIVEN: 둘 이상의 역할과 Pin이 있는 완료 결과가 있다.
- WHEN: 역할을 선택하고 Pin을 연다.
- THEN: 해당 역할의 용어·확인 포인트·원순서 Pin을 표시하고 원본 `pin_url`을 새 탭에서 연다.

**AC-02 · 부분 결과**

- GIVEN: 한 역할은 Pin이 있고 다른 역할은 `PIN_SEARCH_UNAVAILABLE`이다.
- WHEN: 부분 결과를 표시한다.
- THEN: 사용 가능한 Pin을 유지하고 실패 역할의 안내·`search_url`·새 Job 재검색·조건 수정 행동을 표시한다.

**AC-03 · 질문과 실패**

- GIVEN: `needs_clarification` 또는 Job `failed` 응답이 있다.
- WHEN: UI가 응답을 표시한다.
- THEN: 질문 상태에는 질문과 직접 입력을 보이며 `reference_plan`은 숨기고, 실패 상태에는 `user_message`만 표시한다.

**AC-04 · 접근 불가와 저장 경계**

- GIVEN: Pin이 `deleted`이거나 `thumbnail_url=null`이다.
- WHEN: 카드를 표시한다.
- THEN: 이미지 대신 접근 불가 안내를 표시하고 썸네일 URL·이미지 바이트를 저장하지 않는다.
