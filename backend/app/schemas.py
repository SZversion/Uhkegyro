"""Pydantic contracts shared by the API and domain services."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Axis = Literal["body", "pose", "composition", "detail"]
CompositionKind = Literal["view", "perspective", "layout"]
Role = Literal["body", "pose", "view", "perspective", "layout"]


class AgentRequest(BaseModel):
    """The client request contract for a future agent invocation."""

    model_config = ConfigDict(extra="forbid")

    request_text: str = Field(min_length=1, max_length=500)
    anonymous_user_id: UUID
    session_id: UUID

    @field_validator("request_text")
    @classmethod
    def require_non_whitespace_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("request_text must contain non-whitespace characters")
        return value


class Selection(BaseModel):
    """A term candidate emitted by the future LLM interpreter."""

    model_config = ConfigDict(extra="forbid")

    axis: Axis
    kind: CompositionKind | None = None
    term_id: str = Field(min_length=1, max_length=80)
    evidence: list[str] = Field(min_length=1, max_length=5)


class PinterestSearch(BaseModel):
    """A browser URL generated locally without requesting Pinterest."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=500)
    url: str = Field(min_length=1, max_length=1_000)


class ReferencePlanItem(BaseModel):
    """One role-specific reference search derived from a validated term."""

    model_config = ConfigDict(extra="forbid")

    role: Role
    term_id: str
    label: str
    look_for: str
    pinterest_search: PinterestSearch


class SearchPlan(BaseModel):
    """The foundation-stage search result before catalog evidence is added."""

    model_config = ConfigDict(extra="forbid")

    combined_pinterest_search: PinterestSearch | None = None
    reference_plan: list[ReferencePlanItem] = Field(default_factory=list)
