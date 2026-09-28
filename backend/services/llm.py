"""기본 해석 LLM 어댑터 (T14).

LLM 호출은 이 파일 하나로 모은다. 라우터·worker·MCP는 openai를 직접 import하지 않는다.

책임:
- `INTERPRETER_PROMPT_PATH`가 가리키는 프롬프트 파일의 System message와
  User message template 조립 (경로 미설정·불가 시 `PromptConfigurationError`로 초기화 실패)
- OpenRouter(OpenAI 호환) 구조화 출력(JSON object) 단발 호출
- 출력을 Pydantic(`InterpretationOutput`)으로 재검증해 resolver·provider에 전달하지 않을 불량을 차단
- 오류를 안정된 `FailureCode`로 분류(모두 재시도 가능한 LLM_* 코드)

범위 밖(후속 티켓): 최종 상태·사유 코드·검색 URL 결정은 T17 resolver/assembler, 자동 재시도 카운트·attempt
정책은 T18 worker, Langfuse 원격 Prompt 등록·production 라벨은 T33. Langfuse 키가 설정된 경우에만
최소 trace를 남기고, 키가 없으면 구조화 stdout 로그만 사용한다.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
import openai
from pydantic import ValidationError

from backend.schemas.enums import FailureCode
from backend.schemas.models import InterpretationOutput
from backend.services.catalog_repository import CatalogSnapshot

logger = logging.getLogger("backend.services.llm")

PROMPT_FILE_NAME = "uhkegryo-interpreter-v0.md"
SYSTEM_HEADING = "## System message"
USER_TEMPLATE_HEADING = "## User message template"
FENCE = "```"


class LLMError(Exception):
    """LLM 호출 실패를 안정된 failure_code로 분류한다 (api-contract.md §37)."""

    failure_code: FailureCode
    retryable: bool = True


class LLMTimeout(LLMError):
    failure_code = FailureCode.LLM_TIMEOUT


class LLMRateLimited(LLMError):
    failure_code = FailureCode.LLM_RATE_LIMITED


class LLMUpstreamUnavailable(LLMError):
    failure_code = FailureCode.LLM_UPSTREAM_UNAVAILABLE


class LLMInvalidStructuredOutput(LLMError):
    failure_code = FailureCode.LLM_INVALID_STRUCTURED_OUTPUT


class PromptConfigurationError(LLMError):
    """프롬프트 경로 설정 누락·불가. 재시도 대상이 아니다.

    LLMError 계층에 두어 오류 분류(failure_code)를 기존과 같은 방식으로 읽게 한다.
    `LLM_*` 코드가 아니라 `CONFIGURATION_ERROR`로 매핑되고 재시도하지 않는다.
    """

    failure_code = FailureCode.CONFIGURATION_ERROR
    retryable = False


class AgentInterpretationAdapter(Protocol):
    """T18 worker가 사용하는 해석 어댑터 계약."""

    async def interpret(
        self,
        request_text: str,
        *,
        job_id: str,
        active_cards_json: str = "",
    ) -> InterpretationOutput:
        ...


class LLMInterpretationAdapter:
    """OpenRouter 기반 기본 해석 어댑터 (단발 호출).

    SDK 자체 재시도(max_retries)는 쓰지 않는다. 재시도는 api-contract.md §44에 따라
    worker가 attempt 단위로 관리한다. `client`는 테스트 seam으로, 별도 지정 시 그대로 사용한다.

    프롬프트 경로는 `INTERPRETER_PROMPT_PATH`만 사용하고 저장소 고정 경로로 폴백하지 않는다.
    미설정·경로 없음·읽기 불가면 `PromptConfigurationError`로 여기서 실패한다.
    """

    def __init__(
        self,
        *,
        client: Any | None = None,
        settings: Any | None = None,
        prompt_path: Path | None = None,
        system_message: str | None = None,
        user_template: str | None = None,
    ) -> None:
        from backend.shared.config import get_settings

        self.settings = settings or get_settings()
        if system_message is None or user_template is None:
            path = prompt_path if prompt_path is not None else self._resolve_prompt_path()
            system_message, user_template = load_interpreter_prompt(_require_prompt_file(path))
        self._system_message = system_message
        self._user_template = user_template
        if client is None:
            client = openai.AsyncOpenAI(
                api_key=self.settings.openrouter_api_key,
                base_url=self.settings.openrouter_base_url,
                timeout=self.settings.llm_timeout_seconds,
                max_retries=0,
            )
        self._client = client

    def _resolve_prompt_path(self) -> Path:
        return default_prompt_path(self.settings)

    @property
    def prompt_version(self) -> str:
        return self.settings.interpreter_prompt_version

    async def interpret(
        self,
        request_text: str,
        *,
        job_id: str,
        active_cards_json: str = "",
    ) -> InterpretationOutput:
        user_message = render_user_message(self._user_template, request_text, active_cards_json)
        started = time.perf_counter()
        try:
            response = await self._client.chat.completions.create(
                model=self.settings.openrouter_model,
                messages=[
                    {"role": "system", "content": self._system_message},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=self.settings.llm_max_tokens,
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeout(f"OpenRouter 요청 시간 초과: {exc}") from exc
        except openai.RateLimitError as exc:
            raise LLMRateLimited(f"OpenRouter rate limit: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMUpstreamUnavailable(f"OpenRouter 연결 실패: {exc}") from exc
        except openai.APIStatusError as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            if status and int(status) == 429:
                raise LLMRateLimited(f"OpenRouter rate limit: {exc}") from exc
            raise LLMUpstreamUnavailable(f"OpenRouter HTTP {status}: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeout(f"OpenRouter 요청 시간 초과: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMUpstreamUnavailable(f"OpenRouter 전송 실패: {exc}") from exc

        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        content = _extract_content(response)
        interpretation = _validate_output(content)
        usage = _extract_usage(response)
        summary = {
            "interpretation_state": interpretation.interpretation_state.value,
            "roles": [s.role.value for s in interpretation.selections],
            "term_ids": [s.term_id for s in interpretation.selections],
            "clarification_type": (
                interpretation.clarification_type.value if interpretation.clarification_type else None
            ),
        }
        logger.info(
            json.dumps(
                {
                    "event": "llm.interpret.ok",
                    "job_id": job_id,
                    "model": self.settings.openrouter_model,
                    "prompt_version": self.prompt_version,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "output": summary,
                },
                ensure_ascii=False,
            )
        )
        self._observe_langfuse(
            job_id=job_id,
            usage=usage,
            output=summary,
            input_chars=len(request_text),
        )
        return interpretation

    def _observe_langfuse(
        self,
        *,
        job_id: str,
        usage: dict[str, int],
        output: dict[str, Any],
        input_chars: int,
    ) -> None:
        if not (self.settings.langfuse_public_key and self.settings.langfuse_secret_key):
            return
        try:
            from langfuse import Langfuse

            langfuse = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                host=self.settings.langfuse_host,
            )
            generation = langfuse.generation(
                name=self.prompt_version,
                model=self.settings.openrouter_model,
                input={"request_text_chars": input_chars},
                output=output,
                metadata={"job_id": job_id},
            )
            if usage:
                generation.usage = usage
        except Exception:
            logger.debug("Langfuse trace 미전송(무시): job_id=%s", job_id, exc_info=True)


def default_prompt_path(settings: Any | None = None) -> Path:
    """INTERPRETER_PROMPT_PATH(env) 경로를 그대로 사용해 프롬프트 파일을 가리킨다.

    저장소 고정 경로로 폴백하지 않는다. 요청 기준에 따라 아래는 모두
    `PromptConfigurationError`로 명확히 실패한다.
    - `INTERPRETER_PROMPT_PATH` 미설정 또는 빈 값
    - 설정값이 파일이 아니거나 존재하지 않음
    - 설정값이 읽을 수 없는 경로

    어댑터 초기화 시점에 실패해 프롬프트가 없는 상태로 LLM을 호출하지 않는다.
    """
    from backend.shared.config import get_settings

    if settings is None:
        settings = get_settings()

    configured = str(getattr(settings, "interpreter_prompt_path", "") or "").strip()
    if not configured:
        raise PromptConfigurationError(
            "INTERPRETER_PROMPT_PATH 환경변수가 설정되지 않았다. "
            "저장소 고정 경로로 폴백하지 않는다. "
            f".env 또는 배포 환경 변수에 prompts/{PROMPT_FILE_NAME} 경로를 명시해야 한다."
        )

    path = Path(configured)
    return _require_prompt_file(path)


def _require_prompt_file(path: Path) -> Path:
    """프롬프트 경로가 실제 읽을 수 있는 파일인지 확인한다."""
    if not path.is_file():
        raise PromptConfigurationError(
            f"프롬프트 경로가 파일이 아니거나 존재하지 않는다: {path}"
        )
    return path


def load_interpreter_prompt(prompt_path: Path) -> tuple[str, str]:
    """prompts/{version}.md에서 System message와 User message template을 추출한다.

    Langfuse Prompt 등록이 완료되기 전(T33)까지 저장소 파일을 런타임 prompt로 읽는다.
    """
    try:
        text = prompt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PromptConfigurationError(
            f"INTERPRETER_PROMPT_PATH 파일을 읽을 수 없다: {prompt_path}"
        ) from exc
    system_message = _extract_fenced_block(text, SYSTEM_HEADING)
    user_template = _extract_fenced_block(text, USER_TEMPLATE_HEADING)
    return system_message, user_template


def _extract_fenced_block(text: str, heading: str) -> str:
    heading_index = text.find(heading)
    if heading_index < 0:
        raise ValueError(f"프롬프트 파일에 '{heading}' 섹션이 없다")
    fence_start = text.find(FENCE, heading_index)
    if fence_start < 0:
        raise ValueError(f"'{heading}' 다음에 코드 펜스를 찾지 못했다")
    body_start = text.find("\n", fence_start) + 1
    fence_end = text.find(FENCE, body_start)
    if fence_end < 0:
        raise ValueError(f"'{heading}' 코드 펜스가 닫히지 않았다")
    return text[body_start:fence_end].strip("\n")


def render_user_message(template: str, request_text: str, active_cards_json: str) -> str:
    """User message template의 {{request_text}}, {{active_cards_json}} 자리를 채운다."""
    return (
        template.replace("{{request_text}}", request_text)
        .replace("{{active_cards_json}}", active_cards_json)
    )


def format_active_cards_json(snapshot: CatalogSnapshot) -> str:
    """prompt-interpreter-v0.md §65: 활성 카드의 계약 필드만 담은 JSON.

    role, term_id, label_ko, confidence_gate, requires_all_of, requires_any_of만 포함한다.
    """
    active_cards: list[dict[str, Any]] = []
    for role in snapshot.roles_order:
        for term_id in snapshot.role_terms.get(role, []):
            card = snapshot.active_cards.get(term_id, {})
            active_cards.append(
                {
                    "role": card.get("role"),
                    "term_id": term_id,
                    "label_ko": card.get("label_ko"),
                    "confidence_gate": card.get("confidence_gate"),
                    "requires_all_of": card.get("requires_all_of") or [],
                    "requires_any_of": card.get("requires_any_of") or [],
                }
            )
    return json.dumps({"active_cards": active_cards}, ensure_ascii=False)


def _extract_content(response: Any) -> str:
    message = getattr(response, "choices", None) and getattr(response.choices[0], "message", None)
    content = getattr(message, "content", None)
    if not content or not str(content).strip():
        raise LLMInvalidStructuredOutput("완료 응답이 내용이 비어 있다")
    return str(content)


def _extract_usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
        "total_tokens": getattr(usage, "total_tokens", 0) or 0,
    }


def _validate_output(content: str) -> InterpretationOutput:
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        raise LLMInvalidStructuredOutput("JSON 객체를 찾지 못했다")
    payload = content[start : end + 1]
    try:
        data = json.loads(payload)
        return InterpretationOutput.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        logger.debug("구조화 출력 검증 실패", exc_info=True)
        raise LLMInvalidStructuredOutput("출력이 InterpretationOutput 계약을 위반했다") from exc