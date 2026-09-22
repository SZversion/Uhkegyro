# TERM_CARD JSON 카탈로그 계약

## Why

팀이 검수한 전문용어만 LLM 선택·화면 설명·검색 계획에 사용하려면, 카드 원본과 검증 규칙이 하나여야 한다.

## Goal

- `index.json`과 index가 선언한 역할별 JSON을 TERM_CARD의 런타임 단일 원본으로 사용한다.
- 활성 카드 수를 고정하지 않고 카탈로그에서 동적으로 계산한다.
- 카탈로그가 유효하지 않으면 앱을 ready 상태로 만들지 않는다.

## What

앱 시작 시 index의 `categories` 순서대로 `body`, `pose`, `view`, `perspective`, `layout` JSON만 읽는다. 활성 조건 `runtime_eligible=true && mvp_status=active_in_current_contract`를 통과한 카드를 `term_id -> card` 메모리 사전과 역할별 목록으로 로드한다. 요청 처리 중 파일을 다시 읽지 않는다.

카드 변경은 JSON 수정, PR 검수, 배포, 새 인스턴스 시작 순서로 반영한다. TERM_CARD는 DB에 적재하거나 외부 어휘·Getty 데이터를 병합하지 않는다.

## How

시작 검증은 다음을 모두 확인한다.

- index와 index가 선언한 모든 역할 파일 존재
- JSON 파싱 가능
- 전역 고유 `term_id`
- 카드 `role`과 선언된 역할 일치
- `term_id`, `role`, `label_ko`, `label_en`, `query_fragments`, `look_for`, `confidence_gate`, `requires_all_of`, `requires_any_of`, `runtime_eligible`, `mvp_status` 필수 필드 존재
- 활성 카드의 비어 있지 않은 `query_fragments`
- 허용 역할과 활성 조건 유효성

전체 카드 수, 활성 카드 수, `card_count`의 특정 값은 검증하지 않는다. 카탈로그 검증 실패는 `CATALOG_INVALID_AT_STARTUP` 운영 원인으로 기록하고 worker/job 수신을 시작하지 않는다.

모든 카드의 `source_type`은 `team_card`다. Getty URI·외부 어휘 결과·이미지·Pin 메타데이터는 카드에 저장하지 않는다.

## AC

**AC-01 · 동적 활성 카드 로드**

- GIVEN: 구조적으로 유효한 index와 역할별 JSON이 있다.
- WHEN: 앱이 시작한다.
- THEN: 활성 조건을 통과한 모든 카드를 메모리에 로드한다.
- AND THEN: 카드 수가 바뀌어도 고정 수 검증으로 시작이 실패하지 않는다.

**AC-02 · 카탈로그 fail-closed**

- GIVEN: 선언 파일 누락, JSON 파싱 실패, 중복 ID 또는 필수 필드 누락이 있다.
- WHEN: 앱이 시작한다.
- THEN: ready 상태와 worker 시작을 거부한다.

**AC-03 · 런타임 선택 경계**

- GIVEN: 요청 처리 중 LLM 후보가 있다.
- WHEN: resolver가 후보를 검증한다.
- THEN: 메모리 사전에 존재하는 활성 카드만 선택·검색 계획에 사용한다.
