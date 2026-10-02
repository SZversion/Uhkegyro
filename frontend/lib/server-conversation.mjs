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
export async function createConversation(options = {}) {
  return sessionId((await read("/api/sessions", options, "POST")).session_id);
}
export async function restoreConversation(options = {}) {
  const response = await (options.fetchImpl || globalThis.fetch)("/api/sessions?limit=1", {
    credentials: "include", cache: "no-store", signal: options.signal,
  });
  if (response.status === 401) return { sessionId: null, turns: [] };
  if (!response.ok) throw new Error(RESTORE_ERROR);
  const list = await response.json();
  if (!Array.isArray(list?.items)) throw new Error(RESTORE_ERROR);
  if (!list.items.length) return { sessionId: null, turns: [] };
  const id = sessionId(list.items[0].session_id);
  await read(`/api/sessions/${id}`, options);
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
  const latest = turns.at(-1);
  if (latest) {
    const job = await read(`/api/jobs/${encodeURIComponent(latest.id)}`, options);
    if (job.job_id !== latest.id || job.session_id !== id
      || !Object.hasOwn(STATUS_LABELS, job.job_status)) throw new Error(RESTORE_ERROR);
    turns = upsertTurn(turns, { ...latest, job });
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
