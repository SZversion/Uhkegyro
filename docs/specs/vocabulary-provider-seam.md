# Vocabulary Candidate Provider 교체 지점 Spec

## Why

- 현재 Getty AAT는 실험 단계의 용어 후보 출처다. 팀의 자체 DB가 준비되면 Getty를 계속 호출하거나 MCP·검토 흐름의 결과 형식을 다시 설계하지 않고 교체할 수 있어야 한다.
- 다만 현재는 자체 DB의 스키마·권리 검토·운영 책임자가 확정되지 않았으므로 DB 테이블, 마이그레이션, 배포 설정을 앞서 만들지 않는다.

## Goal

- `VocabularyCandidateProvider` 계약을 두고, 현재 Getty AAT 클라이언트를 그 구현체로 연결한다.
- 자체 DB 구현체도 같은 `search_terms(query, limit)` 계약과 구조화 후보 결과를 반환하면 서버 구성 시 교체할 수 있게 한다.

## What

1. 서버는 구체적인 `GettyAatClient`가 아니라 `VocabularyCandidateProvider`에 의존한다.
2. 후보의 `source_name`과 `source_url`은 Getty로 고정하지 않고 실제 공급자가 제공한 값을 반환한다.
3. 현재 기본 공급자는 Getty AAT이며, `search_getty_aat_terms` MCP 도구의 현재 동작과 출력은 유지한다.
4. 미래 자체 DB 공급자는 이 계약을 구현해 서버 구성 시 주입한다. 이 단계에서 Getty와 자체 DB를 동시에 병합 조회하지 않는다.

## How

- **책임 분리**: `VocabularyCandidateProvider`는 `search_terms(query, limit)`만 정의하는 공급자 계약이다. 서버와 Getty-정적 카드 파이프라인은 이 계약에만 의존하고, `GettyAatClient`가 현재 기본 구현을 맡는다. 미래 자체 DB는 같은 계약을 구현하는 어댑터로만 교체한다.
- **입력 계약**: 공급자는 정규화된 영문 용어 `query`와 1~5 범위의 `limit`을 받는다. 현재 Getty 구현은 공백·길이·제어 문자를 검증한 후 SPARQL literal로 escape한다. 자체 DB 구현도 사용자 원문이 아니라 이 정규화된 용어만 받아야 한다.
- **출력 계약**: 모든 공급자는 `status`, `terms`, `limitations`을 가진 `VocabularyLookup`을 반환한다. 각 후보는 `subject_uri`, `label`, `source_name`, `source_url`만 가진 `VocabularyTerm`이다. 자체 DB 공급자는 자신의 출처명을 채우며, 서버는 이를 Getty로 다시 표기하지 않는다.
- **외부 연동과 제약**: Getty 구현만 공개 SPARQL endpoint에 `httpx` POST를 사용하고 timeout·HTTP 오류·비정상 JSON을 `unavailable` 결과로 바꾼다. 자체 DB의 저장소·ORM·접속 설정은 아직 만들지 않으며, 실행 중 두 공급자의 결과를 병합하거나 이미지·웹 본문을 조회하지 않는다.

## Out of Scope

- 자체 DB 테이블·ORM·마이그레이션·관리 화면
- 환경변수로 공급자를 선택하는 런타임 설정
- Getty 결과와 자체 DB 결과의 자동 병합·동기화
- term 카드 자동 변경, 이미지 수집, RAG, Metropolitan Museum API

## AC (Given-When-Then)

**AC-01 · 자체 공급자 교체 가능성**
- GIVEN: 자체 DB 구현체가 URI, label, `source_name`, `source_url`을 가진 후보를 반환한다.
- WHEN: 서버의 후보 공급자를 해당 구현체로 교체한다.
- THEN: 서버는 Getty라는 고정 출처로 바꾸지 않고 자체 공급자의 출처 메타데이터를 그대로 반환한다.

**AC-02 · 현재 Getty 기본값 유지**
- GIVEN: 별도 공급자를 주입하지 않는다.
- WHEN: Getty AAT 후보 조회를 실행한다.
- THEN: 기존과 같이 Getty AAT URI·label·출처 URL만 반환한다.
