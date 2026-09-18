from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.schemas import AgentRequest


def test_agent_request_accepts_text_and_anonymous_identifiers() -> None:
    request = AgentRequest(
        request_text="넓은 어깨 캐릭터가 서 있어요.",
        anonymous_user_id=uuid4(),
        session_id=uuid4(),
    )

    assert request.request_text == "넓은 어깨 캐릭터가 서 있어요."


def test_agent_request_rejects_whitespace_only_text() -> None:
    with pytest.raises(ValidationError):
        AgentRequest(
            request_text="  \t",
            anonymous_user_id=uuid4(),
            session_id=uuid4(),
        )


def test_agent_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentRequest(
            request_text="정면 캐릭터예요.",
            anonymous_user_id=uuid4(),
            session_id=uuid4(),
            unexpected="not allowed",
        )
