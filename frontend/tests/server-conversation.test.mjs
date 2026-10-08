import test from "node:test";
import assert from "node:assert/strict";
import { restoreConversation, createConversation, listConversations, loadInitialConversation, resumeConversation, createHistoryLoader } from "../lib/server-conversation.mjs";
import { showThumbnail } from "../lib/result-view.mjs";
import { submitAgentRequest } from "../lib/agent-submit.mjs";
import { answerForJob, upsertTurn, stopTurnPolling } from "../lib/conversation.mjs";
const sid = "00000000-0000-0000-0000-000000000001";
const sid2 = "00000000-0000-0000-0000-000000000002";
const job = (id, status = "completed") => ({ job_id: id, session_id: sid, job_status: status,
  request_text: `요청 ${id}`, result: status === "completed" ? { agent_status: "partial_result", answer_text: "통합 설명", reason_codes: ["PIN_SEARCH_UNAVAILABLE"] } : null });
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });

test("세션 이력 한 번의 페이지 응답으로 대화를 복원하고 더미는 즉시 연다", async () => {
  const pin = { status: "available", pin_url: "https://www.pinterest.com/pin/123/" };
  const stored = [job("old"), job("latest")].map((j) => ({ ...j, result: { reference_plan: { terms: [{ pins: [pin] }] } } }));
  const enriched = (j) => ({ ...j, result: { reference_plan: { terms: [{ pins: [{ ...pin, thumbnail_url: "https://i.pinimg.com/fixture.jpg" }] }] } } });
  const calls = [], fetchImpl = async (url, options) => {
    calls.push(url); assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store");
    if (url === `/api/sessions/${sid}/jobs?limit=100&offset=0`) return response({ items: stored.map(enriched) });
    if (url === "/api/jobs/old") return response(enriched(stored[0]));
    throw new Error(`unexpected request ${url}`);
  };
  const { turns } = await restoreConversation({ sessionId: sid, fetchImpl });
  assert.equal(showThumbnail(turns[0].job.result.reference_plan.terms[0].pins[0]), true);
  assert.equal(showThumbnail(turns[1].job.result.reference_plan.terms[0].pins[0]), true);
  assert.deepEqual(calls, [`/api/sessions/${sid}/jobs?limit=100&offset=0`]);
  let selected; const states = [];
  const loader = createHistoryLoader({ fetchImpl, onJob: (j) => { selected = j; }, onState: (s) => states.push(s) });
  await loader.open(turns[0]); assert.equal(calls.at(-1), "/api/jobs/old");
  assert.equal(showThumbnail(selected.result.reference_plan.terms[0].pins[0]), true);
  assert.equal(states.some((s) => s.loading), true); assert.equal(states.at(-1).loading, false);
  const count = calls.length; await loader.open({ ...turns[0], demo: true }); assert.equal(calls.length, count);
});

test("기록 조회 오류는 Pin 상태를 바꾸지 않고 다른 선택·정리 후 늦은 응답을 차단", async () => {
  const releases = [], states = [], selected = [], signals = [];
  const loader = createHistoryLoader({ onState: (s) => states.push(s), onJob: (j) => selected.push(j.job_id),
    fetchImpl: (_, options) => { signals.push(options.signal); return new Promise((resolve) => releases.push(resolve)); } });
  const entry = (id) => ({ id, job: job(id) });
  const failed = loader.open(entry("bad")); releases[0](response({}, 503)); await failed;
  assert.match(states.at(-1).error, /검색 기록/); assert.equal(states.at(-1).loading, false); assert.deepEqual(selected, []);
  const old = loader.open(entry("old")), next = loader.open(entry("next"));
  releases[2](response(job("next"))); await next; releases[1](response(job("old"))); await old;
  assert.equal(signals[1].aborted, true); assert.deepEqual(selected, ["next"]);
  const removed = loader.open(entry("removed")); loader.cancel(); releases[3](response(job("removed"))); await removed;
  assert.equal(signals[3].aborted, true); assert.deepEqual(selected, ["next"]);
});

test("서버 페이지 복원은 Job별 상세 요청 없이 페이지 단위로 완료된다", async () => {
  const calls = [], controller = new AbortController();
  const restored = await restoreConversation({ signal: controller.signal, fetchImpl: async (url, options) => {
    calls.push(url);
    assert.equal(options.credentials, "include"); assert.equal(options.cache, "no-store");
    assert.equal(options.signal, controller.signal);
    if (url.endsWith("offset=0")) return response({ items: Array.from({ length: 100 }, (_, i) => job(`${i}`, i === 0 ? "completed" : "failed")) });
    if (url.endsWith("offset=100")) return response({ items: [job("99", "failed"), job("100")] });
    throw new Error(`unexpected request ${url}`);
  }, sessionId: sid });
  assert.equal(restored.sessionId, sid); assert.equal(restored.turns.length, 101);
  assert.deepEqual(restored.turns.map((turn) => turn.id), Array.from({ length: 101 }, (_, i) => `${i}`));
  assert.equal(restored.turns[0].job.enriched, undefined);
  assert.equal(restored.turns.at(-1).job.enriched, undefined);
  assert.equal(answerForJob(restored.turns[0].job), "통합 설명");
  assert.equal(calls.length, 2);
});

test("미인증·빈 bootstrap은 빈 대화이며 새 ID를 후속 제출에 명시", async () => {
  for (const r of [response({}, 401), response({ items: [], session_id: null, latest_job: null, has_older_jobs: false })]) {
    assert.deepEqual(await restoreConversation({ fetchImpl: async () => r }), { sessionId: null, turns: [] });
  }
  const created = await createConversation({ fetchImpl: async (url, options) => {
    assert.equal(url, "/api/sessions"); assert.equal(options.method, "POST");
    return response({ session_id: sid, created_at: "2026-10-07T01:00:00Z" }, 201);
  } });
  const sent = await submitAgentRequest("포즈만 수정", { sessionId: created.session_id, createId: () => "key", fetchImpl: async (_, options) => {
    assert.deepEqual(JSON.parse(options.body), { request_text: "포즈만 수정", session_id: sid });
    return response({ job_id: "next", poll_after_ms: 1000 }, 202);
  } });
  assert.equal(sent.ok, true);
});

test("세션 목록 복원과 선택한 세션의 대화만 복원", async () => {
  const calls = [];
  const sessions = [
    { session_id: sid, created_at: "2026-10-06T01:00:00Z" },
    { session_id: sid2, created_at: "2026-10-07T01:00:00Z" },
  ];
  const items = [job("selected", "completed")].map((entry) => ({ ...entry, session_id: sid }));
  const fetchImpl = async (url) => {
    calls.push(url);
    if (url === "/api/sessions?limit=100&offset=0") return response({ items: sessions });
    if (url === `/api/sessions/${sid}`) return response(sessions[0]);
    if (url === `/api/sessions/${sid}/jobs?limit=100&offset=0`) return response({ items });
    if (url === "/api/jobs/selected") return response(items[0]);
    throw new Error(`unexpected request ${url}`);
  };
  const listed = await listConversations({ fetchImpl });
  assert.deepEqual(listed.map((entry) => entry.session_id), [sid2, sid]);
  const restored = await restoreConversation({ fetchImpl, sessionId: sid });
  assert.equal(restored.sessionId, sid);
  assert.deepEqual(restored.turns.map((turn) => turn.id), ["selected"]);
  assert.equal(calls.some((url) => url.includes(sid2)), false);
});

test("세션 소유 쿠키가 없으면 세션 목록은 빈 목록으로 시작", async () => {
  const listed = await listConversations({ fetchImpl: async (url) => {
    assert.equal(url, "/api/sessions?limit=100&offset=0");
    return response({}, 401);
  } });
  assert.deepEqual(listed, []);
});

test("초기 복원 실패는 오류를 표시하되 새 대화를 시작할 수 있게 준비 상태로 반환", async () => {
  const failed = await loadInitialConversation({
    fetchImpl: async () => { throw new Error("offline"); },
  });
  assert.equal(failed.ready, true);
  assert.deepEqual(failed.sessions, []);
  assert.equal(failed.sessionId, null);
  assert.deepEqual(failed.turns, []);
  assert.equal(failed.restoreError, "대화를 복원하지 못했습니다. 다시 불러온 뒤 요청해 주세요.");
});

test("세션 쿠키가 없는 초기 진입은 오류 없이 빈 대화로 준비 완료", async () => {
  const state = await loadInitialConversation({
    fetchImpl: async () => response({}, 401),
  });
  assert.equal(state.ready, true);
  assert.deepEqual(state.sessions, []);
  assert.equal(state.sessionId, null);
  assert.deepEqual(state.turns, []);
  assert.equal(state.restoreError, "");
});

test("초기 복원은 bootstrap 한 번으로 세션 목록과 최신 Job만 가져온다", async () => {
  const calls = [];
  const latest = { ...job("latest"), created_at: "2026-10-08T00:00:00Z" };
  const result = await loadInitialConversation({ fetchImpl: async (url) => {
    calls.push(url);
    return response({ items: [{ session_id: sid, created_at: latest.created_at }],
      session_id: sid, latest_job: latest, has_older_jobs: true });
  } });
  assert.deepEqual(calls, ["/api/sessions/bootstrap?limit=100"]);
  assert.equal(result.sessionId, sid);
  assert.deepEqual(result.turns.map((turn) => turn.id), ["latest"]);
  assert.equal(result.hasOlderJobs, true);
});

test("새 세션 생성 뒤 목록에서 해당 세션을 추가할 수 있는 메타데이터 반환", async () => {
  const created = { session_id: sid2, created_at: "2026-10-07T01:00:00Z" };
  const result = await createConversation({ fetchImpl: async (url, options) => {
    assert.equal(url, "/api/sessions");
    assert.equal(options.method, "POST");
    return response(created, 201);
  } });
  assert.deepEqual(result, created);
});

test("목록 장애·이력 권한 오류·손상 데이터는 복원 실패하고 fallback하지 않는다", async () => {
  for (const bad of [response({}, 503), response({}), response({ items: [{ session_id: "bad" }] })]) {
    await assert.rejects(restoreConversation({ fetchImpl: async () => bad }));
  }
  for (const bad of [response({}, 401), response({}, 404), response({ items: [job("x", "invalid")] })]) {
    await assert.rejects(restoreConversation({ sessionId: sid, fetchImpl: async () => bad }));
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
