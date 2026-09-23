# Booru 태그 참고용 TERM_CARD 실험 후보 Implementation Plan

> **상태: 완료된 후보 검토 단계의 실행 기록.** 이 계획의 8개 후보는 이후 `docs/specs/term-card-candidate-data-promotion.md`에 따라 로컬 활성 카탈로그로 승격됐다. 아래의 `reviewed_not_promoted` 검증, 역할 JSON·`index.json` 무변경 제약, 후보 ID 비중복 명령은 **승격 전 이력**이므로 현재 브랜치에서 다시 실행하거나 최종 PR 상태 판단에 사용하지 않는다. 현재 정합성은 데이터 승격 Spec의 AC를 따른다.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 런타임 카탈로그와 격리된 JSON 파일에 검수 완료 TERM_CARD 후보 8건을 기록하고, 중복·격리·외부 데이터 경계를 정적으로 검증한다.

**Architecture:** `docs/domains/illustration-reference/term-cards/candidates/`는 `index.json`이 선언하지 않는 검수 전용 경로다. 후보는 현재 활성 카드와 동일한 용어 설명 구조를 참고하되, `candidate_query_fragments`와 명시적 비활성 상태를 사용해 현재 MCP·loader·Pinterest 검색 입력이 되지 않도록 한다.

**Tech Stack:** versioned JSON, PowerShell `ConvertFrom-Json`, Git diff checks

## Global Constraints

- 기존 5개 역할 JSON과 `index.json`은 수정하지 않는다.
- 후보 ID 8개는 활성 74개 카드 및 `evals/**/*.jsonl`의 참조 ID와 중복되지 않아야 한다.
- 모든 후보는 `runtime_eligible: false`, `mvp_status: "candidate_outside_current_contract"`, `review_status: "reviewed"`여야 한다.
- `candidate_query_fragments`에는 검수자가 라벨 적합성을 확인한 표준 용어 조각만 저장한다. 중복된 `pose reference`와 `drawing`은 넣지 않지만, `full body reference`처럼 최종 Pinterest 검색어 적합성을 위해 검수자가 선택한 `reference` 조각은 허용한다. 향후 검색 URL 생성 코드가 `drawing`을 붙인다.
- Booru-Pictag 계열은 개발 단계의 일반 용어 조사 참고 수단일 뿐 런타임 의존성이 아니다.
- 외부 조회가 현재 작성 환경에서 실패했으므로, `crosscheck.status`는 `not_verified`이며 외부 응답·게시물·이미지·프롬프트·작가·캐릭터·저작권 태그를 저장하지 않는다.
- Git commit, push, Pull Request 생성은 사용자의 별도 명시 승인 전까지 수행하지 않는다.

---

### Task 1: 격리된 후보 배치 작성

**Files:**
- Create: `docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json`
- Reference: `docs/domains/illustration-reference/term-cards/index.json`
- Reference: `docs/domains/illustration-reference/term-cards/{pose,view,layout}.json`

**Interfaces:**
- Consumes: 5개 역할 JSON의 기존 `term_id` 집합과 `evals/**/*.jsonl`의 `term_id` 참조 집합
- Produces: 최상위 `document_type`, `status`, `runtime_contract`, `research_boundary`, `candidates`를 가진 검수 전용 JSON 배치
- Candidate contract: 각 항목은 `term_id`, `role`, `component`, `label_ko`, `label_en`, `candidate_query_fragments`, `source_answer_draft`, `look_for`, `confidence_gate`, `requires_all_of`, `requires_any_of`, `review_status`, `runtime_eligible`, `mvp_status`, `crosscheck`를 가진다. 최상위 `active_term_feedback_draft`는 후보 ID별 초보자 UX 필드를 가진다.

- [ ] **Step 1: 후보 ID 사전 조건 검사**

Run:

```powershell
$cardIds = Get-ChildItem docs/domains/illustration-reference/term-cards -Filter '*.json' -File |
  Where-Object Name -ne 'index.json' |
  ForEach-Object { (Get-Content $_ -Raw | ConvertFrom-Json).cards.term_id }
$planned = @(
  'pose_hands_on_hips', 'pose_arms_crossed', 'pose_hands_behind_back',
  'pose_hand_on_chin', 'pose_hand_on_chest', 'pose_salute',
  'view_over_the_shoulder', 'view_full_body'
)
Compare-Object $planned $cardIds -IncludeEqual -ExcludeDifferent
```

Expected: 출력 없음. 출력이 있으면 해당 ID를 후보로 쓰지 않는다.

- [ ] **Step 2: 후보 JSON 작성**

Create exactly these candidate IDs and roles:

```json
[
  {"term_id":"pose_hands_on_hips","role":"pose"},
  {"term_id":"pose_arms_crossed","role":"pose"},
  {"term_id":"pose_hands_behind_back","role":"pose"},
  {"term_id":"pose_hand_on_chin","role":"pose"},
  {"term_id":"pose_hand_on_chest","role":"pose"},
  {"term_id":"pose_salute","role":"pose"},
  {"term_id":"view_over_the_shoulder","role":"view"},
  {"term_id":"view_full_body","role":"view"}
]
```

For every item, use `runtime_eligible: false`, `mvp_status: "candidate_outside_current_contract"`, `review_status: "reviewed"`, and `crosscheck.status: "not_verified"`. Set the top-level status to `reviewed_not_promoted` with a review summary of eight retained and two excluded candidates. Store only the reviewed standard term in `candidate_query_fragments`; do not add duplicate `pose reference` or `drawing`, while preserving a reviewer-approved `reference` fragment such as `full body reference`. Put the top-level candidate file outside the index and record that no external raw data is persisted.

- [ ] **Step 3: Parse JSON and assert the candidate contract**

Run:

```powershell
$candidate = Get-Content docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json -Raw | ConvertFrom-Json
if ($candidate.candidates.Count -ne 8) { throw 'candidate count must be 8' }
if (($candidate.candidates.term_id | Select-Object -Unique).Count -ne 8) { throw 'candidate term_id values must be unique' }
if ($candidate.status -ne 'reviewed_not_promoted' -or $candidate.review_summary.review_completed -ne $true) { throw 'candidate review summary mismatch' }
$invalid = $candidate.candidates | Where-Object {
  $_.runtime_eligible -ne $false -or
  $_.mvp_status -ne 'candidate_outside_current_contract' -or
  $_.review_status -ne 'reviewed' -or
  $_.crosscheck.status -ne 'not_verified'
}
if ($invalid) { throw 'candidate runtime or review contract mismatch' }
$forbiddenFragment = $candidate.candidates.candidate_query_fragments | Where-Object { $_ -match '(?i)(^|\s)pose\s+reference(\s|$)' -or $_ -match '(?i)(^|\s)drawing(\s|$)' }
if ($forbiddenFragment) { throw "forbidden query fragments: $($forbiddenFragment -join ', ')" }
```

Expected: 명령이 오류 없이 끝난다.

### Task 2: 중복·런타임 격리·변경 범위 검증

**Files:**
- Verify: `docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json`
- Verify unchanged: `docs/domains/illustration-reference/term-cards/index.json`
- Verify unchanged: `docs/domains/illustration-reference/term-cards/{body,pose,view,perspective,layout}.json`

**Interfaces:**
- Consumes: Task 1의 후보 배치, 현재 index와 카드 JSON, `evals/**/*.jsonl`
- Produces: 후보 ID 교집합 0건 및 허용된 변경 파일만 존재한다는 검증 결과

- [ ] **Step 1: 기존 카드·평가 JSONL과의 ID 교집합 검사**

Run:

```powershell
function Get-TermIds($node) {
  if ($null -eq $node) { return }
  if ($node -is [System.Collections.IDictionary] -or $node -is [pscustomobject]) {
    foreach ($property in $node.PSObject.Properties) {
      if ($property.Name -eq 'term_id' -and $null -ne $property.Value) { [string]$property.Value }
      Get-TermIds $property.Value
    }
    return
  }
  if ($node -is [System.Collections.IEnumerable] -and $node -isnot [string]) {
    foreach ($item in $node) { Get-TermIds $item }
  }
}
$candidateIds = (Get-Content docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json -Raw | ConvertFrom-Json).candidates.term_id
$cardIds = Get-ChildItem docs/domains/illustration-reference/term-cards -Filter '*.json' -File |
  Where-Object Name -ne 'index.json' |
  ForEach-Object { (Get-Content $_ -Raw | ConvertFrom-Json).cards.term_id }
$evalIds = Get-ChildItem evals -Recurse -Filter '*.jsonl' -File |
  ForEach-Object { Get-Content $_ | Where-Object { $_.Trim() } | ForEach-Object { Get-TermIds ($_ | ConvertFrom-Json) } }
$overlap = $candidateIds | Where-Object { $_ -in $cardIds -or $_ -in $evalIds }
if ($overlap) { throw "duplicate candidate IDs: $($overlap -join ', ')" }
```

Expected: 명령이 오류 없이 끝난다.

- [ ] **Step 2: index 격리와 외부 데이터 금지 검사**

Run:

```powershell
$index = Get-Content docs/domains/illustration-reference/term-cards/index.json -Raw | ConvertFrom-Json
if ($index.categories.file -contains 'candidates/booru-crosscheck-candidates.json') { throw 'candidate file must not be indexed' }
$raw = Get-Content docs/domains/illustration-reference/term-cards/candidates/booru-crosscheck-candidates.json -Raw
if ($raw -match '(?i)post_id|post_url|image_url|thumbnail|wiki_text|prompt|artist|copyright|character') {
  throw 'external raw metadata field is prohibited'
}
```

Expected: 명령이 오류 없이 끝난다.

- [ ] **Step 3: 최종 diff 검증**

Run:

```powershell
git diff --check
git diff --name-only
git status --short
```

Expected: 공백 오류가 없고, 추적·미추적 변경을 합쳐 이 Plan, Spec, 후보 JSON 세 파일뿐이다. 검증 뒤에도 commit, push, PR 생성은 수행하지 않는다.
