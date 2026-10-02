import test from "node:test";
import assert from "node:assert/strict";
import * as view from "../lib/result-view.mjs";
import { createMindMapSlots } from "../lib/term-mind-map.mjs";

const term = (role, extra = {}) => ({ role, term_id: role, label_ko: role, ...extra });
const completed = (agent_status, extra = {}) => ({ job_status: "completed", result: { agent_status, ...extra } });

test("결과는 완료된 success/partial_result에만 노출한다", () => {
  for (const status of ["success", "partial_result"]) {
    assert.equal(view.resultTerms(completed(status, { reference_plan: { terms: [term("body")] } })).length, 1);
  }
  for (const status of ["needs_clarification", "out_of_scope", "unsafe_input"]) {
    assert.deepEqual(view.resultTerms(completed(status, { reference_plan: { terms: [term("body")] } })), []);
  }
  assert.deepEqual(view.resultTerms({ job_status: "searching" }), []);
});

test("실패와 빈 카테고리 및 접근 불가 Pin을 순서대로 보존한다", () => {
  const rows = view.createGalleryRows(createMindMapSlots([
    term("body", { reason_codes: ["PIN_SEARCH_UNAVAILABLE"], pins: [] }),
    term("pose", { reason_codes: ["PIN_RESULTS_EMPTY"], pins: [] }),
    term("view", { pins: [{ pin_id: "deleted", status: "deleted", thumbnail_url: "old" }] }),
  ]));
  assert.deepEqual(rows.map((row) => row.role), ["body", "pose", "view"]);
  assert.match(view.roleNotice(rows[0].term), /가져오지/);
  assert.match(view.roleNotice(rows[1].term), /없습니다/);
  assert.equal(rows[2].pins[0].pin_id, "deleted");
  assert.equal(view.showThumbnail(rows[2].pins[0]), false);
  assert.equal(view.showThumbnail({ status: "available", thumbnail_url: "image" }), true);
  assert.equal(view.showThumbnail({ status: "available", thumbnail_url: null }), false);
});

test("카테고리당 8개 순서를 보존하고 썸네일이 있는 용어를 우선한다", () => {
  const pins = Array.from({ length: 10 }, (_, index) => ({ pin_id: String(index), status: "available", thumbnail_url: "image" }));
  const rows = view.createGalleryRows(createMindMapSlots([term("pose"), term("pose", { term_id: "second", pins })]));
  assert.equal(rows[0].term.term_id, "second");
  assert.deepEqual(rows[0].pins.map((pin) => pin.pin_id), ["0", "1", "2", "3", "4", "5", "6", "7"]);
});

test("실패 안내와 추가 질문은 결과 상태에 맞게 분리한다", () => {
  assert.equal(view.resultUserMessage({ job_status: "failed", failure: { user_message: "실패 안내" } }), "실패 안내");
  for (const status of ["out_of_scope", "unsafe_input"]) assert.equal(view.resultUserMessage(completed(status, { user_message: "입력 안내" })), "입력 안내");
  assert.equal(view.resultUserMessage(completed("needs_clarification")), null);
  assert.deepEqual(view.clarificationChoices({}), []);
  assert.deepEqual(view.clarificationChoices({ clarification_choices: [{ label: "앉기", request_text: "앉은 캐릭터" }] }), [{ label: "앉기", request_text: "앉은 캐릭터" }]);
});
