# Structured output Skill 실제 호출 평가

- 이 결과는 대화 기억 확장이 병합되기 전 `codex/interpreter-json-shape` 작업 기준이다. 최신 main에 복원·통합한 뒤의 재평가 결과는 아니다.
- 모델: `openai/gpt-4o-mini`; 프롬프트: `uhkegryo-interpreter-v2`.
- 실제 LLM 호출 대상 22문항: EVAL-01~16, EVAL-23~28.
- EVAL-17~22 안전 게이트, EVAL-29 강제 오류, EVAL-30 worker 중단 fixture는 이 실제 호출 평가에서 제외.
- JSON/Pydantic 계약: 20/22. 필수·금지 카드와 질문 상태 최소 기준: 13/22.
- 추가 추론 카드를 금지하고 resolver의 전체 거부도 실패로 계산: 8/22.
- Pinterest·공개 API·최종 AgentResult까지 평가한 점수가 아니다.
- 실행 카탈로그: `/app/term-cards`, 활성 카드 82개.
- 평가 입력 SHA-256: `e58d87e80da4e9bdd2a74fc4bd3ce25cb63019cddb5a2054dbe1eeebafe5e997`.

## 잔여 문제

- EVAL-08: `role_duplicate` 피드백을 전달해도 3회 연속 중복 역할.
- EVAL-14: `role_order` 피드백을 전달해도 3회 연속 순서 위반.
- 기타: 입력에 없는 조건 추론, 질문해야 하는 입력의 확정, 카드 선택 오차, 요청 원문과 evidence 불일치로 resolver 전체 거부.
- Skill 분리·JSON Schema·재시도 피드백은 의미 해석 정확도를 보장하지 않는다.
- 현재 UI의 실행 프롬프트는 v1을 유지한다. v2 production 활성화 전 의미 해석 평가를 통과해야 한다.

## 문항별 결과

| 문항 | JSON 계약 | 최소 기준 | 엄격 기준 | resolver/오류 |
|---|---|---|---|---|
| EVAL-01 | valid | True | True | proceed |
| EVAL-02 | valid | True | True | proceed |
| EVAL-03 | valid | True | True | proceed |
| EVAL-04 | valid | False | False | all_invalid |
| EVAL-05 | valid | True | True | proceed |
| EVAL-06 | valid | False | False | proceed |
| EVAL-07 | valid | True | False | proceed |
| EVAL-08 | error | False | False | validation_after_three_attempts |
| EVAL-09 | valid | False | False | proceed |
| EVAL-10 | valid | True | False | all_invalid |
| EVAL-11 | valid | True | False | proceed |
| EVAL-12 | valid | False | False | proceed |
| EVAL-13 | valid | False | False | proceed |
| EVAL-14 | error | False | False | validation_after_three_attempts |
| EVAL-15 | valid | False | False | proceed |
| EVAL-16 | valid | True | True | clarify |
| EVAL-23 | valid | True | True | proceed |
| EVAL-24 | valid | False | False | proceed |
| EVAL-25 | valid | True | True | proceed |
| EVAL-26 | valid | True | True | proceed |
| EVAL-27 | valid | True | False | proceed |
| EVAL-28 | valid | True | False | all_invalid |
