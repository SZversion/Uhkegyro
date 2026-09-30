"use client";

import { useEffect, useRef, useState } from "react";
import { countCharacters, createSubmissionController, validateRequestText } from "../lib/agent-submit.mjs";
import { createJobPoller, STATUS_LABELS } from "../lib/job-polling.mjs";
import { clarificationChoices, defaultRole, resultTerms, resultUserMessage, ROLE_LABELS, roleNotice, showThumbnail } from "../lib/result-view.mjs";

export default function HomePage() {
  const [requestText, setRequestText] = useState("");
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState(null);
  const [job, setJob] = useState(null);
  const [pollError, setPollError] = useState("");
  const [selectedRole, setSelectedRole] = useState(null);
  const [mobileView, setMobileView] = useState("input");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef(null);
  const pollerRef = useRef(null);
  const submissionRef = useRef(null);
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

  async function submit(text) {
    if (submissionRef.current.isPending()) return;
    const validationError = validateRequestText(text);
    if (validationError) { setError(validationError); return; }
    pollerRef.current?.stop();
    setIsSubmitting(true);
    setError("");
    setPollError("");
    setSubmission(null);
    setJob(null);
    setSelectedRole(null);
    setMobileView("input");
    try {
      const result = await submissionRef.current.submit(text);
      if (result.ok) setSubmission({ ...result, requestText: text });
      else setError(result.error);
    } finally {
      setIsSubmitting(false);
    }
  }

  function fillInput(text) {
    setRequestText(text);
    setError("");
    inputRef.current?.focus();
  }

  const terms = resultTerms(job);
  const activeRole = selectedRole || defaultRole(terms);
  const term = terms.find((item) => item.role === activeRole);
  const result = job?.job_status === "completed" ? job.result : null;
  const userMessage = resultUserMessage(job);
  const busy = submission && !pollError && !["completed", "failed"].includes(job?.job_status);

  return (
    <main className={`workspace mobile-${mobileView}`}>
      <div className="mobile-switch" aria-label="화면 전환">
        <button type="button" aria-pressed={mobileView === "references"} onClick={() => setMobileView("references")}>레퍼런스</button>
        <button type="button" aria-pressed={mobileView === "input"} onClick={() => setMobileView("input")}>입력·설명</button>
      </div>
      <section className="reference-board" aria-labelledby="reference-title">
        <header className="board-header">
          <span className="brand-mark" aria-hidden="true">U</span>
          <span className="brand-name">UH케그려</span>
        </header>
        {terms.length ? (
          <div className="board-results">
            <nav className="role-tabs" aria-label="레퍼런스 역할">
              {terms.map((item) => (
                <button key={item.role} type="button" className={activeRole === item.role ? "active" : ""}
                  aria-pressed={activeRole === item.role} onClick={() => setSelectedRole(item.role)}>
                  {ROLE_LABELS[item.role]}
                </button>
              ))}
            </nav>
            {term && <>
              <div className="term-heading">
                <span>{ROLE_LABELS[term.role]}</span>
                <h1 id="reference-title">{term.label_ko}</h1>
                <small>{term.label_en}</small>
              </div>
              {roleNotice(term) && <p className="role-notice">{roleNotice(term)}</p>}
              <div className="pin-grid">
                {term.pins.map((pin) => showThumbnail(pin) ? (
                  <a key={pin.pin_id} className="pin-card" href={pin.pin_url} target="_blank" rel="noopener noreferrer"
                    aria-label={`${term.label_ko} 원본 Pin 열기`}>
                    <img src={pin.thumbnail_url} alt={`${term.label_ko} 레퍼런스`} loading="lazy" />
                  </a>
                ) : <div key={pin.pin_id} className="pin-card pin-unavailable">접근할 수 없는 Pin</div>)}
              </div>
            </>}
          </div>
        ) : (
          <div className="board-empty">
            <span className="board-empty-icon" aria-hidden="true">✳</span>
            <h1 id="reference-title">{busy ? "레퍼런스를 준비하고 있어요" : "그림의 출발점을 찾아보세요"}</h1>
            <p>오른쪽에 그리고 싶은 캐릭터를 설명하면 레퍼런스 탐색을 시작합니다.</p>
          </div>
        )}
      </section>

      <aside className="prompt-panel" aria-labelledby="prompt-title">
        <div className="panel-top">
          <span className="panel-eyebrow">REFERENCE STUDIO</span>
          <h2 id="prompt-title">어떤 캐릭터를 그리고 싶나요?</h2>
          {!submission && <>
            <p>체형, 자세, 보는 각도처럼 떠오르는 모습을 편하게 적어 주세요.</p>
            <div className="example-note">예: 한쪽 다리에 힘을 주고 아래에서 올려다보는 캐릭터</div>
          </>}
          {submission && <p className="submitted-text">{submission.requestText}</p>}
          {busy && <div className="receipt" role="status">{STATUS_LABELS[job?.job_status || "queued"]}</div>}
          {pollError && <p className="panel-message" role="alert">{pollError}</p>}
          {userMessage && <p className="panel-message" role={job?.job_status === "failed" ? "alert" : undefined}>{userMessage}</p>}
          {result?.agent_status === "needs_clarification" && <div className="result-note">
            <h3>조금 더 알려주세요</h3>
            <p>{result.clarifying_question}</p>
            {clarificationChoices(result).map((choice) => (
              <button key={choice.request_text} type="button" className="choice-chip" onClick={() => fillInput(choice.request_text)}>{choice.label}</button>
            ))}
            <button type="button" className="text-action" onClick={() => inputRef.current?.focus()}>직접 입력하기</button>
          </div>}
          {term && <div className="result-note">
            <h3>{term.label_ko}</h3>
            <p>{term.plain_meaning_ko}</p>
            {term.selection_reason && <p>{term.selection_reason}</p>}
            {term.reference_checkpoints?.length > 0 && <ul>{term.reference_checkpoints.map((point) => <li key={point}>{point}</li>)}</ul>}
            {roleNotice(term) && <div className="result-actions">
              <a href={term.search_url} target="_blank" rel="noopener noreferrer">검색 링크 열기</a>
              <button type="button" onClick={() => submit(submission.requestText)}>같은 조건으로 다시 찾기</button>
              <button type="button" onClick={() => fillInput(submission.requestText)}>조건 바꿔 입력하기</button>
            </div>}
          </div>}
        </div>

        <form className="composer" onSubmit={(event) => { event.preventDefault(); submit(requestText); }} noValidate>
          <label htmlFor="request-text">캐릭터 설명</label>
          <textarea ref={inputRef} id="request-text" name="request_text" rows={5} value={requestText}
            disabled={isSubmitting} onChange={(event) => { setRequestText(event.target.value); if (error) setError(""); }}
            placeholder="원하는 체형, 포즈, 시점을 적어 주세요" aria-invalid={Boolean(error)}
            aria-describedby={error ? "request-error" : "request-count"} />
          {error && <p id="request-error" className="form-error" role="alert">{error}</p>}
          <div className="composer-footer">
            <span id="request-count" className="character-count">{countCharacters(requestText)} / 500</span>
            <button type="submit" disabled={isSubmitting}>{isSubmitting ? "전송 중…" : "레퍼런스 찾기"}</button>
          </div>
        </form>
      </aside>
    </main>
  );
}
