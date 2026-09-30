"use client";

import { useEffect, useRef, useState } from "react";
import { countCharacters, createSubmissionController, validateRequestText } from "../lib/agent-submit.mjs";
import { createJobPoller, STATUS_LABELS } from "../lib/job-polling.mjs";

export default function HomePage() {
  const [requestText, setRequestText] = useState("");
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState(null);
  const [job, setJob] = useState(null);
  const [pollError, setPollError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
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
    if (submissionRef.current.isPending()) return;

    const validationError = validateRequestText(requestText);
    if (validationError) {
      setError(validationError);
      return;
    }

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
          <span className="brand-mark" aria-hidden="true">U</span>
          <span className="brand-name">UH케그려</span>
        </header>
        <div className="board-empty">
          <span className="board-empty-icon" aria-hidden="true">✳</span>
          <h1 id="reference-title">그림의 출발점을 찾아보세요</h1>
          <p>오른쪽에 그리고 싶은 캐릭터를 설명하면 레퍼런스 탐색을 시작합니다.</p>
        </div>
      </section>

      <aside className="prompt-panel" aria-labelledby="prompt-title">
        <div className="panel-top">
          <span className="panel-eyebrow">REFERENCE STUDIO</span>
          <h2 id="prompt-title">어떤 캐릭터를 그리고 싶나요?</h2>
          <p>체형, 자세, 보는 각도처럼 떠오르는 모습을 편하게 적어 주세요.</p>
          <div className="example-note">예: 한쪽 다리에 힘을 주고 아래에서 올려다보는 캐릭터</div>
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
          <label htmlFor="request-text">캐릭터 설명</label>
          <textarea
            id="request-text"
            name="request_text"
            rows={5}
            value={requestText}
            disabled={isSubmitting}
            onChange={(event) => {
              setRequestText(event.target.value);
              if (error) setError("");
            }}
            placeholder="원하는 체형, 포즈, 시점을 적어 주세요"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? "request-error" : "request-count"}
          />
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
