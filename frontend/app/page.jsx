"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { countCharacters, createSubmissionController, validateRequestText } from "../lib/agent-submit.mjs";
import { createJobPoller, STATUS_LABELS } from "../lib/job-polling.mjs";
import { DEMO_JOB, DEMO_REQUEST_TEXT, uiDemoEnabled } from "../lib/demo-job.mjs";
import { createMindMapSlots, firstSelectableTermId } from "../lib/term-mind-map.mjs";
import { getRecommendedSearchQuery } from "../lib/recommended-query.mjs";
import { createGalleryRows, resultTerms, roleNotice, showThumbnail } from "../lib/result-view.mjs";

export default function HomePage() {
  const [requestText, setRequestText] = useState("");
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState(null);
  const [job, setJob] = useState(() => (uiDemoEnabled ? DEMO_JOB : null));
  const [selectedTermId, setSelectedTermId] = useState(null);
  const [pollError, setPollError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [copiedTermId, setCopiedTermId] = useState(null);
  const [activeGalleryRole, setActiveGalleryRole] = useState(null);
  const [failedThumbnails, setFailedThumbnails] = useState({});
  const [menuOpen, setMenuOpen] = useState(false);
  const [previewPin, setPreviewPin] = useState(null);
  const [previewFailed, setPreviewFailed] = useState(false);
  const previewDialogRef = useRef(null);
  const previewTriggerRef = useRef(null);
  const [boardView, setBoardView] = useState("results");
  const [searchHistory, setSearchHistory] = useState(() => uiDemoEnabled
    ? [{ id: "demo-initial", request: DEMO_REQUEST_TEXT, job: DEMO_JOB, demo: true }]
    : []);
  const pendingRequestRef = useRef("");
  const menuButtonRef = useRef(null);
  const copyTimerRef = useRef(null);
  const inputRef = useRef(null);
  const galleryRef = useRef(null);
  const submissionRef = useRef(null);
  const pollerRef = useRef(null);
  const selectedJobRef = useRef(null);
  const mindMapSlots = useMemo(
    () => createMindMapSlots(resultTerms(job)),
    [job],
  );
  const hasTerms = mindMapSlots.some((slot) => slot.terms.length > 0);
  const activeTermId = mindMapSlots.some((slot) => slot.terms.some((term) => term.term_id === selectedTermId))
    ? selectedTermId
    : firstSelectableTermId(mindMapSlots);
  const homeTerm = mindMapSlots.flatMap((slot) => slot.terms).find((term) => term.term_id === activeTermId) || null;
  const galleryRows = useMemo(() => createGalleryRows(mindMapSlots), [mindMapSlots]);
  const hasGalleryRows = galleryRows.length > 0;
  const galleryTerm = galleryRows.find((row) => row.role === activeGalleryRole)?.term || galleryRows[0]?.term || null;
  const queryTerm = ["results", "term-results"].includes(boardView) && hasGalleryRows ? galleryTerm : homeTerm;
  const recommendedSearchQuery = getRecommendedSearchQuery(queryTerm);
  const conversationBusy = isSubmitting || Boolean(submission && !pollError
    && !["completed", "failed"].includes(job?.job_status));
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

  useEffect(() => () => clearTimeout(copyTimerRef.current), []);
  useEffect(() => {
    if (previewPin && !previewDialogRef.current.open) previewDialogRef.current.showModal();
  }, [previewPin]);

  useEffect(() => {
    if (job !== selectedJobRef.current) {
      selectedJobRef.current = job;
      setSelectedTermId(firstSelectableTermId(mindMapSlots));
      setFailedThumbnails({});
    }
  }, [job, mindMapSlots]);

  useEffect(() => {
    setActiveGalleryRole((current) => (
      galleryRows.some((row) => row.role === current) ? current : galleryRows[0]?.role || null
    ));
  }, [galleryRows]);

  useEffect(() => {
    if (!["results", "term-results"].includes(boardView)) return;
    const syncMobileGallery = () => {
      if (window.matchMedia("(max-width: 760px)").matches && galleryRef.current) {
        syncGalleryRole(galleryRef.current);
      }
    };
    window.addEventListener("scroll", syncMobileGallery, { passive: true });
    window.addEventListener("resize", syncMobileGallery);
    syncMobileGallery();
    return () => {
      window.removeEventListener("scroll", syncMobileGallery);
      window.removeEventListener("resize", syncMobileGallery);
    };
  }, [boardView, galleryRows]);

  useEffect(() => {
    if (!menuOpen) return;
    function closeOnEscape(event) {
      if (event.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  useEffect(() => {
    if (!submission || !["completed", "failed"].includes(job?.job_status)) return;
    setSearchHistory((entries) => entries.some((entry) => entry.id === submission.jobId)
      ? entries
      : [{ id: submission.jobId, request: pendingRequestRef.current, job, demo: false }, ...entries]);
  }, [job, submission]);

  async function handleSubmit(event) {
    event.preventDefault();
    await submit(requestText);
  }

  function fillInput(text) {
    setRequestText(text);
    setError("");
    inputRef.current?.focus();
  }

  function toggleMenu(event) {
    menuButtonRef.current = event.currentTarget;
    setMenuOpen((open) => !open);
  }

  function openTermSearch(term) {
    setSelectedTermId(term.term_id);
    setActiveGalleryRole(term.role);
    setBoardView("results");
  }

  async function submit(text) {
    if (conversationBusy || submissionRef.current.isPending()) return;

    const validationError = validateRequestText(text);
    if (validationError) {
      setError(validationError);
      return;
    }

    if (uiDemoEnabled) {
      const demoJob = DEMO_JOB;
      const id = crypto.randomUUID();
      setJob(demoJob);
      setSearchHistory((entries) => [{ id, request: text, job: demoJob, demo: true }, ...entries]);
      setBoardView("results");
      setRequestText("");
      setError("");
      setSelectedTermId(firstSelectableTermId(mindMapSlots));
      return;
    }

    pollerRef.current?.stop();
    pendingRequestRef.current = text;
    setBoardView("results");
    setIsSubmitting(true);
    setError("");
    setPollError("");
    setSubmission(null);
    setJob(null);
    setSelectedTermId(null);
    selectedJobRef.current = null;
    try {
      const result = await submissionRef.current.submit(text);
      if (result.ok) {
        setSubmission({ ...result, requestText: text });
        setRequestText("");
      }
      else setError(result.error);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function copyRecommendedSearchQuery() {
    if (!recommendedSearchQuery || !queryTerm) return;
    try {
      await navigator.clipboard.writeText(recommendedSearchQuery);
      clearTimeout(copyTimerRef.current);
      setCopiedTermId(queryTerm.term_id);
      copyTimerRef.current = setTimeout(() => setCopiedTermId(null), 3000);
    } catch {
      clearTimeout(copyTimerRef.current);
      setCopiedTermId(null);
    }
  }

  function handleGalleryScroll(event) {
    syncGalleryRole(event.currentTarget);
  }

  function syncGalleryRole(gallery) {
    const mobile = window.matchMedia("(max-width: 760px)").matches;
    const bounds = gallery.getBoundingClientRect();
    const headerHeight = gallery.closest(".reference-board").querySelector(".board-header").getBoundingClientRect().height;
    if (mobile && (bounds.top > window.innerHeight || bounds.bottom < headerHeight)) return;
    const galleryTop = mobile ? headerHeight : bounds.top;
    const closestRow = galleryRows.reduce((closest, row) => {
      const element = gallery.querySelector(`[data-gallery-role="${row.role}"]`);
      if (!element) return closest;
      const distance = Math.abs(element.getBoundingClientRect().top - galleryTop);
      return !closest || distance < closest.distance ? { role: row.role, distance } : closest;
    }, null);

    if (closestRow) {
      setActiveGalleryRole((current) => current === closestRow.role ? current : closestRow.role);
    }
  }

  function navigateBoard(view) {
    setBoardView(view);
    setMenuOpen(false);
    menuButtonRef.current?.focus();
  }

  function openHistory(entry) {
    if (conversationBusy) return;
    pollerRef.current?.stop();
    setSubmission(null);
    setPollError("");
    setJob(entry.job);
    setActiveGalleryRole(null);
    setBoardView("results");
  }

  return (
    <main className="workspace">
      <section className="reference-board" aria-labelledby="reference-title">
        <header className="board-header">
          <div className="brand-navigation-anchor">
            <button className="brand-identity brand-menu-button" type="button" ref={menuButtonRef}
              aria-label="탐색 메뉴" aria-expanded={menuOpen} aria-controls="board-navigation"
              onClick={toggleMenu}>
              <span className="brand-mark" aria-hidden="true">UH</span>
              <span className="brand-name">UH케그려</span>
            </button>
              <nav id="board-navigation" className="board-navigation" aria-label="보드 탐색"
                data-open={menuOpen} aria-hidden={!menuOpen} inert={!menuOpen}>
                <button type="button" onClick={() => navigateBoard("home")}>홈</button>
                <button type="button" onClick={() => navigateBoard("history")}>기록</button>
              </nav>
          </div>
          {boardView !== "history" && recommendedSearchQuery && (
            <div className="recommended-query" aria-label="즉시 검색">
              <a href={`https://kr.pinterest.com/search/pins/?${new URLSearchParams({ q: recommendedSearchQuery })}`}
                aria-label="Pinterest에서 검색" aria-describedby="instant-search-tooltip"
                target="_blank" rel="noopener noreferrer">
                Pinterest ↗
                <span id="instant-search-tooltip" className="instant-search-tooltip" role="tooltip">
                  Pinterest 검색 결과는 계정, 이용 기록 등에 따라 달라질 수 있습니다.
                </span>
              </a>
              <div className="query-value">
                <code tabIndex={0} aria-label="추천 검색어" aria-describedby="full-query-tooltip">{recommendedSearchQuery}</code>
                <span id="full-query-tooltip" className="full-query-tooltip" role="tooltip">{recommendedSearchQuery}</span>
              </div>
              <button type="button" onClick={copyRecommendedSearchQuery}>
                {copiedTermId === queryTerm?.term_id ? "복사 됨" : "복사"}
              </button>
            </div>
          )}
          <span className="board-header-balance" aria-hidden="true" />
        </header>
        {menuOpen && (
          <>
            <button className="board-menu-dismiss" type="button" aria-label="메뉴 닫기" onClick={() => setMenuOpen(false)} />
          </>
        )}
        {boardView === "history" ? (
          <section className="search-history" aria-label="검색 기록">
            <h1>검색 기록</h1>
            <p>현재 탭에서 진행한 검색을 다시 확인하세요.</p>
            {searchHistory.length ? searchHistory.map((entry) => (
              <button className="search-history-entry" type="button" key={entry.id} disabled={conversationBusy} onClick={() => openHistory(entry)}>
                <span>{entry.demo ? "미리보기" : entry.job.job_status === "failed" ? "실패" : "완료"}</span>
                <strong>{entry.request}</strong>
                <span>결과 열기 →</span>
              </button>
            )) : <p>아직 검색 기록이 없습니다.</p>}
          </section>
        ) : ["results", "term-results"].includes(boardView) && hasGalleryRows ? (
          <div className="pin-gallery" ref={galleryRef} data-single={galleryRows.length === 1}
            aria-label="카테고리별 Pinterest 핀 썸네일" onScroll={handleGalleryScroll}>
            <button className="gallery-back-button" type="button" onClick={() => navigateBoard("home")}>← 용어 둘러보기</button>
            {galleryRows.map(({ role, roleLabel, term, pins }) => (
              <section className="pin-gallery-row" data-gallery-role={role} key={role} aria-label={`${roleLabel} 검색 결과`}>
                <div className="pin-gallery-toolbar">
                <button className="pin-gallery-heading" type="button"
                  aria-pressed={term.term_id === galleryTerm?.term_id}
                  aria-label={`${roleLabel} ${term.label_ko} 검색어 보기`}
                  onClick={() => { setSelectedTermId(term.term_id); setActiveGalleryRole(role); }}>
                  <span>{roleLabel}</span>
                  <strong>{term.label_ko}</strong>
                  {term.term_id === galleryTerm?.term_id && <span className="active-term-badge">보고 있는 용어</span>}
                </button>
                </div>
                <div className="pin-gallery-items">
                  {roleNotice(term) && <p className="pin-unavailable" role="status">{roleNotice(term)}</p>}
                  {pins.map((pin, index) => showThumbnail(pin) && !failedThumbnails[`${term.term_id}:${pin.pin_id}`] ? (
                    <button
                      className="pin-gallery-card"
                      type="button"
                      key={pin.pin_id}
                      aria-label={`${roleLabel} ${term.label_ko} 핀 ${index + 1} 확대 보기`}
                      onClick={(event) => {
                        previewTriggerRef.current = event.currentTarget;
                        setPreviewFailed(false);
                        setPreviewPin({ ...pin, label: `${roleLabel} · ${term.label_ko}` });
                      }}
                    >
                      <img
                        key={pin.thumbnail_url}
                        src={pin.thumbnail_url}
                        alt={`${term.label_ko} 레퍼런스 ${index + 1}`}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={() => setFailedThumbnails((current) => ({ ...current, [`${term.term_id}:${pin.pin_id}`]: true }))}
                      />
                    </button>
                  ) : <div className="pin-gallery-card pin-unavailable" key={pin.pin_id}>접근할 수 없는 Pin</div>)}
                </div>
              </section>
            ))}
          </div>
        ) : hasTerms ? (
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
              <button className="mind-map-hub" type="button" aria-label="중앙 브랜드 탐색 메뉴"
                aria-expanded={menuOpen} aria-controls="board-navigation" aria-describedby="hub-menu-tip" onClick={toggleMenu}>
                <span aria-hidden="true">UH</span>
                <span id="hub-menu-tip" className="hub-menu-tip" role="tooltip">홈·기록 메뉴</span>
              </button>
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
                        onClick={() => openTermSearch(term)}
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
        <div className="panel-top" >
          {uiDemoEnabled && <span className="demo-badge">대화 UI 더미 · LLM 미연결</span>}
          <h2 id="prompt-title">UH케 그릴 건가요?</h2>
          {submission && !pollError && !["completed", "failed"].includes(job?.job_status) &&
            <div className="receipt" role="status">{STATUS_LABELS[job?.job_status || "queued"]}</div>}
          {job?.job_status === "completed" && <article className="term-detail"><p>
            {job.result?.user_message || galleryTerm?.plain_meaning_ko || homeTerm?.plain_meaning_ko || "검색 결과를 확인해 주세요."}
          </p></article>}
          {job?.job_status === "failed" && <p className="form-error" role="alert">{job.failure?.user_message}</p>}
          {pollError && <p className="form-error" role="alert">{pollError}</p>}
        </div>

        <form className="composer" onSubmit={handleSubmit} noValidate>
          <div className="composer-input-frame" data-invalid={Boolean(error)}>
          <textarea
            id="request-text"
            ref={inputRef}
            name="request_text"
            aria-label="캐릭터 설명"
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
            aria-describedby={`request-hint request-count${error ? " request-error" : ""}`}
          />
          </div>
          {error && <p id="request-error" className="form-error" role="alert">{error}</p>}
          <div className="composer-footer">
            <span id="request-hint" className="input-hint">Enter로 검색 · Shift+Enter로 줄바꿈</span>
            <span id="request-count" className="character-count">{countCharacters(requestText)} / 500</span>
          </div>
        </form>
      </aside>
      <dialog className="image-preview" ref={previewDialogRef} aria-labelledby="preview-title"
        onClick={(event) => { if (event.target === event.currentTarget) event.currentTarget.close(); }}
        onClose={() => { setPreviewPin(null); previewTriggerRef.current?.focus(); }}>
        {previewPin && <div className="image-preview-content">
          <header className="image-preview-header">
            <h2 id="preview-title">{previewPin.label}</h2>
            <button type="button" autoFocus onClick={() => previewDialogRef.current.close()}>닫기</button>
          </header>
          {previewFailed ? <p role="status">이미지를 표시할 수 없습니다. 핀 원본에서 확인해 주세요.</p>
            : <img key={previewPin.thumbnail_url} src={previewPin.thumbnail_url} alt={`${previewPin.label} 확대 레퍼런스`}
                referrerPolicy="no-referrer" onError={() => setPreviewFailed(true)} />}
          <footer><span>썸네일 확대 보기 · 원본 해상도는 핀에서 확인하세요.</span>
            <a href={previewPin.pin_url} target="_blank" rel="noopener noreferrer">핀 원본 열기 ↗</a>
          </footer>
        </div>}
      </dialog>
    </main>
  );
}
