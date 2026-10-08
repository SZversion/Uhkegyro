# 모호·상충 해석과 초보자 답변 품질

## Why
- 페르소나: 체형·자세 용어를 모르는 레퍼런스 탐색 사용자.
- 상황: 실제 v4 adapter 단독 평가 16건에서 12건만 기대 동작과 일치했다.
- 문제: 모호한 자세·의상 효과를 단정하고 중복 역할 오류를 반복한다. 설명은 의미·근거만 있고 관찰 지점이 부족하다.
- 지표: 실패 사례 및 변형 기대값 일치, 전체 30건 회귀, 질문 도메인 단서와 실제 답변의 관찰 지점.

## Goal
- GPT-4.1-mini와 v4에서 추측 대신 필요한 단서를 질문하고, 재시도에서 검증 피드백을 활용한다.
- 선택이 명확한 입력은 불필요하게 질문하지 않는다. 설명에는 쉬운 뜻·현재 입력 근거·카드 관찰 지점을 포함한다.
- 목표: 회귀 묶음 전부 통과, 전체 고정 30건 회귀 없음. 실측 결과와 미달 항목도 그대로 기록한다.
- 제외: 모델/production 기본값 변경, 임의 후보 자동 선택, UI·DB migration, 실제 Pinterest 품질 평가.

## What
- 인상·곡선만으로 콘트라포스토를 선택하지 않는다. 지지 다리와 어깨·골반의 반대 기울기가 명시되어야 한다.
- 명시된 한쪽 다리 체중 지지는 어깨·골반의 같은 방향 기울기와 양립한다. 이 추가 단서 때문에 weight_shift 선택을 포기하거나 불필요하게 되묻지 않는다.
- 의상으로 넓어 보이는 어깨는 실제 체형과 겉실루엣 중 무엇을 원하는지 묻는다. 실제 골격 비율이 별도로 명시되면 그 단서를 사용한다.
- 같은 역할 조건이 충돌하면 우선순위를 묻고 context_updates를 비워 기존 조건을 보존한다.
- server next_state는 확인 질문 결과에서 context_updates를 적용하지 않는다. 모델이 변경 후보를 반환해도 기존 constraints는 유지한다.
- 앉아서 가까운 손을 내미는 경우 포즈는 앉기 하나, 가까운 손의 확대는 원근 역할로 선택한다.
- 확인 질문은 현재 계약대로 selections=[]·answer_text=""·검색 없음이다. 명확한 기존 대화 조건은 삭제하지 않는다.
- v4는 attempt마다 provider를 두 번 호출한다. 첫 호출은 구조화 해석 JSON만 생성하고, 코드가 이를 검증한 다음 두 번째 호출에서 최종 답변을 생성한다. 두 번째 호출에는 항상 원문과 검증된 전체 JSON을 전달한다. `clarification_type`이 있으면 이때만 전용 Skill을 읽어 함께 전달해 질문을 만들고, 없으면 Skill 없이 일반 답변을 만든다.
- 정상 답변은 내부 ID·선택 알고리즘 설명 없이 짧은 한국어로 뜻·근거·참고 이미지 관찰 지점을 안내한다.

## How
- v4 System/User template의 모순된 답변 금지·6필드 계약을 answer_text 포함 7필드 계약으로 정렬한다. 사례별 결정 규칙과 대조 예시를 추가한다.
- v4 Memory classify는 새 시각 요청(mode=none)의 회상 필터를 비운다. 회상 keywords는 기존 schema 한도 5개를 명시한다. 평가 진단에는 해당 정적 필드 경로만 허용한다.
- adapter는 classify mode=none의 사용하지 않는 알려진 필터만 빈 값으로 정규화한다. recall/mixed 필터는 기존 한도를 검증하고, 알려지지 않은 추가 필드는 어느 mode에서도 거부한다.
- v4는 기존 JSON mode를 유지하며 validation_feedback를 다음 attempt의 user 메시지로 전달한다. 고정 system 규칙은 role_duplicate/state_rules 처리 방법을 설명한다. v0-v3의 해석 호출 형식·피드백 전달 정책은 유지한다.
- v4 다음 attempt의 user 메시지에는 서버 고정 repair_rules도 포함해 앉기+가까운 손의 역할 분리, 복합 동작 흐름의 단일 포즈와 상충 조건 질문을 교정한다. 모델 원문을 재주입하지 않는다.
- v4 첫 호출은 `skills/SKILL.md` 전체와 해석 프롬프트를 system message에 결합해 `answer_text=""`인 해석 JSON만 생성한다. provider JSON Schema, 프롬프트 예시, Pydantic 검증은 기존 `selections`·`context_updates` 배열 형식을 유지하고 `ambiguous_fields`를 추가한 동일 계약을 사용한다. `ambiguous_fields`는 이 첫 호출에서 요청의 의미를 보고 판단한다. 코드가 JSON/schema를 검증한 뒤 두 번째 호출은 항상 최종 답변을 생성한다. 일반 답변이면 clarification Skill은 읽지 않고 답변 지침과 검증된 JSON, 제공된 대화 맥락을 전달한다. 질문이면 `clarification_type`으로 코드가 `skills/clarification-response/SKILL.md`를 읽어 두 번째 호출에만 포함한다. 활성 term ID는 resolver가 검증한다.
- 질문은 `ambiguous_fields`의 역할을 실제 요청 의미에 맞춰 다루며, 짧은 한국어 한 문장으로 작성한다. 코드 검증은 역할 허용값·중복·상태 규칙과 질문 길이·형식·안전성에 한정한다. 질문 속 역할 단어를 문자열 cue로 검사해 의미 범위를 추론하거나, 그 결과를 고정 질문으로 바꾸지 않는다. 질문의 의미적 관련성은 첫 JSON 생성 지침과 평가 기준으로 다룬다. 이전 prompt version은 기존 동작을 유지한다.
- `CLARIFICATION_SKILL_PATH`는 기본 `skills/clarification-response/SKILL.md`를 지정하며 Docker image에 포함한다. Skill은 v4 JSON 검증 후 `clarification_type`이 있을 때만 읽는다. 이 경로의 파일 오류는 질문 응답 생성 시 설정 오류이며 일반 답변 경로는 Skill 파일을 읽지 않는다. 다른 Prompt 버전은 이 Skill 파일에 접근하지 않는다.
- 체형 충돌 질문은 어깨·골반 폭의 동등 단서와 어깨가 골반보다 넓다는 명시적 비교 단서가 모두 있을 때만 선택한다. 시점 충돌 질문은 옆모습을 원하는 동시에 정면처럼 보이길 원하는 대조 표현이 있을 때 선택한다. 단어의 존재만으로 충돌 축을 단정하지 않는다. 두 축 모두 충돌하거나 어느 축도 확정할 수 없으면 공통 충돌 질문을 사용한다.
- 선택·질문 기대값은 기존 dataset을 변경하지 않는다. 별도 ambiguity.jsonl에 명시/생략/부정/상충 대조 사례를 추가하고 LIVE_EVAL_INCLUDE_AMBIGUITY=1로 기존 runner에 포함한다.
- runner는 최종 사용자 질문의 must_address(_any_of)를 검사하고 실제 answer_text를 review.md로 내보낸다. 자동으로 정성 점수를 확정하지 않는다.
- 평가 DB는 이번 평가용 로컬 PostgreSQL만 사용하고 임시 schema를 삭제한다. Langfuse·실제 검색은 사용하지 않는다. synthetic 입력의 생성 답변만 산출물에 보존한다.
- 코드·프롬프트·데이터셋 지문, 수정 상태, 실제 응답 model, 호출·지연·비용을 기록한다. dirty 상태 실행은 commit 단독 재현 결과로 주장하지 않는다.

## AC
- Given 중복 역할 응답, When v4 다음 attempt, Then user 메시지에 제한된 검증 피드백을 받고 provider는 attempt당 한 번 호출된다.
- Given 모호한 곡선 자세 또는 의상 효과만 존재, When 해석, Then 필요한 지지·기울기 또는 체형/의상 단서를 묻고 검색하지 않는다.
- Given 명시된 한쪽 다리 지지·반대 어깨/골반 기울기 또는 실제 골격 비율, When 해석, Then 해당 카드 하나를 선택하고 질문을 남발하지 않는다.
- Given 상충하는 체형/시점 조건, When 해석, Then 우선 조건 질문이며 이전 대화 constraints를 수정하지 않는다.
- Given 명확한 동등 체형과 시점 충돌, When 고정 질문 선택, Then 시점만 질문하고 더 넓은 어깨 조건을 추가하지 않는다.
- Given 명확한 시점과 폭 비율 충돌, When 고정 질문 선택, Then 체형만 질문하고 옆모습/정면 선택지를 추가하지 않는다.
- Given 어깨·골반 단어만 있거나 비교 축이 불명확함, When 충돌 질문 선택, Then 공통 질문을 반환한다.
- Given v4 결과가 `select_terms`, When 파이프라인이 응답을 생성, Then 첫 번째 호출에는 도메인 Skill을 주입하고 두 번째 호출에는 clarification Skill 없이 대화 맥락을 포함해 일반 답변을 생성하며 총 두 번 호출한다.
- Given v4 결과가 `needs_clarification`이고 각 허용된 `clarification_type` 중 하나, When 파이프라인이 응답을 생성, Then 첫 번째 호출에 도메인 Skill을, 두 번째 호출에 질문 Skill과 대화 맥락을 포함해 최종 질문을 만들고 총 두 번 호출한다.
- Given 첫 호출의 v4 JSON이 유효하지 않음, When 해석 검증, Then 해당 attempt는 실패하고 최종 답변 호출은 실행하지 않는다.
- Given 일반 답변 결과와 존재하지 않는 Skill 경로, When v4 파이프라인 실행, Then Skill을 읽지 않고 두 번 호출을 완료한다.
- Given 내부 정책이나 비밀을 요구하는 질문 문구, When v4 JSON schema 검증, Then 구조화 출력이 거부되어 resolver가 그 문구를 전달하지 않는다.
- Given 사용자가 “당당한 자세”만 요청했고 모호함 상태 JSON에 `ambiguous_fields=["pose"]`, When 첫 LLM이 해석 JSON을 생성, Then `body`, `view`, `perspective`, `layout`은 추가하지 않는다.
- Given 포즈만 요청한 평가 사례, When 질문이 체형 자체를 묻거나 범용 질문임, Then 질문 품질 평가가 실패로 판정한다. 이는 resolver의 문자열 cue 검사로 의미를 재판정한다는 뜻이 아니다.
- Given 안전하고 형식이 유효한 v4 질문 JSON, When resolver, Then JSON의 질문을 그대로 전달하고 역할별 고정 질문으로 대체하지 않는다.
- Given v4 질문이 길이·형식·안전성 규칙을 위반, When JSON schema 검증, Then 구조화 출력이 거부된다.
- Given `ambiguous_fields`에 여러 역할이 명시됨, When 첫 LLM이 질문 JSON을 생성, Then 질문은 명시된 역할의 모호함을 함께 다룬다.
- Given 명확한 앉기와 가까운 손, When 해석, Then pose_sitting과 perspective_foreshortening을 역할별 하나씩 선택한다.
- Given 일반 결과, When 답변 검토, Then 쉬운 뜻·입력 근거·카드 관찰 지점이 있고 내부 ID·URL/Pin 추측이 없다.
- Given 고정 회귀/전체 평가, When runner, Then 실제 최종 질문을 검사하고 실제 답변과 지문·실패 내역을 검토 산출물에 기록한다.

검증(2026-10-02): 기존 30/30 + 대조 10/10 기대값 일치, backend 467 passed / 19 skipped. 실제 답변 근거와 한계는 [검증 문서](../../evals/ambiguity-quality-review-2026-10-02.md)에 기록했다.
