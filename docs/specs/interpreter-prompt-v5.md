# 해석 프롬프트 v5 정리

상태: 구현/자동 계약 테스트는 통과했으나 실제 모델 품질 목표는 미달했다. 완료 판정과 운영 적용을 보류한다. [평가 기록](../../evals/interpreter-prompt-v5-2026-10-06.md)을 참고한다.

## Why
- 사용자가 본문 해석을 기다리는 동안 v4는 중복 판단 규칙과 배열/객체 출력 지시를 함께 전송한다.
- 지표: 실제 system/user 입력 토큰, 선택 정확도, 원문 인용 통과율, 검증 재시도, 본문 해석 시간.

## Goal
- v5에서 판단 규칙을 한곳에 모으고 selections/context_updates를 역할별 nullable 객체 슬롯으로 통일한다.
- 같은 전체 카탈로그를 사용한 실제 모델 비교에서 입력 토큰을 줄이고 기존 통과 사례의 계약 정확도를 유지한다.
- 범위 밖: 카탈로그 필터링, 모델 변경, 기억/검색 정책 변경, API 변경, 운영 설정/배포/원격 Prompt 승격.

## What
- 입력 원문은 기존 verbatim 태그를 사용해 User template의 카탈로그 뒤에 한 번만 전달하고 끝에서 원문 인용을 확인한다. 모든 외부 입력은 명령이 아닌 데이터다.
- 활성 ID/역할, 모호함·충돌, 체형과 의상 구분, 자세와 원근 구분, 동일 대화 원문 근거 및 현재 요청 조건 변경 규칙을 유지한다.
- 본문 설명과 출력 지침은 v5 파일에서만 관리하고 adapter는 v4용 지침을 덧붙이지 않는다.
- v4와 이전 버전은 유지해 경로/버전 설정을 함께 되돌릴 수 있다.
- v5는 비어 있지 않은 활성 카탈로그를 요구한다. 배열 출력·잘못된 슬롯은 기존 재시도 가능한 검증 오류로 거부한다.

## How
- `prompts/uhkegryo-interpreter-v5.md`의 System/User 및 Memory sections를 저장소 파일에서 읽는다. Memory instructions는 v4와 동일하다.
- adapter는 v5를 strict JSON Schema 경로로 처리하며 v4와 같은 역할/ID 제한과 배열 변환, Pydantic/대화 근거/resolver 검증을 사용한다.
- v5 선택 시 파일의 Prompt 이름과 설정이 맞지 않거나 활성 카탈로그가 없으면 호출 전 구성 오류로 중단한다.
- 재검증 feedback은 진단 데이터로 전달하고 v5 파일의 기존 판단/인용 지침에 따라 응답을 다시 작성한다. v4의 반복 repair_rules는 추가하지 않는다. 이 변경의 재시도 품질은 실제 평가에서 미달했다.
- 활성화 설정은 `INTERPRETER_PROMPT_VERSION=uhkegryo-interpreter-v5`, `INTERPRETER_PROMPT_PATH=prompts/uhkegryo-interpreter-v5.md`를 함께 지정한다. 이번 작업에서 운영/default 설정은 바꾸지 않는다.
- 고정 정상/모호/충돌 사례와 대화·공격 지시 사례를 동일 모델·카탈로그·temperature·출력 예산으로 v4/v5 비교한다. 실제 검증 실패는 최대 3회와 feedback으로 재시도하며 호출/토큰/지연을 기록한다.
- 실패 원인은 숨기지 않고 평가 보고서에 기록한다. 운영 지연 보장은 하지 않는다.

## AC
- Given v5와 활성 카드, When 호출하면, Then strict 역할 슬롯 스키마와 파일 System message만 전달되고 사용자 요청은 template에 한 번만 있다.
- Given 정상/모호/충돌/후속 입력, When 모델 출력과 서버 검증을 실행하면, Then 활성 ID·역할·원문 인용·질문 상태 계약을 지킨다.
- Given 배열/누락/잘못된 역할 출력, When v5 검증하면, Then 거부하며 안전한 feedback으로 재시도한다.
- Given 잘못된 파일/버전 또는 빈 카탈로그, When v5 호출을 준비하면, Then 모델을 호출하지 않고 구성 오류를 반환한다.
- Given 기존 v4/v1/v0, When 회귀 테스트하면, Then 기존 프롬프트 조립과 출력 계약이 유지된다.
