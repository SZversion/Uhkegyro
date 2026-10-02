# 로컬 Agent 통합 답변·검색 연동 확인

## Why

- **페르소나·상황**: 최신 main을 받아 로컬 UI에서 실제 레퍼런스를 검색하는 팀원.
- **문제**: 오래된 API 이미지에는 `answer_text`가 없고, SearXNG가 실행되지 않으면 화면과 검색 결과를 함께 확인할 수 없다. `/health` 성공만으로 전체 요청 성공을 판단할 수 없다.
- **측정 지표**: 프론트 제출 → DB job → LLM 해석 → 검색 → 통합 답변·Pin 반환까지 실제 요청 한 건의 종결 상태와 결과를 기록한다.

## Goal

- 기존 구현을 최신 이미지로 실행하고 실제 API 경로에서 통합 답변과 검색 결과를 확인한다.
- 재현에 필요한 로컬 설정과 검증 범위를 공유한다.
- **범위 밖**: 검색 의미 품질 개선, 모델 기본값 변경, 애플리케이션 코드 변경, DB migration, 전체 평가셋 통과율 측정, 운영 배포.

## What

1. 로컬 `.env`에 Compose 필수값과 `SEARXNG_SECRET`을 준비한다.
2. 최신 코드로 API 이미지를 빌드하고 API와 SearXNG를 실행한다.
3. API 응답 스키마와 SearXNG JSON 검색을 확인한다.
4. 프론트에서 실제 요청을 제출하고 같은 세션 쿠키로 종결까지 polling한다.
5. 반환된 통합 답변, 용어, Pin 링크, 썸네일 응답을 확인한다.

| 상황 | 확인·처리 |
| --- | --- |
| 실행 중인 API 이미지가 오래됨 | `restart`만 하지 않고 최신 코드로 `--build` 후 컨테이너를 다시 만든다. |
| `SEARXNG_SECRET` 누락 | 로컬 `.env`에 임의의 긴 비밀값을 넣고 Compose 설정 검증을 다시 실행한다. 비밀값을 공유 문서나 커밋에 넣지 않는다. |
| 모델 일반 호출은 되지만 엄격한 JSON Schema 요청은 404 | 동일한 `response_format`과 provider 조건을 처리할 endpoint가 있는 모델로 로컬 설정을 맞춘다. 일반 호출 성공만으로 호환성을 판단하지 않는다. |
| 기존 이력에 `answer_text`가 없음 | 과거 답변이 자동 생성되지는 않는다. 최신 API에서 새 요청으로 확인한다. |
| 이미지 검색이 비거나 실패함 | `partial_result`와 검색 사유 코드를 확인한다. 통합 답변 누락과 이미지 검색 문제를 각각 확인한다. |

## How

### 로컬 설정·기동

Neon 개발 DB, OpenRouter key, Langfuse 내부 비밀값은 기존 `.env.example`의 계약을 따른다. 이미 준비된 개발 DB를 사용하며 이번 확인에서는 migration을 실행하지 않았다.

이번 실측에서는 로컬 `.env`의 다음 설정을 사용했다. 저장소의 모델 기본값은 변경하지 않는다.

```dotenv
LLM_MODEL=openai/gpt-4.1-mini
INTERPRETER_PROMPT_PATH=./prompts/uhkegryo-interpreter-v1.md
INTERPRETER_PROMPT_VERSION=uhkegryo-interpreter-v1
```

`SEARXNG_SECRET`은 별도로 생성해 로컬 `.env`에만 설정한다. Compose가 API의 `SEARXNG_BASE_URL`을 `http://searxng:8080`으로 설정한다.

```powershell
# 저장소 루트: 기존 Langfuse 저장 서비스가 실행 중인 환경
docker compose config --quiet
docker compose up -d --build --no-deps api searxng
```

`.env`의 모델 설정만 바꾼 뒤에는 다음 명령으로 API 컨테이너를 다시 만든다.

```powershell
docker compose up -d --no-deps api
```

별도 터미널에서 프론트를 실행한다.

```powershell
cd frontend
npm run dev -- --hostname 127.0.0.1 --port 3001
```

### 요청·확인 경로

- API health: `GET http://127.0.0.1:8000/health` → 200.
- 실행 중인 API의 `GET /openapi.json`에서 `AgentResult.properties.answer_text`가 있는지 확인한다.
- SearXNG: `GET http://127.0.0.1:8080/search`에 `q=!goi contrapposto drawing site:pinterest.com/pin`, `categories=images`, `format=json`, `language=en`을 URL 인코딩해 전달한다. `results`와 `unresponsive_engines`를 확인한다.
- 프론트 origin `http://127.0.0.1:3001`에서 `POST /api/agent`에 아래 입력과 UUID `Idempotency-Key`를 보낸다. 응답 쿠키를 유지해 `GET /api/jobs/{job_id}`를 polling한다. 브라우저 입력창을 사용하면 프론트가 이 처리를 수행한다.
- 종결 후 `result.answer_text`, `reference_plan.terms`, 역할별 `pins`, `reason_codes`를 확인한다. 이미지 URL은 HEAD 응답의 200과 이미지 Content-Type으로 확인하며 이미지 파일은 내려받지 않는다.

검증 입력:

> 마른 체형의 캐릭터가 한쪽 다리에 체중을 싣고 서 있는 자세 레퍼런스를 찾아줘.

### 2026-10-02 실측

- 코드 기준: `1e7a921` (main, PR #102 병합 상태).
- 기존 API 이미지에는 `answer_text`가 없음을 OpenAPI와 컨테이너 스키마에서 확인했다. 최신 이미지에서는 해당 필드가 있다.
- 당시 `openai/gpt-6-luna` 일반 호출은 200이었지만, 앱의 엄격한 JSON Schema 요청은 OpenRouter 404 (`No endpoints found that can handle the requested parameters`)로 실패했다. 이 관측을 모든 provider·미래 시점의 모델 지원 여부로 일반화하지 않는다.
- 로컬 모델을 `openai/gpt-4.1-mini`로 변경한 후 실제 프론트 프록시를 거친 요청 한 건이 `completed / success`, `reason_codes=[]`, `failure=null`로 종결됐다.
- `answer_text` 336자, `body_slim`과 `pose_contrapposto` 각각 Pin 8개, 서로 다른 Pin 링크 총 16개를 받았다.
- 썸네일 16개 모두 HEAD 응답 200 및 이미지 Content-Type을 확인했다.
- 프론트 `answerForJob()`의 반환값이 API의 `answer_text`와 일치하고, 호환 안내 문구가 반환되지 않았다. 갤러리 helper가 용어 2개와 표시 가능한 썸네일 16개를 반환했다.
- SearXNG 직접 검색은 결과 20개와 `unresponsive_engines=[]`를 반환했다. 검색 결과 수는 외부 서비스 상태에 따라 달라질 수 있다.
- 이는 요청·검색 연결 검증이다. 브라우저 DOM의 실제 렌더링 검증, 30문항 평가, 이미지의 의미 적합성·검색 품질 채점은 수행하지 않았다.
- 저장소에는 비밀값, DB 연결 문자열, 세션 쿠키, 전체 응답 원문, 썸네일 URL을 추가하지 않는다.

## AC

- **Given** 필수 로컬 설정, **When** `docker compose config --quiet` 실행, **Then** 비밀값을 출력하지 않고 설정 검증이 통과한다.
- **Given** 최신 API 이미지, **When** 실행 중인 OpenAPI 조회, **Then** `AgentResult`에 `answer_text` 필드가 있다.
- **Given** SearXNG와 프론트·API 실행, **When** 검증 입력을 실제 API로 제출, **Then** 같은 쿠키로 job 종결을 조회하고 상태·답변·검색 결과를 확인할 수 있다.
- **Given** 이번 성공 응답, **When** 프론트 답변·갤러리 helper 및 썸네일 HEAD 검사, **Then** 통합 답변이 보존되고 용어 2개·썸네일 16개와 200 이미지 응답을 확인한다.
- **Given** 문서의 실측 결과, **When** 검증 범위를 읽음, **Then** 한 건의 연결 성공을 검색 품질이나 전체 평가 통과율로 해석하지 않는다.
