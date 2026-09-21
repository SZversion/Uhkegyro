# Getty Term Resolution Pipeline Spec

## Why

- LLM이 프로젝트 밖의 임의 용어를 만들지 않고, 프로젝트 `term_id`를 먼저 선택하도록 제한한다.
- 선택된 용어를 Getty AAT로 확인할 수 있으면 URI와 출처를 함께 보여 주되, Getty 결과가 없거나 일시적으로 실패해도 초보자의 Pinterest 탐색 흐름은 멈추지 않아야 한다.

## Goal

- FastMCP 도구가 구조화된 `Selection` 목록을 받아 term ID를 검증하고, term ID에서 역할 접두사를 제외한 영문 용어로 Getty AAT를 조회한 뒤, 성공/폴백 출처와 Pinterest 검색 계획을 한 결과로 반환한다.

## What

1. LLM은 허용된 프로젝트 `term_id`와 역할·근거를 `Selection`으로 출력한다. 실제 LLM 호출은 이 실험 범위 밖이다.
2. FastMCP의 `resolve_illustration_reference_plan` 도구는 `Selection`을 검증한다.
3. 각 term ID에서 `body_`, `pose_`, `view_`, `perspective_`, `layout_` 역할 접두사를 제외하고 `_`를 공백으로 바꾼 Getty 조회어로 AAT를 최대 한 건 조회한다. 예: `pose_contrapposto` → `contrapposto`.
4. Getty가 후보를 반환하면 `source=getty_aat`과 Getty label·URI·출처 URL을 반환한다.
5. Getty가 후보를 찾지 못하거나 timeout·5xx·비정상 응답이면 `source=term_cards`와 정적 카드 label·관찰 기준을 사용한다.
6. 코드가 검증된 정적 카드의 `query_fragment`로 역할별·통합 Pinterest 링크를 만든다. Getty의 동적 label은 링크 생성에 사용하지 않는다.

## How

- **책임 분리**: LLM은 허용된 `Selection` 구조만 만들고, `validate_selection`이 역할·프로젝트 `term_id`를 먼저 검증한다. `resolve_reference_plan`은 Getty 결과와 정적 카드 폴백을 결정하며, 기존 `build_search_plan`은 검증된 카드로 Pinterest URL만 생성한다. FastMCP의 `resolve_illustration_reference_plan`은 이 서비스를 호출하는 경계다.
- **입력 계약**: 도구 입력은 `role`, `term_id`, 하나 이상의 `evidence`를 가진 `Selection` 목록이다. 역할 중복, 알 수 없는 term ID는 Getty 요청 전에 오류로 거부한다.
- **출력 계약**: `ReferenceResolution`은 역할별 `TermResolution` 목록과 `SearchPlan`을 반환한다. 성공한 항목은 `resolution_source=getty_aat` 및 `VocabularyTerm`의 `subject_uri`, `label`, `source_name`, `source_url`을 포함한다. 폴백 항목은 `resolution_source=term_cards`와 `getty_aat_term_not_found` 또는 `getty_aat_unavailable` limitation을 포함한다.
- **외부 연동과 제약**: `GettyAatClient`만 Getty SPARQL endpoint에 최대 한 건을 POST로 조회하며, timeout·HTTP 오류·비정상 JSON은 `status=unavailable`으로 변환한다. Getty label·URI는 Pinterest 검색어를 바꾸거나 LLM 프롬프트·RAG에 자동 주입하지 않는다. 이미지·소장품·Pinterest HTTP 요청은 하지 않는다.

## Out of Scope

- 실제 OpenAI 또는 다른 LLM 호출
- Getty 결과를 LLM 프롬프트·RAG에 자동 주입
- Getty·Pinterest 이미지 요청, 다운로드, 저장, 재게시
- Getty와 자체 DB의 병합 조회
- term 카드 자동 생성·수정

## Fallback Rules

| Getty 결과 | `resolution_source` | Pinterest 검색 조각 | limitation |
| --- | --- | --- | --- |
| `status=ok`, 후보 1건 이상 | `getty_aat` | 정적 `TERM_CARDS`의 `query_fragment` | 없음 |
| `status=ok`, 후보 없음 | `term_cards` | 정적 `TERM_CARDS`의 `query_fragment` | `getty_aat_term_not_found` |
| timeout·5xx·비정상 응답 | `term_cards` | 정적 `TERM_CARDS`의 `query_fragment` | `getty_aat_unavailable` |

## AC (Given-When-Then)

**AC-01 · Getty 성공**
- GIVEN: LLM이 `pose_contrapposto`를 선택하고 Getty가 `contrapposto` URI를 반환한다.
- WHEN: FastMCP 파이프라인을 실행한다.
- THEN: Getty URI·label·출처 URL과 `getty_aat` 출처를 반환하고 Pinterest 링크를 만든다.

**AC-02 · 미존재 폴백**
- GIVEN: 유효한 프로젝트 term ID와 후보 없는 Getty 응답이 있다.
- WHEN: FastMCP 파이프라인을 실행한다.
- THEN: 정적 `TERM_CARDS` 정보, `term_cards` 출처, `getty_aat_term_not_found` limitation과 Pinterest 링크를 반환한다.

**AC-03 · 장애 폴백**
- GIVEN: 유효한 프로젝트 term ID와 Getty timeout 또는 5xx 응답이 있다.
- WHEN: FastMCP 파이프라인을 실행한다.
- THEN: 예외를 전파하지 않고 정적 카드와 `getty_aat_unavailable` limitation으로 Pinterest 링크를 반환한다.

**AC-04 · 허용 term ID만 조회**
- GIVEN: 유효하지 않은 역할 또는 term ID가 있다.
- WHEN: FastMCP 파이프라인을 실행한다.
- THEN: Getty 조회와 Pinterest 링크 생성 전에 입력 오류로 거부한다.
