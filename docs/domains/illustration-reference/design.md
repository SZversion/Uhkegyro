# Illustration Reference Agent Design

현재 구현 기준은 `docs/PRD.md`, `docs/SDD.md`, `docs/specs/api-contract.md`, `docs/specs/term-card-catalog.md`다. TERM_CARD는 역할별 JSON 카탈로그를 시작 시 검증해 메모리에 로드하며 DB에 적재하지 않는다.

LLM은 활성 term ID 후보와 근거만 만든다. 서버는 카탈로그와 조건을 검증하고 `query_fragments`만 검색 provider에 전달한다. 사용자 의미 상태와 Pin 상태는 API 계약의 enum만 사용한다. Pinterest 크롤링은 범위 밖이다.
