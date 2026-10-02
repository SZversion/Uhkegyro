"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { countCharacters, createSubmissionController, validateRequestText } from "../lib/agent-submit.mjs";
import { createJobPoller, STATUS_LABELS } from "../lib/job-polling.mjs";
import { DEMO_JOB, uiDemoEnabled } from "../lib/demo-job.mjs";
import { createMindMapSlots, firstSelectableTermId } from "../lib/term-mind-map.mjs";
import { resultTerms } from "../lib/result-view.mjs";

export default function HomePage() {
  const [requestText, setRequestText] = useState("");
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState(null);
  const [job, setJob] = useState(() => uiDemoEnabled ? DEMO_JOB : null);
  const [selectedTermId, setSelectedTermId] = useState(null);
  const mindMapSlots = useMemo(() => createMindMapSlots(resultTerms(job)), [job]);
  const hasTerms = mindMapSlots.some((slot) => slot.terms.length);
  const activeTermId = selectedTermId || firstSelectableTermId(mindMapSlots);
  const [pollError, setPollError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const conversationBusy = isSubmitting || Boolean(submission && !pollError && !["completed", "failed"].includes(job?.job_status));
  const submissionRef = useRef(null);
  const pollerRef = useRef(null);
  if (!submissionRef.current) submissionRef.current = createSubmissionController();

  useEffect(() => {
    if (!submission) return;
    const poller = createJobPoller(submission.jobId, { onUpdate: setJob, onError: setPollError });
    pollerRef.current = poller;
    poller.start(submission.pollAfterMs);
    return () => {
      poller.stop();
      if (pollerRef.current === poller) pollerRef.current = null;
    };
  }, [submission]);

  async function handleSubmit(event) {
    event.preventDefault();
    if (conversationBusy || submissionRef.current.isPending()) return;

    const validationError = validateRequestText(requestText);
    if (validationError) {
      setError(validationError);
      return;
    }

    if (uiDemoEnabled) { setJob(DEMO_JOB); setRequestText(""); return; }
    pollerRef.current?.stop();
    setIsSubmitting(true);
    setError("");
    setPollError("");
    setSubmission(null);
    setJob(null);
    try {
      const result = await submissionRef.current.submit(requestText);
      if (result.ok) setSubmission(result);
      else setError(result.error);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="workspace">
      <section className="reference-board" aria-labelledby="reference-title">
        <header className="board-header">
          <div className="brand-identity"><span className="brand-mark" aria-hidden="true">UH</span>
            <span className="brand-name">UH케그려</span></div>
        </header>
        {hasTerms ? (
          <div className="mind-map-stage" aria-label="해석된 용어 관계도">
            <p className="mind-map-guide">용어를 누르면 레퍼런스를 볼 수 있어요.</p>
            <div className="mind-map">
              <svg className="mind-map-connectors" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <line x1="50" y1="61.2" x2="50" y2="29" />
                <line x1="50" y1="61.2" x2="69.1" y2="37.8" />
                <line x1="50" y1="61.2" x2="81.3" y2="61.2" />
                <line x1="50" y1="61.2" x2="18.7" y2="61.2" />
                <line x1="50" y1="61.2" x2="30.9" y2="37.8" />
              </svg>
              <span className="mind-map-hub" aria-hidden="true">UH</span>
              {mindMapSlots.map((slot, index) => (
                <section className={`mind-map-group mind-map-group-${index}`} key={slot.role} aria-label={`${slot.roleLabel} TERM_CARD`}>
                  <span className="mind-map-group-role">{slot.roleLabel}</span>
                  <div className="mind-map-group-cards">
                    {slot.terms.length > 0 ? slot.terms.map((term) => (
                      <button
                        type="button"
                        className="mind-map-node"
                        aria-label={`${slot.roleLabel} ${term.label_ko}`}
                        aria-pressed={term.term_id === activeTermId}
                        key={term.term_id}
                        onClick={() => setSelectedTermId(term.term_id)}
                      >
                        {term.label_ko}
                      </button>
                    )) : (
                      <div className="mind-map-node mind-map-node-empty">해석 없음</div>
                    )}
                  </div>
                </section>
              ))}
            </div>
          </div>
        ) : (
        <div className="board-empty">
          <span className="board-empty-icon" aria-hidden="true">🖌️</span>
          <h1 id="reference-title">그림의 출발점을 찾아보세요</h1>
          <p>오른쪽에 그리고 싶은 캐릭터를 설명하면 레퍼런스 탐색을 시작합니다.</p>
        </div>
        )}
      </section>

      <aside className="prompt-panel" aria-labelledby="prompt-title">
        <div className="panel-top">
          <h2 id="prompt-title">UH케 그릴 건가요?</h2>
          {uiDemoEnabled && <span className="demo-badge">UI 더미 · LLM 미연결</span>}
          {submission && !pollError && !["completed", "failed"].includes(job?.job_status) && (
            <div className="receipt" role="status">
              {STATUS_LABELS[job?.job_status || "queued"]}
            </div>
          )}
          {job?.job_status === "completed" && <div className="receipt" role="status">완료</div>}
          {job?.job_status === "failed" && <p className="form-error" role="alert">{job.failure?.user_message}</p>}
          {pollError && <p className="form-error" role="alert">{pollError}</p>}
        </div>

        <form className="composer" onSubmit={handleSubmit} noValidate>
          <div className="composer-input-frame" data-invalid={Boolean(error)}>
          <textarea
            id="request-text"
            aria-label="캐릭터 설명"
            name="request_text"
            rows={5}
            value={requestText}
            disabled={conversationBusy}
            onChange={(event) => {
              setRequestText(event.target.value);
              if (error) setError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder="원하는 체형, 포즈, 시점을 적어 주세요"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "request-error" : "request-count"}
          />
          </div>
          {error && <p id="request-error" className="form-error" role="alert">{error}</p>}
          <div className="composer-footer">
            <span id="request-count" className="character-count">{countCharacters(requestText)} / 500</span>
            <button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "전송 중…" : "레퍼런스 찾기"}
            </button>
          </div>
        </form>
      </aside>
    </main>
  );
}
