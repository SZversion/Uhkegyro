import test from "node:test";
import assert from "node:assert/strict";
import { clarificationChoices, defaultRole, resultTerms, resultUserMessage, roleNotice, showThumbnail } from "../lib/result-view.mjs";

test("AC-01: 결과 역할 중 Pin이 있는 첫 역할을 기본 선택한다", () => {
  const terms = [
    { role: "body", pins: [] },
    { role: "pose", pins: [{ pin_id: "1" }] },
    { role: "view", pins: [{ pin_id: "2" }] },
  ];
  assert.equal(defaultRole(terms), "pose");
  assert.deepEqual(resultTerms({ job_status: "completed", result: {
    agent_status: "success", reference_plan: { terms },
  } }), terms);
  assert.deepEqual(resultTerms({ job_status: "failed", result: null }), []);
  assert.deepEqual(resultTerms({ job_status: "completed", result: {
    agent_status: "needs_clarification", clarifying_question: "어떤 자세인가요?", reference_plan: null,
  } }), []);
});

test("AC-02/04: 부분 실패와 접근 불가 Pin을 구분한다", () => {
  assert.equal(roleNotice({ reason_codes: ["PIN_SEARCH_UNAVAILABLE"] }), "검색 결과를 가져오지 못했습니다.");
  assert.equal(roleNotice({ reason_codes: ["PIN_RESULTS_EMPTY"] }), "검색 결과가 없습니다.");
  assert.equal(showThumbnail({ status: "deleted", thumbnail_url: null }), false);
  assert.equal(showThumbnail({ status: "available", thumbnail_url: null }), false);
  assert.equal(showThumbnail({ status: "available", thumbnail_url: "https://images.example/pin.jpg" }), true);
});

test("AC-03: 질문 선택지 부재와 실패 사용자 메시지를 처리한다", () => {
  assert.deepEqual(clarificationChoices({ agent_status: "needs_clarification" }), []);
  const choice = { label: "한쪽 다리", request_text: "한쪽 다리에 힘을 준 캐릭터" };
  assert.deepEqual(clarificationChoices({ clarification_choices: [choice] }), [choice]);
  assert.equal(resultUserMessage({ job_status: "failed", failure: { user_message: "잠시 후 다시 시도해 주세요." } }), "잠시 후 다시 시도해 주세요.");
  assert.equal(resultUserMessage({ job_status: "completed", result: { agent_status: "out_of_scope", user_message: "그림 요청을 입력해 주세요." } }), "그림 요청을 입력해 주세요.");
  assert.equal(resultUserMessage({ job_status: "completed", result: { agent_status: "needs_clarification", user_message: "" } }), null);
});
