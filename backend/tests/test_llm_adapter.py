"""T14 기본 해석 LLM 어댑터 테스트.

진짜 API 호출 없이 가짜 transport로 오류 분류 전 경로와 prompt 조립·출력 검증 계약을 확인한다.
"""
import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import openai
import pytest

from backend.schemas.enums import FailureCode, InterpretationState
from backend.services import llm
from backend.schemas.models import InterpretationOutput
from backend.shared.config import Settings, get_settings

PROMPT_ENV_VAR = "INTERPRETER_PROMPT_PATH"
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
REPO_PROMPT_FILE = REPO_ROOT / "prompts" / "uhkegryo-interpreter-v0.md"


def _real_settings() -> Settings:
    """저장소 `.env`와 무관하게 실제 Settings를 로드한다 (설정 로딩 자체를 검증)."""
    return Settings(_env_file=None)


def _write_prompt(path: Path, marker: str) -> Path:
    path.write_text(
        f"## System message\n```text\n{marker}\n```\n\n"
        "## User message template\n```text\n"
        "{{request_text}}\n{{active_cards_json}}\n```\n",
        encoding="utf-8",
    )
    return path

SELECT_JSON = """{
  "interpretation_state": "select_terms",
  "clarification_type": null,
  "selections": [
    {"role": "pose", "term_id": "pose_contrapposto", "evidence": ["반동", "허리 꼬임"], "confidence": 0.9}
  ],
  "unresolved_constraints": [],
  "clarifying_question": null
}"""

CLARIFY_JSON = """{
  "interpretation_state": "needs_clarification",
  "clarification_type": "insufficient_visual_evidence",
  "selections": [],
  "unresolved_constraints": ["체형 비율을 확정할 실제 신체 단서가 없음"],
  "clarifying_question": "의상을 제외한 실제 체형 비율을 찾으시나요?"
}"""

SYSTEM_EXAMPLE = "You are the structured interpreter for UH Keguryeo."
TEMPLATE_EXAMPLE = (
    "사용자 요청:\n<request_text>\n{{request_text}}\n</request_text>\n"
    "활성 TERM_CARD JSON:\n<active_cards_json>\n{{active_cards_json}}\n</active_cards_json>"
)


class _FakeUsage:
    def __init__(self, prompt_tokens=10, completion_tokens=5, total_tokens=15):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _FakeMessage:
    def __init__(self, content):
        self.content = content
        self.role = "assistant"


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


class _FakeCompletions:
    def __init__(self, responses=None, error=None):
        self._responses = list(responses or [])
        self._error = error
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        if not self._responses:
            raise AssertionError("가짜 응답이 없습니다")
        return self._responses.pop(0)


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, completions):
        self.chat = _FakeChat(completions)


def _adapter(completions, **kwargs):
    return llm.LLMInterpretationAdapter(
        client=_FakeClient(completions),
        system_message=SYSTEM_EXAMPLE,
        user_template=TEMPLATE_EXAMPLE,
        **kwargs,
    )


def _run(coro):
    return asyncio.run(coro)


# --- prompt 조립 -------------------------------------------------------------


def test_load_interpreter_prompt_reads_repo_file():
    system_message, template = llm.load_interpreter_prompt(REPO_PROMPT_FILE)
    assert "You are the structured interpreter for UH Keguryeo." in system_message
    assert "{{request_text}}" in template
    assert "{{active_cards_json}}" in template
    assert "```" not in system_message
    assert "```" not in template


def test_render_user_message_replaces_placeholders():
    rendered = llm.render_user_message(TEMPLATE_EXAMPLE, "반동 자세", "[{...}]")
    assert "반동 자세" in rendered
    assert "[{...}]" in rendered
    assert "{{request_text}}" not in rendered
    assert "{{active_cards_json}}" not in rendered


def test_format_active_cards_json_keeps_only_contract_fields(snapshot_factory, card_factory):
    card = card_factory("pose_contrapposto", role="pose")
    snapshot = snapshot_factory([card])
    payload = llm.format_active_cards_json(snapshot)
    parsed = json.loads(payload)
    item = parsed["active_cards"][0]
    assert item["term_id"] == "pose_contrapposto"
    assert item["role"] == "pose"
    assert item["label_ko"] == "라벨"
    assert "confidence_gate" in item
    assert "requires_all_of" in item
    assert "requires_any_of" in item
    assert "query_fragments" not in item
    assert "look_for" not in item
    assert "source_answer_draft" not in item


# --- 정상 출력 ---------------------------------------------------------------


def test_interpret_select_terms_valid():
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    adapter = _adapter(completions)
    result = _run(adapter.interpret("반동 자세를 찾아요", request_id="r1", active_cards_json="{}"))
    assert isinstance(result, InterpretationOutput)
    assert result.interpretation_state is InterpretationState.SELECT_TERMS
    assert len(result.selections) == 1
    assert result.selections[0].term_id == "pose_contrapposto"
    assert result.selections[0].evidence == ["반동", "허리 꼬임"]


def test_interpret_needs_clarification_valid():
    completions = _FakeCompletions(responses=[_FakeResponse(CLARIFY_JSON)])
    adapter = _adapter(completions)
    result = _run(adapter.interpret("자연스러운 자세", request_id="r1"))
    assert result.interpretation_state is InterpretationState.NEEDS_CLARIFICATION
    assert result.clarifying_question
    assert result.clarification_type is not None


def test_interpret_passes_system_and_user_messages():
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    adapter = _adapter(completions)
    _run(adapter.interpret("반동", request_id="r1", active_cards_json='{"active_cards": []}'))
    assert len(completions.calls) == 1
    call = completions.calls[0]
    assert call["model"] == "openai/gpt-4o-mini"
    assert call["response_format"] == {"type": "json_object"}
    messages = call["messages"]
    assert messages[0]["role"] == "system"
    assert SYSTEM_EXAMPLE in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "반동" in messages[1]["content"]
    assert '{"active_cards": []}' in messages[1]["content"]


# --- 구조화 출력 실패 (LLM_INVALID_STRUCTURED_OUTPUT) ------------------------


def test_interpret_invalid_json_raises_structured_output_error():
    completions = _FakeCompletions(responses=[_FakeResponse("이건 JSON이 아닙니다")])
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMInvalidStructuredOutput):
        _run(adapter.interpret("반동", request_id="r1"))


def test_interpret_schema_violation_raises_structured_output_error():
    bad = '{"interpretation_state": "select_terms", "selections": [], "clarifying_question": null}'
    completions = _FakeCompletions(responses=[_FakeResponse(bad)])
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMInvalidStructuredOutput):
        _run(adapter.interpret("반동", request_id="r1"))


def test_interpret_empty_content_raises_structured_output_error():
    completions = _FakeCompletions(responses=[_FakeResponse("")])
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMInvalidStructuredOutput):
        _run(adapter.interpret("반동", request_id="r1"))


# --- 오류 분류 (LLM_* retryable) ---------------------------------------------


_REQ = httpx.Request("POST", "https://openrouter.ai/api/v1")


def test_interpret_timeout_raises_llm_timeout():
    error = openai.APITimeoutError(request=_REQ)
    completions = _FakeCompletions(error=error)
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMTimeout) as exc:
        _run(adapter.interpret("반동", request_id="r1"))
    assert exc.value.failure_code is FailureCode.LLM_TIMEOUT
    assert exc.value.retryable


def test_interpret_rate_limited_raises_llm_rate_limited():
    error = openai.RateLimitError(
        "rate", response=httpx.Response(status_code=429, request=_REQ), body=None
    )
    completions = _FakeCompletions(error=error)
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMRateLimited) as exc:
        _run(adapter.interpret("반동", request_id="r1"))
    assert exc.value.failure_code is FailureCode.LLM_RATE_LIMITED
    assert exc.value.retryable


def test_interpret_upstream_5xx_raises_llm_upstream_unavailable():
    error = openai.InternalServerError(
        "up", response=httpx.Response(status_code=500, request=_REQ), body=None
    )
    completions = _FakeCompletions(error=error)
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMUpstreamUnavailable) as exc:
        _run(adapter.interpret("반동", request_id="r1"))
    assert exc.value.failure_code is FailureCode.LLM_UPSTREAM_UNAVAILABLE
    assert exc.value.retryable


def test_interpret_connection_error_raises_llm_upstream_unavailable():
    error = openai.APIConnectionError(request=_REQ)
    completions = _FakeCompletions(error=error)
    adapter = _adapter(completions)
    with pytest.raises(llm.LLMUpstreamUnavailable):
        _run(adapter.interpret("반동", request_id="r1"))


@pytest.mark.parametrize(
    "cls",
    [llm.LLMTimeout, llm.LLMRateLimited, llm.LLMUpstreamUnavailable, llm.LLMInvalidStructuredOutput],
)
def test_llm_errors_are_retryable(cls):
    assert cls.retryable is True


# --- 리뷰 반영: INTERPRETER_PROMPT_PATH는 env → 실제 Settings → 어댑터 경로까지 ----
# 폴백 없음. 미설정·경로 없음·읽기 불가면 모두 PromptConfigurationError로 실패해야 한다.


def test_settings_reads_interpreter_prompt_path_from_env(tmp_path):
    prompt_file = _write_prompt(tmp_path / "env-prompt.md", "ENV SYSTEM MARKER")
    with patch.dict(os.environ, {PROMPT_ENV_VAR: str(prompt_file)}):
        settings = _real_settings()
    assert settings.interpreter_prompt_path == str(prompt_file)


def test_settings_interpreter_prompt_path_defaults_to_empty():
    with patch.dict(os.environ, {PROMPT_ENV_VAR: ""}):
        settings = _real_settings()
    assert settings.interpreter_prompt_path == ""


def test_default_prompt_path_uses_env_var_via_real_settings(tmp_path):
    prompt_file = _write_prompt(tmp_path / "my-prompt.md", "Hi")
    with patch.dict(os.environ, {PROMPT_ENV_VAR: str(prompt_file)}):
        settings = _real_settings()
        p = llm.default_prompt_path(settings)
        system_message, template = llm.load_interpreter_prompt(p)
    assert p == prompt_file
    assert "Hi" in system_message
    assert "{{request_text}}" in template


def test_default_prompt_path_without_arg_still_reads_env_var(tmp_path):
    """인자를 넘기지 않아도 get_settings()가 env var를 실제로 읽는지 확인."""
    prompt_file = _write_prompt(tmp_path / "no-arg-prompt.md", "NO ARG MARKER")
    with patch.dict(os.environ, {PROMPT_ENV_VAR: str(prompt_file)}):
        get_settings.cache_clear()
        try:
            p = llm.default_prompt_path()
        finally:
            get_settings.cache_clear()
    assert p == prompt_file


def test_default_prompt_path_raises_when_env_not_configured():
    with patch.dict(os.environ, {PROMPT_ENV_VAR: ""}):
        settings = _real_settings()
        with pytest.raises(llm.PromptConfigurationError) as exc:
            llm.default_prompt_path(settings)
    assert PROMPT_ENV_VAR in str(exc.value)


def test_default_prompt_path_raises_when_configured_file_missing():
    with patch.dict(os.environ, {PROMPT_ENV_VAR: "/nonexistent/prompt.md"}):
        settings = _real_settings()
        with pytest.raises(llm.PromptConfigurationError):
            llm.default_prompt_path(settings)


def test_default_prompt_path_raises_when_configured_path_is_directory(tmp_path):
    with patch.dict(os.environ, {PROMPT_ENV_VAR: str(tmp_path)}):
        settings = _real_settings()
        with pytest.raises(llm.PromptConfigurationError):
            llm.default_prompt_path(settings)


def test_prompt_configuration_error_is_not_retryable():
    assert llm.PromptConfigurationError.failure_code is FailureCode.CONFIGURATION_ERROR
    assert llm.PromptConfigurationError.retryable is False


def test_adapter_initialization_raises_when_env_not_configured():
    with patch.dict(os.environ, {PROMPT_ENV_VAR: ""}):
        settings = _real_settings()
        with pytest.raises(llm.PromptConfigurationError):
            llm.LLMInterpretationAdapter(client=_FakeClient(_FakeCompletions()), settings=settings)


def test_adapter_uses_prompt_file_configured_by_env(tmp_path):
    """env var → 실제 Settings → 어댑터가 해당 파일을 system message로 쓰는 경로."""
    prompt_file = _write_prompt(tmp_path / "adapter-prompt.md", "ADAPTER ENV MARKER")
    completions = _FakeCompletions(responses=[_FakeResponse(SELECT_JSON)])
    with patch.dict(os.environ, {PROMPT_ENV_VAR: str(prompt_file)}):
        settings = _real_settings()
        adapter = llm.LLMInterpretationAdapter(
            client=_FakeClient(completions), settings=settings
        )
    _run(adapter.interpret("반동", request_id="r1"))
    sent = completions.calls[0]["messages"][0]["content"]
    assert "ADAPTER ENV MARKER" in sent
    assert sent.strip() == "ADAPTER ENV MARKER"


def test_openai_client_has_max_retries_zero():
    with patch("openai.AsyncOpenAI") as fake_client_cls:
        adapter = llm.LLMInterpretationAdapter(
            system_message=SYSTEM_EXAMPLE,
            user_template=TEMPLATE_EXAMPLE,
        )
    call_kwargs = fake_client_cls.call_args.kwargs
    assert call_kwargs.get("max_retries") == 0


def test_env_example_declares_concrete_local_prompt_path():
    """.env.example에 주석이 아니라 실제 설정값이 있어야 한다."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assignments = [
        line.split("=", 1)[1].strip()
        for line in env_example.splitlines()
        if line.strip().startswith(f"{PROMPT_ENV_VAR}=")
    ]
    assert assignments == ["./prompts/uhkegryo-interpreter-v0.md"]


def test_docker_deploy_path_consistency():
    assert REPO_PROMPT_FILE.exists()
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY prompts/uhkegryo-interpreter-v0.md /app/prompts/uhkegryo-interpreter-v0.md" in dockerfile
    cloudbuild = (REPO_ROOT / "cloudbuild.yaml").read_text(encoding="utf-8")
    assert "INTERPRETER_PROMPT_PATH=/app/prompts/uhkegryo-interpreter-v0.md" in cloudbuild
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert f"{PROMPT_ENV_VAR}=" in env_example
    assert "./prompts/uhkegryo-interpreter-v0.md" in env_example
