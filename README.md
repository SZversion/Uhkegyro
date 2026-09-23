# UH케그려 — 캐주얼 캐릭터 일러스트 레퍼런스 해석 Agent

> 전문 용어가 낯선 초보자가 텍스트로 묘사한 캐주얼 캐릭터의 **체형/소체, 포즈, 구도**를 기초 드로잉 용어와 역할별 Pinterest 탐색 계획으로 바꾸는 Agent입니다.

> **현재 상태: 기반 골조 구현 중**
> 현재 API는 `GET /health`만 동작합니다. LLM 기반 해석, Agent 메시지 API, MCP 도구, Langfuse, UI 및 배포는 아직 구현·측정하지 않았습니다. 아래의 목표 구조와 계획 항목은 완료 기능으로 해석하면 안 됩니다.

## 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 핵심 사용자 | 캐주얼 캐릭터 일러스트를 시작했고 드로잉 전문 용어가 낯선 사용자 |
| 반복 문제 | 원하는 체형·포즈·구도를 일상어로만 검색해 넓은 결과를 반복 탐색한다. |
| 해결 방식 | 일상어를 구조화한 뒤, 용어 설명과 역할별 외부 탐색 링크를 함께 제공한다. |
| 팀 | UH케그려 (4조) |
| 현재 실행 가능 범위 | Docker Compose 기반 FastAPI `GET /health` 골조 |

## 팀원

| 이름 | 역할 |
| --- | --- |
| 오세창 | 도메인 경험·용어 검토 |
| 김호섭 | MCP, 아키텍처 |
| 윤태현 | 백엔드, 에이전트 출력 |

## 문제와 도메인 경험

프리랜서 캐주얼 캐릭터 일러스트레이터로 약 3년 활동한 오세창의 작업 경험에서 출발했습니다. 의뢰 이미지나 텍스트 설명만으로 캐릭터를 그릴 때, 하나의 이미지에서 모든 조건을 찾기보다 **체형/소체 → 지지점과 포즈 → 시점·원근·배치 → 세부 표현** 순서로 조건을 나눠 여러 레퍼런스를 병렬로 확인했습니다.

초보자는 “한쪽 다리에 힘을 준 자연스러운 자세”, “상체가 넓고 다리가 긴 캐릭터”, “아래에서 올려다보는 구도”처럼 묘사하지만, 이를 `contrapposto`, `inverted triangle body type`, `low angle` 또는 `foreshortening` 같은 탐색 가능한 용어로 바꾸기 어렵습니다. 이 Agent는 그 번역과 탐색 계획 수립을 돕습니다.

## 목표 사용자 흐름

1. 사용자가 만들고 싶은 캐릭터를 일상어로 입력합니다.
2. Agent가 체형/소체, 포즈, 시점, 원근, 배치를 구분해 해석합니다.
3. 각 조건을 쉬운 말과 드로잉 용어로 설명하고, 확신하지 못한 조건은 질문 또는 한계로 표시합니다.
4. 서버 Playwright가 선택한 역할별 `query_fragments`로 공개 Pinterest 검색을 수행해 상위 8개의 원본 Pin 링크를 찾고, 각 Pin ID를 widget endpoint로 조회해 원격 썸네일 URL을 현재 응답에만 넣습니다.
5. UI는 서버가 반환한 원격 썸네일을 원본 Pin 링크로 표시합니다. 서비스는 이미지 파일·썸네일 URL·Pin 메타데이터를 저장하지 않습니다.
6. 사용자는 하나의 ‘정답 이미지’가 아니라 역할별 레퍼런스를 조합해 러프를 시작합니다.

### 입력과 목표 출력 예시

| 입력 | 목표 해석 예시 |
| --- | --- |
| “한쪽 다리에 힘 주고 상체는 살짝 틀어진 마른 캐릭터” | `body: slim`, `pose: contrapposto`, `pose: torso twist` |
| “낮은 곳에서 올려다보는 앉은 캐릭터” | `pose: seated`, `view: low angle`, `perspective: foreshortening` |

용어 해석은 사용자의 의도를 확인하는 제안이며, 신체 비율이나 포즈를 단정하는 판정이 아닙니다.

## MVP 범위

### 제공할 것

- 1~500자 텍스트 설명의 구조화 해석
- 체형/소체, 포즈, 구도(`view`, `perspective`, `layout`)의 역할 분리
- 전문 용어의 초보자용 설명과 불확실성 표시
- 선택된 역할별 Pinterest 원격 썸네일 미리보기와 원본 Pin 링크(역할별 최대 8개)
- 세션 이력에 포함된 Pin URL·상태 유지와 썸네일 URL·이미지의 비저장
- 팀 검수 TERM_CARD JSON 카탈로그의 용어·설명·검색 조각

### 제공하지 않을 것

- 이미지 생성, 편집, 업로드 이미지 분석, 특정 작가 화풍 복제
- Pinterest 이미지 파일·썸네일·메타데이터의 저장, 재게시 또는 브라우저 직접 크롤링
- 단일 이미지가 모든 조건에 맞는다고 보장하는 추천
- 문서를 청크로 검색해 답변에 주입하는 RAG

제외 범위와 이유는 [NOT_BUILD.md](./NOT_BUILD.md)에서 확인할 수 있습니다.

## 목표 아키텍처

```text
사용자 UI
  -> POST /api/agent (미구현, 서버 세션 쿠키 발급·재사용, 202 + job_id)
  -> GET /api/jobs/{job_id} polling (미구현, completed/failed까지)
Job executor / recovery (미구현)
  -> LLM: 일상어를 허용된 term_id와 역할로 구조화
  -> 결정론 코드: Pydantic 검증, 역할 순서, 허용 ID, URL 인코딩
  -> FastMCP: TERM_CARD JSON 카탈로그의 활성 카드 정보를 구조화 조회
  -> PinterestCrawlerProvider: 서버 Playwright 공개 검색 크롤링 -> Pin ID widget 조회 -> 역할별 최대 8개 {pin_url, thumbnail_url, status} 반환
  -> UI: 원격 썸네일을 원본 Pin 링크로 표시
```

| 계층 | 담당 책임 |
| --- | --- |
| LLM | 일상어의 의미 해석, 조건 충돌·모호성 인식, 허용된 구조화 선택 생성 |
| 결정론 코드 | Pydantic 스키마 검증, 허용 `term_id`, 역할 순서, URL 인코딩, 실패 응답 |
| FastMCP | 시작 시 검증해 메모리에 로드한 TERM_CARD JSON 카탈로그의 활성 카드만 조회하고, Getty 데이터·외부 어휘 API·SPARQL·웹 호출은 하지 않음 |
| UI | 입력 안내, 로딩·실패 안내, 용어·한계·외부 링크 표시 |

LLM은 링크를 임의로 만들거나 데이터 출처를 지어내지 않습니다. 링크 생성과 출력 검증은 코드가 맡습니다.

## 도메인 데이터와 출처 경계

| 구분 | 계획된 역할 | 출력에 보이는 정보 |
| --- | --- | --- |
| TERM_CARD JSON 카탈로그 | `index.json`과 다섯 역할 JSON으로 이루어진 팀 검수 런타임 단일 원본 | term ID, 설명, query fragment, 검수 상태 |
| Pinterest | 사용자가 원본을 직접 확인할 외부 탐색 대상 | 원본 Pin 링크와 응답 전용 원격 썸네일 미리보기 |

PinterestCrawlerProvider는 서버 Playwright에서 활성 TERM_CARD의 `query_fragments`만 사용해 공개 검색을 크롤링하고, 수집한 모든 Pin ID를 widget endpoint로 조회해 현재 응답용 `thumbnail_url`을 조립합니다. Pinterest API v5는 사용하지 않습니다. Pinterest 이미지 바이트와 `thumbnail_url`은 저장·재게시하지 않습니다. Pin URL과 상태는 별도 수집·저장하지 않고 세션·job 이력에 포함된 결과로만 유지합니다. UI는 현재 응답의 원격 썸네일을 원본 Pin 링크로 표시하며, 썸네일 URL이 없으면 링크만 제공합니다. 썸네일 부재와 검색 오류는 provider가 반환한 상태로 구분합니다. 용어 선택·설명·검색 조각은 구현 후 팀이 작성·검수한 TERM_CARD JSON 카탈로그만 사용합니다. 카탈로그는 시작 시 검증해 메모리에 로드하며 요청 중 파일을 다시 읽거나 DB에 적재하지 않습니다. Getty는 용어 조사 시 참고한 자료일 뿐, 서비스 데이터·사용자 화면·LLM 입력·런타임 조회에 포함하지 않습니다. 자체 카드와 권리 검토 기준은 팀 승인을 거쳐야 하며, 승인되지 않은 데이터를 완료된 카탈로그로 주장하지 않습니다.

## API와 MCP 상태

| 항목 | 현재 상태 | 최종 목표 |
| --- | --- | --- |
| `GET /health` | 구현됨. `{"status":"ok"}` 반환 | Cloud Run 상태 확인 |
| `POST /api/agent` | 명세 확정·미구현 | 가이드 제출용 Agent API. 서버 세션 쿠키를 발급·재사용하고 `202`와 비동기 `job_id` 반환 |
| `GET /api/jobs/{job_id}` | 명세 확정·미구현 | 소유 job의 실제 상태·완료 결과·실패·재시도 가능 여부 반환 |
| `/docs` | FastAPI 기본 문서에서 확인 가능 | 요청·응답 모델 및 오류 응답 확인 |
| `/mcp` | 미구현. `example_tool` 골조만 존재 | `get_active_term_card(term_id)` FastMCP Streamable HTTP endpoint와 도구 호출 증거 |
| TERM_CARD JSON 카탈로그 | 문서화·미구현 | 시작 검증 뒤 역할별 활성 카드를 메모리에서 조회 |
| MCP 접근 제어 | 미구현 | 토큰 또는 허용 클라이언트 정책을 문서화하고 적용 |

`/mcp`를 공개 데모 API처럼 무제한 노출하지 않습니다. 구현 시 연결 방법, 도구 목록, 실제 호출 결과, 접근 제어 방식을 이 README에 추가합니다.

## 로컬 실행

### 사전 준비

- Docker Desktop 또는 Docker Engine과 Docker Compose
- Git
- `.env`에 둘 API 키가 필요한 기능은 아직 구현되지 않았습니다. 현재 골조는 키 없이도 `GET /health` 확인이 가능해야 합니다.

### PowerShell

```powershell
git clone <팀-저장소-URL>
cd proj2-4
Copy-Item .env.example .env
docker compose up --build
```

실행 뒤 다음 주소를 확인합니다.

| 주소 | 현재 기대 결과 |
| --- | --- |
| `http://localhost:8000/health` | `{"status":"ok"}` |
| `http://localhost:8000/docs` | FastAPI 자동 문서 |

종료는 다음 명령으로 합니다.

```powershell
docker compose down
```

> 아직 전체 MVP를 10분 안에 재현하는 실측은 수행하지 않았습니다. LLM·MCP·Langfuse·UI 구현 후, 새 환경에서 위 절차를 검증하고 결과를 갱신합니다.

## 환경 변수와 보안

필요한 변수명은 [.env.example](./.env.example)에만 공개합니다. 실제 값은 로컬 `.env` 또는 배포 환경의 Secret Manager에만 저장합니다.

- `.env`, API 키, 토큰, 서비스 계정 파일, 사용자 원문 이미지·개인정보를 커밋하지 않습니다.
- 키가 노출되면 Git 이력 삭제만으로 충분하지 않으므로 즉시 폐기·재발급합니다.
- 브라우저 UI는 LLM SDK 또는 비밀값을 직접 호출하지 않습니다.

## 평가와 운영 지표

최종 평가는 정상·경계·실패 유도 케이스를 포함한 최소 30건의 평가셋으로 수행합니다. 동일한 평가셋으로 한 가지 변경 후 다시 실행해 회귀를 확인합니다.

| 지표 | 현재 값 | 최종 기록 위치 |
| --- | --- | --- |
| 평가셋 품질 점수 | 미측정 | [EVAL_REPORT.md](./EVAL_REPORT.md) |
| 계약 준수율 | 미측정 | `EVAL_REPORT.md` |
| p50 / p95 지연 | 미측정 | `EVAL_REPORT.md` |
| 요청당 평균 비용 | 미측정 | `EVAL_REPORT.md` |
| LLM·MCP 오류율 | 미측정 | `EVAL_REPORT.md` |

평가 문항과 판정 기준은 [evals/README.md](./evals/README.md), 실제 개선 전후 결과·실패 사례·Keep/Discard 판단은 [EVAL_REPORT.md](./EVAL_REPORT.md)에 남깁니다.

## 프로젝트 문서

| 문서 | 내용 |
| --- | --- |
| [PRD](./docs/PRD.md) | 제품 요구사항, 사용자 흐름, 범위와 수용 기준 |
| [SDD](./docs/SDD.md) | 시스템 아키텍처, 데이터 흐름, 검증·비동기 처리 설계 |
| [도메인 프로필](./docs/domains/illustration-reference/domain-profile.md) | 사용자, 업무 경험, 경쟁 서비스, 범위와 데이터 출처 |
| [경쟁 서비스 분석](./docs/domains/illustration-reference/competitive-analysis.md) | 실제 시작 흐름 비교, 차별점과 조사 한계 |
| [설계 문서](./docs/domains/illustration-reference/design.md) | LLM·결정론 코드·MCP의 책임 분리와 폴백 설계 |
| [API 계약](./docs/specs/api-contract.md) | `POST /api/agent`, 비동기 job 상태, 완료 결과, worker 실패·재시도 및 LLM JSON 계약 |
| [MCP 계약](./docs/specs/mcp-contract.md) | JSON 카탈로그 기반 `get_active_term_card` 도구의 입력·출력·접근 제어 |
| [NOT_BUILD.md](./NOT_BUILD.md) | MVP에서 의도적으로 만들지 않는 기능과 이유 |
| [EVAL_REPORT.md](./EVAL_REPORT.md) | 관측, 프롬프트 운영, 평가, 비용·지연, 출시 게이트 |
| [evals/](./evals/) | 평가셋과 판정 기준 |
| [작업 티켓](./docs/work-tickets.md) | 역할 분담·의존·일정을 포함한 전체 작업 목록 |
| [docs/SCAFFOLD.md](./docs/SCAFFOLD.md) | 저장소 폴더별 작성 안내 |

## 팀과 협업

1. `main`에는 직접 push하지 않고, 개인 브랜치에서 PR을 만듭니다.
2. PR은 팀원 1명 이상의 approve 뒤에 사람이 merge합니다.
3. 기능 구현 전 `docs/specs/{feature-name}.md`에 Why, Goal, What, How, AC를 작성합니다.
4. API 키·비밀번호·`.env`는 절대 커밋하지 않습니다.
5. 강사 확인이 필요한 질문은 Issue에 남기고 강사를 멘션합니다.

```powershell
git switch main
git pull
git switch -c feat/<작업내용>
# 작업 및 검증 후
git add <변경한-파일>
git commit -m "feat: <변경 내용>"
git push -u origin feat/<작업내용>
```

## 배포와 데모

| 제출 증거 | 상태 |
| --- | --- |
| 사용자 UI URL | 미배포 |
| Cloud Run Agent API URL | 미배포 |
| MCP 연결·도구 호출 화면 | 미구현 |
| Langfuse 대시보드 스크린샷 | 미측정 |
| 정상·실패 경로 데모 영상 | 미제작 |

배포와 평가가 끝나면 실제 URL·실행 날짜·모델·프롬프트 버전·데이터셋 버전만 기록합니다. 추정 수치나 아직 존재하지 않는 URL은 적지 않습니다.
