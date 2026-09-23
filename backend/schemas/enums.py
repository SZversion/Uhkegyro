"""계약 enum 열거형 (docs/specs/api-contract.md 기준).

api-contract.md §35(ReasonCode)·§37(FailureCode)·각 모델 enum을 그대로 반영한다.
"""

from enum import StrEnum


class Role(StrEnum):
    """카탈로그 체택 가능 역할 (category_load_order 기준)."""

    BODY = "body"
    POSE = "pose"
    VIEW = "view"
    PERSPECTIVE = "perspective"
    LAYOUT = "layout"


class JobStatus(StrEnum):
    """job 상태 7종 (완료·실패만 종결 상태)."""

    QUEUED = "queued"
    RUNNING = "running"
    VALIDATING = "validating"
    SEARCHING = "searching"
    RENDERING = "rendering"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(StrEnum):
    """결과 조립 상태 5종 (service_unavailable은 사용하지 않는다)."""

    SUCCESS = "success"
    NEEDS_CLARIFICATION = "needs_clarification"
    OUT_OF_SCOPE = "out_of_scope"
    UNSAFE_INPUT = "unsafe_input"
    PARTIAL_RESULT = "partial_result"


class ReasonCode(StrEnum):
    """AGentResult·TermResult의 사유 코드 8종."""

    ABSTRACT_INTENT_ONLY = "ABSTRACT_INTENT_ONLY"
    INSUFFICIENT_VISUAL_EVIDENCE = "INSUFFICIENT_VISUAL_EVIDENCE"
    CONFLICTING_CONSTRAINTS = "CONFLICTING_CONSTRAINTS"
    DIRECT_SEARCH_DISABLED = "DIRECT_SEARCH_DISABLED"
    PIN_RESULTS_EMPTY = "PIN_RESULTS_EMPTY"
    PIN_SEARCH_UNAVAILABLE = "PIN_SEARCH_UNAVAILABLE"
    OUT_OF_SCOPE_REQUEST = "OUT_OF_SCOPE_REQUEST"
    UNSAFE_INPUT = "UNSAFE_INPUT"


class FailureCode(StrEnum):
    """최종 실패 코드 13종.

    - LLM_*·SEARCH_*·JOB_INSTANCE_INTERRUPTED: 회복 가능 -> 자동 재시도 3회
    - CONFIGURATION_ERROR·DATABASE_*·CATALOG_INVALID_AT_STARTUP·INTERNAL_CODE_ERROR: 즉시 실패
    """

    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMITED = "LLM_RATE_LIMITED"
    LLM_UPSTREAM_UNAVAILABLE = "LLM_UPSTREAM_UNAVAILABLE"
    LLM_INVALID_STRUCTURED_OUTPUT = "LLM_INVALID_STRUCTURED_OUTPUT"
    SEARCH_TIMEOUT = "SEARCH_TIMEOUT"
    SEARCH_RATE_LIMITED = "SEARCH_RATE_LIMITED"
    SEARCH_UPSTREAM_UNAVAILABLE = "SEARCH_UPSTREAM_UNAVAILABLE"
    JOB_INSTANCE_INTERRUPTED = "JOB_INSTANCE_INTERRUPTED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    DATABASE_MIGRATION_ERROR = "DATABASE_MIGRATION_ERROR"
    DATABASE_UNAVAILABLE = "DATABASE_UNAVAILABLE"
    CATALOG_INVALID_AT_STARTUP = "CATALOG_INVALID_AT_STARTUP"
    INTERNAL_CODE_ERROR = "INTERNAL_CODE_ERROR"


class PinStatus(StrEnum):
    """Pin 상태 3종."""

    AVAILABLE = "available"
    THUMBNAIL_UNAVAILABLE = "thumbnail_unavailable"
    DELETED = "deleted"