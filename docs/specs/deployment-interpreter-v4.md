# 배포 해석 모델·프롬프트 v4 정렬

## Why
이전 작업 트리에서 평가한 GPT-4.1-mini·v4를 배포 후보 설정으로 선택한다. 같은 v4 이름이어도 현재 파일의 지문이 달라 과거 40/40을 현재 PR의 품질 통과 근거로 사용할 수 없다. 측정 지표는 배포·로컬 실행 설정의 모델/경로/버전 세 값 일치다.

## Goal
Cloud Build API와 Compose API, 환경 변수 예시를 openai/gpt-4.1-mini·v4로 정렬한다. 제외: 실제 클라우드 배포, 기본 Settings의 구버전 호환 변경, 원격 Prompt 운영 구현, 외부 평가 실행.

## What
과거 40/40·비용·지연은 이전 작업 트리의 참고 결과로 제한한다. 현재 PR의 실제 모델 품질·운영 배포·외부 연결은 재검증 전 미검증이다.

새 Compose API는 v4 파일과 v4 버전을 함께 기본 적용한다. 명시적 환경 변수 override는 유지한다. Cloud Build API는 같은 모델과 이미지 내부 v4 경로·버전을 명시한다. MCP에는 해석 설정을 새로 추가하지 않는다.

## How
- Dockerfile에 v4 파일을 이미지 내부 경로로 복사한다.
- LLM_MODEL=openai/gpt-4.1-mini
- INTERPRETER_PROMPT_VERSION=uhkegryo-interpreter-v4
- Cloud Build: INTERPRETER_PROMPT_PATH=/app/prompts/uhkegryo-interpreter-v4.md
- Compose: 같은 이미지 내부 경로를 기본으로 하며 명시적 override 허용.
- 직접 Python 실행 예시: ./prompts/uhkegryo-interpreter-v4.md
- 경로와 버전을 함께 설정해야 v4 검증 피드백 분기가 적용된다. 배포 가이드·README는 이 계약을 따른다.

- Preview 출력 계약과 2048 토큰 상한은 [interpreter-catalog-output-repair.md](interpreter-catalog-output-repair.md)를 따른다.

## AC
- Given 과거 실행과 현재 파일 지문 불일치, When 모델 선택 근거를 기록, Then 과거 결과는 참고로만 사용하고 현재 PR의 품질 통과로 주장하지 않는다.
- Given 새 배포 구성, When Cloud Build API 환경 변수 확인, Then 모델·v4 경로·v4 버전이 모두 명시된다.
- Given override 없음, When Compose API 설정 확인, Then 같은 세 값이 기본 적용된다.
- Given 환경 변수 예시, When Settings와 adapter를 로드, Then 모델은 GPT-4.1-mini, 버전은 v4이고 실제 v4 파일이 파싱된다.
- Given 기존 adapter/worker 회귀 테스트, When 실행, Then 이전 버전의 명시적 설정과 v4 동작이 유지된다.

검증(2026-10-03): backend 487 passed / 28 skipped. 외부 전송을 비활성화한 테스트 환경에서 실행했다. .env.example과 로컬 .env의 모델·버전 및 실제 v4 파일 파싱 확인. git diff --check 통과. Docker 실행 도구가 없어 이미지 빌드·Compose 렌더링·실제 클라우드 배포는 미검증이다.

PR 분리 검증(2026-10-03): origin/main a0c49f7 기반에서 PR #108 미커밋 파일을 제외한 이번 변경만으로 backend 483 passed / 28 skipped. 실제 외부 연결·품질 검증은 실행하지 않았다.
