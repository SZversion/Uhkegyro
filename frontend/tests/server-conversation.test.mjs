import test from "node:test";
import assert from "node:assert/strict";
import { restoreConversation, createConversation, resumeConversation } from "../lib/server-conversation.mjs";
import { submitAgentRequest } from "../lib/agent-submit.mjs";
import { answerForJob, upsertTurn, stopTurnPolling } from "../lib/conversation.mjs";
const sid = "00000000-0000-0000-0000-000000000001";
const job = (id, status = "completed") => ({ job_id: id, session_id: sid, job_status: status,
  request_text: `요청 ${id}`, result: status === "completed" ? { agent_status: "partial_result", answer_text: "통합 설명", reason_codes: ["PIN_SEARCH_UNAVAILABLE"] } : null });
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

test("서버 페이지 전체 복원, 중복 제거, 마지막 결과 enrichment, 쿠키와 취소 signal", async () => {
  const calls = [], controller = new AbortController();
  const restored = await restoreConversation({ signal: controller.signal, fetchImpl: async (url, options) => {
    calls.push(url);
    assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store");
    assert.equal(options.signal, controller.signal);
    if (url === "/api/sessions?limit=1") return response({ items: [{ session_id: sid }] });
    if (url.endsWith("offset=0")) return response({ items: Array.from({ length: 100 }, (_, i) => job(`${i}`)) });
    if (url.endsWith("offset=100")) return response({ items: [job("99"), job("100")] });
    if (url.endsWith("/jobs/100")) return response({ ...job("100"), enriched: true });
    return response({ session_id: sid });
  } });
  assert.equal(restored.sessionId, sid); assert.equal(restored.turns.length, 101);
  assert.deepEqual(restored.turns.map((turn) => turn.id), Array.from({ length: 101 }, (_, i) => `${i}`));
  assert.equal(restored.turns.at(-1).job.enriched, true);
  assert.equal(answerForJob(restored.turns[0].job), "통합 설명");
  assert.equal(calls.length, 5);
});

test("미인증·빈 목록은 빈 대화이며 새 ID를 후속 제출에 명시", async () => {
  for (const r of [response({}, 401), response({ items: [] })]) {
    assert.deepEqual(await restoreConversation({ fetchImpl: async () => r }), { sessionId: null, turns: [] });
  }
  const id = await createConversation({ fetchImpl: async (url, options) => {
    assert.equal(url, "/api/sessions"); assert.equal(options.method, "POST");
    return response({ session_id: sid }, 201);
  } });
  const sent = await submitAgentRequest("포즈만 수정", { sessionId: id, createId: () => "key", fetchImpl: async (_, options) => {
    assert.deepEqual(JSON.parse(options.body), { request_text: "포즈만 수정", session_id: sid });
    return response({ job_id: "next", poll_after_ms: 1000 }, 202);
  } });
  assert.equal(sent.ok, true);
});

test("목록 장애·이력 권한 오류·손상 데이터는 복원 실패하고 fallback하지 않는다", async () => {
  for (const bad of [response({}, 503), response({}), response({ items: [{ session_id: "bad" }] })]) {
    await assert.rejects(restoreConversation({ fetchImpl: async () => bad }));
  }
  for (const bad of [response({}, 401), response({}, 404), response({ items: [job("x", "invalid")] })]) {
    await assert.rejects(restoreConversation({ fetchImpl: async (url) => url.includes("limit=1")
      && !url.includes("offset=") ? response({ items: [{ session_id: sid }] }) : url.includes("offset=") ? bad : response({}) }));
  }
  await assert.rejects(restoreConversation({ fetchImpl: async () => { throw new Error("offline"); } }));
});

test("복원된 여러 진행 turn이 각각 종결·중단되고 cleanup은 늦은 응답을 차단", async () => {
  let turns = ["a", "b", "c"].map((id) => ({ id, request: id, job: job(id, "running") }));
  const tasks = [], errors = [], updates = [];
  let release;
  const pollers = resumeConversation(turns, { schedule: (fn) => { tasks.push(fn); return tasks.length; }, cancel: () => {},
    fetchImpl: async (url) => url.endsWith("b") ? response({}, 503) : url.endsWith("c")
      ? new Promise((resolve) => { release = resolve; }) : response(job("a")),
    onUpdate: (turn) => { updates.push(turn.id); turns = upsertTurn(turns, turn); },
    onError: (id) => { errors.push(id); turns = stopTurnPolling(turns, id); },
  });
  await tasks[0](); await tasks[1](); const pending = tasks[2]();
  pollers.stop(); release(response(job("c"))); await pending;
  assert.deepEqual(updates, ["a"]); assert.deepEqual(errors, ["b"]);
  assert.equal(turns.length, 3); assert.equal(turns[1].polling_stopped, true);
  assert.equal(answerForJob(turns[0].job), "통합 설명");
});
