import test from "node:test";
import assert from "node:assert/strict";
import { DEMO_JOB, DEMO_REQUEST_TEXT } from "../lib/demo-job.mjs";
import { createMindMapSlots } from "../lib/term-mind-map.mjs";

test("UI 미리보기 Job은 카탈로그의 검수 완료 TERM_CARD 다섯 역할을 제공한다", () => {
  const slots = createMindMapSlots(DEMO_JOB.result.reference_plan.terms);

  assert.equal(DEMO_JOB.job_status, "completed");
  assert.match(DEMO_REQUEST_TEXT, /허리가 들어간/);
  assert.equal(slots.filter((slot) => slot.term).length, 5);
  assert.deepEqual(slots.map((slot) => slot.terms.length), [3, 3, 3, 3, 2]);
  assert.equal(slots[0].term.label_ko, "모래시계형");
  assert.equal(slots[3].term.term_id, "perspective_three_point");
  assert.equal(slots[4].term.label_ko, "삼분할 구도");
  assert.equal(slots[4].term.term_id, "composition_rule_of_thirds");
});
