"""`POST /api/agent`·`GET /api/jobs/{job_id}` 계약 테스트.

`docs/specs/api-contract.md`와 `docs/specs/session-job-persistence.md`의 AC를
직접 번호로 대응시킨다. 저장 계층은 인메모리 mock이므로 DB·LLM·외부 API 없이
끝까지 돈다.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.session_store import SESSION_COOKIE_NAME, reset_session_store


@pytest.fixture
def client() -> TestClient:
    reset_session_store()
    with TestClient(app) as test_client:
        yield test_client
    reset_session_store()


def submit(client: TestClient, text: str, key: str | None = None) -> dict:
    """에이전트 요청을 보내고 상태 코드와 본문을 돌려준다."""
    headers = {"Idempotency-Key": key or str(uuid.uuid4())}
    response = client.post("/api/agent", json={"request_text": text}, headers=headers)
    return {"status": response.status_code, "body": response.json(), "headers": response.headers}


# --- AC-01 · 비동기 제출 ---------------------------------------------------


def test_new_session_gets_httponly_cookie_and_202(client: TestClient) -> None:
    """AC-01: 신규 세션은 90일 HttpOnly 쿠키를 받고 202와 queued job을 받는다."""
    result = submit(client, "옷이 아니라 실제 몸매 비율이 가벼워 보이게")

    assert result["status"] == 202
    assert result["body"]["job_status"] == "queued"
    assert result["body"]["poll_after_ms"] == 1000
    assert uuid.UUID(result["body"]["job_id"])

    cookie_header = result["headers"]["set-cookie"]
    assert SESSION_COOKIE_NAME in cookie_header
    assert "HttpOnly" in cookie_header
    assert "Max-Age=7776000" in cookie_header  # 90일


def test_existing_cookie_is_reused(client: TestClient) -> None:
    """AC-01: 이미 쿠키가 있으면 같은 세션을 재사용한다."""
    first = submit(client, "다리는 옆으로 벌리고 서 있는 자세")
    second = submit(client, "이번에는 앉아 있는 모습")

    assert client.cookies.get(SESSION_COOKIE_NAME)
    assert "set-cookie" not in second["headers"]  # 재발급하지 않는다

    first_envelope = client.get(f"/api/jobs/{first['body']['job_id']}").json()
    second_envelope = client.get(f"/api/jobs/{second['body']['job_id']}").json()
    assert first_envelope["session_id"] == second_envelope["session_id"]


def test_invalid_request_text_is_422(client: TestClient) -> None:
    """공백만 이루어진 요청은 접수하지 않는다."""
    result = submit(client, "   ")

    assert result["status"] == 422
    assert result["body"]["failure_code"] == "invalid_request_text"
    assert result["body"]["retryable"] is False
    assert result["body"]["user_message"]


def test_request_text_over_500_chars_is_422(client: TestClient) -> None:
    assert submit(client, "가" * 501)["status"] == 422


def test_unknown_field_is_rejected(client: TestClient) -> None:
    """브라우저는 role·term_id·검색어 등을 보내지 않는다(extra="forbid")."""
    response = client.post(
        "/api/agent",
        json={"request_text": "서 있는 자세", "role": "pose"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.status_code == 422
    assert response.json()["failure_code"] == "invalid_request_text"


def test_missing_idempotency_key_is_422(client: TestClient) -> None:
    response = client.post("/api/agent", json={"request_text": "서 있는 자세"})

    assert response.status_code == 422
    assert response.json()["failure_code"] == "invalid_request_text"


def test_malformed_idempotency_key_is_422(client: TestClient) -> None:
    """Idempotency-Key는 UUID 형식이어야 한다."""
    result = submit(client, "서 있는 자세", key="not-a-uuid")
    assert result["status"] == 422


# --- AC / session-job-persistence · idempotency ----------------------------


def test_same_request_within_10min_returns_same_job(client: TestClient) -> None:
    """같은 세션·키·원문이면 새 job 없이 기존 job을 반환한다."""
    key = str(uuid.uuid4())
    first = submit(client, "다리를 벌리고 선 자세", key=key)
    second = submit(client, "다리를 벌리고 선 자세", key=key)

    assert first["status"] == 202
    assert second["status"] == 202
    assert first["body"]["job_id"] == second["body"]["job_id"]


def test_same_key_different_text_is_409(client: TestClient) -> None:
    """같은 키에 다른 원문이면 409 IDEMPOTENCY_KEY_CONFLICT."""
    key = str(uuid.uuid4())
    submit(client, "다리를 벌리고 선 자세", key=key)
    conflict = submit(client, "앉아 있는 자세", key=key)

    assert conflict["status"] == 409
    assert conflict["body"]["failure_code"] == "idempotency_key_conflict"
    assert conflict["body"]["retryable"] is False


def test_different_key_creates_new_job(client: TestClient) -> None:
    first = submit(client, "서 있는 자세", key=str(uuid.uuid4()))
    second = submit(client, "서 있는 자세", key=str(uuid.uuid4()))

    assert first["body"]["job_id"] != second["body"]["job_id"]


# --- AC-06 · polling 종료 --------------------------------------------------


def test_job_read_returns_completed_envelope(client: TestClient) -> None:
    """AC-06: 종결 상태는 poll_after_ms=null이고 result를 갖는다."""
    created = submit(client, "다리를 옆으로 벌린 자세")
    response = client.get(f"/api/jobs/{created['body']['job_id']}")

    assert response.status_code == 200
    envelope = response.json()
    assert envelope["job_status"] == "completed"
    assert envelope["poll_after_ms"] is None
    assert envelope["failure"] is None
    assert envelope["result"]["agent_status"] == "needs_clarification"
    assert envelope["result"]["clarifying_question"]
    assert envelope["result"]["reason_codes"] == ["INSUFFICIENT_VISUAL_EVIDENCE"]
    assert 1 <= envelope["attempt"] <= envelope["max_attempts"]


def test_job_read_without_cookie_is_401(client: TestClient) -> None:
    created = submit(client, "서 있는 자세")
    client.cookies.clear()

    response = client.get(f"/api/jobs/{created['body']['job_id']}")

    assert response.status_code == 401
    assert response.json()["failure_code"] == "session_required"


def test_job_of_other_session_is_404(client: TestClient) -> None:
    """소유하지 않은 job은 없는 job과 같은 404를 준다."""
    owner = TestClient(app)
    created = submit(owner, "서 있는 자세")

    submit(client, "앉아 있는 자세")  # 이 브라우저에도 유효한 세션을 만든다
    response = client.get(f"/api/jobs/{created['body']['job_id']}")

    assert response.status_code == 404
    assert response.json()["failure_code"] == "job_not_found"
    owner.close()


def test_unknown_job_is_404(client: TestClient) -> None:
    submit(client, "서 있는 자세")

    response = client.get(f"/api/jobs/{uuid.uuid4()}")

    assert response.status_code == 404


# --- AC-04 / misc ----------------------------------------------------------


def test_health_still_works(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_openapi_documents_both_endpoints(client: TestClient) -> None:
    """`/docs`에서 계약과 오류 모델을 확인할 수 있어야 한다."""
    paths = client.get("/openapi.json").json()["paths"]

    assert set(paths) >= {"/api/agent", "/api/jobs/{job_id}", "/health"}


def test_error_body_has_no_extra_fields(client: TestClient) -> None:
    """오류 본문은 ApiError의 세 필드만 갖는다(extra="forbid")."""
    body = submit(client, "   ")["body"]

    assert set(body) == {"failure_code", "user_message", "retryable"}


def test_response_is_json_content_type(client: TestClient) -> None:
    response = client.post(
        "/api/agent",
        json={"request_text": "서 있는 자세"},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )

    assert response.headers["content-type"].startswith("application/json")
    json.loads(response.text)
