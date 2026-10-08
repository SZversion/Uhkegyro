import { upsertTurn, isTurnPending } from "./conversation.mjs";
import { createJobPoller, STATUS_LABELS } from "./job-polling.mjs";

export const RESTORE_ERROR = "대화를 복원하지 못했습니다. 다시 불러온 뒤 요청해 주세요.";
async function read(path, options, method = "GET") {
  const response = await (options.fetchImpl || globalThis.fetch)(path, {
    method, credentials: "include", cache: "no-store", signal: options.signal,
  });
  if (!response.ok) throw new Error(RESTORE_ERROR);
  return response.json();
}
function sessionId(value) {
  if (typeof value !== "string" || !/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value)) throw new Error(RESTORE_ERROR);
  return value;
}
export function orderConversations(items) {
  return [...items].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}
function validateSessions(items) {
  if (!Array.isArray(items)) throw new Error(RESTORE_ERROR);
  return orderConversations(items.map((item) => {
    sessionId(item?.session_id);
    if (typeof item.created_at !== "string" || Number.isNaN(Date.parse(item.created_at))) throw new Error(RESTORE_ERROR);
    return item;
  }));
}
export async function listConversations(options = {}) {
  const response = await (options.fetchImpl || globalThis.fetch)("/api/sessions?limit=100&offset=0", {
    credentials: "include", cache: "no-store", signal: options.signal,
  });
  if (response.status === 401) return [];
  if (!response.ok) throw new Error(RESTORE_ERROR);
  const list = await response.json();
  return validateSessions(list?.items);
}

async function fetchSessionBootstrap(options = {}) {
  const response = await (options.fetchImpl || globalThis.fetch)("/api/sessions/bootstrap?limit=100", {
    credentials: "include", cache: "no-store", signal: options.signal,
  });
  if (response.status === 401) {
    return { sessions: [], sessionId: null, turns: [], hasOlderJobs: false };
  }
  if (!response.ok) throw new Error(RESTORE_ERROR);
  const data = await response.json();
  const sessions = validateSessions(data?.items);
  const activeId = data?.session_id == null ? null : sessionId(data.session_id);
  if (activeId && !sessions.some((entry) => entry.session_id === activeId)) throw new Error(RESTORE_ERROR);
  if (typeof data?.has_older_jobs !== "boolean") throw new Error(RESTORE_ERROR);
  let turns = [];
  if (data?.latest_job != null) {
    const job = data.latest_job;
    if (!activeId || job.session_id !== activeId || !job.job_id
      || typeof job.request_text !== "string" || typeof job.created_at !== "string"
      || !Object.hasOwn(STATUS_LABELS, job.job_status)) throw new Error(RESTORE_ERROR);
    turns = upsertTurn([], { id: job.job_id, request: job.request_text, job, demo: false });
  }
  return { sessions, sessionId: activeId, turns, hasOlderJobs: data.has_older_jobs };
}

export async function loadInitialConversation(options = {}) {
  try {
    return { ready: true, ...await fetchSessionBootstrap(options), restoreError: "" };
  } catch {
    return {
      ready: true, sessions: [], sessionId: null, turns: [], hasOlderJobs: false, restoreError: RESTORE_ERROR,
    };
  }
}
export async function createConversation(options = {}) {
  const created = await read("/api/sessions", options, "POST");
  validateSessions([created]);
  return created;
}
export async function restoreConversation(options = {}) {
  let id = options.sessionId;
  if (id) sessionId(id);
  else {
    const initial = await fetchSessionBootstrap(options);
    id = initial.sessionId;
    if (!id) return { sessionId: null, turns: [] };
  }
  let turns = [];
  for (let offset = 0; ; offset += 100) {
    const page = await read(`/api/sessions/${id}/jobs?limit=100&offset=${offset}`, options);
    if (!Array.isArray(page?.items)) throw new Error(RESTORE_ERROR);
    for (const job of page.items) {
      if (!job.job_id || job.session_id !== id || typeof job.request_text !== "string"
        || !Object.hasOwn(STATUS_LABELS, job.job_status)) throw new Error(RESTORE_ERROR);
      turns = upsertTurn(turns, { id: job.job_id, request: job.request_text, job, demo: false });
    }
    if (page.items.length < 100) break;
  }
  return { sessionId: id, turns };
}
export function resumeConversation(turns, options) {
  const pollers = turns.filter(isTurnPending).map((turn) => {
    const poller = createJobPoller(turn.id, {
      ...options,
      onUpdate: (job) => {
        if (job.job_id !== turn.id) return options.onError(turn.id, RESTORE_ERROR);
        options.onUpdate({ ...turn, job });
      },
      onError: (message) => options.onError(turn.id, message),
    });
    poller.start(turn.job?.poll_after_ms);
    return poller;
  });
  return { stop: () => pollers.forEach((poller) => poller.stop()) };
}

export function createHistoryLoader(options) {
  let controller;
  const cancel = () => { controller?.abort(); options.onState({ loading: false, error: "" }); };
  return { cancel, async open(entry) {
    cancel();
    if (entry.demo) { options.onJob(entry.job); return; }
    controller = new AbortController();
    const signal = controller.signal;
    options.onState({ loading: true, error: "" });
    try {
      const job = await read(`/api/jobs/${encodeURIComponent(entry.id)}`, { ...options, signal });
      if (signal.aborted) return;
      if (job.job_id !== entry.id || job.session_id !== entry.job.session_id
        || !["completed", "failed"].includes(job.job_status)) throw new Error("invalid history job");
      options.onJob(job);
      options.onState({ loading: false, error: "" });
    } catch {
      if (!signal.aborted) options.onState({ loading: false, error: "검색 기록을 불러오지 못했습니다. 다시 시도해 주세요." });
    }
  } };
}
