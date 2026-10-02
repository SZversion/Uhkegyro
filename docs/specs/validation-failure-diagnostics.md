# 출력 검증 실패 진단 보존

## Why
최종 실패 시 validation_feedback_json이 지워져 JSON 오류와 대화 근거 오류를 구분할 수 없다.

## Goal
최종 검증 실패의 단계·필드 경로·고정 오류 코드를 내부 DB에 보존한다. 사용자 응답, 재시도 정책, 출력 스키마는 변경하지 않는다.

## What
검증 오류 종료 시 진단 목록을 저장한다. 다른 오류 종료 시 이전 진단은 지운다. 원문, 모델 출력, 예외 메시지, 키는 저장하지 않는다.

## How
기존 validation_feedback_json 컬럼을 사용한다. 단계는 interpretation_schema, memory_schema, conversation_validation이다. 최대 8개 항목과 허용된 스키마 필드/오류 코드만 저장한다. 알 수 없는 값은 고정 대체값으로 치환한다. 재시도용 feedback 구조는 유지한다. 기존 실패의 삭제된 기록은 복원할 수 없다.

## AC
- Given 검증 오류, When 최종 시도가 실패하면, Then 단계·경로·코드를 보존한다.
- Given 원문을 담은 임의 진단값, When 저장하면, Then 원문은 고정 대체값으로 치환된다.
- Given 비검증 오류, When 최종 실패하면, Then 진단값은 null이고 공개 실패 계약은 동일하다.
- Given 대화 근거 불일치, When 검증하면, Then 고정 원인 코드와 conversation_validation 단계가 발생한다.

## 검증 경계
모의 DB 테스트 및 관련 회귀 테스트로 확인한다. 실제 유료 LLM 요청과 Neon 쓰기 테스트는 별도 승인 없이는 실행하지 않는다.
