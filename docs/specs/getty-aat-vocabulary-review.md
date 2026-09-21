> 이 문서는 초기 Getty 검토 Spec입니다. 최신 제품·아키텍처 기준은 `docs/PRD.md`와 `docs/SDD.md`를 우선합니다.
>
> **2026-09-21 폐기됨:** 이 외부 어휘 조회 실험은 구현하거나 재개하지 않는다. 현재 용어 데이터·검수 기준은 `docs/specs/self-managed-term-card-store.md`를 따른다.

# Getty AAT 용어 보완 및 저신뢰도 검토 Spec

## Why

- **페르소나**: 캐주얼 캐릭터 일러스트를 배우며 일상어를 기초 드로잉 용어로 바꾸고 싶은 사용자와, 용어 카드의 범위를 검토하는 도메인 담당자
- **상황**: 현재 정적 term 카드에 없는 표현 또는 근거가 부족한 표현이 들어왔을 때, Agent가 새 전문 용어를 지어내지 않아야 한다.
- **문제**: 정적 카드만으로는 새 후보를 체계적으로 검토하기 어렵고, 실패·저신뢰도 결과를 사람 검토와 평가로 연결하는 경로가 없다.
- **측정 지표**: Getty AAT 후보 조회 결과는 URI·label·출처만 반환하고, 저신뢰도 해석은 자동 카드 추가 없이 `pending_human_review` 초안으로 100% 분기한다.

## Goal

- **해결 목표**: Getty AAT SPARQL endpoint를 통해 용어 후보를 조회하는 FastMCP 도구와, 저신뢰도 해석을 사람 검토용 term 카드 초안으로 바꾸는 순수 함수를 만든다.
- **성공 기준**: 현재 Getty 기본 결과는 `subject_uri`, `label`, Getty AAT 출처 URL만 가지며 이미지·웹 본문·핀 데이터는 포함하지 않는다. 미래 자체 DB도 같은 구조에 자신의 출처 메타데이터를 넣어 반환한다. Getty 장애는 `unavailable` 결과로 구분하고, 새 term 카드는 사람 검토와 평가셋 회귀 확인 전까지 정적 카드에 반영하지 않는다.
- **Out of Scope**: Metropolitan Museum API, Getty Museum Collection API, 이미지 다운로드·표시·분석, Getty 결과를 LLM 프롬프트에 자동 주입하는 RAG, term 카드 자동 생성·저장·배포, Langfuse 실제 호출, OpenAI 호출, Pinterest HTTP 요청

## What

**Happy Path**

1. 백엔드 또는 사람이 정규화한 영문 용어 후보를 `search_getty_aat_terms` MCP 도구에 전달한다.
2. 도구는 Getty AAT SPARQL endpoint에서 최대 5개의 URI·선호 label을 조회한다.
3. AAT 결과는 `resolve_illustration_reference_plan`의 출처 메타데이터로 반환하거나, 도메인 담당자가 용어 후보를 검토할 때 사용한다. 어떤 경우에도 LLM 프롬프트·RAG에 자동 주입하지 않는다.
4. LLM이 향후 `confidence=low`와 limitation을 반환하면, 후보와 limitation을 `pending_human_review` 초안으로 만든다.
5. 도메인 담당자가 승인하고 평가셋 회귀를 확인한 경우에만 사람이 정적 `TERM_CARDS`와 Skill을 수정한다.

**Edge Cases**

| # | 상황 | 처리 방식 |
|---|---|---|
| EC-01 | 빈 검색어 또는 80자 초과 검색어 | HTTP 요청 없이 입력 오류로 거부한다. |
| EC-02 | Getty timeout·5xx·비정상 JSON | `status=unavailable`, 빈 후보, limitation code를 반환한다. |
| EC-03 | AAT 후보가 없음 | `status=ok`, 빈 후보를 반환하며 새 term ID를 만들지 않는다. |
| EC-04 | confidence가 `medium` 또는 `high` | 검토 초안을 만들지 않는다. |
| EC-05 | confidence가 `low`이나 limitation이 없음 | 검토 초안을 만들지 않는다. |

## How

- 기본 endpoint는 `https://vocab.getty.edu/sparql`이며, `httpx` POST와 SPARQL JSON 응답만 사용한다. 검색어는 SPARQL 문자열 literal로 escape하며, 호출 timeout은 5초다.
- MCP 도구는 독립 후보 조회용 `search_getty_aat_terms(query, limit)`과 LLM 선택 처리용 `resolve_illustration_reference_plan(selections)`을 제공한다. 후보 결과에는 `subject_uri`, `label`, `source_name`, `source_url`만 둔다. 서버는 `VocabularyCandidateProvider` 계약에 의존하므로, 자체 DB가 같은 결과 계약을 구현하면 Getty 기본 공급자를 교체할 수 있다.
- Getty AAT는 용어 근거이며 레퍼런스 이미지 카탈로그가 아니다. 역할별·통합 Pinterest URL 생성 규칙과 향후 권리 검토된 자체 카탈로그는 대체하지 않는다.
- `TermCardReviewDraft`는 `confidence=low`와 하나 이상의 limitation이 있을 때만 `pending_human_review` 상태로 만든다. 원문 사용자 요청과 식별자는 초안에 저장하지 않는다.
- Langfuse를 도입하는 다음 단계에는 원문 대신 request ID 해시, `confidence`, limitation code, Getty 후보 수·URI만 trace metadata로 기록한다. 실제 Langfuse 호출은 이 Spec 범위에 포함하지 않는다.
- AAT 데이터 표시는 Getty AAT와 J. Paul Getty Trust의 출처를 함께 표기한다. endpoint·라이선스·데이터 구조는 배포 전에 Getty 공식 문서로 재확인한다.

## AC (Given-When-Then)

**AC-01 · AAT 후보 조회**
- GIVEN: `contrapposto` 검색어와 Getty SPARQL JSON 응답
- WHEN: Getty AAT 클라이언트가 결과를 파싱
- THEN: URI·label·Getty 출처만 가진 후보를 반환하고 이미지 필드는 반환하지 않는다.

**AC-02 · Getty 장애 분리**
- GIVEN: Getty endpoint timeout 또는 5xx
- WHEN: MCP 도구가 후보를 조회
- THEN: 예외를 새 term ID로 바꾸지 않고 `unavailable` 상태와 limitation code를 반환한다.

**AC-03 · 저신뢰도 검토 초안**
- GIVEN: `confidence=low`, limitation 한 개 이상, Getty 후보 목록
- WHEN: 검토 초안을 생성
- THEN: `pending_human_review` 상태로 반환하며 정적 term 카드에는 쓰지 않는다.

**AC-04 · 중·고신뢰도 차단**
- GIVEN: `confidence=medium` 또는 `high`
- WHEN: 검토 초안을 생성
- THEN: 초안을 만들지 않는다.

**AC-05 · Metropolitan 미사용**
- GIVEN: 어떤 Getty 후보 조회 또는 검토 초안 생성
- WHEN: 코드가 동작
- THEN: Metropolitan endpoint·이미지·레코드를 호출하거나 반환하지 않는다.
