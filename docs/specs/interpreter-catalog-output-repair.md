# 카탈로그 기반 LLM 출력 복구

## Why
- 발표 시연자가 정면·전신이나 후속 설명을 제출할 때 역할 중복/역할 불일치로 세 번 모두 실패한다.
- 지표: 고정 정면·전신·포즈·후속 입력의 유효 출력 및 resolver 통과 여부.
## Goal
- v4의 기존 역할당 한 카드 계약을 모델 요청 단계에도 전달하고 active term/role 쌍을 제한한다.
- 범위 밖: resolver 검증 완화, 카드 추가, 사용자 원문을 임의 보정, 원격 Prompt 승격.
## What
- 정상 선택은 카탈로그 역할에 맞는 term ID와 원문 evidence를 반환한다.
- 같은 역할의 정면/전신 조건은 방향 카드 하나를 선택하며 나머지는 다른 역할로 옮기지 않는다.
- v4는 `ambiguous_fields`에 모호한 역할을 하나 이상 지정한다. 값은 `body`, `pose`, `view`, `perspective`, `layout` 중복 없는 배열이다. `needs_clarification`에서는 비어 있지 않아야 하고, `select_terms`에서는 빈 배열이어야 한다. 사용자가 요청하지 않은 역할은 모호한 역할로 취급하지 않는다. 예를 들어 포즈만 요청했고 그 조건이 모호하면 `ambiguous_fields=["pose"]`이다. v1 출력 계약은 변경하지 않는다.
- 잘못된 출력은 기존 최대 3회 재시도와 안전한 피드백을 유지한다.
## How
- v4에 코드 유래 strict JSON Schema를 사용한다. 카탈로그가 있으면 selection/context update의 role별 term ID enum을 공급한다.
- 역할별 정의는 로컬 `$ref`로 공유한다. 검증 제약과 전체 카드 입력은 유지하며 전송 표현만 압축한다. 세부 기준은 [interpretation-input-compression.md](./interpretation-input-compression.md)를 따른다.
- 모델 전송 형식의 selections/context_updates는 body·pose·view·perspective·layout 키를 가진 객체다. 각 슬롯은 해당 역할 객체 또는 null이며, 역할 중복을 구조적으로 막는다. 어댑터가 역할 순서의 배열로 변환한 후 기존 검증을 적용한다. 외부 API 형식은 유지한다.
- one-card-per-role, 역할 순서, evidence, 상태 규칙은 Pydantic/resolver가 계속 강제한다. v4 adapter만 `ambiguous_fields`를 schema에 포함하며 Pydantic은 제공된 경우 상태별 cardinality와 중복을 검사한다.
- 기존 v4 계약 보강이며 파일 Prompt/모델/version은 유지한다. v0 JSON mode, v1 기존 schema는 유지한다.
- Preview의 `LLM_MAX_TOKENS`는 2048로 명시한다. 기존 800 토큰에서 finish_reason=length가 발생했던 질문 응답을 수용하되, 중단된 출력은 여전히 거부하고 기존 재시도를 적용한다.
## AC
- Given v4와 활성 카탈로그, When 모델 호출, Then strict schema와 올바른 role/term enum이 전달된다.
- Given 잘못된 역할·중복 출력, When 검증, Then 기존 검증이 거부하고 재시도 피드백을 전달한다.
- Given v4가 `needs_clarification`을 반환한다, When JSON Schema와 Pydantic 검증을 수행한다, Then `ambiguous_fields`에 모호한 역할이 하나 이상 있고 모든 값은 허용 역할 enum이며 중복이 없다.
- Given 사용자가 포즈만 요청했고 그 포즈 조건이 모호하다, When v4가 `needs_clarification`을 반환한다, Then `ambiguous_fields=["pose"]`이고 요청하지 않은 역할은 포함하지 않는다.
- Given v4가 `select_terms`를 반환한다, When JSON Schema와 Pydantic 검증을 수행한다, Then `ambiguous_fields=[]`이다.
- Given v1 모델 호출, When JSON Schema를 구성한다, Then `ambiguous_fields`가 포함되지 않아 기존 출력 계약을 유지한다.
- Given 정면+전신과 명확한 포즈 고정 입력, When 실제 모델·resolver 검증, Then 활성 역할당 하나의 카드로 통과한다.
