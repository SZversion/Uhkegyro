export const ROLE_LABELS = {
  body: "체형", pose: "포즈", view: "시점", perspective: "원근", layout: "배치",
};

export function resultTerms(job) {
  const result = job?.job_status === "completed" ? job.result : null;
  return ["success", "partial_result"].includes(result?.agent_status)
    ? result.reference_plan?.terms || [] : [];
}

export function defaultRole(terms) {
  return terms.find((term) => term.pins?.length)?.role || terms[0]?.role || null;
}

export function roleNotice(term) {
  if (term.reason_codes?.includes("PIN_SEARCH_UNAVAILABLE")) return "검색 결과를 가져오지 못했습니다.";
  if (term.reason_codes?.includes("PIN_RESULTS_EMPTY")) return "검색 결과가 없습니다.";
  return null;
}

export function showThumbnail(pin) {
  return pin.status === "available" && Boolean(pin.thumbnail_url);
}

export function clarificationChoices(result) {
  return Array.isArray(result?.clarification_choices) ? result.clarification_choices : [];
}

export function resultUserMessage(job) {
  if (job?.job_status === "failed") return job.failure?.user_message || null;
  const result = job?.job_status === "completed" ? job.result : null;
  return ["out_of_scope", "unsafe_input"].includes(result?.agent_status) ? result.user_message : null;
}
