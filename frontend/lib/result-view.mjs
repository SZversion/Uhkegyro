export function resultTerms(job) {
  const result = job?.job_status === "completed" ? job.result : null;
  return ["success", "partial_result"].includes(result?.agent_status)
    ? result.reference_plan?.terms || [] : [];
}

export function roleNotice(term) {
  if (term?.reason_codes?.includes("PIN_SEARCH_UNAVAILABLE")) return "검색 결과를 가져오지 못했습니다.";
  if (term?.reason_codes?.includes("PIN_RESULTS_EMPTY")) return "검색 결과가 없습니다.";
  return null;
}

export function showThumbnail(pin) {
  return pin.status === "available" && Boolean(pin.thumbnail_url);
}

export function createGalleryRows(slots) {
  return slots.filter((slot) => slot.terms.length).map((slot) => {
    const term = slot.terms.find((candidate) => candidate.pins?.some(showThumbnail)) || slot.terms[0];
    return { ...slot, term, pins: (term.pins || []).slice(0, 8) };
  });
}

export function clarificationChoices(result) {
  return Array.isArray(result?.clarification_choices) ? result.clarification_choices : [];
}

export function resultUserMessage(job) {
  if (job?.job_status === "failed") return job.failure?.user_message || "요청을 완료하지 못했습니다. 다시 시도해 주세요.";
  const result = job?.job_status === "completed" ? job.result : null;
  return ["out_of_scope", "unsafe_input"].includes(result?.agent_status) ? result.user_message : null;
}
